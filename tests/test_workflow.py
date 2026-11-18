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
Integration tests for the complete merge workflow.

Validates end-to-end execution for File Geodatabase and GeoPackage
outputs, as well as two-stage sequential execution chaining Stage 1
intersection outputs directly into Stage 2 polygon merging.
'''

# standard imports
import pathlib
# third-party imports
import pyogrio
# local imports
from intersect import WorkflowConfig as IntersectConfig
from intersect import run_workflow as run_intersect
from merge import MergeConfig
from merge import run_merge


# ----- test cases
def test_merge_workflow_filegdb(
    synthetic_data: tuple[pathlib.Path, pathlib.Path],
) -> None:
    '''
    Validate complete merge workflow producing File Geodatabase.

    Given:
        A valid synthetic File Geodatabase containing 4 levels.
    When:
        The complete `run_merge` workflow is executed.
    Then:
        The merged GeoDataFrame is produced and written to `.gdb`.
    '''
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

    # verify output on disk
    dest_path = config.destination_dataset
    assert dest_path.exists()
    layers = [name for name, _ in pyogrio.list_layers(dest_path)]
    assert config.merged_layer in layers


def test_merge_workflow_geopackage(
    synthetic_data: tuple[pathlib.Path, pathlib.Path],
) -> None:
    '''
    Validate complete merge workflow producing GeoPackage output.

    Given:
        A synthetic source dataset and a `MergeConfig` for 'geopackage'.
    When:
        The `run_merge` workflow is executed.
    Then:
        The workflow completes and GeoPackage is created on disk.
    '''
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


def test_two_stage_sequential_workflow(
    synthetic_data: tuple[pathlib.Path, pathlib.Path],
) -> None:
    '''
    Validate chained two-stage execution from Stage 1 to Stage 2.

    Given:
        A 4-layer synthetic source dataset.
    When:
        Stage 1 produces intersection layers, and Stage 2 runs chained.
    Then:
        Stage 2 skips intersection, merges polygons, and writes layer.
    '''
    tmp_dir, _ = synthetic_data
    stage1_dest = tmp_dir / "output_sequential"

    # stage 1: intersect
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

    # verify stage 1 created expected layers
    stage1_gdb = intersect_cfg.destination_dataset
    assert stage1_gdb.exists()
    layers_after_stage1 = {name for name, _ in pyogrio.list_layers(stage1_gdb)}
    assert intersect_cfg.intersection_layer in layers_after_stage1
    assert intersect_cfg.neighbour_table in layers_after_stage1

    # stage 2: merge in chained mode consuming stage 1 output
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

    # verify stage 2 succeeded and all three layers exist
    assert not merged_gdf.empty
    layers_after_stage2 = {name for name, _ in pyogrio.list_layers(stage1_gdb)}
    assert intersect_cfg.intersection_layer in layers_after_stage2
    assert intersect_cfg.neighbour_table in layers_after_stage2
    assert merge_cfg.merged_layer in layers_after_stage2


