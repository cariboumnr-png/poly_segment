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
Injectable merge rules and rule sets for polygon neighbour evaluation.

Defines candidate neighbour evaluation, individual metric difference
rules, composite rule sets, and automatic field resolution.

Public APIs:
    - `DEFAULT_MERGE_METRICS`: Default sequence of metric names.
    - `METRIC_NAME_PATTERNS`: Metric name search patterns.
    - `MergeRule`: Base class for polygon neighbour merging rules.
    - `MetricDifferenceRule`: Rule evaluating metric differences.
    - `RuleSet`: Composite rule container evaluating rules in all/any.
    - `DefaultMergeRuleSet`: Default rule comparing standard metrics.
    - `auto_resolve_field_mapping`: Auto-resolve metric column names.
'''

# pylint: disable=missing-function-docstring

# standard imports
import abc
import dataclasses
import re
import typing
# third-party imports
import numpy
import pandas

DEFAULT_MERGE_METRICS: tuple[str, ...] = (
    "zq95",
    "vci_1m",
    "LMoment1",
    "LMoment2",
    "LMoment3",
    "LMoment4",
)

METRIC_NAME_PATTERNS: dict[str, tuple[str, ...]] = {
    "zq95": ("mean_zq95", "zq95", "p95"),
    "vci_1m": ("mean_vci_1m", "vci_1m", "vci"),
    "LMoment1": ("mean_lmoment1", "lmoment1", "lmoments_1", "l_moment1"),
    "LMoment2": ("mean_lmoment2", "lmoment2", "lmoments_2", "l_moment2"),
    "LMoment3": ("mean_lmoment3", "lmoment3", "lmoments_3", "l_moment3"),
    "LMoment4": ("mean_lmoment4", "lmoment4", "lmoments_4", "l_moment4"),
    "S2_Peak2": ("mean_s2_peak2", "s2_peak2", "peak2"),
    "S2_PreLeaf": ("mean_s2_preleaf", "s2_preleaf", "preleaf"),
    "S2_Senes": ("mean_s2_senes", "s2_senes", "senes"),
    "TPI": ("mean_tpi", "tpi"),
}


# ----- public types
class MergeRule(abc.ABC):
    '''Abstract base class for polygon neighbour merging rules.'''
    @property
    @abc.abstractmethod
    def name(self) -> str:
        '''Return human-readable rule identifier.'''

    @abc.abstractmethod
    def can_merge(
        self,
        source_attrs: typing.Mapping[str, float],
        candidate_attrs: typing.Mapping[str, float],
    ) -> bool:
        '''Evaluate whether two neighbouring features can be merged.'''

    @abc.abstractmethod
    def evaluate_batch(
        self,
        sources: pandas.DataFrame,
        candidates: pandas.DataFrame,
    ) -> numpy.ndarray:
        '''Evaluate candidate pairs against merge rule in batch mode.'''


# ----- public dataclasses
@dataclasses.dataclass(frozen=True, slots=True)
class MetricDifferenceRule(MergeRule):
    '''Merge neighbours when metric differences meet threshold.'''
    metrics: tuple[str, ...] = DEFAULT_MERGE_METRICS
    threshold: float = 0.10
    field_mapping: dict[str, str] = dataclasses.field(default_factory=dict)
    per_metric_thresholds: dict[str, float] = dataclasses.field(
        default_factory=dict
    )

    @property
    def name(self) -> str:
        '''Return human-readable rule description with threshold.'''
        return f"MetricDifferenceRule(threshold={self.threshold})"

    def _resolve_column(self, metric: str) -> str:
        '''Resolve metric name to column name via field mapping.'''
        return self.field_mapping.get(metric, metric)

    def _get_threshold(self, metric: str) -> float:
        '''Return metric-specific threshold or global rule default.'''
        return self.per_metric_thresholds.get(metric, self.threshold)

    def can_merge(
        self,
        source_attrs: typing.Mapping[str, float],
        candidate_attrs: typing.Mapping[str, float],
    ) -> bool:
        '''Evaluate pair of objects against metric differences.'''
        for metric in self.metrics:
            col = self._resolve_column(metric)
            if col not in source_attrs or col not in candidate_attrs:
                return False
            val_s = source_attrs[col]
            val_c = candidate_attrs[col]
            if val_s is None or val_c is None:
                return False
            if numpy.isnan(val_s) or numpy.isnan(val_c):
                return False
            thresh = self._get_threshold(metric)
            if abs(float(val_s) - float(val_c)) > thresh:
                return False
        return True

    def evaluate_batch(
        self,
        sources: pandas.DataFrame,
        candidates: pandas.DataFrame,
    ) -> numpy.ndarray:
        '''
        Evaluate candidate pairs in vectorized batch.

        Args:
            sources:
                DataFrame of source object attributes.
            candidates:
                DataFrame of candidate object attributes.

        Returns:
            numpy.ndarray:
                Boolean mask indicating qualifying pairs.

        Raises:
            ValueError:
                If input DataFrames have differing lengths.
            KeyError:
                If required metric column is missing from either table.
        '''
        if len(sources) != len(candidates):
            raise ValueError(
                "Source and candidate DataFrames must have the same length."
            )
        if len(sources) == 0:
            return numpy.empty(0, dtype=bool)

        mask = numpy.ones(len(sources), dtype=bool)
        for metric in self.metrics:
            col = self._resolve_column(metric)
            if col not in sources.columns or col not in candidates.columns:
                raise KeyError(
                    f"Metric column {col!r} (for metric {metric!r}) was not "
                    "found in attribute tables."
                )

            s_vals = sources[col].to_numpy(dtype="float64")
            c_vals = candidates[col].to_numpy(dtype="float64")
            thresh = self._get_threshold(metric)

            valid = ~(numpy.isnan(s_vals) | numpy.isnan(c_vals))
            diff = numpy.abs(s_vals - c_vals)
            metric_passes = valid & (diff <= thresh)
            mask &= metric_passes

        return mask


# ----- public classes
class RuleSet(MergeRule):
    '''Composite rule set evaluating rules under 'all' or 'any'.'''

    def __init__(
        self,
        rules: typing.Sequence[MergeRule],
        mode: typing.Literal["all", "any"] = "all",
    ) -> None:
        '''Initialize composite rule set with child rules and mode.'''
        if not rules:
            raise ValueError("RuleSet must contain at least one MergeRule.")
        if mode not in {"all", "any"}:
            raise ValueError("RuleSet mode must be 'all' or 'any'.")
        self._rules = tuple(rules)
        self._mode = mode

    @property
    def name(self) -> str:
        '''Return composite rule set identifier describing all rules.'''
        rule_names = ", ".join(r.name for r in self._rules)
        return f"RuleSet(mode={self._mode!r}, rules=[{rule_names}])"

    @property
    def rules(self) -> tuple[MergeRule, ...]:
        '''Return tuple of enclosed child merge rules.'''
        return self._rules

    @property
    def mode(self) -> str:
        '''Return evaluation mode string ('all' or 'any').'''
        return self._mode

    def can_merge(
        self,
        source_attrs: typing.Mapping[str, float],
        candidate_attrs: typing.Mapping[str, float],
    ) -> bool:
        '''Evaluate single pair against composite rules.'''
        if self._mode == "all":
            return all(
                r.can_merge(source_attrs, candidate_attrs)
                for r in self._rules
            )
        return any(
            r.can_merge(source_attrs, candidate_attrs)
            for r in self._rules
        )

    def evaluate_batch(
        self,
        sources: pandas.DataFrame,
        candidates: pandas.DataFrame,
    ) -> numpy.ndarray:
        '''Evaluate candidate pairs against composite rules in batch.'''
        if len(sources) == 0:
            return numpy.empty(0, dtype=bool)

        results = [
            r.evaluate_batch(sources, candidates)
            for r in self._rules
        ]
        if self._mode == "all":
            combined = results[0]
            for res in results[1:]:
                combined = combined & res
            return combined

        combined = results[0]
        for res in results[1:]:
            combined = combined | res
        return combined


class DefaultMergeRuleSet(RuleSet):
    '''Default starting rule set for polygon layer merging.'''

    def __init__(
        self,
        threshold: float = 0.10,
        metrics: typing.Sequence[str] = DEFAULT_MERGE_METRICS,
        field_mapping: dict[str, str] | None = None,
        per_metric_thresholds: dict[str, float] | None = None,
    ) -> None:
        '''Initialize default rule set with a metric difference rule.'''
        rule = MetricDifferenceRule(
            metrics=tuple(metrics),
            threshold=threshold,
            field_mapping=field_mapping or {},
            per_metric_thresholds=per_metric_thresholds or {},
        )
        super().__init__(rules=[rule], mode="all")
        self.threshold = threshold
        self.metrics = tuple(metrics)
        self.field_mapping = dict(field_mapping or {})
        self.per_metric_thresholds = dict(per_metric_thresholds or {})

    def with_resolved_mapping(
        self,
        columns: typing.Sequence[str],
        preferred_level: int | None = None,
    ) -> typing.Self:
        '''Return a new instance with auto-resolved field mapping.'''
        resolved = auto_resolve_field_mapping(
            columns=columns,
            metrics=self.metrics,
            preferred_level=preferred_level,
        )
        merged_mapping = {**resolved, **self.field_mapping}
        return self.__class__(
            threshold=self.threshold,
            metrics=self.metrics,
            field_mapping=merged_mapping,
            per_metric_thresholds=self.per_metric_thresholds,
        )


# ----- public functions
def auto_resolve_field_mapping(
    columns: typing.Sequence[str],
    metrics: typing.Sequence[str] = DEFAULT_MERGE_METRICS,
    preferred_level: int | None = None,
) -> dict[str, str]:
    '''
    Automatically resolve column names in available columns for metrics.

    Prefers level-prefixed columns (e.g. `L3_Mean_ZQ95`) when
    `preferred_level` is specified.

    Args:
        columns:
            Available column names in dataset.
        metrics:
            Sequence of metric names to resolve.
        preferred_level:
            Optional preferred segmentation level prefix.

    Returns:
        dict[str, str]:
            Mapping from metric name to corresponding column name.
    '''
    mapping: dict[str, str] = {}
    cleaned_columns = {
        col: re.sub(r"[^a-zA-Z0-9]", "", col.lower()) for col in columns
    }

    for metric in metrics:
        clean_metric = re.sub(r"[^a-zA-Z0-9]", "", metric.lower())
        patterns = METRIC_NAME_PATTERNS.get(metric, (metric.lower(),))
        clean_patterns = [re.sub(r"[^a-zA-Z0-9]", "", p) for p in patterns]

        best_match: str | None = None

        # level-qualified attempt if preferred_level is given
        if preferred_level is not None:
            prefix = f"l{preferred_level}"
            for col, clean_col in cleaned_columns.items():
                if clean_col.startswith(prefix):
                    remainder = clean_col[len(prefix):]
                    if (
                        any(p in remainder for p in clean_patterns)
                        or clean_metric in remainder
                    ):
                        best_match = col
                        break

        # fallback to direct pattern match
        if best_match is None:
            for col, clean_col in cleaned_columns.items():
                if (
                    any(p in clean_col for p in clean_patterns)
                    or clean_metric in clean_col
                ):
                    best_match = col
                    break

        if best_match is not None:
            mapping[metric] = best_match

    return mapping
