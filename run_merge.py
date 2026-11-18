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
Run the Stage 2 polygon-merging workflow from a JSON configuration file.

Relative paths in the JSON document are resolved relative to the
JSON file, making execution independent of current working directory.

Public APIs:
    - `DEFAULT_CONFIG_PATH`: Default configuration file path.
    - `REQUIRED_FIELDS`: Set of required JSON configuration keys.
    - `OPTIONAL_FIELDS`: Set of optional JSON configuration keys.
    - `SUPPORTED_FIELDS`: Set of all supported configuration keys.
    - `parse_args`: Parse command-line arguments.
    - `load_config`: Load, validate, and convert JSON configuration.
    - `main`: Entry point for script execution.
'''

# standard imports
from __future__ import annotations
import argparse
import json
import logging
import pathlib
import typing
# local imports
from merge import MergeConfig
from merge import run_merge
from visual import render_workflow_visualizations

LOGGER = logging.getLogger("poly_segment_merge")

DEFAULT_CONFIG_PATH = pathlib.Path("merge_config.json")

REQUIRED_FIELDS = {
    "mu",
    "source_folder",
    "source_gdb_name",
}

OPTIONAL_FIELDS = {
    "destination_folder",
    "destination_gdb_name",
    "gdb_version",
    "layer_version",
    "metrics",
    "min_shared_length",
    "object_level_merge",
    "output_format",
    "output_html",
    "output_image",
    "output_layer_name",
    "overwrite",
    "per_metric_thresholds",
    "raw_gdb",
    "source_layer",
    "source_layer_name",
    "source_layer_prefix",
    "table_version",
    "threshold",
    "thresholds",
    "visualize",
}

SUPPORTED_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS


# ----- public functions
def parse_args(
    argv: typing.Sequence[str] | None = None,
) -> argparse.Namespace:
    '''
    Parse command-line arguments.

    Args:
        argv:
            Optional sequence of command-line argument strings.

    Returns:
        argparse.Namespace:
            Parsed command-line arguments.
    '''
    parser = argparse.ArgumentParser(
        description="Run Stage 2: polygon-merging workflow from JSON."
    )
    parser.add_argument(
        "config",
        nargs="?",
        type=pathlib.Path,
        default=DEFAULT_CONFIG_PATH,
        help="JSON configuration file for merging.",
    )
    parser.add_argument(
        "--config",
        dest="config_flag",
        type=pathlib.Path,
        default=None,
        help="Explicit flag for JSON configuration file.",
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
        help="Path to export comparison PNG graphic.",
    )
    parser.add_argument(
        "--output-html",
        type=pathlib.Path,
        default=None,
        help="Path to export interactive HTML visualizer.",
    )
    parser.add_argument(
        "--raw-gdb",
        type=pathlib.Path,
        default=None,
        help="Path to raw input segmentation File Geodatabase.",
    )
    return parser.parse_args(argv)


def load_config(config_path: pathlib.Path) -> MergeConfig:
    '''
    Load, validate, and convert a JSON merge workflow configuration.

    Args:
        config_path:
            Path to the JSON configuration file on disk.

    Returns:
        MergeConfig:
            Validated merge configuration dataclass instance.

    Raises:
        FileNotFoundError:
            If configuration file does not exist.
        ValueError:
            If JSON syntax is invalid or fields are missing/unsupported.
        TypeError:
            If JSON root is not an object or field types are invalid.
    '''
    config_path = config_path.resolve()

    if not config_path.is_file():
        raise FileNotFoundError(
            f"Configuration file does not exist: {config_path}"
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

    missing_fields = REQUIRED_FIELDS - raw_config.keys()
    if missing_fields:
        raise ValueError(
            "Configuration is missing required fields: "
            + ", ".join(sorted(missing_fields))
        )

    unexpected_fields = raw_config.keys() - SUPPORTED_FIELDS
    if unexpected_fields:
        raise ValueError(
            "Configuration contains unsupported fields: "
            + ", ".join(sorted(unexpected_fields))
        )

    config_directory = config_path.parent

    source_folder = _resolve_path(
        raw_config["source_folder"],
        config_directory,
        "source_folder",
    )

    if "destination_folder" in raw_config:
        destination_folder = _resolve_path(
            raw_config["destination_folder"],
            config_directory,
            "destination_folder",
        )
    else:
        destination_folder = source_folder

    source_layer = raw_config.get(
        "source_layer",
        raw_config.get("source_layer_name"),
    )
    if source_layer is not None:
        source_layer = _require_string(source_layer, "source_layer")

    source_layer_prefix = raw_config.get("source_layer_prefix")
    if source_layer_prefix is not None:
        source_layer_prefix = _require_string(
            source_layer_prefix, "source_layer_prefix"
        )

    layer_version = raw_config.get(
        "layer_version",
        raw_config.get("table_version", "dummy_001"),
    )
    gdb_version = raw_config.get(
        "gdb_version",
        raw_config.get("layer_version", "dummy_001"),
    )

    output_layer_name = raw_config.get("output_layer_name")
    if output_layer_name is not None:
        output_layer_name = _require_string(
            output_layer_name, "output_layer_name"
        )

    threshold = float(raw_config.get("threshold", 0.10))
    min_shared_length = float(raw_config.get("min_shared_length", 0.0))
    object_level_merge = int(raw_config.get("object_level_merge", 3))

    destination_gdb_name = raw_config.get("destination_gdb_name")
    if destination_gdb_name is not None:
        destination_gdb_name = _require_string(
            destination_gdb_name, "destination_gdb_name"
        )

    metrics_raw = raw_config.get("metrics")
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
                "Field 'metrics' must be a list of strings or "
                "comma-separated string."
            )

    thresholds_raw = raw_config.get(
        "per_metric_thresholds",
        raw_config.get("thresholds"),
    )
    per_metric_thresholds: dict[str, float] | None = None
    if thresholds_raw is not None:
        if isinstance(thresholds_raw, dict):
            per_metric_thresholds = {
                str(k): float(v) for k, v in thresholds_raw.items()
            }
        else:
            raise TypeError(
                "Field 'per_metric_thresholds' must be an object mapping "
                "metric names to float tolerances."
            )

    config = MergeConfig(
        mu=_require_int(raw_config["mu"], "mu"),
        source_folder=source_folder,
        source_gdb_name=_require_string(
            raw_config["source_gdb_name"],
            "source_gdb_name",
        ),
        source_layer=source_layer,
        source_layer_prefix=source_layer_prefix,
        object_level_merge=object_level_merge,
        destination_folder=destination_folder,
        gdb_version=_require_string(gdb_version, "gdb_version"),
        layer_version=_require_string(layer_version, "layer_version"),
        output_format=_require_string(
            raw_config.get("output_format", "filegdb"),
            "output_format",
        ),
        overwrite=_require_bool(
            raw_config.get("overwrite", False),
            "overwrite",
        ),
        threshold=threshold,
        output_layer_name=output_layer_name,
        min_shared_length=min_shared_length,
        destination_gdb_name=destination_gdb_name,
        metrics=metrics,
        per_metric_thresholds=per_metric_thresholds,
    )

    _validate_config(config)
    return config


def main(argv: typing.Sequence[str] | None = None) -> None:
    '''
    Load JSON configuration and execute polygon merging workflow.

    Args:
        argv:
            Optional sequence of command-line argument strings.
    '''
    args = parse_args(argv)
    config_path = args.config_flag or args.config
    config = load_config(config_path)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    LOGGER.info("Merge configuration loaded from %s.", config_path.resolve())
    LOGGER.info("Source dataset: %s.", config.source_dataset)
    if config.source_intersection_layer:
        LOGGER.info(
            "Pre-intersected layer to merge: %s.",
            config.source_intersection_layer,
        )
    else:
        LOGGER.info(
            "Selected source layer prefix: %s.",
            config.source_layer_prefix,
        )
    LOGGER.info("Destination dataset: %s.", config.destination_dataset)
    LOGGER.info("Threshold: %.4f.", config.threshold)

    merged_gdf = run_merge(config)

    # auto-visualize unless disabled
    resolved_path = config_path.resolve()
    with resolved_path.open(encoding="utf-8") as stream:
        raw_json = json.load(stream)

    visualize = bool(raw_json.get("visualize", True))
    if args.no_visualize:
        visualize = False

    if visualize:
        config_dir = resolved_path.parent
        raw_gdb = args.raw_gdb or _resolve_optional_path(
            raw_json.get("raw_gdb"), config_dir
        )
        out_png = args.output_image or _resolve_optional_path(
            raw_json.get("output_image"), config_dir
        )
        out_html = args.output_html or _resolve_optional_path(
            raw_json.get("output_html"), config_dir
        )
        render_workflow_visualizations(
            base_config=config,
            merged_input=merged_gdf,
            raw_source_gdb=raw_gdb,
            output_png=out_png,
            output_html=out_html,
        )


# ----- private helpers
def _resolve_optional_path(
    value: typing.Any,
    config_dir: pathlib.Path,
) -> pathlib.Path | None:
    '''Resolve an optional configuration path relative to config directory.'''
    if value is None:
        return None
    path_val = pathlib.Path(str(value))
    return path_val if path_val.is_absolute() else config_dir / path_val
def _resolve_path(
    value: object,
    base_directory: pathlib.Path,
    field_name: str,
) -> pathlib.Path:
    '''Resolve a configured path relative to the JSON file.'''
    path_value = pathlib.Path(_require_string(value, field_name))

    if not path_value.is_absolute():
        path_value = base_directory / path_value

    return path_value.resolve()


def _require_string(value: object, field_name: str) -> str:
    '''Return a non-empty configuration string.'''
    if not isinstance(value, str) or not value.strip():
        raise TypeError(
            f"Configuration field {field_name!r} must be a non-empty string."
        )
    return value


def _require_int(value: object, field_name: str) -> int:
    '''Return a configuration integer, rejecting booleans.'''
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(
            f"Configuration field {field_name!r} must be an integer."
        )
    return value


def _require_bool(value: object, field_name: str) -> bool:
    '''Return a configuration Boolean.'''
    if not isinstance(value, bool):
        raise TypeError(
            f"Configuration field {field_name!r} must be a Boolean."
        )
    return value


def _validate_config(config: MergeConfig) -> None:
    '''Validate constraints not enforced by the dataclass.'''
    if config.object_level_merge not in {1, 2, 3, 4}:
        raise ValueError(
            "Configuration field 'object_level_merge' must be one of "
            "1, 2, 3, or 4."
        )

    if config.output_format not in {"filegdb", "geopackage"}:
        raise ValueError(
            "Configuration field 'output_format' must be "
            "'filegdb' or 'geopackage'."
        )

    if config.mu < 0:
        raise ValueError("Configuration field 'mu' must be non-negative.")

    if config.threshold < 0:
        raise ValueError(
            "Configuration field 'threshold' must be non-negative."
        )


if __name__ == "__main__":
    main()
