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
Unit tests for spatial operations and polygon merging.

Validates disjoint-set connected components and adjacent polygon merging
with area-weighted attribute aggregation.
'''

# third-party imports
import geopandas
import pytest
import shapely.geometry
# local imports
from merge.rules import MetricDifferenceRule
from merge.spatial import _DisjointSet
from merge.spatial import merge_intersected_polygons


# ----- test cases
def test_disjoint_set() -> None:
    '''
    Validate disjoint-set union-find operations and connectivity.

    Given:
        A `_DisjointSet` initialized with 5 distinct elements.
    When:
        Consecutive union operations are performed on subsets.
    Then:
        Elements are correctly grouped into connected clusters.
    '''
    ds = _DisjointSet(5)
    # initially 5 individual clusters
    assert len(ds.groups()) == 5

    ds.union(0, 1)
    ds.union(1, 2)
    # 0, 1, 2 should be in the same cluster
    groups = ds.groups()
    assert len(groups) == 3
    root = ds.find(0)
    assert set(groups[root]) == {0, 1, 2}

    ds.union(3, 4)
    assert len(ds.groups()) == 2


def test_merge_intersected_polygons_simple() -> None:
    '''
    Validate simple 2x2 grid adjacent polygon merging.

    Given:
        A GeoDataFrame of 4 adjacent grid polygons with attributes.
    When:
        `merge_intersected_polygons` runs with `MetricDifferenceRule`.
    Then:
        The two qualifying polygons are merged into a single polygon.
    '''
    # create 4 adjacent 1x1 squares in a 2x2 grid
    # (0,1): top-left, (1,1): top-right
    # (0,0): bot-left, (1,0): bot-right
    boxes = [
        shapely.geometry.box(0, 0, 1, 1),  # 0: bot-left
        shapely.geometry.box(1, 0, 2, 1),  # 1: bot-right
        shapely.geometry.box(0, 1, 1, 2),  # 2: top-left
        shapely.geometry.box(1, 1, 2, 2),  # 3: top-right
    ]

    # let 0 and 1 have similar zq95 (within 0.10)
    # let 2 and 3 have different zq95
    df = geopandas.GeoDataFrame(
        {
            "segment_id": [1, 2, 3, 4],
            "zq95": [10.00, 10.05, 20.00, 25.00],
            "vci_1m": [0.5, 0.5, 0.5, 0.5],
        },
        geometry=boxes,
        crs="EPSG:26917",
    )

    rule = MetricDifferenceRule(metrics=("zq95", "vci_1m"), threshold=0.10)
    merged = merge_intersected_polygons(df, rule_set=rule)

    # 0 and 1 should merge into 1 polygon of area 2.0
    # 2 and 3 remain distinct (each area 1.0)
    # total merged features = 3
    assert len(merged) == 3

    # check that one merged polygon has area 2.0 and 2 parts
    two_part = merged[merged["num_merged_parts"] == 2]
    assert len(two_part) == 1
    assert pytest.approx(two_part["merged_area_m2"].iloc[0]) == 2.0
    expected_zq95 = (10.00 + 10.05) / 2.0
    assert pytest.approx(two_part["zq95"].iloc[0]) == expected_zq95

