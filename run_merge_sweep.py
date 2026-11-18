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
metrics and tolerance thresholds) loaded from a sweep configuration JSON
document, and produces extended multi-panel graphics and interactive
HTML viewers comparing all trials side-by-side.

Public APIs:
    - `SweepTrial`: Dataclass specifying single trial parameters.
    - `SweepConfig`: Dataclass specifying complete sweep configuration.
    - `DEFAULT_CONFIG_PATH`: Default configuration file path.
    - `DEFAULT_SWEEP_TRIALS`: Predefined array of demonstration trials.
    - `load_sweep_config`: Load and validate sweep JSON configuration.
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
from run_merge import load_config as load_base_merge_config
from visual import render_workflow_visualizations

LOGGER = logging.getLogger("poly_segment_sweep")

DEFAULT_CONFIG_PATH = pathlib.Path("merge_sweep_config.json")
DEFAULT_RAW_GDB = pathlib.Path("sandbox/input/segmentation_R1.gdb")
DEFAULT_PNG_PATH = pathlib.Path("sandbox/output/sweep_visualization.png")
DEFAULT_HTML_PATH = pathlib.Path("sandbox/output/sweep_visualization.html")
DEFAULT_SUMMARY_PATH = pathlib.Path("sandbox/output/sweep_summary.json")

SWEEP_SPECIAL_FIELDS = {
    "base_config",
    "output_html",
    "output_image",
    "output_summary",
    "raw_gdb",
    "trials",
    "visualize",
}


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


@dataclasses.dataclass(frozen=True)
class SweepConfig:
    '''Configuration container for merge parameter sweep execution.'''
    base_config: MergeConfig
    trials: tuple[SweepTrial, ...]
    destination_gdb_name: str | None = None
    visualize: bool = True
    raw_source_gdb: pathlib.Path | None = None
    output_image: pathlib.Path | None = None
    output_html: pathlib.Path | None = None
    output_summary_json: pathlib.Path | None = None


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
        "config",
        nargs="?",
        type=pathlib.Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to merge sweep JSON configuration file.",
    )
    parser.add_argument(
        "--config",
        dest="config_flag",
        type=pathlib.Path,
        default=None,
        help="Explicit flag for merge sweep JSON configuration file.",
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
        default=None,
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
        default=None,
        help="Path to export multi-panel sweep PNG graphic.",
    )
    parser.add_argument(
        "--output-html",
        type=pathlib.Path,
        default=None,
        help="Path to export interactive sweep HTML visualizer.",
    )
    parser.add_argument(
        "--output-summary",
        type=pathlib.Path,
        default=None,
        help="Path to export trial results summary JSON document.",
    )
    return parser.parse_args(argv)


def load_sweep_config(config_path: pathlib.Path) -> SweepConfig:
    '''
    Load, validate, and convert a JSON merge sweep configuration.

    Args:
        config_path:
            Path to the JSON configuration file on disk.

    Returns:
        SweepConfig:
            Validated sweep configuration instance containing base config,
            trials, and visual settings.

    Raises:
        FileNotFoundError:
            If configuration file does not exist.
        ValueError:
            If JSON syntax is invalid or fields are malformed.
        TypeError:
            If JSON root or trial items are not objects.
    '''
    config_path = config_path.resolve()
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Sweep configuration file does not exist: {config_path}"
        )

    try:
        with config_path.open(encoding="utf-8") as stream:
            raw_config = json.load(stream)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Invalid JSON in {config_path}: "
            f"line {error.lineno}, column {error.colno}: {error.msg}"
        ) from error

    if not isinstance(raw_config, dict):
        raise TypeError(
            f"Configuration root must be a JSON object: {config_path}"
        )

    config_dir = config_path.parent

    # 1. resolve base MergeConfig
    base_config: MergeConfig
    if "base_config" in raw_config:
        base_ref = pathlib.Path(str(raw_config["base_config"]))
        base_path = (
            base_ref if base_ref.is_absolute() else config_dir / base_ref
        )
        base_config = load_base_merge_config(base_path)
    else:
        base_config = _parse_inline_merge_config(raw_config, config_dir)

    # 2. resolve destination sweep geodatabase name
    destination_gdb_name = raw_config.get(
        "destination_gdb_name",
        base_config.destination_gdb_name,
    )
    if destination_gdb_name is not None:
        destination_gdb_name = str(destination_gdb_name)

    # 3. parse trials array
    trials: tuple[SweepTrial, ...]
    if "trials" in raw_config and raw_config["trials"] is not None:
        trials = _parse_trials(raw_config["trials"])
    else:
        trials = DEFAULT_SWEEP_TRIALS

    # 4. resolve visualization settings
    visualize = bool(raw_config.get("visualize", True))
    raw_source_gdb = _resolve_optional_path(
        raw_config.get("raw_gdb"), config_dir
    )
    output_image = _resolve_optional_path(
        raw_config.get("output_image"), config_dir
    )
    output_html = _resolve_optional_path(
        raw_config.get("output_html"), config_dir
    )
    output_summary = _resolve_optional_path(
        raw_config.get("output_summary"), config_dir
    )

    return SweepConfig(
        base_config=base_config,
        trials=trials,
        destination_gdb_name=destination_gdb_name,
        visualize=visualize,
        raw_source_gdb=raw_source_gdb,
        output_image=output_image,
        output_html=output_html,
        output_summary_json=output_summary,
    )


