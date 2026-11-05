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

"""Polygon validation, intersection, and neighbour construction."""

# standard imports
import logging
import pathlib
import typing
# third-party imports
import geopandas
import pandas
import pyogrio
import pyproj
import shapely
import shapely.geometry.base as shapely_base


# ----- constants
LOGGER = logging.getLogger("post_obc_neighbour_analysis")


# ----- public functions
def validate_source_dataset(
    source_dataset: pathlib.Path,
    required_layers: typing.Sequence[str],
) -> None:
    """Check that the source dataset and all required layers are present."""
    if not source_dataset.exists():
        raise FileNotFoundError(
            f"Source geodatabase does not exist: {source_dataset}"
        )

    available_layers = {
        str(layer_name)
        for layer_name, _ in pyogrio.list_layers(source_dataset)
    }
    missing_layers = sorted(set(required_layers) - available_layers)
    if missing_layers:
        raise ValueError(
            "The source geodatabase is missing required layers: "
            + ", ".join(missing_layers)
        )


def intersect_polygon_layers(
    source_dataset: pathlib.Path,
    layer_names: typing.Sequence[str],
) -> geopandas.GeoDataFrame:
    """Intersect four polygon layers, retaining each layer's source feature ID."""
    if len(layer_names) != 4:
        raise ValueError("Exactly four polygon segmentation layers are required.")

    LOGGER.info("Reading the four source polygon layers.")
    input_layers = [
        _read_intersection_input(source_dataset, layer_name, level)
        for level, layer_name in enumerate(layer_names, start=1)
    ]

    reference_crs = pyproj.CRS.from_user_input(input_layers[0].crs)
    for layer_name, frame in zip(layer_names[1:], input_layers[1:]):
        if pyproj.CRS.from_user_input(frame.crs) != reference_crs:
            raise ValueError(
                f"Layer {layer_name!r} has a different CRS from "
                f"{layer_names[0]!r}. Reproject inputs before processing."
            )

    intersection = input_layers[0]
    for layer_name, next_layer in zip(layer_names[1:], input_layers[1:]):
        LOGGER.info(
            "Intersecting with %s (%d features).",
            layer_name,
            len(next_layer),
        )
        intersection = geopandas.overlay(
            intersection,
            next_layer,
            how="intersection",
            keep_geom_type=True,
            make_valid=True,
        )
        if intersection.empty:
            raise ValueError(
                "The four source layers have no common polygon area; "
                f"the intersection became empty after processing {layer_name!r}."
            )

    LOGGER.info("Intersection produced %d polygons.", len(intersection))
    return intersection


def build_polygon_neighbours(
    intersection: geopandas.GeoDataFrame,
) -> pandas.DataFrame:
    """Build bidirectional edge- and point-neighbour relationships.

    ``LENGTH`` is the total shared-boundary length in metres. ``NODE_COUNT``
    counts zero-dimensional point contacts; shared line segments contribute to
    ``LENGTH`` rather than to ``NODE_COUNT``.
    """
    id_fields = [
        column for column in intersection.columns if column.startswith("FID_")
    ]
    if len(id_fields) != 4:
        raise ValueError(
            "The intersection layer must contain exactly four FID_* fields."
        )

    geometries = list(intersection.geometry)
    tree = shapely.STRtree(geometries)
    candidate_pairs = tree.query(geometries, predicate="touches")

    output_columns = [
        *(f"src_{field}" for field in id_fields),
        *(f"nbr_{field}" for field in id_fields),
        "LENGTH",
        "NODE_COUNT",
    ]

    if candidate_pairs.size == 0:
        LOGGER.warning("No edge- or point-touching polygon pairs were found.")
        empty_columns: dict[str, pandas.Series] = {}
        for field in id_fields:
            field_dtype = intersection[field].dtype
            empty_columns[f"src_{field}"] = pandas.Series(dtype=field_dtype)
            empty_columns[f"nbr_{field}"] = pandas.Series(dtype=field_dtype)
        empty_columns["LENGTH"] = pandas.Series(dtype="float64")
        empty_columns["NODE_COUNT"] = pandas.Series(dtype="int32")
        return pandas.DataFrame(empty_columns, columns=output_columns)

    metres_per_unit = _metres_per_crs_unit(intersection.crs)
    id_values = {
        field: intersection[field].to_numpy()
        for field in id_fields
    }

    records: list[dict[str, object]] = []
    for left_index, right_index in candidate_pairs.T:
        # STRtree returns directed pairs. Keep one orientation here, then add
        # both directions explicitly to match ArcGIS BOTH_SIDES behavior.
        if left_index >= right_index:
            continue

        shared_boundary = (
            geometries[left_index]
            .boundary.intersection(geometries[right_index].boundary)
        )
        shared_length_m = float(shared_boundary.length * metres_per_unit)
        node_count = _count_point_components(shared_boundary)

        forward: dict[str, object] = {
            f"src_{field}": id_values[field][left_index]
            for field in id_fields
        }
        forward.update(
            {
                f"nbr_{field}": id_values[field][right_index]
                for field in id_fields
            }
        )
        forward.update({"LENGTH": shared_length_m, "NODE_COUNT": node_count})
        records.append(forward)

        reverse: dict[str, object] = {
            f"src_{field}": id_values[field][right_index]
            for field in id_fields
        }
        reverse.update(
            {
                f"nbr_{field}": id_values[field][left_index]
                for field in id_fields
            }
        )
        reverse.update({"LENGTH": shared_length_m, "NODE_COUNT": node_count})
        records.append(reverse)

    neighbours = pandas.DataFrame.from_records(records, columns=output_columns)
    if not neighbours.empty:
        neighbours["LENGTH"] = neighbours["LENGTH"].astype("float64")
        neighbours["NODE_COUNT"] = neighbours["NODE_COUNT"].astype("int32")

    LOGGER.info(
        "Identified %d directed neighbour relationships.",
        len(neighbours),
    )
    return neighbours


