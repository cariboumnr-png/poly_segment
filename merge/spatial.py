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
Spatial operations for polygon intersection and rule-based merging.

Provides four-layer polygon intersection, candidate neighbour detection,
disjoint-set cluster aggregation, and dissolved geometry generation.

Public APIs:
    - `validate_source_dataset`: Validate source dataset existence.
    - `intersect_polygon_layers`: Intersect four polygon layers.
    - `find_candidate_neighbour_pairs`: Find touching neighbour pairs.
    - `merge_intersected_polygons`: Merge polygons using rule sets.
'''

# standard imports
from __future__ import annotations
from collections import defaultdict
import logging
import pathlib
import typing
# third-party imports
import geopandas
import numpy
import pandas
import pyogrio
import pyproj
import shapely
import shapely.geometry.base as shapely_base
# local imports
from .attributes import aggregate_attributes_area_weighted
from .rules import DefaultMergeRuleSet
from .rules import MergeRule

LOGGER = logging.getLogger("poly_segment_merge")


# ----- private classes
class _DisjointSet:
    '''Disjoint-set with path compression and rank optimization.'''
    __slots__ = ("parent", "rank")

    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, item: int) -> int:
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        # path compression
        curr = item
        while curr != root:
            parent_node = self.parent[curr]
            self.parent[curr] = root
            curr = parent_node
        return root

    def union(self, item1: int, item2: int) -> None:
        root1 = self.find(item1)
        root2 = self.find(item2)
        if root1 != root2:
            if self.rank[root1] < self.rank[root2]:
                self.parent[root1] = root2
            elif self.rank[root1] > self.rank[root2]:
                self.parent[root2] = root1
            else:
                self.parent[root2] = root1
                self.rank[root1] += 1

    def groups(self) -> dict[int, list[int]]:
        '''Return mapping of root index to list of member indices.'''
        clusters: dict[int, list[int]] = defaultdict(list)
        for i in range(len(self.parent)):
            clusters[self.find(i)].append(i)
        return clusters


# ----- public functions
def validate_source_dataset(
    source_dataset: pathlib.Path,
    required_layers: typing.Sequence[str],
) -> None:
    '''
    Check that the source dataset and all required layers exist.

    Args:
        source_dataset:
            Path to the source geospatial dataset.
        required_layers:
            Sequence of layer names that must exist in dataset.

    Raises:
        FileNotFoundError:
            If source dataset does not exist.
        ValueError:
            If one or more required layers are missing.
    '''
    if not source_dataset.exists():
        raise FileNotFoundError(
            f"Source dataset does not exist: {source_dataset}"
        )

    available_layers = {
        str(layer_name)
        for layer_name, _ in pyogrio.list_layers(source_dataset)
    }
    missing_layers = sorted(set(required_layers) - available_layers)
    if missing_layers:
        raise ValueError(
            "The source dataset is missing required layers: "
            + ", ".join(missing_layers)
        )


def intersect_polygon_layers(
    source_dataset: pathlib.Path,
    layer_names: typing.Sequence[str],
) -> geopandas.GeoDataFrame:
    '''
    Intersect four polygon layers, retaining source feature IDs.

    Args:
        source_dataset:
            Path to the source geospatial dataset.
        layer_names:
            Sequence of four polygon layer names to intersect.

    Returns:
        geopandas.GeoDataFrame:
            Intersected polygon layer retaining all attributes.

    Raises:
        ValueError:
            If layer count is not 4, CRSs differ, or result is empty.
    '''
    if len(layer_names) != 4:
        raise ValueError(
            "Exactly four polygon segmentation layers are required."
        )

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
                "The source layers have no common polygon area; "
                f"intersection became empty after processing {layer_name!r}."
            )

    LOGGER.info("Intersection produced %d polygons.", len(intersection))
    return intersection


def find_candidate_neighbour_pairs(
    intersection: geopandas.GeoDataFrame,
    min_shared_length: float = 0.0,
) -> tuple[numpy.ndarray, numpy.ndarray]:
    '''
    Find touching candidate neighbour pairs (i, j) where i < j.

    Optionally filters by minimum shared boundary length in metres.

    Args:
        intersection:
            GeoDataFrame of intersected polygons.
        min_shared_length:
            Minimum shared boundary length in metres.

    Returns:
        tuple[numpy.ndarray, numpy.ndarray]:
            Tuple of left and right polygon integer index arrays.
    '''
    geometries = list(intersection.geometry)
    if not geometries:
        return (
            numpy.empty(0, dtype=numpy.int64),
            numpy.empty(0, dtype=numpy.int64),
        )

    tree = shapely.STRtree(geometries)
    candidate_pairs = tree.query(geometries, predicate="touches")

    if candidate_pairs.size == 0:
        return (
            numpy.empty(0, dtype=numpy.int64),
            numpy.empty(0, dtype=numpy.int64),
        )

    # keep only undirected pairs where left < right
    left_indices = []
    right_indices = []
    metres_per_unit = (
        _metres_per_crs_unit(intersection.crs)
        if min_shared_length > 0 else 1.0
    )

    for left_idx, right_idx in candidate_pairs.T:
        if left_idx >= right_idx:
            continue

        if min_shared_length > 0:
            shared = (
                geometries[left_idx]
                .boundary.intersection(geometries[right_idx].boundary)
            )
            shared_length_m = float(shared.length * metres_per_unit)
            if shared_length_m < min_shared_length:
                continue

        left_indices.append(left_idx)
        right_indices.append(right_idx)

    return (
        numpy.array(left_indices, dtype=numpy.int64),
        numpy.array(right_indices, dtype=numpy.int64),
    )


def merge_intersected_polygons(
    intersection: geopandas.GeoDataFrame,
    rule_set: MergeRule,
    object_level: int = 3,
    min_shared_length: float = 0.0,
) -> geopandas.GeoDataFrame:
    '''
    Merge adjacent intersected polygons using injected rule set.

    Args:
        intersection:
            GeoDataFrame of intersected polygon features.
        rule_set:
            Configured merge rule evaluating neighbour pairs.
        object_level:
            Target segmentation level supplying attributes.
        min_shared_length:
            Minimum shared boundary length in metres.

    Returns:
        geopandas.GeoDataFrame:
            Merged polygon layer with aggregated attributes.
    '''
    if intersection.empty:
        LOGGER.warning(
            "Intersection GeoDataFrame is empty; returning copy."
        )
        return intersection.copy()

    # automatically resolve column mapping if using DefaultMergeRuleSet
    effective_rule_set = rule_set
    if isinstance(rule_set, DefaultMergeRuleSet):
        effective_rule_set = rule_set.with_resolved_mapping(
            columns=intersection.columns,
            preferred_level=object_level,
        )

    left_idx, right_idx = find_candidate_neighbour_pairs(
        intersection,
        min_shared_length=min_shared_length,
    )

    n_features = len(intersection)
    disjoint_set = _DisjointSet(n_features)

    if len(left_idx) > 0:
        sources_df = intersection.iloc[left_idx].reset_index(drop=True)
        candidates_df = intersection.iloc[right_idx].reset_index(drop=True)

        can_merge_mask = effective_rule_set.evaluate_batch(
            sources_df, candidates_df
        )
        permitted_left = left_idx[can_merge_mask]
        permitted_right = right_idx[can_merge_mask]

        LOGGER.info(
            "Evaluated %d candidate neighbour pairs; %d permitted to merge "
            "under %s.",
            len(left_idx),
            len(permitted_left),
            rule_set.name,
        )

        for u, v in zip(permitted_left, permitted_right):
            disjoint_set.union(int(u), int(v))
    else:
        LOGGER.info("No touching neighbour candidates found.")

    clusters = disjoint_set.groups()
    LOGGER.info(
        "Clustered %d input polygons into %d merged polygon features.",
        n_features,
        len(clusters),
    )

    # classify columns for aggregation
    geom_col = intersection.geometry.name
    id_cols = [
        c for c in intersection.columns
        if c.startswith("FID_") or c.endswith("_id")
    ]
    color_and_class_cols = [
        c for c in intersection.columns
        if c in ("landcover", "hex_color", "color_r", "color_g", "color_b")
        or any(
            c.endswith(f"_{s}")
            for s in ("landcover", "hex_color", "color_r", "color_g", "color_b")
        )
    ]
    numeric_cols = [
        c for c in intersection.columns
        if c != geom_col
        and c not in id_cols
        and c not in color_and_class_cols
        and pandas.api.types.is_numeric_dtype(intersection[c])
    ]
    representative_cols = id_cols + color_and_class_cols

    merged_records: list[dict[str, object]] = []
    merged_geometries: list[shapely_base.BaseGeometry] = []

    geometries = intersection.geometry.to_numpy()
    areas = intersection.geometry.area.to_numpy()

    for cluster_id, member_indices in clusters.items():
        member_geoms = [geometries[idx] for idx in member_indices]
        member_areas = areas[member_indices]

        if len(member_geoms) == 1:
            union_geom = member_geoms[0]
        else:
            union_geom = shapely.unary_union(member_geoms)

        union_geom = _extract_polygonal(union_geom)
        merged_geometries.append(union_geom)

        member_df = intersection.iloc[member_indices]
        attrs = aggregate_attributes_area_weighted(
            records_df=member_df,
            areas=member_areas,
            numeric_columns=numeric_cols,
            id_columns=representative_cols,
        )
        attrs["merge_cluster_id"] = int(cluster_id)
        merged_records.append(attrs)

    result_df = pandas.DataFrame.from_records(merged_records)

    # promote thematic class and color fields from selected level
    for key in ("landcover", "hex_color", "color_r", "color_g", "color_b"):
        lvl_key = f"L{object_level}_{key}"
        if lvl_key in result_df.columns and key not in result_df.columns:
            result_df[key] = result_df[lvl_key]

    merged_gdf = geopandas.GeoDataFrame(
        result_df,
        geometry=merged_geometries,
        crs=intersection.crs,
    )

    return merged_gdf


# ----- private helpers
def _read_intersection_input(
    source_dataset: pathlib.Path,
    layer_name: str,
    level: int,
) -> geopandas.GeoDataFrame:
    '''Read polygon layer and qualify attributes by level.'''
    frame = pyogrio.read_dataframe(
        source_dataset,
        layer=layer_name,
        fid_as_index=True,
    )
    _validate_polygon_geometries(frame, layer_name)

    id_field = f"FID_{layer_name}"
    frame[id_field] = frame.index.to_numpy()

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
    '''Validate polygon geometry and feature identifiers for layer.'''
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


def _extract_polygonal(
    geometry: shapely_base.BaseGeometry,
) -> shapely_base.BaseGeometry:
    '''Ensure geometry consists only of polygon components.'''
    if geometry.is_empty:
        return geometry

    if geometry.geom_type in {"Polygon", "MultiPolygon"}:
        return geometry

    if geometry.geom_type == "GeometryCollection":
        polygons = [
            g for g in geometry.geoms
            if g.geom_type in {"Polygon", "MultiPolygon"} and not g.is_empty
        ]
        if not polygons:
            return geometry
        return shapely.unary_union(polygons)

    return geometry


def _metres_per_crs_unit(crs_input: object) -> float:
    '''Return linear-unit conversion factor for a projected CRS.'''
    crs = pyproj.CRS.from_user_input(crs_input)
    if not crs.is_projected:
        raise ValueError(
            "Boundary length calculations require a projected CRS. "
            "Reproject inputs before running."
        )

    if not crs.axis_info:
        raise ValueError(f"Unable to determine linear units for CRS {crs}.")

    conversion_factor = crs.axis_info[0].unit_conversion_factor
    if conversion_factor is None or conversion_factor <= 0:
        raise ValueError(f"Invalid linear units for CRS {crs}.")

    return float(conversion_factor)