def run_merge_sweep(
    base_config: MergeConfig | SweepConfig,
    trials: typing.Sequence[SweepTrial] | None = None,
    destination_gdb_name: str | None = None,
    visualize: bool | None = None,
    raw_source_gdb: pathlib.Path | None = None,
    output_image: pathlib.Path | None = None,
    output_html: pathlib.Path | None = None,
    output_summary_json: pathlib.Path | None = None,
) -> dict[str, typing.Any]:
    '''
    Execute an array of merge parameter trials over intersected polygons.

    Args:
        base_config:
            MergeConfig or SweepConfig providing base paths and defaults.
        trials:
            Optional sequence of SweepTrial specifications to execute.
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
    resolved_base: MergeConfig
    resolved_trials: tuple[SweepTrial, ...]
    resolved_gdb_name: str | None
    resolved_vis: bool
    resolved_raw: pathlib.Path | None
    resolved_img: pathlib.Path | None
    resolved_htm: pathlib.Path | None
    resolved_sum: pathlib.Path | None

    if isinstance(base_config, SweepConfig):
        resolved_base = base_config.base_config
        resolved_trials = (
            tuple(trials) if trials is not None else base_config.trials
        )
        resolved_gdb_name = (
            destination_gdb_name or base_config.destination_gdb_name
        )
        resolved_vis = (
            visualize if visualize is not None else base_config.visualize
        )
        resolved_raw = raw_source_gdb or base_config.raw_source_gdb
        resolved_img = output_image or base_config.output_image
        resolved_htm = output_html or base_config.output_html
        resolved_sum = (
            output_summary_json or base_config.output_summary_json
        )
    else:
        resolved_base = base_config
        resolved_trials = (
            tuple(trials) if trials is not None else DEFAULT_SWEEP_TRIALS
        )
        resolved_gdb_name = destination_gdb_name
        resolved_vis = True if visualize is None else visualize
        resolved_raw = raw_source_gdb
        resolved_img = output_image
        resolved_htm = output_html
        resolved_sum = output_summary_json

    if not resolved_trials:
        raise ValueError("Parameter sweep requires at least one SweepTrial.")

    gdb_stem = (
        resolved_gdb_name
        or f"isi_mu{resolved_base.mu}_postOBC_merge_sweep_"
        f"ver{resolved_base.gdb_version}.gdb"
    )

    LOGGER.info(
        "Starting merge sweep (%d trials) writing into %s",
        len(resolved_trials),
        gdb_stem,
    )

    trial_records: list[dict[str, typing.Any]] = []
    visual_items: list[tuple[str, geopandas.GeoDataFrame, str]] = []
    gdfs_by_name: dict[str, geopandas.GeoDataFrame] = {}

    assert resolved_base.destination_folder
    destination_path = resolved_base.destination_folder / gdb_stem

    for trial_idx, trial in enumerate(resolved_trials, start=1):
        layer_name = trial.output_layer_name or f"merged_trial_{trial.name}"
        LOGGER.info(
            "[%d/%d] Running trial %r -> layer %r",
            trial_idx,
            len(resolved_trials),
            trial.name,
            layer_name,
        )

        trial_config = dataclasses.replace(
            resolved_base,
            destination_gdb_name=gdb_stem,
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

    # export summary JSON if path resolved or default
    summary_path = resolved_sum or DEFAULT_SUMMARY_PATH
    try:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_path.open("w", encoding="utf-8") as stream:
            json.dump(
                {
                    "sweep_dataset": str(destination_path),
                    "total_trials": len(resolved_trials),
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

    png_path = resolved_img or DEFAULT_PNG_PATH
    html_path = resolved_htm or DEFAULT_HTML_PATH

    # extended multi-panel visualization
    if resolved_vis:
        render_workflow_visualizations(
            base_config=resolved_base,
            merged_input=visual_items,
            raw_source_gdb=resolved_raw,
            output_png=png_path,
            output_html=html_path,
        )

    return {
        "destination_dataset": destination_path,
        "trials": gdfs_by_name,
        "summary": trial_records,
        "output_image": png_path if resolved_vis else None,
        "output_html": html_path if resolved_vis else None,
        "summary_json": summary_path,
    }


def main(argv: typing.Sequence[str] | None = None) -> None:
    '''
    Load sweep configuration and execute polygon merge parameter sweep.

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

    config_path = args.config_flag or args.config
    sweep_config = load_sweep_config(config_path)

    # CLI flags override sweep config file if provided
    visualize_override = False if args.no_visualize else None

    run_merge_sweep(
        base_config=sweep_config,
        destination_gdb_name=args.sweep_gdb,
        visualize=visualize_override,
        raw_source_gdb=args.raw_gdb,
        output_image=args.output_image,
        output_html=args.output_html,
        output_summary_json=args.output_summary,
    )


