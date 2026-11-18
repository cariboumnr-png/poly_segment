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

"""Injectable merge rules and rule sets for polygon neighbour evaluation.

Defines the contract for candidate neighbour evaluation, individual metric
difference rules, and composite rule sets.
"""

from __future__ import annotations

# standard imports
import abc
import dataclasses
import re
import typing

# third-party imports
import numpy
import pandas


# ----- constants
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
}


# ----- rule protocol / base classes
class MergeRule(abc.ABC):
    """Abstract base class for polygon neighbour merging rules."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Return the descriptive name of the rule."""

    @abc.abstractmethod
    def can_merge(
        self,
        source_attrs: typing.Mapping[str, float],
        candidate_attrs: typing.Mapping[str, float],
    ) -> bool:
        """Evaluate whether a single pair of neighbour objects can merge."""

    @abc.abstractmethod
    def evaluate_batch(
        self,
        sources: pandas.DataFrame,
        candidates: pandas.DataFrame,
    ) -> numpy.ndarray:
        """Vectorized evaluation of multiple candidate neighbour pairs.

        Returns a 1-D boolean numpy array indicating whether each pair permits
        merging.
        """


@dataclasses.dataclass(frozen=True, slots=True)
class MetricDifferenceRule(MergeRule):
    """Rule that merges neighbours if absolute differences are within threshold.

    For each specified metric:
        abs(source[metric] - candidate[metric]) <= threshold
    All specified metrics must satisfy this condition.
    """

    metrics: tuple[str, ...] = DEFAULT_MERGE_METRICS
    threshold: float = 0.10
    field_mapping: dict[str, str] = dataclasses.field(default_factory=dict)
    per_metric_thresholds: dict[str, float] = dataclasses.field(
        default_factory=dict
    )

    @property
    def name(self) -> str:
        return f"MetricDifferenceRule(threshold={self.threshold})"

    def _resolve_column(self, metric: str) -> str:
        return self.field_mapping.get(metric, metric)

    def _get_threshold(self, metric: str) -> float:
        return self.per_metric_thresholds.get(metric, self.threshold)

    def can_merge(
        self,
        source_attrs: typing.Mapping[str, float],
        candidate_attrs: typing.Mapping[str, float],
    ) -> bool:
        """Evaluate a single pair of objects against the metric differences."""
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
        """Evaluate candidate pairs in vectorized batch."""
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


class RuleSet(MergeRule):
    """Composite rule set evaluating multiple rules under 'all' or 'any' mode."""

    def __init__(
        self,
        rules: typing.Sequence[MergeRule],
        mode: typing.Literal["all", "any"] = "all",
    ) -> None:
        if not rules:
            raise ValueError("RuleSet must contain at least one MergeRule.")
        if mode not in {"all", "any"}:
            raise ValueError("RuleSet mode must be 'all' or 'any'.")
        self._rules = tuple(rules)
        self._mode = mode

    @property
    def name(self) -> str:
        rule_names = ", ".join(r.name for r in self._rules)
        return f"RuleSet(mode={self._mode!r}, rules=[{rule_names}])"

    @property
    def rules(self) -> tuple[MergeRule, ...]:
        return self._rules

    @property
    def mode(self) -> str:
        return self._mode

    def can_merge(
        self,
        source_attrs: typing.Mapping[str, float],
        candidate_attrs: typing.Mapping[str, float],
    ) -> bool:
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


def auto_resolve_field_mapping(
    columns: typing.Sequence[str],
    metrics: typing.Sequence[str] = DEFAULT_MERGE_METRICS,
    preferred_level: int | None = None,
) -> dict[str, str]:
    """Automatically resolve column names in available columns for each metric.

    Prefers level-prefixed columns (e.g. `L3_Mean_ZQ95`) when `preferred_level`
    is specified, then looks for clean matches across candidates.
    """
    mapping: dict[str, str] = {}
    cleaned_columns = {col: re.sub(r"[^a-zA-Z0-9]", "", col.lower()) for col in columns}

    for metric in metrics:
        clean_metric = re.sub(r"[^a-zA-Z0-9]", "", metric.lower())
        patterns = METRIC_NAME_PATTERNS.get(metric, (metric.lower(),))
        clean_patterns = [re.sub(r"[^a-zA-Z0-9]", "", p) for p in patterns]

        best_match: str | None = None

        # Level-qualified attempt if preferred_level is given
        if preferred_level is not None:
            prefix = f"l{preferred_level}"
            for col, clean_col in cleaned_columns.items():
                if clean_col.startswith(prefix):
                    remainder = clean_col[len(prefix):]
                    if any(p in remainder for p in clean_patterns) or clean_metric in remainder:
                        best_match = col
                        break

        # Fallback to direct pattern match
        if best_match is None:
            for col, clean_col in cleaned_columns.items():
                if any(p in clean_col for p in clean_patterns) or clean_metric in clean_col:
                    best_match = col
                    break

        if best_match is not None:
            mapping[metric] = best_match

    return mapping


class DefaultMergeRuleSet(RuleSet):
    """The default starting rule set for polygon layer merging.

    Performs a direct comparison of zq95, vci_1m, and LMoments (1-4), requiring
    the absolute difference for each metric to be <= constant threshold (default 0.10).
    """

    def __init__(
        self,
        threshold: float = 0.10,
        metrics: typing.Sequence[str] = DEFAULT_MERGE_METRICS,
        field_mapping: dict[str, str] | None = None,
        per_metric_thresholds: dict[str, float] | None = None,
    ) -> None:
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
    ) -> DefaultMergeRuleSet:
        """Return a new instance with auto-resolved field mapping for columns."""
        resolved = auto_resolve_field_mapping(
            columns=columns,
            metrics=self.metrics,
            preferred_level=preferred_level,
        )
        merged_mapping = {**resolved, **self.field_mapping}
        return DefaultMergeRuleSet(
            threshold=self.threshold,
            metrics=self.metrics,
            field_mapping=merged_mapping,
            per_metric_thresholds=self.per_metric_thresholds,
        )
