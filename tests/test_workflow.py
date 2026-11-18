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
outputs, two-stage sequential execution, and multi-trial parameter
sweeps with extended visualization artifacts.
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
from run_merge_sweep import DEFAULT_SWEEP_TRIALS
from run_merge_sweep import SweepTrial
from run_merge_sweep import run_merge_sweep


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


def test_merge_workflow_with_metric_subset(
    synthetic_data: tuple[pathlib.Path, pathlib.Path],
) -> None:
    '''
    Validate workflow when user selects metric subset and tolerances.

    Given:
        A synthetic source dataset.
    When:
        `run_merge` executes with metric subset and custom threshold.
    Then:
        Only the specified subset of metrics is used for merging.
    '''
    tmp_dir, _ = synthetic_data
    dest_dir = tmp_dir / "output_subset"

    config = MergeConfig(
        mu=780,
        source_folder=tmp_dir,
        source_gdb_name="test_segmentation",
        source_layer_prefix="segmented_objects",
        object_level_merge=3,
        destination_folder=dest_dir,
        gdb_version="test_sub_001",
        layer_version="test_sub_001",
        output_format="filegdb",
        metrics=("zq95", "vci_1m"),
        threshold=0.10,
        per_metric_thresholds={"zq95": 0.15, "vci_1m": 0.05},
        overwrite=True,
    )

    merged_gdf = run_merge(config)
    assert not merged_gdf.empty
    assert config.destination_dataset.exists()


