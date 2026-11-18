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

"""Run the Stage 2 polygon-merging workflow from a JSON configuration file.

Relative paths in the JSON document are resolved relative to the JSON file,
making execution independent of the current working directory.

Run from the project root:

    python run_merge.py

Use another configuration file:

    python run_merge.py path/to/merge_config.json
"""

from __future__ import annotations

# standard imports
import argparse
import json
import logging
import pathlib
import typing

# local imports
from merge import MergeConfig
from merge import run_merge


LOGGER = logging.getLogger("poly_segment_merge")

DEFAULT_CONFIG_PATH = pathlib.Path("merge_config.json")

REQUIRED_FIELDS = {
    "mu",
    "source_folder",
    "source_gdb_name",
}

OPTIONAL_FIELDS = {
    "source_layer",
    "source_layer_name",
    "source_layer_prefix",
    "object_level_merge",
    "destination_folder",
    "gdb_version",
    "layer_version",
    "table_version",
    "output_layer_name",
    "output_format",
    "overwrite",
    "threshold",
    "min_shared_length",
}

SUPPORTED_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS


def parse_args(
    argv: typing.Sequence[str] | None = None,
) -> argparse.Namespace:
    """Parse command-line arguments."""
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
    return parser.parse_args(argv)


def load_config(config_path: pathlib.Path) -> MergeConfig:
    """Load, validate, and convert a JSON merge workflow configuration."""
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
        source_layer_prefix = _require_string(source_layer_prefix, "source_layer_prefix")

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
        output_layer_name = _require_string(output_layer_name, "output_layer_name")

    threshold = float(raw_config.get("threshold", 0.10))
    min_shared_length = float(raw_config.get("min_shared_length", 0.0))
    object_level_merge = int(raw_config.get("object_level_merge", 3))

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
    )

    _validate_config(config)
    return config


def _resolve_path(
    value: object,
    base_directory: pathlib.Path,
    field_name: str,
) -> pathlib.Path:
    """Resolve a configured path relative to the JSON file."""
    path_value = pathlib.Path(_require_string(value, field_name))

    if not path_value.is_absolute():
        path_value = base_directory / path_value

    return path_value.resolve()


def _require_string(value: object, field_name: str) -> str:
    """Return a non-empty configuration string."""
    if not isinstance(value, str) or not value.strip():
        raise TypeError(
            f"Configuration field {field_name!r} must be a non-empty string."
        )
    return value


def _require_int(value: object, field_name: str) -> int:
    """Return a configuration integer, rejecting booleans."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(
            f"Configuration field {field_name!r} must be an integer."
        )
    return value


def _require_bool(value: object, field_name: str) -> bool:
    """Return a configuration Boolean."""
    if not isinstance(value, bool):
        raise TypeError(
            f"Configuration field {field_name!r} must be a Boolean."
        )
    return value


def _validate_config(config: MergeConfig) -> None:
    """Validate constraints not enforced by the dataclass."""
    if config.object_level_merge not in {1, 2, 3, 4}:
        raise ValueError(
            "Configuration field 'object_level_merge' must be one of 1, 2, 3, or 4."
        )

    if config.output_format not in {"filegdb", "geopackage"}:
        raise ValueError(
            "Configuration field 'output_format' must be 'filegdb' or 'geopackage'."
        )

    if config.mu < 0:
        raise ValueError("Configuration field 'mu' must be non-negative.")

    if config.threshold < 0:
        raise ValueError("Configuration field 'threshold' must be non-negative.")


def main(argv: typing.Sequence[str] | None = None) -> None:
    """Load the JSON configuration and execute the polygon merging workflow."""
    args = parse_args(argv)
    config = load_config(args.config)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    LOGGER.info("Merge configuration loaded from %s.", args.config.resolve())
    LOGGER.info("Source dataset: %s.", config.source_dataset)
    if config.source_intersection_layer:
        LOGGER.info("Pre-intersected layer to merge: %s.", config.source_intersection_layer)
    else:
        LOGGER.info("Selected source layer prefix: %s.", config.source_layer_prefix)
    LOGGER.info("Destination dataset: %s.", config.destination_dataset)
    LOGGER.info("Threshold: %.4f.", config.threshold)

    run_merge(config)


if __name__ == "__main__":
    main()
