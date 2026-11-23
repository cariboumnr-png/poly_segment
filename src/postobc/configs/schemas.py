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
Centralized configuration schemas for polygon segmentation pipelines.

Provides strongly-typed, flat dataclasses representing common runtime
options, Stage 1 (intersect) settings, Stage 2 (merge) tolerances, and
visualization outputs.

Public APIs:
    - `CommonConfig`: Shared execution options across stages.
    - `IntersectConfig`: Stage 1 geometric intersection parameters.
    - `MergeConfig`: Stage 2 polygon merging rules and tolerances.
    - `VisualConfig`: Visual comparison and HTML export parameters.
    - `RootConfig`: Unified configuration container with adapters.
'''

# standard imports
import dataclasses
import pathlib
import typing

# for static type checkers
if typing.TYPE_CHECKING:
    import postobc.intersect.configs as intersect_configs
    import postobc.merge.configs as merge_configs


# ----- public dataclasses
# pylint: disable=too-many-instance-attributes
@dataclasses.dataclass(frozen=True, slots=True)
class CommonConfig:
    '''Shared execution options across workflow stages.'''
    mu: int = 780
    output_format: str = "filegdb"
    overwrite: bool = True
    verbose: bool = False


# pylint: disable=too-many-instance-attributes
@dataclasses.dataclass(frozen=True, slots=True)
class IntersectConfig:
    '''Stage 1 geometric intersection parameters.'''
    source_folder: pathlib.Path
    source_gdb_name: str
    source_layer_prefix: str
    object_level_merge: int = 3
    destination_folder: pathlib.Path | None = None
    gdb_version: str = "dummy_001"
    table_version: str = "dummy_001"
    destination_gdb_name: str | None = None


# pylint: disable=too-many-instance-attributes
@dataclasses.dataclass(frozen=True, slots=True)
class MergeConfig:
    '''Stage 2 polygon merging rules and tolerances.'''
    threshold: float = 0.10
    metrics: tuple[str, ...] | None = None
    per_metric_thresholds: dict[str, float] | None = None
    min_shared_length: float = 0.0
    source_folder: pathlib.Path | None = None
    source_gdb_name: str | None = None
    source_layer: str | None = None
    destination_folder: pathlib.Path | None = None
    gdb_version: str = "dummy_001"
    layer_version: str = "dummy_001"
    output_layer_name: str | None = None
    destination_gdb_name: str | None = None


# pylint: disable=too-many-instance-attributes
@dataclasses.dataclass(frozen=True, slots=True)
class VisualConfig:
    '''Visual comparison and interactive HTML export options.'''
    visualize: bool = True
    raw_gdb: pathlib.Path | None = None
    output_image: pathlib.Path | None = None
    output_html: pathlib.Path | None = None


# pylint: disable=too-many-instance-attributes
@dataclasses.dataclass(frozen=True, slots=True)
class RootConfig:
    '''Unified configuration container with conversion adapters.'''
    common: CommonConfig
    intersect: IntersectConfig | None = None
    merge: MergeConfig | None = None
    visual: VisualConfig | None = None

    def to_stage1_config(self) -> typing.Any:
        '''
        Convert into internal Stage 1 WorkflowConfig instance.

        Returns:
            WorkflowConfig:
                Resolved Stage 1 intersection configuration.

        Raises:
            ValueError:
                If intersect configuration is not defined.
        '''
        if self.intersect is None:
            raise ValueError(
                "Stage 1 (intersect) configuration is not defined."
            )
        import postobc.intersect.configs as intersect_configs

        dest_folder = (
            self.intersect.destination_folder
            or self.intersect.source_folder
        )
        return intersect_configs.WorkflowConfig(
            mu=self.common.mu,
            source_folder=self.intersect.source_folder,
            source_gdb_name=self.intersect.source_gdb_name,
            source_layer_prefix=self.intersect.source_layer_prefix,
            object_level_merge=self.intersect.object_level_merge,
            destination_folder=dest_folder,
            gdb_version=self.intersect.gdb_version,
            table_version=self.intersect.table_version,
            output_format=self.common.output_format,
            overwrite=self.common.overwrite,
            destination_gdb_name=self.intersect.destination_gdb_name,
        )

    def to_stage2_config(
        self,
        fallback_source_folder: pathlib.Path | None = None,
        fallback_source_gdb: str | None = None,
        fallback_source_layer: str | None = None,
    ) -> typing.Any:
        '''
        Convert into internal Stage 2 MergeConfig instance.

        Args:
            fallback_source_folder:
                Optional folder if merge.source_folder is unspecified.
            fallback_source_gdb:
                Optional GDB name if merge source is unspecified.
            fallback_source_layer:
                Optional layer name if merge source is unspecified.

        Returns:
            LegacyMergeConfig:
                Resolved Stage 2 merge configuration.

        Raises:
            ValueError:
                If merge configuration or source dataset is undefined.
        '''
        if self.merge is None:
            raise ValueError("Stage 2 (merge) configuration is not defined.")
        import postobc.merge.configs as merge_configs

        source_folder = self._resolve_merge_source_folder(
            fallback_source_folder
        )
        source_gdb_name = self._resolve_merge_source_gdb(fallback_source_gdb)
        source_layer = self._resolve_merge_source_layer(fallback_source_layer)
        dest_folder = self.merge.destination_folder or source_folder

        return merge_configs.MergeConfig(
            mu=self.common.mu,
            source_folder=source_folder,
            source_gdb_name=source_gdb_name,
            source_layer=source_layer,
            destination_folder=dest_folder,
            gdb_version=self.merge.gdb_version,
            layer_version=self.merge.layer_version,
            output_format=self.common.output_format,
            overwrite=self.common.overwrite,
            threshold=self.merge.threshold,
            output_layer_name=self.merge.output_layer_name,
            min_shared_length=self.merge.min_shared_length,
            destination_gdb_name=self.merge.destination_gdb_name,
            metrics=self.merge.metrics,
            per_metric_thresholds=self.merge.per_metric_thresholds,
        )

    def _resolve_merge_source_folder(
        self,
        fallback: pathlib.Path | None,
    ) -> pathlib.Path:
        '''Resolve input source folder for Stage 2.'''
        assert self.merge is not None
        if self.merge.source_folder is not None:
            return self.merge.source_folder
        if fallback is not None:
            return fallback
        if self.intersect is not None:
            return (
                self.intersect.destination_folder
                or self.intersect.source_folder
            )
        raise ValueError("Merge source_folder could not be resolved.")

    def _resolve_merge_source_gdb(self, fallback: str | None) -> str:
        '''Resolve input source geodatabase name for Stage 2.'''
        assert self.merge is not None
        if self.merge.source_gdb_name is not None:
            return self.merge.source_gdb_name
        if fallback is not None:
            return fallback
        if self.intersect is not None:
            return self.to_stage1_config().destination_stem
        raise ValueError("Merge source_gdb_name could not be resolved.")

    def _resolve_merge_source_layer(self, fallback: str | None) -> str:
        '''Resolve input pre-intersected layer name for Stage 2.'''
        assert self.merge is not None
        if self.merge.source_layer is not None:
            return self.merge.source_layer
        if fallback is not None:
            return fallback
        if self.intersect is not None:
            return self.to_stage1_config().intersection_layer
        raise ValueError("Merge source_layer could not be resolved.")
