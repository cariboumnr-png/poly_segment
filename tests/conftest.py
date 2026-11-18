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
Shared pytest fixtures for the polygon segmentation test suite.

Provides session- and module-scoped synthetic datasets for testing
spatial operations, rule evaluations, and complete workflows.

Public APIs:
    - `synthetic_data`: Fixture providing synthetic dataset.
'''

# standard imports
import pathlib
# third-party imports
import pytest
# local imports
from scripts.generate_dummy_data import generate_dummy_dataset


# ----- shared fixtures
@pytest.fixture(scope="module")
def synthetic_data(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[pathlib.Path, pathlib.Path]:
    '''
    Generate synthetic 4-layer polygon segmentation dataset.

    Args:
        tmp_path_factory:
            Pytest factory for generating unique temporary directories.

    Returns:
        tuple[pathlib.Path, pathlib.Path]:
            Tuple of temporary root directory and source GDB path.
    '''
    tmp_dir = tmp_path_factory.mktemp("merge_test_data")
    source_gdb = tmp_dir / "test_segmentation.gdb"
    generate_dummy_dataset(
        source_dataset=source_gdb,
        layer_prefix="segmented_objects",
        overwrite=True,
    )
    return tmp_dir, source_gdb

