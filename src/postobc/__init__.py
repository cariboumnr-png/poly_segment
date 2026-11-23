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
Top-level namespace for the postobc package.

Exposes stable configuration dataclasses, workflow execution runners,
rule definitions, and visualization utilities via lazy resolution.

Public APIs:
    - `WorkflowConfig`: Configuration dataclass for intersection.
    - `run_workflow`: Execute polygon-neighbour analysis workflow.
    - `MergeConfig`: Configuration dataclass for polygon merging.
    - `MergeRule`: Base contract for candidate neighbour merge rules.
    - `MetricDifferenceRule`: Rule comparing metric differences.
    - `RuleSet`: Composite rule container evaluating rules.
    - `DefaultMergeRuleSet`: Default rule comparing standard metrics.
    - `merge_intersected_polygons`: Spatial operation to merge polygons.
    - `run_merge`: Execute the complete polygon merge workflow.
    - `LANDCOVER_COLORS`: Mapping of vegetation classes to hex colors.
    - `generate_interactive_html`: Render self-contained HTML viewer.
    - `plot_comparison_figure`: Render multi-panel comparison graphic.
    - `render_workflow_visualizations`: Render workflow visual outputs.
'''

# standard imports
import importlib
import typing

__all__ = [
    # submodules
    'cli',
    'configs',
    'intersect',
    'merge',
    'visual',
    # intersect public APIs
    'WorkflowConfig',
    'run_workflow',
    # merge public APIs
    'DefaultMergeRuleSet',
    'MergeConfig',
    'MergeRule',
    'MetricDifferenceRule',
    'RuleSet',
    'merge_intersected_polygons',
    'run_merge',
    # visual public APIs
    'LANDCOVER_COLORS',
    'generate_interactive_html',
    'plot_comparison_figure',
    'render_workflow_visualizations',
]


# for static type checkers
if typing.TYPE_CHECKING:
    from . import cli
    from . import configs
    from . import intersect
    from . import merge
    from . import visual
    from .intersect.configs import WorkflowConfig
    from .intersect.executor import run_workflow
    from .merge.configs import MergeConfig
    from .merge.executor import run_merge
    from .merge.rules import DefaultMergeRuleSet
    from .merge.rules import MergeRule
    from .merge.rules import MetricDifferenceRule
    from .merge.rules import RuleSet
    from .merge.spatial import merge_intersected_polygons
    from .visual.renderer import LANDCOVER_COLORS
    from .visual.renderer import generate_interactive_html
    from .visual.renderer import plot_comparison_figure
    from .visual.renderer import render_workflow_visualizations


def __getattr__(name: str) -> typing.Any:
    '''Resolve top-level lazy exports and submodules on demand.'''
    if name in {'cli', 'configs', 'intersect', 'merge', 'visual'}:
        return importlib.import_module(f'.{name}', __package__)

    if name in {'WorkflowConfig', 'run_workflow'}:
        module = importlib.import_module('.intersect', __package__)
        return getattr(module, name)

    if name in {
        'DefaultMergeRuleSet',
        'MergeConfig',
        'MergeRule',
        'MetricDifferenceRule',
        'RuleSet',
        'merge_intersected_polygons',
        'run_merge',
    }:
        module = importlib.import_module('.merge', __package__)
        return getattr(module, name)

    if name in {
        'LANDCOVER_COLORS',
        'generate_interactive_html',
        'plot_comparison_figure',
        'render_workflow_visualizations',
    }:
        module = importlib.import_module('.visual', __package__)
        return getattr(module, name)

    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
