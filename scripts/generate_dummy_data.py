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

"""
Generate synthetic polygon layers for workflow integration testing.

This script only creates the source File Geodatabase. It does not import or
execute the application workflow.

Run from the project root:

    python generate_dummy_data.py

Replace an existing dummy source dataset:

    python generate_dummy_data.py --overwrite
"""

# standard imports
import argparse
import logging
import pathlib
import shutil
import typing
# third-party imports
import geopandas
import pyogrio
import shapely.geometry


LOGGER = logging.getLogger(__name__)

CRS = "EPSG:26917"

DEFAULT_SOURCE_DATASET = pathlib.Path("sandbox/input/segmentation_R1.gdb")
DEFAULT_LAYER_PREFIX = "segmented_objects_R1"

EXTENT = (
    500_000.0,
    4_900_000.0,
    501_000.0,
    4_901_000.0,
)

ATTRIBUTE_FIELDS = (
    "Mean_S2_Peak2",
    "Mean_S2_PreLeaf",
    "Mean_S2_Senes",
    "Mean_TPI",
    "Mean_vci_1m",
    "Mean_ZQ95",
)

LAYER_GRID_SHAPES = (
    (2, 2),
    (3, 3),
    (4, 4),
    (5, 5),
)


def parse_args(
    argv: typing.Sequence[str] | None = None,
) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate four synthetic polygon segmentation layers in a "
            "File Geodatabase."
        )
    )
    parser.add_argument(
        "--source-dataset",
        type=pathlib.Path,
        default=DEFAULT_SOURCE_DATASET,
        help=(
            "Destination File Geodatabase. Relative paths are resolved "
            "from the current working directory."
        ),
    )
    parser.add_argument(
        "--layer-prefix",
        default=DEFAULT_LAYER_PREFIX,
        help="Prefix for the four generated source layers.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace the source dataset if it already exists.",
    )
    return parser.parse_args(argv)


def remove_dataset(path: pathlib.Path) -> None:
    """Remove a vector dataset and common SQLite sidecar files."""
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()

    for suffix in ("-wal", "-shm"):
        sidecar = pathlib.Path(f"{path}{suffix}")
        if sidecar.exists():
            sidecar.unlink()


def validate_environment() -> dict[str, str] | None:
    """Validate File Geodatabase support and return layer options."""
    writable_drivers = pyogrio.list_drivers(write=True)

    if "OpenFileGDB" not in writable_drivers:
        raise RuntimeError(
            "The GDAL OpenFileGDB driver is not available for writing. "
            "Install a GDAL/Pyogrio build with writable OpenFileGDB support."
        )

    if pyogrio.__gdal_version__ < (3, 6, 0):
        raise RuntimeError(
            "Creating a File Geodatabase through OpenFileGDB requires "
            f"GDAL >= 3.6; installed version: "
            f"{pyogrio.__gdal_version_string__}."
        )

    if pyogrio.__gdal_version__ >= (3, 9, 0):
        return {
            "TARGET_ARCGIS_VERSION": "ARCGIS_PRO_3_2_OR_LATER",
        }

    return None


def create_grid(
    rows: int,
    columns: int,
    level: int,
) -> geopandas.GeoDataFrame:
    """Create one synthetic rectangular polygon grid."""
    minimum_x, minimum_y, maximum_x, maximum_y = EXTENT
    cell_width = (maximum_x - minimum_x) / columns
    cell_height = (maximum_y - minimum_y) / rows

    records: list[dict[str, object]] = []

    for row in range(rows):
        for column in range(columns):
            feature_number = row * columns + column
            x_min = minimum_x + column * cell_width
            x_max = x_min + cell_width
            y_min = minimum_y + row * cell_height
            y_max = y_min + cell_height

            base_value = (
                level * 100.0
                + row * 10.0
                + column
                + feature_number * 0.1
            )

            records.append(
                {
                    "segment_id": feature_number + 1,
                    "grid_level": level,
                    "row_number": row,
                    "column_number": column,
                    "Mean_S2_Peak2": base_value + 10.0,
                    "Mean_S2_PreLeaf": base_value + 20.0,
                    "Mean_S2_Senes": base_value + 30.0,
                    "Mean_TPI": (row - column) * 2.5 + level,
                    "Mean_vci_1m": 0.2 + feature_number * 0.01,
                    "Mean_ZQ95": 15.0 + row * 3.0 + column * 1.5,
                    "geometry": shapely.geometry.box(
                        x_min,
                        y_min,
                        x_max,
                        y_max,
                    ),
                }
            )

    frame = geopandas.GeoDataFrame(
        records,
        geometry="geometry",
        crs=CRS,
    )

    integer_fields = (
        "segment_id",
        "grid_level",
        "row_number",
        "column_number",
    )
    for field in integer_fields:
        frame[field] = frame[field].astype("int32")

    for field in ATTRIBUTE_FIELDS:
        frame[field] = frame[field].astype("float64")

    return frame


def generate_dummy_dataset(
    source_dataset: pathlib.Path,
    layer_prefix: str,
    overwrite: bool = False,
) -> None:
    """Generate the four synthetic source polygon layers."""
    layer_options = validate_environment()
    source_dataset = source_dataset.resolve()

    if source_dataset.exists():
        if not overwrite:
            raise FileExistsError(
                f"Source dataset already exists: {source_dataset}. "
                "Use --overwrite to replace it."
            )
        remove_dataset(source_dataset)

    source_dataset.parent.mkdir(parents=True, exist_ok=True)

    for level, (rows, columns) in enumerate(
        LAYER_GRID_SHAPES,
        start=1,
    ):
        layer_name = f"{layer_prefix}_{level}"
        frame = create_grid(
            rows=rows,
            columns=columns,
            level=level,
        )

        LOGGER.info(
            "Writing %s with %d polygons.",
            layer_name,
            len(frame),
        )

        pyogrio.write_dataframe(
            frame,
            source_dataset,
            layer=layer_name,
            driver="OpenFileGDB",
            append=source_dataset.exists(),
            promote_to_multi=True,
            layer_options=layer_options,
        )

    LOGGER.info(
        "Synthetic source dataset written to %s.",
        source_dataset,
    )


def main(argv: typing.Sequence[str] | None = None) -> None:
    """Generate the dummy source dataset."""
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    generate_dummy_dataset(
        source_dataset=args.source_dataset,
        layer_prefix=args.layer_prefix,
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    main()