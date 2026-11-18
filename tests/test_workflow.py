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


def test_two_stage_sequential_workflow(synthetic_data):
    """
    Given:
        A 4-layer synthetic source dataset.
    When:
        Stage 1 (run_workflow from intersect) produces the intersection layer and neighbour table,
        and Stage 2 (run_merge from merge) is executed in chained mode directly consuming
        Stage 1's intersection layer.
    Then:
        Stage 2 skips geometric intersection, merges candidate polygons according to the rule set,
        and safely adds the merged layer to the geodatabase preserving all previous layers.
    """
    from intersect import WorkflowConfig as IntersectConfig
    from intersect import run_workflow as run_intersect

    tmp_dir, _ = synthetic_data
    stage1_dest = tmp_dir / "output_sequential"

    # Stage 1: Intersect
    intersect_cfg = IntersectConfig(
        mu=780,
        source_folder=tmp_dir,
        source_gdb_name="test_segmentation",
        source_layer_prefix="segmented_objects",
        object_level_merge=3,
        destination_folder=stage1_dest,
        gdb_version="seq_001",
        table_version="seq_001",
        output_format="filegdb",
        overwrite=True,
    )
    run_intersect(intersect_cfg)

    # Verify Stage 1 created expected layers
    stage1_gdb = intersect_cfg.destination_dataset
    assert stage1_gdb.exists()
    layers_after_stage1 = {name for name, _ in pyogrio.list_layers(stage1_gdb)}
    assert intersect_cfg.intersection_layer in layers_after_stage1
    assert intersect_cfg.neighbour_table in layers_after_stage1

    # Stage 2: Merge in chained mode consuming Stage 1 output
    merge_cfg = MergeConfig(
        mu=780,
        source_folder=stage1_dest,
        source_gdb_name="isi_mu780_postOBC_process_verseq_001",
        source_layer=intersect_cfg.intersection_layer,
        object_level_merge=3,
        destination_folder=stage1_dest,
        gdb_version="seq_001",
        layer_version="seq_001",
        threshold=0.10,
        output_format="filegdb",
        overwrite=True,
    )
    merged_gdf = run_merge(merge_cfg)

    # Verify Stage 2 succeeded and all three layers exist in the same geodatabase
    assert not merged_gdf.empty
    layers_after_stage2 = {name for name, _ in pyogrio.list_layers(stage1_gdb)}
    assert intersect_cfg.intersection_layer in layers_after_stage2
    assert intersect_cfg.neighbour_table in layers_after_stage2
    assert merge_cfg.merged_layer in layers_after_stage2

