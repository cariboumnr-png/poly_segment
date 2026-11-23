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
Execution runner for Stage 2 polygon merging workflow.

Orchestrates loading pre-intersected or raw polygon layers, applying
rule sets to evaluate neighbours, dissolving qualifying components,
and atomically writing results.

Public APIs:
    - `run_merge`: Execute the complete polygon merge workflow.
    - `run_workflow`: Workflow runner alias for `run_merge`.
'''

# standard imports
import logging
import pathlib
import shutil
import typing
import uuid
# third-party imports
import geopandas
import pyogrio
# local imports
import postobc.merge.configs as configs
import postobc.merge.rules as rules
import postobc.merge.spatial as spatial

LOGGER = logging.getLogger("poly_segment_merge")


# ----- public functions
def run_merge(
    config: configs.MergeConfig,
    rule_set: rules.MergeRule | None = None,
) -> geopandas.GeoDataFrame:
    '''
    Execute Stage 2 of the workflow: polygon layer merging.

    Args:
        config:
            Merge configuration with source and destination parameters.
        rule_set:
            Optional custom merge rule set overriding configuration.

    Returns:
        geopandas.GeoDataFrame:
            Merged polygon layer with aggregated attributes.

    Raises:
        FileNotFoundError:
            If source dataset does not exist.
        FileExistsError:
            If destination exists without required layer and overwrite
            is False.
        ValueError:
            If no source layers can be found to merge.
    '''
    _validate_environment(config.output_format)

    if not config.source_dataset.exists():
        raise FileNotFoundError(
            f"Source dataset does not exist: {config.source_dataset}"
        )

    destination = config.destination_dataset
    layer_name = config.merged_layer

    if destination.exists() and not config.overwrite:
        if _destination_is_complete(destination, (layer_name,)):
            LOGGER.info(
                "Output layer %r already exists in %s; skipping. "
                "Use overwrite=True to rebuild it.",
                layer_name,
                destination,
            )
            return geopandas.read_file(destination, layer=layer_name)

    # 1. obtain intersected polygons: chained from Stage 1 or fallback
    source_layer = config.source_intersection_layer
    if source_layer is not None:
        LOGGER.info(
            "Stage 2 (Chained Mode): Reading pre-intersected layer %r "
            "from %s.",
            source_layer,
            config.source_dataset,
        )
        intersection = pyogrio.read_dataframe(
            config.source_dataset,
            layer=source_layer,
        )
        if not isinstance(intersection, geopandas.GeoDataFrame):
            intersection = geopandas.GeoDataFrame(
                intersection,
                geometry=intersection.geometry.name,
                crs=intersection.crs,
            )
    else:
        if not config.source_layers:
            raise ValueError(
                f"No pre-intersected layer found in {config.source_dataset}, "
                "and no 'source_layer_prefix' was provided."
            )
        LOGGER.info("Executing 4-layer polygon intersection fallback.")
        spatial.validate_source_dataset(
            config.source_dataset, config.source_layers
        )
        intersection = spatial.intersect_polygon_layers(
            source_dataset=config.source_dataset,
            layer_names=config.source_layers,
        )

    # 2. resolve or create the effective rule set
    effective_rule_set = rule_set or config.rule_set
    if effective_rule_set is None:
        effective_rule_set = rules.DefaultMergeRuleSet(
            threshold=config.threshold,
            metrics=config.metrics or rules.DEFAULT_MERGE_METRICS,
            field_mapping=config.field_mapping or {},
            per_metric_thresholds=config.per_metric_thresholds or {},
        )

    LOGGER.info(
        "Merging intersected polygons using rule set: %s (threshold: %.4f).",
        effective_rule_set.name,
        config.threshold,
    )
    merged_layer = spatial.merge_intersected_polygons(
        intersection=intersection,
        rule_set=effective_rule_set,
        object_level=config.object_level_merge,
        min_shared_length=config.min_shared_length,
    )

    LOGGER.info(
        "Result: %d merged polygons produced from %d original "
        "intersection polygons.",
        len(merged_layer),
        len(intersection),
    )

    # 3. write outputs safely
    _write_outputs(
        merged_gdf=merged_layer,
        destination=destination,
        output_format=config.output_format,
        layer_name=layer_name,
        overwrite=config.overwrite,
    )

    return merged_layer


# api symmetry alias
run_workflow = run_merge


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
            f"GDAL >= 3.6; installed version is "
            f"{pyogrio.__gdal_version_string__}. "
            "Use output_format='geopackage' or upgrade GDAL/Pyogrio."
        )

    if output_format == "filegdb" and pyogrio.__gdal_version__ < (3, 9, 0):
        LOGGER.warning(
            "GDAL versions before 3.9 may store 64-bit integer fields as "
            "Float64 in File Geodatabases."
        )


def _remove_dataset(path: pathlib.Path) -> None:
    '''Remove temporary dataset and SQLite sidecars.'''
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
    '''Return True if destination contains all required layers.'''
    existing_layers = {
        str(layer_name)
        for layer_name, _ in pyogrio.list_layers(destination)
    }
    return set(required_layers).issubset(existing_layers)


def _write_outputs(
    merged_gdf: geopandas.GeoDataFrame,
    destination: pathlib.Path,
    output_format: str,
    layer_name: str,
    overwrite: bool,
) -> None:
    '''Write merged polygons and atomically publish to destination.'''
    _, driver = configs.OUTPUT_FORMATS[output_format]
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = destination.with_name(
        f".{destination.stem}.{uuid.uuid4().hex}.tmp{destination.suffix}"
    )

    layer_options: dict[str, str] = {}
    if output_format == "filegdb" and pyogrio.__gdal_version__ >= (3, 9, 0):
        layer_options["TARGET_ARCGIS_VERSION"] = "ARCGIS_PRO_3_2_OR_LATER"

    try:
        # if destination already exists and contains other layers, copy
        # them to the temporary dataset first so they are preserved.
        if destination.exists():
            other_layers = [
                name for name, _ in pyogrio.list_layers(destination)
                if name != layer_name
            ]
            for prev_layer in other_layers:
                LOGGER.info("Preserving existing layer: %s", prev_layer)
                prev_df = pyogrio.read_dataframe(destination, layer=prev_layer)
                pyogrio.write_dataframe(
                    prev_df,
                    temporary_path,
                    layer=prev_layer,
                    driver=driver,
                    append=temporary_path.exists(),
                    layer_options=layer_options or None,
                )

        LOGGER.info("Writing merged polygon layer: %s", layer_name)
        pyogrio.write_dataframe(
            merged_gdf,
            temporary_path,
            layer=layer_name,
            driver=driver,
            append=temporary_path.exists(),
            promote_to_multi=True,
            layer_options=layer_options or None,
        )

        backup_path: pathlib.Path | None = None
        if destination.exists():
            existing_layers = [
                name for name, _ in pyogrio.list_layers(destination)
            ]
            if not overwrite and layer_name in existing_layers:
                raise FileExistsError(
                    f"Layer {layer_name!r} already exists in {destination}. "
                    "Use overwrite=True to replace it."
                )

            backup_path = destination.with_name(
                f".{destination.name}.{uuid.uuid4().hex}.bak"
            )
            destination.replace(backup_path)

        try:
            temporary_path.replace(destination)
        except Exception:  # pylint: disable=broad-exception-caught
            if backup_path is not None and backup_path.exists():
                backup_path.replace(destination)
            raise
        if backup_path is not None:
            _remove_dataset(backup_path)

    finally:
        if temporary_path.exists():
            _remove_dataset(temporary_path)

    LOGGER.info("Merged polygons successfully written to %s", destination)
