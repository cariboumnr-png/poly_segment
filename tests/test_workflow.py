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

"""Integration tests for the complete merge workflow."""

import pyogrio

from merge import MergeConfig, run_merge


def test_merge_workflow_filegdb(synthetic_data):
    """
    Given:
        A valid synthetic File Geodatabase containing four segmentation levels
        and a MergeConfig targeting 'filegdb' format.
    When:
        The complete run_merge workflow is executed.
    Then:
        The merged GeoDataFrame is produced with cluster and area metadata, and
        the output layer is atomically written to the destination .gdb.
    """
    tmp_dir, _ = synthetic_data
    dest_dir = tmp_dir / "output"

    config = MergeConfig(
        mu=780,
        source_folder=tmp_dir,
        source_gdb_name="test_segmentation",
        source_layer_prefix="segmented_objects",
        object_level_merge=3,
        destination_folder=dest_dir,
        gdb_version="test_001",
        layer_version="test_001",
        output_format="filegdb",
        threshold=0.10,
        overwrite=True,
    )

    merged_gdf = run_merge(config)

    assert not merged_gdf.empty
    assert "merge_cluster_id" in merged_gdf.columns
    assert "num_merged_parts" in merged_gdf.columns
    assert "merged_area_m2" in merged_gdf.columns

    # Verify output on disk
    dest_path = config.destination_dataset
    assert dest_path.exists()
    layers = [name for name, _ in pyogrio.list_layers(dest_path)]
    assert config.merged_layer in layers


def test_merge_workflow_geopackage(synthetic_data):
    """
    Given:
        A synthetic source dataset and a MergeConfig targeting 'geopackage' (.gpkg)
        output format.
    When:
        The run_merge workflow is executed.
    Then:
        The workflow completes successfully and the output GeoPackage file is created
        on disk containing the merged polygon layer.
    """
    tmp_dir, _ = synthetic_data
    dest_dir = tmp_dir / "output_gpkg"

    config = MergeConfig(
        mu=780,
        source_folder=tmp_dir,
        source_gdb_name="test_segmentation",
        source_layer_prefix="segmented_objects",
        object_level_merge=3,
        destination_folder=dest_dir,
        gdb_version="test_001",
        layer_version="test_001",
        output_format="geopackage",
        threshold=0.10,
        overwrite=True,
    )

    merged_gdf = run_merge(config)
    assert not merged_gdf.empty
    assert config.destination_dataset.exists()
