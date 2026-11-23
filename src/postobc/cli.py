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
Command-line interface and orchestrator for postobc pipelines.

Provides subcommands to execute Stage 1 (intersect), Stage 2 (merge),
or the complete end-to-end workflow from a unified JSON configuration.

Public APIs:
    - `DEFAULT_CONFIG_PATH`: Default configuration file path.
    - `build_parser`: Construct command-line argument parser.
    - `run_intersect`: Programmatic Stage 1 execution entry point.
    - `run_merge`: Programmatic Stage 2 execution entry point.
    - `run_e2e`: Programmatic end-to-end execution entry point.
    - `main`: Command-line interface entry point.
'''

# standard imports
import argparse
import logging
import pathlib
import typing
# local imports
import postobc.configs as configs

LOGGER = logging.getLogger("postobc")
DEFAULT_CONFIG_PATH = pathlib.Path("postobc_config.json")


# ----- public functions
def build_parser() -> argparse.ArgumentParser:
    '''
    Construct command-line argument parser with stage subcommands.

    Returns:
        argparse.ArgumentParser:
            Configured top-level argument parser.
    '''
    parser = argparse.ArgumentParser(
        prog="postobc",
        description="Multi-scale polygon segmentation and merge CLI.",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        help="Pipeline stage to execute.",
    )

    _add_stage_parser(subparsers, "intersect", "Run Stage 1 intersection.")
    _add_stage_parser(subparsers, "merge", "Run Stage 2 polygon merge.")
    _add_stage_parser(subparsers, "e2e", "Run full end-to-end pipeline.")

    return parser


def run_intersect(config_path: pathlib.Path) -> None:
    '''
    Execute Stage 1 geometric intersection from configuration file.

    Args:
        config_path:
            Path to JSON configuration file.
    '''
    import postobc.intersect.executor as executor

    config = configs.load_config(config_path, stage="intersect")
    stage1_config = config.to_stage1_config()
    LOGGER.info("Starting Stage 1 intersection for mu %d", config.common.mu)
    executor.run_workflow(stage1_config)
    LOGGER.info("Stage 1 intersection completed successfully.")


def run_merge(
    config_path: pathlib.Path,
    visualize: bool = True,
) -> typing.Any:
    '''
    Execute Stage 2 polygon merging from configuration file.

    Args:
        config_path:
            Path to JSON configuration file.
        visualize:
            Whether to render comparison visuals after merging.

    Returns:
        geopandas.GeoDataFrame:
            Merged polygon GeoDataFrame.
    '''
    import postobc.merge.executor as executor

    config = configs.load_config(config_path, stage="merge")
    stage2_config = config.to_stage2_config()
    LOGGER.info(
        "Starting Stage 2 merge (threshold=%.4f)",
        stage2_config.threshold,
    )
    merged_gdf = executor.run_merge(stage2_config)
    LOGGER.info(
        "Stage 2 merge completed: %d stands generated.",
        len(merged_gdf),
    )

    if visualize:
        _render_visuals(config, stage2_config, merged_gdf)

    return merged_gdf


def run_e2e(
    config_path: pathlib.Path,
    visualize: bool = True,
) -> typing.Any:
    '''
    Execute complete end-to-end pipeline (intersect -> merge -> visual).

    Args:
        config_path:
            Path to JSON configuration file.
        visualize:
            Whether to render comparison visuals after merging.

    Returns:
        geopandas.GeoDataFrame:
            Merged polygon GeoDataFrame.
    '''
    import postobc.intersect.executor as intersect_executor
    import postobc.merge.executor as merge_executor

    config = configs.load_config(config_path, stage="e2e")
    stage1_config = config.to_stage1_config()
    LOGGER.info("Starting E2E Pipeline [Stage 1: Intersect]")
    intersect_executor.run_workflow(stage1_config)

    stage2_config = config.to_stage2_config()
    LOGGER.info("Starting E2E Pipeline [Stage 2: Merge]")
    merged_gdf = merge_executor.run_merge(stage2_config)
    LOGGER.info("E2E Pipeline merge completed successfully.")

    if visualize:
        _render_visuals(config, stage2_config, merged_gdf)

    return merged_gdf


def main(argv: typing.Sequence[str] | None = None) -> int:
    '''
    Parse command-line arguments and dispatch pipeline execution.

    Args:
        argv:
            Optional sequence of command-line argument strings.

    Returns:
        int:
            Process exit status code.
    '''
    parser = build_parser()
    args = parser.parse_args(argv)

    _configure_logging(verbose=args.verbose)
    config_path = args.config or DEFAULT_CONFIG_PATH

    if args.command == "intersect":
        run_intersect(config_path)
    elif args.command == "merge":
        run_merge(config_path, visualize=not args.no_visualize)
    elif args.command == "e2e":
        run_e2e(config_path, visualize=not args.no_visualize)

    return 0


# ----- private helpers
def _add_stage_parser(
    subparsers: typing.Any,
    name: str,
    help_text: str,
) -> None:
    '''Add standardized options to stage subparser.'''
    sub = subparsers.add_parser(name, help=help_text)
    sub.add_argument(
        "--config",
        "-c",
        type=pathlib.Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to JSON configuration file.",
    )
    sub.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug-level logging.",
    )
    if name in {"merge", "e2e"}:
        sub.add_argument(
            "--no-visualize",
            action="store_true",
            help="Disable automatic generation of comparison visuals.",
        )


def _configure_logging(verbose: bool) -> None:
    '''Initialize logging configuration with standard formatting.'''
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _render_visuals(
    config: configs.RootConfig,
    stage2_config: typing.Any,
    merged_gdf: typing.Any,
) -> None:
    '''Render workflow visual comparison graphics and HTML.'''
    import postobc.visual.renderer as renderer

    if config.visual is None or not config.visual.visualize:
        return

    raw_gdb = config.visual.raw_gdb
    if raw_gdb is None and config.intersect is not None:
        raw_gdb = config.to_stage1_config().source_dataset

    renderer.render_workflow_visualizations(
        base_config=stage2_config,
        merged_input=merged_gdf,
        raw_source_gdb=raw_gdb,
        output_png=config.visual.output_image,
        output_html=config.visual.output_html,
    )