# ----- private helpers
def _read_intersection_input(
    source_dataset: pathlib.Path,
    layer_name: str,
    level: int,
) -> geopandas.GeoDataFrame:
    """Read one polygon layer and qualify its attributes by segmentation level."""
    frame = pyogrio.read_dataframe(
        source_dataset,
        layer=layer_name,
        fid_as_index=True,
    )
    _validate_polygon_geometries(frame, layer_name)

    id_field = f"FID_{layer_name}"
    frame[id_field] = frame.index.to_numpy()

    # Keep all source attributes, as ArcPy Intersect(join_attributes="ALL")
    # did, but prefix them to avoid ambiguous names across segmentation levels.
    geometry_name = frame.geometry.name
    field_renames = {
        field: f"L{level}_{field}"
        for field in frame.columns
        if field not in {geometry_name, id_field}
    }
    frame = frame.rename(columns=field_renames).reset_index(drop=True)
    return geopandas.GeoDataFrame(frame, geometry=geometry_name, crs=frame.crs)


def _validate_polygon_geometries(
    frame: geopandas.GeoDataFrame,
    layer_name: str,
) -> None:
    """Validate polygon geometry and feature identifiers for one input layer."""
    if frame.crs is None:
        raise ValueError(
            f"Layer {layer_name!r} has no coordinate reference system."
        )

    if frame.empty:
        raise ValueError(f"Layer {layer_name!r} contains no features.")

    if frame.geometry.isna().any():
        raise ValueError(f"Layer {layer_name!r} contains null geometries.")

    if frame.geometry.is_empty.any():
        raise ValueError(f"Layer {layer_name!r} contains empty geometries.")

    geometry_types = set(frame.geometry.geom_type.unique())
    unsupported_types = geometry_types - {"Polygon", "MultiPolygon"}
    if unsupported_types:
        raise TypeError(
            f"Layer {layer_name!r} must contain only polygons; found "
            f"{sorted(unsupported_types)}."
        )

    if not frame.index.is_unique:
        raise ValueError(
            f"Layer {layer_name!r} has non-unique OGR feature IDs."
        )

    if frame.index.hasnans:
        raise ValueError(f"Layer {layer_name!r} contains null feature IDs.")


def _count_point_components(geometry: shapely_base.BaseGeometry) -> int:
    """Count zero-dimensional components in a shared-boundary geometry."""
    if geometry.is_empty:
        return 0

    if geometry.geom_type == "Point":
        return 1

    if geometry.geom_type in {"MultiPoint", "GeometryCollection"}:
        assert isinstance(geometry, shapely_base.BaseMultipartGeometry)
        return sum(_count_point_components(part) for part in geometry.geoms)

    return 0


def _metres_per_crs_unit(crs_input: object) -> float:
    """Return the linear-unit conversion factor for a projected CRS."""
    crs = pyproj.CRS.from_user_input(crs_input)
    if not crs.is_projected:
        raise ValueError(
            "Neighbour boundary lengths require a projected CRS. "
            "Reproject the segmentation layers before running this script."
        )

    if not crs.axis_info:
        raise ValueError(f"Unable to determine linear units for CRS {crs}.")

    conversion_factor = crs.axis_info[0].unit_conversion_factor
    if conversion_factor is None or conversion_factor <= 0:
        raise ValueError(f"Invalid linear units for CRS {crs}.")

    return float(conversion_factor)
