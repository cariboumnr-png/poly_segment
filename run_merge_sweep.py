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
Parameter sweep orchestrator for Stage 2 polygon merging.

Executes an array of parameter combinations (e.g. varying structural
metrics and tolerance thresholds) over Stage 1 intersected polygon
products, and produces extended multi-panel graphics and interactive
HTML viewers comparing all trials side-by-side.

Public APIs:
    - `SweepTrial`: Dataclass specifying single trial parameters.
    - `DEFAULT_SWEEP_TRIALS`: Predefined array of demonstration trials.
    - `run_merge_sweep`: Programmatic sweep orchestrator function.
    - `parse_args`: Parse command-line arguments.
    - `main`: Entry point for script execution.
'''

# standard imports
from __future__ import annotations
import argparse
import dataclasses
import json
import logging
import pathlib
import time
import typing
# third-party imports
import geopandas
import pyogrio
# local imports
from merge import MergeConfig
from merge import run_merge
from run_merge import load_config
from scripts.visualize import generate_interactive_html
from scripts.visualize import plot_comparison_figure

LOGGER = logging.getLogger("poly_segment_sweep")

DEFAULT_CONFIG_PATH = pathlib.Path("merge_config.json")
DEFAULT_RAW_GDB = pathlib.Path("sandbox/input/segmentation_R1.gdb")
DEFAULT_PNG_PATH = pathlib.Path("sandbox/output/sweep_visualization.png")
DEFAULT_HTML_PATH = pathlib.Path("sandbox/output/sweep_visualization.html")
DEFAULT_SUMMARY_PATH = pathlib.Path("sandbox/output/sweep_summary.json")


# ----- public dataclasses
@dataclasses.dataclass(frozen=True)
class SweepTrial:
    '''Specification for a single merge parameter combination trial.'''
    name: str
    label: str
    description: str
    threshold: float = 0.10
    metrics: tuple[str, ...] | None = None
    per_metric_thresholds: dict[str, float] | None = None
    output_layer_name: str | None = None


DEFAULT_SWEEP_TRIALS: tuple[SweepTrial, ...] = (
    SweepTrial(
        name="all_standard",
        label="Trial 1: All Metrics (Standard)",
        description="All 6 structural metrics at 10% tolerance",
        threshold=0.10,
        metrics=None,
        per_metric_thresholds=None,
    ),
    SweepTrial(
        name="canopy_only",
        label="Trial 2: Canopy Height Only",
        description="Canopy height (ZQ95) at 10% tolerance",
        threshold=0.10,
        metrics=("zq95",),
        per_metric_thresholds=None,
    ),
    SweepTrial(
        name="canopy_strict_vci",
        label="Trial 3: Canopy + Strict VCI",
        description="Relaxed ZQ95 (15%) + strict foliage density (3%)",
        threshold=0.10,
        metrics=("zq95", "vci_1m"),
        per_metric_thresholds={"zq95": 0.15, "vci_1m": 0.03},
    ),
    SweepTrial(
        name="strict_structural",
        label="Trial 4: Strict Structural",
        description="Ultra-tight 2% tolerance preserving sub-stand variations",
        threshold=0.02,
        metrics=("zq95", "vci_1m"),
        per_metric_thresholds=None,
    ),
)


# ----- public functions
def parse_args(
    argv: typing.Sequence[str] | None = None,
) -> argparse.Namespace:
    '''
    Parse command-line arguments for the merge parameter sweep.

    Args:
        argv:
            Optional sequence of command-line argument strings.

    Returns:
        argparse.Namespace:
            Parsed command-line arguments.
    '''
    parser = argparse.ArgumentParser(
        description=(
            "Orchestrate Stage 2 polygon merge parameter sweeps with "
            "extended visualization panels."
        )
    )
    parser.add_argument(
        "--config",
        type=pathlib.Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to base merge JSON configuration file.",
    )
    parser.add_argument(
        "--sweep-gdb",
        type=str,
        default=None,
        help="Custom file geodatabase name for all sweep trial layers.",
    )
    parser.add_argument(
        "--raw-gdb",
        type=pathlib.Path,
        default=DEFAULT_RAW_GDB,
        help="Path to raw input segmentation File Geodatabase.",
    )
    parser.add_argument(
        "--no-visualize",
        action="store_true",
        help="Disable automatic generation of comparison PNG and HTML.",
    )
    parser.add_argument(
        "--output-image",
        type=pathlib.Path,
        default=DEFAULT_PNG_PATH,
        help="Path to export multi-panel sweep PNG graphic.",
    )
    parser.add_argument(
        "--output-html",
        type=pathlib.Path,
        default=DEFAULT_HTML_PATH,
        help="Path to export interactive sweep HTML visualizer.",
    )
    parser.add_argument(
        "--output-summary",
        type=pathlib.Path,
        default=DEFAULT_SUMMARY_PATH,
        help="Path to export trial results summary JSON document.",
    )
    return parser.parse_args(argv)


def run_merge_sweep(
    base_config: MergeConfig,
    trials: typing.Sequence[SweepTrial] = DEFAULT_SWEEP_TRIALS,
    destination_gdb_name: str | None = None,
    visualize: bool = True,
    raw_source_gdb: pathlib.Path | None = None,
    output_image: pathlib.Path | None = None,
    output_html: pathlib.Path | None = None,
    output_summary_json: pathlib.Path | None = None,
) -> dict[str, typing.Any]:
    '''
    Execute an array of merge parameter trials over intersected polygons.

    Args:
        base_config:
            Base MergeConfig instance providing source paths and defaults.
        trials:
            Sequence of SweepTrial specifications to execute.
        destination_gdb_name:
            Optional geodatabase name to store all trial layers.
        visualize:
            Whether to render extended multi-panel PNG and interactive HTML.
        raw_source_gdb:
            Optional path to raw multi-scale segmentation dataset.
        output_image:
            Optional target path for exported PNG graphic.
        output_html:
            Optional target path for exported interactive HTML.
        output_summary_json:
            Optional target path for JSON summary statistics.

    Returns:
        dict[str, typing.Any]:
            Execution report containing trial statistics, GeoDataFrames,
            and generated artifact paths.
    '''
    if not trials:
        raise ValueError("Parameter sweep requires at least one SweepTrial.")

    resolved_gdb_name = (
        destination_gdb_name
        or f"isi_mu{base_config.mu}_postOBC_merge_sweep_"
        f"ver{base_config.gdb_version}.gdb"
    )

    LOGGER.info(
        "Starting merge sweep (%d trials) writing into %s",
        len(trials),
        resolved_gdb_name,
    )

    trial_records: list[dict[str, typing.Any]] = []
    visual_items: list[tuple[str, geopandas.GeoDataFrame, str]] = []
    gdfs_by_name: dict[str, geopandas.GeoDataFrame] = {}

    assert base_config.destination_folder
    destination_path = base_config.destination_folder / resolved_gdb_name

    for trial_idx, trial in enumerate(trials, start=1):
        layer_name = trial.output_layer_name or f"merged_trial_{trial.name}"
        LOGGER.info(
            "[%d/%d] Running trial %r -> layer %r",
            trial_idx,
            len(trials),
            trial.name,
            layer_name,
        )

        trial_config = dataclasses.replace(
            base_config,
            destination_gdb_name=resolved_gdb_name,
            output_layer_name=layer_name,
            threshold=trial.threshold,
            metrics=trial.metrics,
            per_metric_thresholds=trial.per_metric_thresholds,
            overwrite=True,
        )

        start_time = time.perf_counter()
        gdf = run_merge(trial_config)
        elapsed_sec = time.perf_counter() - start_time

        badge_desc = _format_trial_badge(trial)
        visual_items.append((trial.label, gdf, badge_desc))
        gdfs_by_name[trial.name] = gdf

        area_ha_total = float(gdf.geometry.area.sum() / 10_000.0)
        area_ha_mean = (
            float(gdf.geometry.area.mean() / 10_000.0)
            if not gdf.empty
            else 0.0
        )

        record = {
            "trial_name": trial.name,
            "label": trial.label,
            "description": trial.description,
            "layer_name": layer_name,
            "threshold": trial.threshold,
            "metrics": list(trial.metrics) if trial.metrics else "all",
            "per_metric_thresholds": trial.per_metric_thresholds,
            "polygon_count": len(gdf),
            "total_area_ha": round(area_ha_total, 3),
            "mean_stand_area_ha": round(area_ha_mean, 3),
            "elapsed_seconds": round(elapsed_sec, 2),
        }
        trial_records.append(record)
        LOGGER.info(
            "Trial %r finished in %.2fs: %d stands (mean %.2f ha)",
            trial.name,
            elapsed_sec,
            len(gdf),
            area_ha_mean,
        )

    # export summary JSON if path provided
    summary_path = output_summary_json or DEFAULT_SUMMARY_PATH
    try:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_path.open("w", encoding="utf-8") as stream:
            json.dump(
                {
                    "sweep_dataset": str(destination_path),
                    "total_trials": len(trials),
                    "trials": trial_records,
                },
                stream,
                indent=2,
            )
        LOGGER.info("Sweep summary saved to %s", summary_path)
    except OSError as err:
        LOGGER.warning(
            "Could not write summary JSON to %s: %s", summary_path, err
        )

    png_path = output_image or DEFAULT_PNG_PATH
    html_path = output_html or DEFAULT_HTML_PATH

    # extended multi-panel visualization
    if visualize:
        _render_sweep_visualizations(
            base_config=base_config,
            visual_items=visual_items,
            raw_source_gdb=raw_source_gdb,
            output_png=png_path,
            output_html=html_path,
        )

    return {
        "destination_dataset": destination_path,
        "trials": gdfs_by_name,
        "summary": trial_records,
        "output_image": png_path if visualize else None,
        "output_html": html_path if visualize else None,
        "summary_json": summary_path,
    }


def main(argv: typing.Sequence[str] | None = None) -> None:
    '''
    Load base configuration and execute polygon merge parameter sweep.

    Args:
        argv:
            Optional sequence of command-line argument strings.
    '''
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    base_config = load_config(args.config)

    run_merge_sweep(
        base_config=base_config,
        destination_gdb_name=args.sweep_gdb,
        visualize=not args.no_visualize,
        raw_source_gdb=args.raw_gdb,
        output_image=args.output_image,
        output_html=args.output_html,
        output_summary_json=args.output_summary,
    )


# ----- private helpers
def _format_trial_badge(trial: SweepTrial) -> str:
    '''Format metrics and tolerance legend banner text for subplot.'''
    if trial.per_metric_thresholds:
        threshold_parts = [
            f"{k.upper()}={v:.2f}"
            for k, v in trial.per_metric_thresholds.items()
        ]
        return " | ".join(threshold_parts)
    if trial.metrics:
        metrics_str = ", ".join(m.upper() for m in trial.metrics)
        return f"{metrics_str} | Tol: {trial.threshold:.2f}"
    return f"All Metrics (6) | Tol: {trial.threshold:.2f}"


def _render_sweep_visualizations(
    base_config: MergeConfig,
    visual_items: list[tuple[str, geopandas.GeoDataFrame, str]],
    raw_source_gdb: pathlib.Path | None,
    output_png: pathlib.Path,
    output_html: pathlib.Path,
) -> None:
    '''Load raw and intersection layers, then render PNG and HTML viewers.'''
    raw_gdb = raw_source_gdb or DEFAULT_RAW_GDB
    if not raw_gdb.exists():
        fallback_cand = base_config.source_folder / "segmentation_R1.gdb"
        if fallback_cand.exists():
            raw_gdb = fallback_cand

    if not raw_gdb.exists():
        LOGGER.warning(
            "Raw input GDB not found at %s; skipping visual export.",
            raw_gdb,
        )
        return

    LOGGER.info("Loading raw segmentation levels from %s...", raw_gdb)
    avail_raw = {name for name, _ in pyogrio.list_layers(raw_gdb)}
    raw_layers: dict[int, geopandas.GeoDataFrame] = {}
    for lvl in range(1, 5):
        matched = [
            n for n in avail_raw
            if n.endswith(f"_{lvl}") or n == f"level_{lvl}"
        ]
        layer_name = matched[0] if matched else f"segmented_objects_R1_{lvl}"
        raw_layers[lvl] = pyogrio.read_dataframe(raw_gdb, layer=layer_name)

    LOGGER.info(
        "Loading Stage 1 intersection layer from %s...",
        base_config.source_dataset,
    )
    intersect_layer = base_config.source_intersection_layer
    if intersect_layer is None:
        avail = [
            name for name, _ in pyogrio.list_layers(base_config.source_dataset)
        ]
        cands = [n for n in avail if n.startswith("intersected_")]
        if not cands:
            LOGGER.warning(
                "No intersected layer found; skipping visual export."
            )
            return
        intersect_layer = cands[0]

    intersected_gdf = pyogrio.read_dataframe(
        base_config.source_dataset,
        layer=intersect_layer,
    )

    LOGGER.info(
        "Rendering extended %d-panel comparison figure...",
        5 + len(visual_items),
    )
    plot_comparison_figure(
        raw_layers=raw_layers,
        intersected_gdf=intersected_gdf,
        merged_gdf=visual_items,
        output_png=output_png,
    )

    LOGGER.info("Rendering extended interactive HTML viewer...")
    generate_interactive_html(
        raw_layers=raw_layers,
        intersected_gdf=intersected_gdf,
        merged_gdf=visual_items,
        output_html=output_html,
    )


if __name__ == "__main__":
    main()
