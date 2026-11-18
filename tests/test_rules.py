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
Unit tests for merge rules and rule sets.

Validates single-pair evaluation, vectorized batch evaluation, composite
rule sets under 'all' and 'any' modes, and automatic field resolution.
'''

# third-party imports
import numpy
import pandas
# local imports
from merge.rules import DefaultMergeRuleSet
from merge.rules import MetricDifferenceRule
from merge.rules import RuleSet
from merge.rules import auto_resolve_field_mapping


# ----- test cases
def test_metric_difference_rule_single() -> None:
    '''
    Validate single-pair evaluation across differences and nulls.

    Given:
        A `MetricDifferenceRule` for metrics (threshold 0.10).
    When:
        Single-pair candidate neighbour attributes are evaluated.
    Then:
        Only pairs where all differences are <= 0.10 return True.
    '''
    metrics = ("zq95", "vci_1m")
    rule = MetricDifferenceRule(metrics=metrics, threshold=0.10)

    # within threshold on both
    source = {"zq95": 10.05, "vci_1m": 0.52}
    cand = {"zq95": 10.00, "vci_1m": 0.50}
    assert rule.can_merge(source, cand) is True

    # exceeds threshold on one metric
    cand_fail = {"zq95": 10.20, "vci_1m": 0.50}
    assert rule.can_merge(source, cand_fail) is False

    # `NaN` attribute
    cand_nan = {"zq95": float("nan"), "vci_1m": 0.50}
    assert rule.can_merge(source, cand_nan) is False

    # missing attribute
    cand_missing = {"zq95": 10.00}
    assert rule.can_merge(source, cand_missing) is False


def test_metric_difference_rule_batch() -> None:
    '''
    Validate vectorized batch evaluation of candidate pairs.

    Given:
        A `MetricDifferenceRule` configured for three metrics and 0.10.
    When:
        Vectorized evaluation via evaluate_batch is executed.
    Then:
        A 1-D boolean array is returned identifying qualifying pairs.
    '''
    metrics = ("zq95", "vci_1m", "LMoment1")
    rule = MetricDifferenceRule(metrics=metrics, threshold=0.10)

    sources = pandas.DataFrame({
        "zq95": [10.0, 10.0, 10.0, numpy.nan],
        "vci_1m": [0.5, 0.5, 0.5, 0.5],
        "LMoment1": [1.0, 1.0, 1.0, 1.0],
    })
    candidates = pandas.DataFrame({
        "zq95": [10.08, 10.15, 10.05, 10.0],  # row 1 exceeds (0.15 > 0.10)
        "vci_1m": [0.55, 0.52, 0.65, 0.5],   # row 2 exceeds (0.15 > 0.10)
        "LMoment1": [1.02, 1.01, 1.03, 1.0],
    })

    result = rule.evaluate_batch(sources, candidates)
    assert numpy.array_equal(result, numpy.array([True, False, False, False]))


def test_rule_set_modes() -> None:
    '''
    Validate composite RuleSet under 'all' and 'any' combination modes.

    Given:
        Two distinct `MetricDifferenceRule` instances.
    When:
        `RuleSet` evaluates pairs under 'all' and 'any' modes.
    Then:
        Mode 'all' requires both rules to pass, while mode 'any' permits
        either rule to pass.
    '''
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

    # mode "all": both must pass -> both fail
    ruleset_all = RuleSet([r1, r2], mode="all")
    assert numpy.array_equal(
        ruleset_all.evaluate_batch(sources, candidates),
        numpy.array([False, False]),
    )

    # mode "any": either can pass -> both pass
    ruleset_any = RuleSet([r1, r2], mode="any")
    assert numpy.array_equal(
        ruleset_any.evaluate_batch(sources, candidates),
        numpy.array([True, True]),
    )


def test_auto_resolve_field_mapping() -> None:
    '''
    Validate auto-resolution of level-prefixed attribute columns.

    Given:
        Layer attribute column names prefixed by segmentation level.
    When:
        `auto_resolve_field_mapping` is called with preferred level 3.
    Then:
        A dictionary mapping standard metrics to L3 columns is returned.
    '''
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


def test_default_merge_rule_set() -> None:
    '''
    Validate DefaultMergeRuleSet metric initialization.

    Given:
        `DefaultMergeRuleSet` initialized with a threshold of 0.10.
    When:
        The instance configuration is inspected.
    Then:
        The rule set contains exactly the 6 required standard metrics.
    '''
    rule_set = DefaultMergeRuleSet(threshold=0.10)
    assert len(rule_set.metrics) == 6
    assert "zq95" in rule_set.metrics
    assert "vci_1m" in rule_set.metrics
    assert "LMoment1" in rule_set.metrics


def test_metric_subset_selection() -> None:
    '''
    Validate rule evaluation when a subset of attributes is chosen.

    Given:
        A `DefaultMergeRuleSet` configured only for 'zq95' and 'vci_1m'.
    When:
        Candidate neighbours are evaluated where other metrics differ.
    Then:
        Only selected metrics must satisfy tolerance for merge to pass.
    '''
    rule_set = DefaultMergeRuleSet(
        threshold=0.10,
        metrics=("zq95", "vci_1m"),
    )
    assert rule_set.metrics == ("zq95", "vci_1m")

    # non-selected metrics (e.g. `LMoment1`) differ greatly
    # but are ignored
    source = {"zq95": 10.05, "vci_1m": 0.52, "LMoment1": 1.0}
    cand = {"zq95": 10.00, "vci_1m": 0.50, "LMoment1": 99.0}
    assert rule_set.can_merge(source, cand) is True

    # selected metric exceeds tolerance
    cand_fail = {"zq95": 10.25, "vci_1m": 0.50, "LMoment1": 1.0}
    assert rule_set.can_merge(source, cand_fail) is False


def test_per_metric_thresholds() -> None:
    '''
    Validate per-metric custom tolerance levels.

    Given:
        A rule set with custom thresholds for 'zq95' and 'vci_1m'.
    When:
        Pairs are evaluated against individual tolerance levels.
    Then:
        Each metric respects its specific threshold rather than global.
    '''
    rule_set = DefaultMergeRuleSet(
        threshold=0.10,
        metrics=("zq95", "vci_1m"),
        per_metric_thresholds={"zq95": 0.20, "vci_1m": 0.02},
    )

    # zq95 diff = 0.15 (<= 0.20), vci_1m diff = 0.01 (<= 0.02)
    source = {"zq95": 10.00, "vci_1m": 0.50}
    cand = {"zq95": 10.15, "vci_1m": 0.51}
    assert rule_set.can_merge(source, cand) is True

    # vci_1m diff = 0.05 (> 0.02 custom tolerance) -> fails
    cand_fail = {"zq95": 10.05, "vci_1m": 0.55}
    assert rule_set.can_merge(source, cand_fail) is False