# ----- private helpers
def _parse_trials(raw_trials: typing.Any) -> tuple[SweepTrial, ...]:
    '''Parse sequence of trial specification dictionaries.'''
    if not isinstance(raw_trials, (list, tuple)):
        raise TypeError("Configuration field 'trials' must be a list.")

    parsed: list[SweepTrial] = []
    for idx, item in enumerate(raw_trials, start=1):
        if not isinstance(item, dict):
            raise TypeError(f"Trial item #{idx} must be a JSON object.")
        if "name" not in item:
            raise ValueError(f"Trial item #{idx} is missing 'name' field.")

        name = str(item["name"])
        label = str(item.get("label", f"Trial: {name}"))
        desc = str(item.get("description", ""))
        threshold = float(item.get("threshold", 0.10))

        metrics_raw = item.get("metrics")
        metrics: tuple[str, ...] | None = None
        if metrics_raw is not None:
            if isinstance(metrics_raw, str):
                metrics = tuple(
                    m.strip() for m in metrics_raw.split(",") if m.strip()
                )
            elif isinstance(metrics_raw, (list, tuple)):
                metrics = tuple(str(m).strip() for m in metrics_raw)
            else:
                raise TypeError(
                    f"Trial {name!r} 'metrics' must be list or string."
                )

        per_metric_raw = item.get("per_metric_thresholds")
        per_metric: dict[str, float] | None = None
        if per_metric_raw is not None:
            if isinstance(per_metric_raw, dict):
                per_metric = {
                    str(k): float(v) for k, v in per_metric_raw.items()
                }
            else:
                raise TypeError(
                    f"Trial {name!r} 'per_metric_thresholds' must be an object."
                )

        out_layer = item.get("output_layer_name")
        parsed.append(
            SweepTrial(
                name=name,
                label=label,
                description=desc,
                threshold=threshold,
                metrics=metrics,
                per_metric_thresholds=per_metric,
                output_layer_name=str(out_layer) if out_layer else None,
            )
        )
    return tuple(parsed)


def _parse_inline_merge_config(
    raw_config: dict[str, typing.Any],
    config_dir: pathlib.Path,
) -> MergeConfig:
    '''Extract base MergeConfig fields from root configuration document.'''
    base_fields = {
        k: v for k, v in raw_config.items() if k not in SWEEP_SPECIAL_FIELDS
    }
    temp_json = config_dir / f"._tmp_merge_cfg_{time.time_ns()}.json"
    try:
        with temp_json.open("w", encoding="utf-8") as stream:
            json.dump(base_fields, stream)
        return load_base_merge_config(temp_json)
    finally:
        if temp_json.exists():
            temp_json.unlink(missing_ok=True)


def _resolve_optional_path(
    value: typing.Any,
    config_dir: pathlib.Path,
) -> pathlib.Path | None:
    '''Resolve an optional configuration path relative to config directory.'''
    if value is None:
        return None
    path_val = pathlib.Path(str(value))
    return path_val if path_val.is_absolute() else config_dir / path_val


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


if __name__ == "__main__":
    main()
