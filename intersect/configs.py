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

"""Command-line configuration for polygon-neighbour analysis."""

# standard imports
import argparse
import dataclasses
import logging
import pathlib
import typing


# ----- constants
ATTRIBUTE_FIELDS: tuple[str, ...] = (
    "Mean_S2_Peak2",
    "Mean_S2_PreLeaf",
    "Mean_S2_Senes",
    "Mean_TPI",
    "Mean_vci_1m",
    "Mean_ZQ95",
)

OUTPUT_FORMATS = {
    "filegdb": (".gdb", "OpenFileGDB"),
    "geopackage": (".gpkg", "GPKG"),
}


# ----- public dataclasses
@dataclasses.dataclass(frozen=True, slots=True)
class WorkflowConfig:
    """Configuration for one post-processing run."""

    mu: int
    source_folder: pathlib.Path
    source_gdb_name: str
    source_layer_prefix: str
    object_level_merge: int
    destination_folder: pathlib.Path
    gdb_version: str
    table_version: str
    output_format: str = "filegdb"
    overwrite: bool = False

    @property
    def source_dataset(self) -> pathlib.Path:
        """Return the source File Geodatabase path."""
        return self.source_folder / f"{self.source_gdb_name}.gdb"

    @property
    def source_layers(self) -> tuple[str, ...]:
        """Return the four source segmentation layer names."""
        return tuple(
            f"{self.source_layer_prefix}_{level}"
            for level in range(1, 5)
        )

    @property
    def selected_source_layer(self) -> str:
        """Return the layer supplying attributes for comparison."""
        return self.source_layers[self.object_level_merge - 1]

    @property
    def destination_stem(self) -> str:
        """Return the versioned destination dataset name without extension."""
        return f"isi_mu{self.mu}_postOBC_process_ver{self.gdb_version}"

    @property
    def destination_dataset(self) -> pathlib.Path:
        """Return the destination dataset path."""
        extension, _ = OUTPUT_FORMATS[self.output_format]
        return self.destination_folder / f"{self.destination_stem}{extension}"

    @property
    def intersection_layer(self) -> str:
        """Return the output intersection layer name."""
        return f"intersected_{self.table_version}"

    @property
    def neighbour_table(self) -> str:
        """Return the output neighbour-table name."""
        return f"polygon_neighbour_table_{self.table_version}"


# ----- public functions
def parse_args(argv: typing.Sequence[str] | None = None) -> WorkflowConfig:
    """Parse command-line arguments and return workflow configuration."""
    parser = argparse.ArgumentParser(
        description=(
            "Intersect four polygon segmentation levels, identify neighbours, "
            "and compare selected-level attributes."
        )
    )
    parser.add_argument("--mu", type=int, default=780)
    parser.add_argument(
        "--source-folder",
        type=pathlib.Path,
        default=pathlib.Path("D:/process/isi/obc_results/runtime_002"),
        help="Folder containing the source .gdb.",
    )
    parser.add_argument(
        "--source-gdb-name",
        default="segmentation_R1",
        help="Source geodatabase name without the .gdb extension.",
    )
    parser.add_argument(
        "--source-layer-prefix",
        default="segmented_objects_R1",
        help="Prefix for the four source polygon layers.",
    )
    parser.add_argument(
        "--object-level-merge",
        type=int,
        choices=(1, 2, 3, 4),
        default=3,
        help="Segmentation level supplying the six attributes to compare.",
    )
    parser.add_argument(
        "--destination-folder",
        type=pathlib.Path,
        default=pathlib.Path("D:/process/isi/post_obc_process"),
    )
    parser.add_argument("--gdb-version", default="002")
    parser.add_argument("--table-version", default="002")
    parser.add_argument(
        "--output-format",
        choices=tuple(OUTPUT_FORMATS),
        default="filegdb",
        help="Destination format: filegdb or geopackage.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing destination dataset.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug-level logging.",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    return WorkflowConfig(
        mu=args.mu,
        source_folder=args.source_folder,
        source_gdb_name=args.source_gdb_name,
        source_layer_prefix=args.source_layer_prefix,
        object_level_merge=args.object_level_merge,
        destination_folder=args.destination_folder,
        gdb_version=args.gdb_version,
        table_version=args.table_version,
        output_format=args.output_format,
        overwrite=args.overwrite,
    )
