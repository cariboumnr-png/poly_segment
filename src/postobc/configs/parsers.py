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
Parser and loader for JSON polygon segmentation configurations.

Translates nested JSON dictionaries into strongly-typed dataclasses,
resolving relative paths against the configuration file location and
enforcing stage-scoped validation.

Public APIs:
    - `parse_dict`: Parse in-memory dictionary into RootConfig.
    - `load_config`: Load, parse, and validate JSON file on disk.
'''

# standard imports
import json
import pathlib
import typing
# local imports
import postobc.configs.schemas as schemas
import postobc.configs.validators as validators


# ----- public functions
def parse_dict(
    raw: dict[str, typing.Any],
    base_dir: pathlib.Path,
    stage: str = "e2e",
) -> schemas.RootConfig:
    '''
    Parse in-memory configuration dictionary into RootConfig.

    Args:
        raw:
            Raw dictionary loaded from configuration JSON document.
        base_dir:
            Base directory for resolving relative path values.
        stage:
            Target execution stage ('intersect', 'merge', or 'e2e').

    Returns:
        RootConfig:
            Parsed and validated root configuration container.
    '''
    if not isinstance(raw, dict):
        raise TypeError("Configuration root must be a JSON object.")

    common = _parse_common(raw.get("common", {}))

    intersect_block = raw.get("intersect")
    intersect = (
        _parse_intersect(intersect_block, base_dir)
        if intersect_block is not None
        else None
    )

    merge_block = raw.get("merge")
    merge = (
        _parse_merge(merge_block, base_dir)
        if merge_block is not None
        else None
    )

    visual_block = raw.get("visual")
    visual = (
        _parse_visual(visual_block, base_dir)
        if visual_block is not None
        else None
    )

    config = schemas.RootConfig(
        common=common,
        intersect=intersect,
        merge=merge,
        visual=visual,
    )

    validators.validate_stage_config(config, stage=stage)
    return config


def load_config(
    config_path: pathlib.Path,
    stage: str = "e2e",
) -> schemas.RootConfig:
    '''
    Load, parse, and validate a JSON configuration file from disk.

    Args:
        config_path:
            Target JSON configuration file path.
        stage:
            Execution stage identifier ('intersect', 'merge', or 'e2e').

    Returns:
        RootConfig:
            Validated configuration instance.

    Raises:
        FileNotFoundError:
            If target configuration file does not exist.
        ValueError:
            If JSON syntax is invalid or fields fail validation.
    '''
    resolved_path = config_path.resolve()
    if not resolved_path.is_file():
        raise FileNotFoundError(
            f"Configuration file not found: {resolved_path}"
        )

    try:
        with resolved_path.open(encoding="utf-8") as stream:
            raw_dict = json.load(stream)
    except json.JSONDecodeError as err:
        raise ValueError(
            f"Invalid JSON in {resolved_path}: line {err.lineno}: {err.msg}"
        ) from err

    return parse_dict(raw_dict, resolved_path.parent, stage=stage)


# ----- private helpers
def _parse_common(raw: dict[str, typing.Any]) -> schemas.CommonConfig:
    '''Parse common global execution settings.'''
    mu = _require_int(raw.get("mu", 780), "common.mu")
    output_format = _require_str(
        raw.get("output_format", "filegdb"), "common.output_format"
    )
    overwrite = _require_bool(
        raw.get("overwrite", True), "common.overwrite"
    )
    verbose = _require_bool(
        raw.get("verbose", False), "common.verbose"
    )
    return schemas.CommonConfig(
        mu=mu,
        output_format=output_format,
        overwrite=overwrite,
        verbose=verbose,
    )


def _parse_intersect(
    raw: dict[str, typing.Any],
    base_dir: pathlib.Path,
) -> schemas.IntersectConfig:
    '''Parse Stage 1 geometric intersection settings.'''
    source_folder = _resolve_path(
        raw.get("source_folder", "sandbox/input"),
        base_dir,
        "intersect.source_folder",
    )
    destination_folder = _resolve_opt_path(
        raw.get("destination_folder"),
        base_dir,
        "intersect.destination_folder",
    )
    return schemas.IntersectConfig(
        source_folder=source_folder,
        source_gdb_name=_require_str(
            raw.get("source_gdb_name", "segmentation_R1"),
            "intersect.source_gdb_name",
        ),
        source_layer_prefix=_require_str(
            raw.get("source_layer_prefix", "segmented_objects_R1"),
            "intersect.source_layer_prefix",
        ),
        object_level_merge=_require_int(
            raw.get("object_level_merge", 3),
            "intersect.object_level_merge",
        ),
        destination_folder=destination_folder,
        gdb_version=_require_str(
            raw.get("gdb_version", "dummy_001"),
            "intersect.gdb_version",
        ),
        table_version=_require_str(
            raw.get("table_version", "dummy_001"),
            "intersect.table_version",
        ),
        destination_gdb_name=raw.get("destination_gdb_name"),
    )


def _parse_merge(
    raw: dict[str, typing.Any],
    base_dir: pathlib.Path,
) -> schemas.MergeConfig:
    '''Parse Stage 2 polygon merge settings.'''
    source_folder = _resolve_opt_path(
        raw.get("source_folder"), base_dir, "merge.source_folder"
    )
    destination_folder = _resolve_opt_path(
        raw.get("destination_folder"), base_dir, "merge.destination_folder"
    )
    metrics = _parse_metrics(raw.get("metrics"))
    per_metric_thresholds = _parse_per_metric_thresholds(
        raw.get("per_metric_thresholds")
    )
    return schemas.MergeConfig(
        threshold=_require_float(
            raw.get("threshold", 0.10), "merge.threshold"
        ),
        metrics=metrics,
        per_metric_thresholds=per_metric_thresholds,
        min_shared_length=_require_float(
            raw.get("min_shared_length", 0.0), "merge.min_shared_length"
        ),
        source_folder=source_folder,
        source_gdb_name=raw.get("source_gdb_name"),
        source_layer=raw.get("source_layer"),
        destination_folder=destination_folder,
        gdb_version=_require_str(
            raw.get("gdb_version", "dummy_001"), "merge.gdb_version"
        ),
        layer_version=_require_str(
            raw.get("layer_version", "dummy_001"), "merge.layer_version"
        ),
        output_layer_name=raw.get("output_layer_name"),
        destination_gdb_name=raw.get("destination_gdb_name"),
    )


def _parse_visual(
    raw: dict[str, typing.Any],
    base_dir: pathlib.Path,
) -> schemas.VisualConfig:
    '''Parse visualization and HTML export settings.'''
    visualize = _require_bool(
        raw.get("visualize", True), "visual.visualize"
    )
    raw_gdb = _resolve_opt_path(
        raw.get("raw_gdb"), base_dir, "visual.raw_gdb"
    )
    output_image = _resolve_opt_path(
        raw.get("output_image"), base_dir, "visual.output_image"
    )
    output_html = _resolve_opt_path(
        raw.get("output_html"), base_dir, "visual.output_html"
    )
    return schemas.VisualConfig(
        visualize=visualize,
        raw_gdb=raw_gdb,
        output_image=output_image,
        output_html=output_html,
    )


def _parse_metrics(value: object) -> tuple[str, ...] | None:
    '''Parse metric collection to immutable tuple of strings.'''
    if value is None:
        return None
    if isinstance(value, str):
        return tuple(m.strip() for m in value.split(",") if m.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(m).strip() for m in value)
    raise TypeError("Field 'metrics' must be list of strings or string.")


def _parse_per_metric_thresholds(
    value: object,
) -> dict[str, float] | None:
    '''Parse metric tolerance dictionary.'''
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): float(v) for k, v in value.items()}
    raise TypeError("Field 'per_metric_thresholds' must be an object.")


def _require_str(val: object, name: str) -> str:
    '''Validate value is a non-empty string.'''
    if not isinstance(val, str) or not val.strip():
        raise TypeError(f"Field {name!r} must be a non-empty string.")
    return val.strip()


def _require_int(val: object, name: str) -> int:
    '''Validate value is an integer, rejecting Booleans.'''
    if isinstance(val, bool) or not isinstance(val, int):
        raise TypeError(f"Field {name!r} must be an integer.")
    return val


def _require_float(val: object, name: str) -> float:
    '''Validate value is a float or integer, rejecting Booleans.'''
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise TypeError(f"Field {name!r} must be a number.")
    return float(val)


def _require_bool(val: object, name: str) -> bool:
    '''Validate value is a Boolean.'''
    if not isinstance(val, bool):
        raise TypeError(f"Field {name!r} must be a Boolean.")
    return val


def _resolve_path(
    val: object,
    base_dir: pathlib.Path,
    name: str,
) -> pathlib.Path:
    '''Resolve relative path against base directory.'''
    str_val = _require_str(val, name)
    path_val = pathlib.Path(str_val)
    if not path_val.is_absolute():
        path_val = base_dir / path_val
    return path_val.resolve()


def _resolve_opt_path(
    val: object,
    base_dir: pathlib.Path,
    name: str,
) -> pathlib.Path | None:
    '''Resolve optional relative path against base directory.'''
    if val is None:
        return None
    return _resolve_path(val, base_dir, name)
