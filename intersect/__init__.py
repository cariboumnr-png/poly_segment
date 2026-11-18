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
Top-level namespace for the polygon intersection module.

Exposes configuration dataclasses and workflow execution runners via
lazy resolution.

Public APIs:
    - `WorkflowConfig`: Configuration dataclass for intersection.
    - `run_workflow`: Execute polygon-neighbour analysis workflow.
'''

# standard imports
from __future__ import annotations
import importlib
import typing

__all__ = [
    # classes
    'WorkflowConfig',
    # functions
    'run_workflow',
]


# for static check
if typing.TYPE_CHECKING:
    from .configs import WorkflowConfig
    from .executor import run_workflow


def __getattr__(name: str) -> typing.Any:
    if name in {'WorkflowConfig'}:
        obj = importlib.import_module('.configs', __package__)
        return getattr(obj, name)

    if name in {'run_workflow'}:
        obj = importlib.import_module('.executor', __package__)
        return getattr(obj, name)

    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')

