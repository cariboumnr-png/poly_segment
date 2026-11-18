# =========================================================================== #
#            Copyright © His Majesty the King in right of Ontario,            #
#         as represented by the Minister of Natural Resources, 2026.          #
#                                                                             #
#                      © King's Printer for Ontario, 2026.                    #
#                                                                             #
#       Licensed under the Apache License, Version 2.0 (the 'License');       #
#          you may not use this file except in compliance with the            #
#                                  License.                                   #
#                  You may obtain a copy of the License at:                   #
#                                                                             #
#                  http://www.apache.org/licenses/LICENSE-2.0                 #
#                                                                             #
#    Unless required by applicable law or agreed to in writing, software      #
#     distributed under the License is distributed on an 'AS IS' BASIS,       #
#      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or        #
#                                   implied.                                  #
#       See the License for the specific language governing permissions       #
#                       and limitations under the License.                    #
# =========================================================================== #

'''
Execution runner for polygon-neighbour analysis workflow.

Orchestrates multi-layer geometric intersection, attribute enrichment,
and atomic dataset publishing to File Geodatabase or GeoPackage.

Public APIs:
    - `run_workflow`: Execute the complete polygon-neighbour analysis
      workflow.
'''

# pylint: disable=R0402

# standard imports
import logging
import pathlib
import shutil
import typing
import uuid
# third-party imports
import geopandas
import pandas
import pyogrio
# local imports
import intersect.configs as configs
import intersect.attributes as attributes
import intersect.spatial as spatial

LOGGER = logging.getLogger("post_obc_neighbour_analysis")


# ----- public functions
def run_workflow(config: configs.WorkflowConfig) -> None:
    '''
    Execute the complete polygon-neighbour analysis workflow.

    Args:
        config:
            Workflow configuration containing source and destination
            parameters.

    Raises:
        FileExistsError:
            If destination lacks required output layers and overwrite
            is False.
    '''
    _validate_environment(config.output_format)
    spatial.validate_source_dataset(config.source_dataset, config.source_layers)

    output_layers = (config.intersection_layer, config.neighbour_table)
    destination = config.destination_dataset

    if destination.exists() and not config.overwrite:
        if _destination_is_complete(destination, output_layers):
            LOGGER.info(
                "Both output layers already exist in %s; skipping. "
                "Use --overwrite to rebuild them.",
                destination,
            )
            return
        raise FileExistsError(
            f"Destination exists but does not contain both expected output "
            f"layers: {destination}. Use --overwrite to replace it."
        )

    intersection = spatial.intersect_polygon_layers(
        config.source_dataset,
        config.source_layers,
    )

    neighbours = spatial.build_polygon_neighbours(intersection)
    selected_layer = config.selected_source_layer
    selected_id_field = f"FID_{selected_layer}"
    attrs = attributes.read_comparison_attributes(
        config.source_dataset,
        selected_layer,
        configs.ATTRIBUTE_FIELDS,
    )
    neighbours = attributes.enrich_neighbours_with_attributes(
        neighbours,
        attrs,
        selected_id_field,
        configs.ATTRIBUTE_FIELDS,
    )

    _write_outputs(
        intersection=intersection,
        neighbours=neighbours,
        destination=destination,
        output_format=config.output_format,
        intersection_layer=config.intersection_layer,
        neighbour_table=config.neighbour_table,
        overwrite=config.overwrite,
    )


# ----- private helpers
def _validate_environment(output_format: str) -> None:
    '''Ensure the requested output driver is available and writable.'''
    _, driver = configs.OUTPUT_FORMATS[output_format]
    writable_drivers = pyogrio.list_drivers(write=True)

    if driver not in writable_drivers:
        raise RuntimeError(
            f"GDAL driver {driver!r} is not available for writing. "
            "Check the GDAL/Pyogrio installation."
        )

    if output_format == "filegdb" and pyogrio.__gdal_version__ < (3, 6, 0):
        raise RuntimeError(
            "File Geodatabase writing through OpenFileGDB requires "
            f"GDAL >= 3.6; the installed version is "
            f"{pyogrio.__gdal_version_string__}. "
            "Use --output-format geopackage or upgrade GDAL/Pyogrio."
        )

    if output_format == "filegdb" and pyogrio.__gdal_version__ < (3, 9, 0):
        LOGGER.warning(
            "GDAL versions before 3.9 may store 64-bit integer fields as "
            "Float64 in File Geodatabases. This should not affect ordinary "
            "ObjectID values, but verify very large IDs if applicable."
        )


def _remove_dataset(path: pathlib.Path) -> None:
    '''Remove temporary or backup dataset and SQLite sidecars.'''
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()

    for suffix in ("-wal", "-shm"):
        sidecar = pathlib.Path(f"{path}{suffix}")
        if sidecar.exists():
            sidecar.unlink()


def _destination_is_complete(
    destination: pathlib.Path,
    required_layers: typing.Sequence[str],
) -> bool:
    '''Return True if destination contains both output layers.'''
    existing_layers = {
        str(layer_name)
        for layer_name, _ in pyogrio.list_layers(destination)
    }
    return set(required_layers).issubset(existing_layers)


def _write_outputs(
    intersection: geopandas.GeoDataFrame,
    neighbours: pandas.DataFrame,
    destination: pathlib.Path,
    output_format: str,
    intersection_layer: str,
    neighbour_table: str,
    overwrite: bool,
) -> None:
    '''Write outputs to temporary dataset and publish on success.'''
    _, driver = configs.OUTPUT_FORMATS[output_format]
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = destination.with_name(
        f".{destination.stem}.{uuid.uuid4().hex}.tmp{destination.suffix}"
    )

    layer_options: dict[str, str] = {}
    if (
        output_format == "filegdb"
        and pyogrio.__gdal_version__ >= (3, 9, 0)
    ):
        layer_options["TARGET_ARCGIS_VERSION"] = "ARCGIS_PRO_3_2_OR_LATER"

    try:
        LOGGER.info("Writing intersection layer: %s", intersection_layer)
        pyogrio.write_dataframe(
            intersection,
            temporary_path,
            layer=intersection_layer,
            driver=driver,
            promote_to_multi=True,
            layer_options=layer_options or None,
        )

        LOGGER.info("Writing neighbour table: %s", neighbour_table)
        pyogrio.write_dataframe(
            neighbours,
            temporary_path,
            layer=neighbour_table,
            driver=driver,
            append=True,
            layer_options=layer_options or None,
        )

        backup_path: pathlib.Path | None = None
        if destination.exists():
            if not overwrite:
                raise FileExistsError(
                    f"Destination already exists: {destination}. "
                    "Use --overwrite to replace it."
                )

            backup_path = destination.with_name(
                f".{destination.name}.{uuid.uuid4().hex}.bak"
            )
            destination.replace(backup_path)

        try:
            temporary_path.replace(destination)
        except Exception:
            if backup_path is not None and backup_path.exists():
                backup_path.replace(destination)
            raise
        else:
            if backup_path is not None:
                _remove_dataset(backup_path)

    finally:
        if temporary_path.exists():
            _remove_dataset(temporary_path)

    LOGGER.info("Outputs written to %s", destination)

