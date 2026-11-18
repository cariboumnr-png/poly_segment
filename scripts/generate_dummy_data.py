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

Generates realistic organic polygon segmentations using Lloyd-relaxed Voronoi
tessellations with distinct forest stand profiles and visual color mappings,
or traditional rectangular grids.

Run from the project root:

    python scripts/generate_dummy_data.py

Replace an existing dummy source dataset:

    python scripts/generate_dummy_data.py --overwrite

Use traditional rectangular grid:

    python scripts/generate_dummy_data.py --overwrite --pattern grid
"""

# standard imports
import argparse
import logging
import pathlib
import shutil
import typing

# third-party imports
import geopandas
import numpy
import pyogrio
import shapely
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
    "Mean_LMoment1",
    "Mean_LMoment2",
    "Mean_LMoment3",
    "Mean_LMoment4",
)

LAYER_ORGANIC_COUNTS = (6, 12, 24, 45)
LAYER_GRID_SHAPES = ((2, 2), (3, 3), (4, 4), (5, 5))

# Four realistic vegetation stand profiles with thematic color mappings
ZONE_PROFILES = [
    {
        "name": "Mature Conifer",
        "zq95": 24.5,
        "vci": 0.68,
        "lm1": 23.8,
        "lm2": 3.4,
        "lm3": 0.42,
        "lm4": 0.16,
        "s2_peak2": 850.0,
        "s2_preleaf": 620.0,
        "s2_senes": 730.0,
        "tpi": 12.0,
        "color": "#1e5631",  # Deep forest green
        "rgb": (30, 86, 49),
    },
    {
        "name": "Mixed Forest",
        "zq95": 17.2,
        "vci": 0.48,
        "lm1": 16.5,
        "lm2": 2.6,
        "lm3": 0.34,
        "lm4": 0.12,
        "s2_peak2": 1420.0,
        "s2_preleaf": 980.0,
        "s2_senes": 1150.0,
        "tpi": 4.5,
        "color": "#4c9a2a",  # Vibrant foliage green
        "rgb": (76, 154, 42),
    },
    {
        "name": "Regenerating Forest",
        "zq95": 7.8,
        "vci": 0.31,
        "lm1": 7.2,
        "lm2": 1.5,
        "lm3": 0.22,
        "lm4": 0.07,
        "s2_peak2": 1850.0,
        "s2_preleaf": 1250.0,
        "s2_senes": 1400.0,
        "tpi": -2.0,
        "color": "#8dc63f",  # Fresh lime green
        "rgb": (141, 198, 63),
    },
    {
        "name": "Wetland Meadow",
        "zq95": 1.4,
        "vci": 0.12,
        "lm1": 1.2,
        "lm2": 0.35,
        "lm3": 0.08,
        "lm4": 0.02,
        "s2_peak2": 950.0,
        "s2_preleaf": 820.0,
        "s2_senes": 880.0,
        "tpi": -8.5,
        "color": "#e5c158",  # Warm golden amber
        "rgb": (229, 193, 88),
    },
]

ZONE_CENTERS = [
    (0.28, 0.72),  # Northwest: Mature Conifer
    (0.72, 0.70),  # Northeast: Mixed Forest
    (0.70, 0.28),  # Southeast: Regenerating Forest
    (0.25, 0.25),  # Southwest: Wetland Meadow
]


def parse_args(
    argv: typing.Sequence[str] | None = None,
) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate four synthetic polygon segmentation layers."
    )
    parser.add_argument(
        "--source-dataset",
        type=pathlib.Path,
        default=DEFAULT_SOURCE_DATASET,
        help="Destination File Geodatabase.",
    )
    parser.add_argument(
        "--layer-prefix",
        default=DEFAULT_LAYER_PREFIX,
        help="Prefix for the four generated source layers.",
    )
    parser.add_argument(
        "--pattern",
        choices=("organic", "grid"),
        default="organic",
        help="Pattern type: 'organic' (Voronoi stands) or 'grid' (rectangular).",
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
            f"GDAL >= 3.6; installed version: {pyogrio.__gdal_version_string__}."
        )

    if pyogrio.__gdal_version__ >= (3, 9, 0):
        return {
            "TARGET_ARCGIS_VERSION": "ARCGIS_PRO_3_2_OR_LATER",
        }

    return None


def create_organic_layer(
    n_points: int,
    level: int,
    seed: int = 42,
) -> geopandas.GeoDataFrame:
    """Create one realistic organic polygon segmentation layer using Lloyd Voronoi."""
    min_x, min_y, max_x, max_y = EXTENT
    box = shapely.geometry.box(min_x, min_y, max_x, max_y)
    rng = numpy.random.default_rng(seed + level * 100)

    # Initial random points
    pts = [
        shapely.geometry.Point(x, y)
        for x, y in zip(
            rng.uniform(min_x, max_x, n_points),
            rng.uniform(min_y, max_y, n_points),
        )
    ]

    # Two Lloyd relaxation iterations to produce well-formed, natural cells
    for _ in range(2):
        vor = shapely.voronoi_polygons(shapely.MultiPoint(pts), extend_to=box)
        cells = [
            p.intersection(box)
            for p in vor.geoms
            if not p.intersection(box).is_empty
        ]
        pts = [c.centroid for c in cells]

    records: list[dict[str, object]] = []

    for i, poly in enumerate(cells):
        centroid = poly.centroid
        u = (centroid.x - min_x) / (max_x - min_x)
        v = (centroid.y - min_y) / (max_y - min_y)

        # Assign to nearest stand center
        dists = [
            ((u - cx) ** 2 + (v - cy) ** 2) ** 0.5
            for cx, cy in ZONE_CENTERS
        ]
        zone_id = int(numpy.argmin(dists))
        z = ZONE_PROFILES[zone_id]

        # Subtle intra-zone noise in [-0.025, 0.025] so adjacent polygons
        # within the same zone have differences <= 0.05 (below the 0.10 threshold)
        noise = (rng.random(6) - 0.5) * 0.05

        records.append(
            {
                "segment_id": int(i + 1),
                "grid_level": int(level),
                "row_number": int(v * 4),
                "column_number": int(u * 4),
                "Mean_S2_Peak2": float(z["s2_peak2"] + rng.uniform(-15, 15)),
                "Mean_S2_PreLeaf": float(z["s2_preleaf"] + rng.uniform(-15, 15)),
                "Mean_S2_Senes": float(z["s2_senes"] + rng.uniform(-15, 15)),
                "Mean_TPI": float(z["tpi"] + rng.uniform(-0.5, 0.5)),
                "Mean_vci_1m": float(z["vci"] + noise[0]),
                "Mean_ZQ95": float(z["zq95"] + noise[1]),
                "Mean_LMoment1": float(z["lm1"] + noise[2]),
                "Mean_LMoment2": float(z["lm2"] + noise[3]),
                "Mean_LMoment3": float(z["lm3"] + noise[4]),
                "Mean_LMoment4": float(z["lm4"] + noise[5]),
                "landcover": str(z["name"]),
                "hex_color": str(z["color"]),
                "color_r": int(z["rgb"][0]),
                "color_g": int(z["rgb"][1]),
                "color_b": int(z["rgb"][2]),
                "geometry": poly,
            }
        )

    frame = geopandas.GeoDataFrame(records, geometry="geometry", crs=CRS)

    for field in ("segment_id", "grid_level", "row_number", "column_number", "color_r", "color_g", "color_b"):
        frame[field] = frame[field].astype("int32")

    for field in ATTRIBUTE_FIELDS:
        frame[field] = frame[field].astype("float64")

    return frame


def create_grid(
    rows: int,
    columns: int,
    level: int,
) -> geopandas.GeoDataFrame:
    """Create one synthetic rectangular polygon grid (fallback)."""
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
                    "Mean_LMoment1": base_value + 5.0,
                    "Mean_LMoment2": 1.0 + (row + column) * 0.05,
                    "Mean_LMoment3": 0.5 + row * 0.02,
                    "Mean_LMoment4": 0.2 + column * 0.01,
                    "landcover": "Synthetic Stand",
                    "hex_color": "#4c9a2a",
                    "color_r": 76,
                    "color_g": 154,
                    "color_b": 42,
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

    for field in ("segment_id", "grid_level", "row_number", "column_number", "color_r", "color_g", "color_b"):
        frame[field] = frame[field].astype("int32")

    for field in ATTRIBUTE_FIELDS:
        frame[field] = frame[field].astype("float64")

    return frame


def generate_dummy_dataset(
    source_dataset: pathlib.Path,
    layer_prefix: str,
    pattern: str = "organic",
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

    for level in range(1, 5):
        layer_name = f"{layer_prefix}_{level}"
        if pattern == "organic":
            n_pts = LAYER_ORGANIC_COUNTS[level - 1]
            frame = create_organic_layer(n_points=n_pts, level=level)
        else:
            rows, cols = LAYER_GRID_SHAPES[level - 1]
            frame = create_grid(rows=rows, columns=cols, level=level)

        LOGGER.info(
            "Writing %s with %d polygons (%s pattern).",
            layer_name,
            len(frame),
            pattern,
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
        pattern=args.pattern,
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    main()