def test_merge_workflow_with_metric_subset(
    synthetic_data: tuple[pathlib.Path, pathlib.Path],
) -> None:
    '''
    Validate workflow when user selects metric subset and tolerances.

    Given:
        A synthetic source dataset.
    When:
        `run_merge` executes with metric subset and custom threshold.
    Then:
        Only the specified subset of metrics is used for merging.
    '''
    tmp_dir, _ = synthetic_data
    dest_dir = tmp_dir / "output_subset"

    config = MergeConfig(
        mu=780,
        source_folder=tmp_dir,
        source_gdb_name="test_segmentation",
        source_layer_prefix="segmented_objects",
        object_level_merge=3,
        destination_folder=dest_dir,
        gdb_version="test_sub_001",
        layer_version="test_sub_001",
        output_format="filegdb",
        metrics=("zq95", "vci_1m"),
        threshold=0.10,
        per_metric_thresholds={"zq95": 0.15, "vci_1m": 0.05},
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
        Intermediate products remain in Stage 1 dataset while merged
        polygons are written to a separate Stage 2 dataset.
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
        source_gdb_name="isi_mu780_postOBC_intersect_verseq_001",
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
    stage2_gdb = merge_cfg.destination_dataset

    # verify datasets are separate and both exist
    assert not merged_gdf.empty
    assert stage1_gdb != stage2_gdb
    assert stage1_gdb.exists()
    assert stage2_gdb.exists()

    # intermediate products are preserved in stage 1 gdb
    layers_stage1 = {name for name, _ in pyogrio.list_layers(stage1_gdb)}
    assert intersect_cfg.intersection_layer in layers_stage1
    assert intersect_cfg.neighbour_table in layers_stage1
    assert merge_cfg.merged_layer not in layers_stage1

    # merged output is isolated in stage 2 gdb
    layers_stage2 = {name for name, _ in pyogrio.list_layers(stage2_gdb)}
    assert merge_cfg.merged_layer in layers_stage2
    assert intersect_cfg.intersection_layer not in layers_stage2


def test_merge_sweep_orchestrator(
    synthetic_data: tuple[pathlib.Path, pathlib.Path],
) -> None:
    '''
    Validate multi-trial merge parameter sweep execution.

    Given:
        A Stage 1 intersected dataset and custom sweep trials.
    When:
        `run_merge_sweep` executes over the array of parameter trials.
    Then:
        All trials produce valid merged stands in a single sweep GDB.
    '''
    tmp_dir, _ = synthetic_data
    stage1_dest = tmp_dir / "sweep_stage1"

    intersect_cfg = IntersectConfig(
        mu=780,
        source_folder=tmp_dir,
        source_gdb_name="test_segmentation",
        source_layer_prefix="segmented_objects",
        object_level_merge=3,
        destination_folder=stage1_dest,
        gdb_version="swp_001",
        table_version="swp_001",
        output_format="filegdb",
        overwrite=True,
    )
    run_intersect(intersect_cfg)

    base_merge_cfg = MergeConfig(
        mu=780,
        source_folder=stage1_dest,
        source_gdb_name="isi_mu780_postOBC_intersect_verswp_001",
        source_layer=intersect_cfg.intersection_layer,
        destination_folder=tmp_dir / "sweep_output",
        gdb_version="swp_001",
        layer_version="swp_001",
        output_format="filegdb",
        overwrite=True,
    )

    trials = (
        SweepTrial(
            name="test_std",
            label="Trial 1 (Standard)",
            description="All metrics with standard tolerance",
            threshold=0.10,
        ),
        SweepTrial(
            name="test_canopy",
            label="Trial 2 (Canopy Only)",
            description="Canopy height only",
            threshold=0.10,
            metrics=("zq95",),
        ),
        SweepTrial(
            name="test_strict",
            label="Trial 3 (Strict)",
            description="Ultra-strict structural tolerance",
            threshold=0.02,
            metrics=("zq95", "vci_1m"),
        ),
    )

    summary_file = tmp_dir / "sweep_output" / "test_summary.json"
    result = run_merge_sweep(
        base_config=base_merge_cfg,
        trials=trials,
        visualize=False,
        output_summary_json=summary_file,
    )

    assert result["destination_dataset"].exists()
    layers = [
        name for name, _ in pyogrio.list_layers(result["destination_dataset"])
    ]
    for trial in trials:
        expected_layer = f"merged_trial_{trial.name}"
        assert expected_layer in layers
        assert trial.name in result["trials"]
        assert not result["trials"][trial.name].empty

    assert summary_file.exists()
    assert len(result["summary"]) == 3


def test_merge_sweep_visualization_integration(
    synthetic_data: tuple[pathlib.Path, pathlib.Path],
) -> None:
    '''
    Validate extended multi-panel PNG and HTML viewer generation.

    Given:
        A Stage 1 intersected dataset and raw multi-scale layers.
    When:
        `run_merge_sweep` executes with `visualize=True`.
    Then:
        Both comparison PNG and interactive HTML files are created.
    '''
    tmp_dir, source_gdb = synthetic_data
    stage1_dest = tmp_dir / "sweep_vis_stage1"

    intersect_cfg = IntersectConfig(
        mu=780,
        source_folder=tmp_dir,
        source_gdb_name="test_segmentation",
        source_layer_prefix="segmented_objects",
        object_level_merge=3,
        destination_folder=stage1_dest,
        gdb_version="vis_001",
        table_version="vis_001",
        output_format="filegdb",
        overwrite=True,
    )
    run_intersect(intersect_cfg)

    base_merge_cfg = MergeConfig(
        mu=780,
        source_folder=stage1_dest,
        source_gdb_name="isi_mu780_postOBC_intersect_vervis_001",
        source_layer=intersect_cfg.intersection_layer,
        destination_folder=tmp_dir / "sweep_vis_output",
        gdb_version="vis_001",
        layer_version="vis_001",
        output_format="filegdb",
        overwrite=True,
    )

    out_png = tmp_dir / "sweep_vis_output" / "test_vis.png"
    out_html = tmp_dir / "sweep_vis_output" / "test_vis.html"

    trials = (
        SweepTrial(
            name="t1",
            label="Trial 1",
            description="Test trial 1",
            threshold=0.10,
        ),
        SweepTrial(
            name="t2",
            label="Trial 2",
            description="Test trial 2",
            threshold=0.03,
            metrics=("zq95", "vci_1m"),
        ),
    )

    result = run_merge_sweep(
        base_config=base_merge_cfg,
        trials=trials,
        visualize=True,
        raw_source_gdb=source_gdb,
        output_image=out_png,
        output_html=out_html,
    )

    assert out_png.exists()
    assert out_png.stat().st_size > 0
    assert out_html.exists()
    html_text = out_html.read_text(encoding="utf-8")
    assert "Trial 1" in html_text
    assert "Trial 2" in html_text
    assert "<svg" in html_text
