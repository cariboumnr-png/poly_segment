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

"""Shared pytest fixtures for the poly_segment test suite."""

import pathlib
import pytest

from scripts.generate_dummy_data import generate_dummy_dataset


@pytest.fixture(scope="module")
def synthetic_data(tmp_path_factory: pytest.TempPathFactory) -> tuple[pathlib.Path, pathlib.Path]:
    """
    Given:
        A temporary test directory provided by pytest.
    When:
        generate_dummy_dataset creates synthetic 4-layer polygon segmentation data.
    Then:
        A tuple of (temporary_directory, source_gdb_path) is returned for test use.
    """
    tmp_dir = tmp_path_factory.mktemp("merge_test_data")
    source_gdb = tmp_dir / "test_segmentation.gdb"
    generate_dummy_dataset(
        source_dataset=source_gdb,
        layer_prefix="segmented_objects",
        overwrite=True,
    )
    return tmp_dir, source_gdb
