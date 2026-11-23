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
Unit tests for centralized configuration parsing and validation.

Validates stage-scoped decoupled validation, parameter boundaries, and
conversion adapters for Stage 1 and Stage 2 workflows.
'''

# standard imports
import contextlib
import json
import pathlib
import typing
# third-party imports
try:
    import pytest
except ImportError:
    pytest = None
# local imports
import postobc.configs as configs


# ----- test cases
def test_parse_dict_e2e_valid(tmp_path: pathlib.Path) -> None:
    '''
    Validate successful parsing and stage adapters for e2e workflow.

    Given:
        A complete dictionary containing common, intersect, and merge.
    When:
        The dictionary is parsed under 'e2e' stage mode.
    Then:
        All stage dataclasses resolve and conversion adapters succeed.
    '''
    raw = {
        "common": {
            "mu": 780,
            "output_format": "filegdb",
            "overwrite": True,
        },
        "intersect": {
            "source_folder": "input",
            "source_gdb_name": "segmentation_R1",
            "source_layer_prefix": "segmented_objects_R1",
            "object_level_merge": 3,
            "destination_folder": "output",
        },
        "merge": {
            "threshold": 0.10,
            "metrics": ["zq95", "vci_1m"],
            "destination_folder": "output",
        },
        "visual": {
            "visualize": False,
        },
    }

    config = configs.parse_dict(raw, base_dir=tmp_path, stage="e2e")
    assert config.common.mu == 780
    assert config.intersect is not None
    assert config.merge is not None
    assert config.visual is not None
    assert config.visual.visualize is False

    # adapter to stage 1
    stage1 = config.to_stage1_config()
    assert stage1.mu == 780
    assert stage1.source_gdb_name == "segmentation_R1"

    # adapter to stage 2
    stage2 = config.to_stage2_config()
    assert stage2.mu == 780
    assert stage2.threshold == 0.10
    assert stage2.metrics == ("zq95", "vci_1m")


def test_decoupled_intersect_only(tmp_path: pathlib.Path) -> None:
    '''
    Validate decoupled validation when only intersect stage is defined.

    Given:
        A dictionary with only common and intersect (no merge block).
    When:
        Parsed under 'intersect' stage mode.
    Then:
        Validation passes without requiring merge fields.
    '''
    raw = {
        "common": {"mu": 780},
        "intersect": {
            "source_folder": "input",
            "source_gdb_name": "seg_test",
            "source_layer_prefix": "seg_prefix",
        },
    }

    config = configs.parse_dict(raw, base_dir=tmp_path, stage="intersect")
    assert config.intersect is not None
    assert config.merge is None

    # attempting to convert to stage 2 raises error
    with _raises(ValueError, match="Stage 2"):
        config.to_stage2_config()


def test_decoupled_merge_only(tmp_path: pathlib.Path) -> None:
    '''
    Validate decoupled validation when only merge stage is defined.

    Given:
        A dictionary with only common and merge (no intersect block).
    When:
        Parsed under 'merge' stage mode.
    Then:
        Validation passes without requiring intersect fields.
    '''
    raw = {
        "common": {"mu": 780},
        "merge": {
            "source_folder": "output",
            "source_gdb_name": "intersect_result",
            "source_layer": "intersected_dummy_001",
            "threshold": 0.05,
        },
    }

    config = configs.parse_dict(raw, base_dir=tmp_path, stage="merge")
    assert config.merge is not None
    assert config.intersect is None

    # attempting to convert to stage 1 raises error
    with _raises(ValueError, match="Stage 1"):
        config.to_stage1_config()

    # stage 2 adapter succeeds because merge source is specified
    stage2 = config.to_stage2_config()
    assert stage2.threshold == 0.05


def test_e2e_fails_when_intersect_missing(tmp_path: pathlib.Path) -> None:
    '''
    Validate e2e stage failure when a required stage block is omitted.

    Given:
        A dictionary with common and merge, but missing intersect.
    When:
        Parsed under 'e2e' stage mode.
    Then:
        ValueError is raised identifying missing intersect section.
    '''
    raw = {
        "common": {"mu": 780},
        "merge": {"threshold": 0.10},
    }
    with _raises(ValueError, match="requires 'intersect'"):
        configs.parse_dict(raw, base_dir=tmp_path, stage="e2e")


def test_validation_bounds(tmp_path: pathlib.Path) -> None:
    '''
    Validate numeric boundaries and allowed choices.

    Given:
        Invalid configuration values for mu, format, and threshold.
    When:
        Validated under respective stages.
    Then:
        Appropriate ValueError exceptions are raised.
    '''
    # negative mu
    raw_bad_mu = {
        "common": {"mu": -1},
        "intersect": {
            "source_folder": "in",
            "source_gdb_name": "g",
            "source_layer_prefix": "p",
        },
    }
    with _raises(ValueError, match="non-negative"):
        configs.parse_dict(raw_bad_mu, base_dir=tmp_path, stage="intersect")

    # unsupported format
    raw_bad_format = {
        "common": {"output_format": "shapefile"},
        "intersect": {
            "source_folder": "in",
            "source_gdb_name": "g",
            "source_layer_prefix": "p",
        },
    }
    with _raises(ValueError, match="Unsupported output_format"):
        configs.parse_dict(
            raw_bad_format, base_dir=tmp_path, stage="intersect"
        )

    # negative threshold
    raw_bad_tol = {
        "common": {"mu": 780},
        "merge": {"threshold": -0.05},
    }
    with _raises(ValueError, match="threshold"):
        configs.parse_dict(raw_bad_tol, base_dir=tmp_path, stage="merge")


def test_load_config_file(tmp_path: pathlib.Path) -> None:
    '''
    Validate loading and relative path resolution from JSON file.

    Given:
        A JSON configuration file on disk.
    When:
        `load_config` is called with file path.
    Then:
        Relative paths resolve relative to the JSON file directory.
    '''
    cfg_file = tmp_path / "test_cfg.json"
    raw_data = {
        "common": {"mu": 780},
        "intersect": {
            "source_folder": "relative/in",
            "source_gdb_name": "src_gdb",
            "source_layer_prefix": "pref",
        },
    }
    cfg_file.write_text(json.dumps(raw_data), encoding="utf-8")

    loaded = configs.load_config(cfg_file, stage="intersect")
    assert loaded.intersect is not None
    assert loaded.intersect.source_folder == (
        tmp_path / "relative/in"
    ).resolve()


# ----- private helpers
@contextlib.contextmanager
def _raises(
    expected_exc: type[Exception],
    match: str | None = None,
) -> typing.Iterator[None]:
    '''Context manager asserting an exception is raised.'''
    try:
        yield
    except expected_exc as err:
        if match is not None:
            assert match in str(err)
    else:
        raise AssertionError(f"Expected {expected_exc.__name__} was not raised")
