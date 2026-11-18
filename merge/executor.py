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

"""Execute the polygon merging workflow and safely write outputs to disk."""

from __future__ import annotations

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
from .configs import MergeConfig
from .configs import OUTPUT_FORMATS
from .rules import DefaultMergeRuleSet
from .rules import MergeRule
from .spatial import intersect_polygon_layers
from .spatial import merge_intersected_polygons
from .spatial import validate_source_dataset


LOGGER = logging.getLogger("poly_segment_merge")


# ----- public functions
def run_merge(
    config: MergeConfig,
    rule_set: MergeRule | None = None,
) -> geopandas.GeoDataFrame:
    """Execute the complete polygon layer merging workflow.

    1. Validates the environment and source dataset.
    2. Intersects the four source polygon layers.
    3. Evaluates neighbour pairs against the injected rule set.
    4. Merges adjacent qualifying polygons into a single polygon layer.
    5. Writes the merged layer atomically to the destination dataset.
    """
    _validate_environment(config.output_format)
    validate_source_dataset(config.source_dataset, config.source_layers)

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
        raise FileExistsError(
            f"Destination exists but does not contain expected output layer "
            f"{layer_name!r}: {destination}. Use overwrite=True to replace it."
        )

    # Resolve or create the effective rule set
    effective_rule_set = rule_set or config.rule_set
    if effective_rule_set is None:
        effective_rule_set = DefaultMergeRuleSet(
            threshold=config.threshold,
            field_mapping=config.field_mapping or {},
        )

    LOGGER.info("Executing 4-layer polygon intersection.")
    intersection = intersect_polygon_layers(
        source_dataset=config.source_dataset,
        layer_names=config.source_layers,
    )

    LOGGER.info(
        "Merging intersected polygons using rule set: %s (threshold: %.4f).",
        effective_rule_set.name,
        config.threshold,
    )
    merged_layer = merge_intersected_polygons(
        intersection=intersection,
        rule_set=effective_rule_set,
        object_level=config.object_level_merge,
        min_shared_length=config.min_shared_length,
    )

    LOGGER.info(
        "Result: %d merged polygons produced from %d original intersection polygons.",
        len(merged_layer),
        len(intersection),
    )

    _write_outputs(
        merged_gdf=merged_layer,
        destination=destination,
        output_format=config.output_format,
        layer_name=layer_name,
        overwrite=config.overwrite,
    )

    return merged_layer


# API symmetry alias
run_workflow = run_merge


# ----- private helpers
def _validate_environment(output_format: str) -> None:
    """Ensure the requested output driver is available and writable."""
    _, driver = OUTPUT_FORMATS[output_format]
    writable_drivers = pyogrio.list_drivers(write=True)

    if driver not in writable_drivers:
        raise RuntimeError(
            f"GDAL driver {driver!r} is not available for writing. "
            "Check the GDAL/Pyogrio installation."
        )

    if output_format == "filegdb" and pyogrio.__gdal_version__ < (3, 6, 0):
        raise RuntimeError(
            "File Geodatabase writing through OpenFileGDB requires GDAL >= 3.6; "
            f"the installed version is {pyogrio.__gdal_version_string__}. "
            "Use output_format='geopackage' or upgrade GDAL/Pyogrio."
        )

    if output_format == "filegdb" and pyogrio.__gdal_version__ < (3, 9, 0):
        LOGGER.warning(
            "GDAL versions before 3.9 may store 64-bit integer fields as "
            "Float64 in File Geodatabases."
        )


def _remove_dataset(path: pathlib.Path) -> None:
    """Remove a temporary or backup dataset and common SQLite sidecars."""
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
    """Return True when an existing destination contains all required layers."""
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
    """Write merged polygons to a temporary dataset and atomically publish."""
    _, driver = OUTPUT_FORMATS[output_format]
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = destination.with_name(
        f".{destination.stem}.{uuid.uuid4().hex}.tmp{destination.suffix}"
    )

    layer_options: dict[str, str] = {}
    if output_format == "filegdb" and pyogrio.__gdal_version__ >= (3, 9, 0):
        layer_options["TARGET_ARCGIS_VERSION"] = "ARCGIS_PRO_3_2_OR_LATER"

    try:
        LOGGER.info("Writing merged polygon layer: %s", layer_name)
        pyogrio.write_dataframe(
            merged_gdf,
            temporary_path,
            layer=layer_name,
            driver=driver,
            promote_to_multi=True,
            layer_options=layer_options or None,
        )

        backup_path: pathlib.Path | None = None
        if destination.exists():
            if not overwrite:
                raise FileExistsError(
                    f"Destination already exists: {destination}. "
                    "Use overwrite=True to replace it."
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

    LOGGER.info("Merged polygons successfully written to %s", destination)
