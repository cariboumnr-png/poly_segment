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
Shared fixtures and unit test environment setup.

Ensures heavy native GIS and visualization libraries are mocked if
unavailable in isolated unit testing environments.
'''

# standard imports
import importlib
import sys
from unittest import mock

for _dep in (
    "geopandas",
    "matplotlib",
    "matplotlib.patches",
    "matplotlib.pyplot",
    "numpy",
    "pandas",
    "pandas.api",
    "pandas.api.types",
    "pyogrio",
    "pyproj",
    "shapely",
    "shapely.geometry",
    "shapely.geometry.base",
):
    try:
        importlib.import_module(_dep)
    except ImportError:
        if _dep not in sys.modules:
            sys.modules[_dep] = mock.MagicMock()
