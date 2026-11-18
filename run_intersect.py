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
Run the polygon-neighbour workflow from a JSON configuration file.

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
from intersect import WorkflowConfig
from intersect import run_workflow

LOGGER = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = pathlib.Path("intersect_config.json")

REQUIRED_FIELDS = {
    "mu",
    "source_folder",
    "source_gdb_name",
    "source_layer_prefix",
    "object_level_merge",
    "destination_folder",
    "gdb_version",
    "table_version",
}

OPTIONAL_FIELDS = {
    "output_format",
    "overwrite",
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
        description="Run the polygon-neighbour workflow from JSON."
    )
    parser.add_argument(
        "config",
        nargs="?",
        type=pathlib.Path,
        default=DEFAULT_CONFIG_PATH,
        help="JSON configuration file.",
    )
    return parser.parse_args(argv)


def load_config(config_path: pathlib.Path) -> WorkflowConfig:
    '''
    Load, validate, and convert a JSON workflow configuration.

    Args:
        config_path:
            Path to the JSON configuration file on disk.

    Returns:
        WorkflowConfig:
            Validated configuration dataclass instance.

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
    destination_folder = _resolve_path(
        raw_config["destination_folder"],
        config_directory,
        "destination_folder",
    )

    config = WorkflowConfig(
        mu=_require_int(raw_config["mu"], "mu"),
        source_folder=source_folder,
        source_gdb_name=_require_string(
            raw_config["source_gdb_name"],
            "source_gdb_name",
        ),
        source_layer_prefix=_require_string(
            raw_config["source_layer_prefix"],
            "source_layer_prefix",
        ),
        object_level_merge=_require_int(
            raw_config["object_level_merge"],
            "object_level_merge",
        ),
        destination_folder=destination_folder,
        gdb_version=_require_string(
            raw_config["gdb_version"],
            "gdb_version",
        ),
        table_version=_require_string(
            raw_config["table_version"],
            "table_version",
        ),
        output_format=_require_string(
            raw_config.get("output_format", "filegdb"),
            "output_format",
        ),
        overwrite=_require_bool(
            raw_config.get("overwrite", False),
            "overwrite",
        ),
    )

    _validate_config(config)
    return config


def main(argv: typing.Sequence[str] | None = None) -> None:
    '''
    Load the JSON configuration and execute the public workflow API.

    Args:
        argv:
            Optional sequence of command-line argument strings.
    '''
    args = parse_args(argv)
    config = load_config(args.config)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    LOGGER.info("Configuration loaded from %s.", args.config.resolve())
    LOGGER.info("Source dataset: %s.", config.source_dataset)
    LOGGER.info("Selected source layer: %s.", config.selected_source_layer)
    LOGGER.info("Destination dataset: %s.", config.destination_dataset)

    run_workflow(config)


# ----- private helpers
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
            f"Configuration field {field_name!r} must be a "
            "non-empty string."
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


def _validate_config(config: WorkflowConfig) -> None:
    '''Validate constraints not enforced by the dataclass.'''
    if config.object_level_merge not in {1, 2, 3, 4}:
        raise ValueError(
            "Configuration field 'object_level_merge' must be "
            "one of 1, 2, 3, or 4."
        )

    if config.output_format not in {"filegdb", "geopackage"}:
        raise ValueError(
            "Configuration field 'output_format' must be "
            "'filegdb' or 'geopackage'."
        )

    if config.mu < 0:
        raise ValueError(
            "Configuration field 'mu' must be non-negative."
        )


if __name__ == "__main__":
    main()
