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

"""Top-level namespace for the polygon merging module.

Exposes configuration, rule definitions, and workflow execution runners via lazy
resolution.

Public APIs:
    - MergeConfig: configuration dataclass for polygon layer merging.
    - MergeRule: abstract protocol for merge rules.
    - MetricDifferenceRule: rule comparing absolute attribute differences.
    - RuleSet: composite rule container (all/any).
    - DefaultMergeRuleSet: default rule comparing zq95, vci_1m, and LMoments 1-4.
    - merge_intersected_polygons: spatial operation to merge intersected polygons.
    - run_merge: execute the complete merge workflow.
    - run_workflow: alias for run_merge.
"""

from __future__ import annotations

# standard imports
import importlib
import typing


__all__ = [
    # classes & configs
    "MergeConfig",
    "MergeRule",
    "MetricDifferenceRule",
    "RuleSet",
    "DefaultMergeRuleSet",
    # functions & operations
    "merge_intersected_polygons",
    "run_merge",
    "run_workflow",
]


# for static type checkers
if typing.TYPE_CHECKING:
    from .configs import MergeConfig
    from .executor import run_merge
    from .executor import run_workflow
    from .rules import DefaultMergeRuleSet
    from .rules import MergeRule
    from .rules import MetricDifferenceRule
    from .rules import RuleSet
    from .spatial import merge_intersected_polygons


def __getattr__(name: str) -> typing.Any:
    if name in {"MergeConfig"}:
        module = importlib.import_module(".configs", __package__)
        return getattr(module, name)

    if name in {"MergeRule", "MetricDifferenceRule", "RuleSet", "DefaultMergeRuleSet"}:
        module = importlib.import_module(".rules", __package__)
        return getattr(module, name)

    if name in {"merge_intersected_polygons"}:
        module = importlib.import_module(".spatial", __package__)
        return getattr(module, name)

    if name in {"run_merge", "run_workflow"}:
        module = importlib.import_module(".executor", __package__)
        return getattr(module, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
