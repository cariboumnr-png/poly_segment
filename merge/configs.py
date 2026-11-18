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
Configuration for polygon layer merging with injectable rule sets.

Defines the merge workflow configuration dataclass, supported output
formats, and argument parser.

Public APIs:
    - `OUTPUT_FORMATS`: Mapping of output format names to drivers.
    - `MergeConfig`: Configuration dataclass for polygon layer merging.
    - `parse_args`: Parse command-line arguments into `MergeConfig`.
'''

# standard imports
from __future__ import annotations
import argparse
import dataclasses
import logging
import pathlib
import typing
# third-party imports
import pyogrio
# local imports
from .rules import MergeRule

OUTPUT_FORMATS: dict[str, tuple[str, str]] = {
    "filegdb": (".gdb", "OpenFileGDB"),
    "geopackage": (".gpkg", "GPKG"),
}


# ----- public dataclasses
@dataclasses.dataclass(frozen=True, slots=True)
class MergeConfig:
    '''Configuration for Stage 2 polygon merging workflow run.'''
    mu: int
    source_folder: pathlib.Path
    source_gdb_name: str
    object_level_merge: int = 3
    source_layer: str | None = None
    source_layer_prefix: str | None = None
    destination_folder: pathlib.Path | None = None
    gdb_version: str = "001"
    layer_version: str = "001"
    output_format: str = "filegdb"
    overwrite: bool = False
    threshold: float = 0.10
    output_layer_name: str | None = None
    rule_set: MergeRule | None = None
    field_mapping: dict[str, str] | None = None
    min_shared_length: float = 0.0
    destination_gdb_name: str | None = None

    @property
    def source_dataset(self) -> pathlib.Path:
        '''Return the source dataset path.'''
        raw = self.source_gdb_name
        for ext in (".gdb", ".gpkg"):
            if raw.endswith(ext):
                p = self.source_folder / raw
                if p.exists():
                    return p

        for ext in (".gdb", ".gpkg"):
            p = self.source_folder / f"{raw}{ext}"
            if p.exists():
                return p
            for prefix in (
                f"isi_mu{self.mu}_postOBC_intersect_ver",
                f"isi_mu{self.mu}_postOBC_process_ver",
                f"isi_mu{self.mu}_postOBC_merge_ver",
            ):
                p_versioned = self.source_folder / f"{prefix}{raw}{ext}"
                if p_versioned.exists():
                    return p_versioned

        dest_ext, _ = OUTPUT_FORMATS.get(
            self.output_format, (".gdb", "OpenFileGDB")
        )
        return self.source_folder / f"{raw}{dest_ext}"

    @property
    def source_intersection_layer(self) -> str | None:
        '''Return pre-intersected layer name to merge, if available.'''
        if self.source_layer is not None:
            return self.source_layer

        if self.source_dataset.exists():
            try:
                available = {
                    str(name)
                    for name, _ in pyogrio.list_layers(self.source_dataset)
                }
                candidates = (
                    f"intersected_{self.layer_version}",
                    f"intersected_{self.gdb_version}",
                )
                for candidate in candidates:
                    if candidate in available:
                        return candidate
                matching = [
                    name for name in available
                    if name.startswith("intersected_")
                ]
                if len(matching) == 1:
                    return matching[0]
            except Exception:
                pass
        return None

    @property
    def source_layers(self) -> tuple[str, ...]:
        '''Return four source layers if prefix is provided.'''
        if self.source_layer_prefix is None:
            return ()
        return tuple(
            f"{self.source_layer_prefix}_{level}"
            for level in range(1, 5)
        )

    @property
    def selected_source_layer(self) -> str | None:
        '''Return layer supplying attributes in fallback mode.'''
        layers = self.source_layers
        if layers and 1 <= self.object_level_merge <= len(layers):
            return layers[self.object_level_merge - 1]
        return None

    @property
    def effective_destination_folder(self) -> pathlib.Path:
        '''Return destination folder, defaulting to source_folder.'''
        return self.destination_folder or self.source_folder

    @property
    def destination_stem(self) -> str:
        '''Return destination dataset name without extension.'''
        if self.destination_gdb_name is not None:
            raw = self.destination_gdb_name
            for ext in (".gdb", ".gpkg"):
                if raw.endswith(ext):
                    return raw[:-len(ext)]
            return raw
        return f"isi_mu{self.mu}_postOBC_merge_ver{self.gdb_version}"

    @property
    def destination_dataset(self) -> pathlib.Path:
        '''Return the destination dataset path.'''
        extension, _ = OUTPUT_FORMATS[self.output_format]
        dest_folder = self.effective_destination_folder
        return dest_folder / f"{self.destination_stem}{extension}"

    @property
    def merged_layer(self) -> str:
        '''Return the output merged polygon layer name.'''
        if self.output_layer_name is not None:
            return self.output_layer_name
        return f"merged_polygons_{self.layer_version}"


# ----- public functions
def parse_args(argv: typing.Sequence[str] | None = None) -> MergeConfig:
    '''
    Parse command-line arguments and return MergeConfig.

    Args:
        argv:
            Optional sequence of command-line argument strings.

    Returns:
        MergeConfig:
            Resolved merge workflow configuration instance.
    '''
    parser = argparse.ArgumentParser(
        description=(
            "Stage 2: Merge intersected polygon layers according to an "
            "injectable rule set."
        )
    )
    parser.add_argument("--mu", type=int, default=780)
    parser.add_argument(
        "--source-folder",
        type=pathlib.Path,
        default=pathlib.Path("sandbox/output"),
        help="Folder containing the Stage 1 output dataset.",
    )
    parser.add_argument(
        "--source-gdb-name",
        default="isi_mu780_postOBC_intersect_verdummy_001",
        help="Source dataset name from Stage 1.",
    )
    parser.add_argument(
        "--source-layer",
        default=None,
        help=(
            "Name of pre-intersected layer from Stage 1 "
            "(e.g. intersected_dummy_001)."
        ),
    )
    parser.add_argument(
        "--source-layer-prefix",
        default=None,
        help="Prefix for raw 4-layer fallback intersection.",
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
        default=None,
        help="Destination folder (defaults to source_folder).",
    )
    parser.add_argument(
        "--destination-gdb-name",
        default=None,
        help="Custom destination geodatabase name without extension.",
    )
    parser.add_argument("--gdb-version", default="dummy_001")
    parser.add_argument("--layer-version", default="dummy_001")
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
        help="Replace an existing destination dataset or layer.",
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
        help="Minimum shared boundary length (metres) to qualify.",
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
        source_layer=args.source_layer,
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
        destination_gdb_name=args.destination_gdb_name,
    )
