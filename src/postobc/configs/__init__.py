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
Centralized configuration management package for postobc.

Provides schema dataclasses, stage-scoped validation, and JSON
parsers for decoupled polygon segmentation pipelines.

Public APIs:
    - `CommonConfig`: Global shared options across stages.
    - `IntersectConfig`: Stage 1 geometric intersection options.
    - `MergeConfig`: Stage 2 polygon merging rules and tolerances.
    - `VisualConfig`: Visual comparison and export options.
    - `RootConfig`: Unified configuration container with adapters.
    - `SUPPORTED_FORMATS`: Frozenset of valid spatial drivers.
    - `SUPPORTED_STAGES`: Frozenset of valid execution stages.
    - `validate_common`: Validate global common settings.
    - `validate_intersect`: Validate Stage 1 geometric settings.
    - `validate_merge`: Validate Stage 2 merge settings.
    - `validate_visual`: Validate visualization settings.
    - `validate_stage_config`: Decoupled active-stage validator.
    - `load_config`: Load, parse, and validate JSON config file.
    - `parse_dict`: Parse in-memory dictionary into RootConfig.
'''

# local imports
from .parsers import load_config
from .parsers import parse_dict
from .schemas import CommonConfig
from .schemas import IntersectConfig
from .schemas import MergeConfig
from .schemas import RootConfig
from .schemas import VisualConfig
from .validators import SUPPORTED_FORMATS
from .validators import SUPPORTED_STAGES
from .validators import validate_common
from .validators import validate_intersect
from .validators import validate_merge
from .validators import validate_stage_config
from .validators import validate_visual

__all__ = [
    "CommonConfig",
    "IntersectConfig",
    "MergeConfig",
    "VisualConfig",
    "RootConfig",
    "SUPPORTED_FORMATS",
    "SUPPORTED_STAGES",
    "validate_common",
    "validate_intersect",
    "validate_merge",
    "validate_visual",
    "validate_stage_config",
    "load_config",
    "parse_dict",
]
