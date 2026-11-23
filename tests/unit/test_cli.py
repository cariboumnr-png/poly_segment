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
Unit tests for postobc command-line interface and stage dispatching.

Validates subcommand argument parsing, decoupled configuration
execution, and end-to-end pipeline invocation.
'''

# standard imports
import json
import pathlib
from unittest import mock
# local imports
import postobc.cli as cli


# ----- test cases
def test_cli_intersect_subcommand(tmp_path: pathlib.Path) -> None:
    '''
    Validate intersect subcommand dispatches to execute_intersect.

    Given:
        A configuration containing only common and intersect blocks.
    When:
        CLI `intersect` subcommand is executed.
    Then:
        `execute_intersect` is invoked with resolved Stage 1 config.
    '''
    cfg_file = tmp_path / "intersect_only.json"
    cfg_file.write_text(
        json.dumps(
            {
                "common": {"mu": 780},
                "intersect": {
                    "source_folder": "in",
                    "source_gdb_name": "src",
                    "source_layer_prefix": "pfx",
                },
            }
        ),
        encoding="utf-8",
    )

    with mock.patch("postobc.intersect.executor.run_workflow") as mock_run:
        exit_code = cli.main(["intersect", "--config", str(cfg_file)])
        assert exit_code == 0
        mock_run.assert_called_once()
        stage1_cfg = mock_run.call_args[0][0]
        assert stage1_cfg.mu == 780
        assert stage1_cfg.source_gdb_name == "src"


def test_cli_merge_subcommand(tmp_path: pathlib.Path) -> None:
    '''
    Validate merge subcommand dispatches to execute_merge.

    Given:
        A JSON configuration containing only common and merge blocks.
    When:
        CLI `merge` subcommand is executed with `--no-visualize`.
    Then:
        `execute_merge` is invoked and visualization is skipped.
    '''
    cfg_file = tmp_path / "merge_only.json"
    cfg_file.write_text(
        json.dumps(
            {
                "common": {"mu": 780},
                "merge": {
                    "source_folder": "out",
                    "source_gdb_name": "src_merge",
                    "source_layer": "intersected_dummy_001",
                    "threshold": 0.08,
                },
            }
        ),
        encoding="utf-8",
    )

    with (
        mock.patch(
            "postobc.merge.executor.run_merge",
            return_value=[1, 2, 3],
        ) as mock_merge,
        mock.patch(
            "postobc.visual.renderer.render_workflow_visualizations"
        ) as mock_vis,
    ):
        exit_code = cli.main(
            ["merge", "--config", str(cfg_file), "--no-visualize"]
        )
        assert exit_code == 0
        mock_merge.assert_called_once()
        stage2_cfg = mock_merge.call_args[0][0]
        assert stage2_cfg.threshold == 0.08
        mock_vis.assert_not_called()


def test_cli_e2e_subcommand(tmp_path: pathlib.Path) -> None:
    '''
    Validate e2e subcommand executes sequential pipeline stages.

    Given:
        A complete JSON configuration document.
    When:
        CLI `e2e` subcommand is executed.
    Then:
        Both Stage 1 intersect and Stage 2 merge are called in order.
    '''
    cfg_file = tmp_path / "e2e.json"
    cfg_file.write_text(
        json.dumps(
            {
                "common": {"mu": 780},
                "intersect": {
                    "source_folder": "in",
                    "source_gdb_name": "src",
                    "source_layer_prefix": "pfx",
                },
                "merge": {
                    "threshold": 0.12,
                },
                "visual": {
                    "visualize": False,
                },
            }
        ),
        encoding="utf-8",
    )

    with (
        mock.patch("postobc.intersect.executor.run_workflow") as mock_intersect,
        mock.patch(
            "postobc.merge.executor.run_merge",
            return_value=[],
        ) as mock_merge,
    ):
        exit_code = cli.main(["e2e", "--config", str(cfg_file)])
        assert exit_code == 0
        mock_intersect.assert_called_once()
        mock_merge.assert_called_once()
        stage2_cfg = mock_merge.call_args[0][0]
        assert stage2_cfg.threshold == 0.12
