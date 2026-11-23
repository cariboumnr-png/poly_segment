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
Validation rules for centralized polygon segmentation configurations.

Enforces parameter boundaries, allowable drivers, and stage decoupling
contracts across common, intersect, merge, and visual settings.

Public APIs:
    - `SUPPORTED_FORMATS`: Supported spatial output drivers.
    - `SUPPORTED_STAGES`: Supported workflow pipeline stages.
    - `validate_common`: Validate shared global settings.
    - `validate_intersect`: Validate Stage 1 geometric settings.
    - `validate_merge`: Validate Stage 2 merge settings.
    - `validate_visual`: Validate visualization settings.
    - `validate_stage_config`: Decoupled validator for active stage.
'''

# local imports
import postobc.configs.schemas as schemas

SUPPORTED_FORMATS: frozenset[str] = frozenset({"filegdb", "geopackage"})
SUPPORTED_STAGES: frozenset[str] = frozenset({"intersect", "merge", "e2e"})


# ----- public functions
def validate_common(config: schemas.CommonConfig) -> None:
    '''
    Validate shared global execution parameters.

    Args:
        config:
            Common execution configuration instance.

    Raises:
        ValueError:
            If mu is negative or output_format is unsupported.
    '''
    if config.mu < 0:
        raise ValueError("Configuration 'mu' must be non-negative.")

    if config.output_format not in SUPPORTED_FORMATS:
        allowed = ", ".join(sorted(SUPPORTED_FORMATS))
        raise ValueError(
            f"Unsupported output_format {config.output_format!r}; "
            f"must be one of: {allowed}."
        )


def validate_intersect(config: schemas.IntersectConfig) -> None:
    '''
    Validate Stage 1 geometric intersection parameters.

    Args:
        config:
            Stage 1 configuration instance.

    Raises:
        ValueError:
            If levels or version identifiers are invalid.
    '''
    if config.object_level_merge not in {1, 2, 3, 4}:
        raise ValueError(
            "Configuration 'object_level_merge' must be in {1, 2, 3, 4}."
        )

    _validate_non_empty_str(config.source_gdb_name, "source_gdb_name")
    _validate_non_empty_str(
        config.source_layer_prefix, "source_layer_prefix"
    )
    _validate_non_empty_str(config.gdb_version, "gdb_version")
    _validate_non_empty_str(config.table_version, "table_version")


def validate_merge(config: schemas.MergeConfig) -> None:
    '''
    Validate Stage 2 polygon merging parameters.

    Args:
        config:
            Stage 2 configuration instance.

    Raises:
        ValueError:
            If tolerances or boundary thresholds are negative.
    '''
    if config.threshold < 0.0:
        raise ValueError("Configuration 'threshold' must be non-negative.")

    if config.min_shared_length < 0.0:
        raise ValueError(
            "Configuration 'min_shared_length' must be non-negative."
        )

    if config.per_metric_thresholds:
        for metric, tol in config.per_metric_thresholds.items():
            if tol < 0.0:
                raise ValueError(
                    f"Threshold for metric {metric!r} must be non-negative."
                )

    _validate_non_empty_str(config.gdb_version, "gdb_version")
    _validate_non_empty_str(config.layer_version, "layer_version")


def validate_visual(config: schemas.VisualConfig) -> None:
    '''
    Validate visualization configuration options.

    Args:
        config:
            Visual configuration instance.
    '''
    # visual options are optional flags; no negative numeric bounds
    del config


def validate_stage_config(
    config: schemas.RootConfig,
    stage: str = "e2e",
) -> None:
    '''
    Validate relevant configuration fields for the target stage.

    Decoupled validation: only sections required for the target stage
    are enforced.

    Args:
        config:
            Root configuration instance to validate.
        stage:
            Execution stage identifier ('intersect', 'merge', or 'e2e').

    Raises:
        ValueError:
            If stage is unsupported or required stage block is missing.
    '''
    if stage not in SUPPORTED_STAGES:
        allowed = ", ".join(sorted(SUPPORTED_STAGES))
        raise ValueError(
            f"Unsupported stage {stage!r}; must be one of: {allowed}."
        )

    validate_common(config.common)

    if stage == "intersect":
        _validate_intersect_stage(config)
    elif stage == "merge":
        _validate_merge_stage(config)
    elif stage == "e2e":
        _validate_e2e_stage(config)


# ----- private helpers
def _validate_non_empty_str(value: str, name: str) -> None:
    '''Validate string identifier is not empty or whitespace.'''
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Configuration field {name!r} must not be empty.")


def _validate_intersect_stage(config: schemas.RootConfig) -> None:
    '''Validate stage 1 requirements.'''
    if config.intersect is None:
        raise ValueError("Stage 'intersect' requires 'intersect' section.")
    validate_intersect(config.intersect)


def _validate_merge_stage(config: schemas.RootConfig) -> None:
    '''Validate stage 2 requirements.'''
    if config.merge is None:
        raise ValueError("Stage 'merge' requires 'merge' section.")
    validate_merge(config.merge)
    if config.visual and config.visual.visualize:
        validate_visual(config.visual)


def _validate_e2e_stage(config: schemas.RootConfig) -> None:
    '''Validate end-to-end pipeline requirements.'''
    _validate_intersect_stage(config)
    _validate_merge_stage(config)
