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

"""Unit tests for merge rules and rule sets."""

import numpy
import pandas

from merge.rules import (
    DefaultMergeRuleSet,
    MetricDifferenceRule,
    RuleSet,
    auto_resolve_field_mapping,
)


def test_metric_difference_rule_single():
    """
    Given:
        A MetricDifferenceRule configured for 'zq95' and 'vci_1m' with a threshold of 0.10.
    When:
        Single-pair candidate neighbour attributes are evaluated across valid differences,
        exceeding differences, NaN attributes, and missing fields.
    Then:
        Only pairs where all metric differences are <= 0.10 return True, while
        exceeding, NaN, and missing attributes return False.
    """
    metrics = ("zq95", "vci_1m")
    rule = MetricDifferenceRule(metrics=metrics, threshold=0.10)

    # Within threshold on both
    source = {"zq95": 10.05, "vci_1m": 0.52}
    cand = {"zq95": 10.00, "vci_1m": 0.50}
    assert rule.can_merge(source, cand) is True

    # Exceeds threshold on one metric
    cand_fail = {"zq95": 10.20, "vci_1m": 0.50}
    assert rule.can_merge(source, cand_fail) is False

    # NaN attribute
    cand_nan = {"zq95": float("nan"), "vci_1m": 0.50}
    assert rule.can_merge(source, cand_nan) is False

    # Missing attribute
    cand_missing = {"zq95": 10.00}
    assert rule.can_merge(source, cand_missing) is False


def test_metric_difference_rule_batch():
    """
    Given:
        A MetricDifferenceRule configured for ('zq95', 'vci_1m', 'LMoment1') and threshold 0.10,
        and parallel source and candidate DataFrames containing 4 candidate pairs.
    When:
        Vectorized evaluation via evaluate_batch is executed.
    Then:
        A 1-D boolean array is returned identifying exactly which pairs satisfied all
        metric thresholds and non-null constraints.
    """
    metrics = ("zq95", "vci_1m", "LMoment1")
    rule = MetricDifferenceRule(metrics=metrics, threshold=0.10)

    sources = pandas.DataFrame({
        "zq95": [10.0, 10.0, 10.0, numpy.nan],
        "vci_1m": [0.5, 0.5, 0.5, 0.5],
        "LMoment1": [1.0, 1.0, 1.0, 1.0],
    })
    candidates = pandas.DataFrame({
        "zq95": [10.08, 10.15, 10.05, 10.0],  # row 1 exceeds threshold (0.15 > 0.10)
        "vci_1m": [0.55, 0.52, 0.65, 0.5],   # row 2 exceeds threshold (0.15 > 0.10)
        "LMoment1": [1.02, 1.01, 1.03, 1.0],
    })

    result = rule.evaluate_batch(sources, candidates)
    assert numpy.array_equal(result, numpy.array([True, False, False, False]))


def test_rule_set_modes():
    """
    Given:
        Two distinct MetricDifferenceRules ('zq95' threshold 0.10, 'vci_1m' threshold 0.05)
        and candidate pairs where each passes only one of the two rules.
    When:
        RuleSet evaluates candidate pairs under 'all' and 'any' combination modes.
    Then:
        Mode 'all' requires both rules to pass (returning all False), while mode 'any'
        permits either rule to pass (returning all True).
    """
    r1 = MetricDifferenceRule(metrics=("zq95",), threshold=0.10)
    r2 = MetricDifferenceRule(metrics=("vci_1m",), threshold=0.05)

    sources = pandas.DataFrame({
        "zq95": [10.0, 10.0],
        "vci_1m": [0.5, 0.5],
    })
    candidates = pandas.DataFrame({
        "zq95": [10.05, 10.20],  # row 0 passes r1, row 1 fails r1
        "vci_1m": [0.60, 0.52],  # row 0 fails r2, row 1 passes r2
    })

    # Mode "all": both must pass -> both fail
    ruleset_all = RuleSet([r1, r2], mode="all")
    assert numpy.array_equal(
        ruleset_all.evaluate_batch(sources, candidates),
        numpy.array([False, False]),
    )

    # Mode "any": either can pass -> both pass
    ruleset_any = RuleSet([r1, r2], mode="any")
    assert numpy.array_equal(
        ruleset_any.evaluate_batch(sources, candidates),
        numpy.array([True, True]),
    )


def test_auto_resolve_field_mapping():
    """
    Given:
        A collection of layer attribute column names prefixed by segmentation level (e.g., L3_Mean_ZQ95).
    When:
        auto_resolve_field_mapping is called with a preferred level of 3 for the default merge metrics.
    Then:
        A dictionary mapping standard metric names to their corresponding L3-prefixed column names is returned.
    """
    columns = [
        "L1_Mean_ZQ95", "L3_Mean_ZQ95",
        "L3_Mean_vci_1m",
        "L3_Mean_LMoment1", "L3_Mean_LMoment2",
        "L3_Mean_LMoment3", "L3_Mean_LMoment4",
    ]
    mapping = auto_resolve_field_mapping(
        columns=columns,
        preferred_level=3,
    )
    assert mapping["zq95"] == "L3_Mean_ZQ95"
    assert mapping["vci_1m"] == "L3_Mean_vci_1m"
    assert mapping["LMoment1"] == "L3_Mean_LMoment1"
    assert mapping["LMoment4"] == "L3_Mean_LMoment4"


def test_default_merge_rule_set():
    """
    Given:
        DefaultMergeRuleSet initialized with a threshold of 0.10.
    When:
        The instance configuration and metric specifications are inspected.
    Then:
        The rule set contains exactly the 6 required metrics ('zq95', 'vci_1m', and 'LMoment1' through 'LMoment4').
    """
    rule_set = DefaultMergeRuleSet(threshold=0.10)
    assert len(rule_set.metrics) == 6
    assert "zq95" in rule_set.metrics
    assert "vci_1m" in rule_set.metrics
    assert "LMoment1" in rule_set.metrics
