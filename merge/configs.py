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

"""Configuration for polygon layer merging with injectable rule sets."""

from __future__ import annotations

# standard imports
import argparse
import dataclasses
import logging
import pathlib
import typing

# local imports
from .rules import DEFAULT_MERGE_METRICS
from .rules import MergeRule


# ----- constants
OUTPUT_FORMATS: dict[str, tuple[str, str]] = {
    "filegdb": (".gdb", "OpenFileGDB"),
    "geopackage": (".gpkg", "GPKG"),
}


# ----- public dataclasses
@dataclasses.dataclass(frozen=True, slots=True)
class MergeConfig:
    """Configuration for one polygon merging workflow run."""

    mu: int
    source_folder: pathlib.Path
    source_gdb_name: str
    source_layer_prefix: str
    object_level_merge: int
    destination_folder: pathlib.Path
    gdb_version: str
    layer_version: str
    output_format: str = "filegdb"
    overwrite: bool = False
    threshold: float = 0.10
    output_layer_name: str | None = None
    rule_set: MergeRule | None = None
    field_mapping: dict[str, str] | None = None
    min_shared_length: float = 0.0

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
    def merged_layer(self) -> str:
        """Return the output merged polygon layer name."""
        if self.output_layer_name is not None:
            return self.output_layer_name
        return f"merged_polygons_{self.layer_version}"


# ----- public functions
def parse_args(argv: typing.Sequence[str] | None = None) -> MergeConfig:
    """Parse command-line arguments and return MergeConfig."""
    parser = argparse.ArgumentParser(
        description=(
            "Intersect four polygon segmentation levels and merge candidate "
            "neighbours according to an injectable rule set."
        )
    )
    parser.add_argument("--mu", type=int, default=780)
    parser.add_argument(
        "--source-folder",
        type=pathlib.Path,
        default=pathlib.Path("sandbox/input"),
        help="Folder containing the source dataset.",
    )
    parser.add_argument(
        "--source-gdb-name",
        default="segmentation_R1",
        help="Source geodatabase name without extension.",
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
        help="Segmentation level supplying merge comparison attributes.",
    )
    parser.add_argument(
        "--destination-folder",
        type=pathlib.Path,
        default=pathlib.Path("sandbox/output"),
    )
    parser.add_argument("--gdb-version", default="001")
    parser.add_argument("--layer-version", default="001")
    parser.add_argument(
        "--output-layer-name",
        default=None,
        help="Custom name for the merged output layer.",
    )
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
        "--threshold",
        type=float,
        default=0.10,
        help="Maximum absolute difference threshold for metric comparisons.",
    )
    parser.add_argument(
        "--min-shared-length",
        type=float,
        default=0.0,
        help="Minimum shared boundary length (metres) to qualify as neighbour candidate.",
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

    return MergeConfig(
        mu=args.mu,
        source_folder=args.source_folder,
        source_gdb_name=args.source_gdb_name,
        source_layer_prefix=args.source_layer_prefix,
        object_level_merge=args.object_level_merge,
        destination_folder=args.destination_folder,
        gdb_version=args.gdb_version,
        layer_version=args.layer_version,
        output_format=args.output_format,
        overwrite=args.overwrite,
        threshold=args.threshold,
        output_layer_name=args.output_layer_name,
        min_shared_length=args.min_shared_length,
    )
