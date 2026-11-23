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
Unit tests for centralized lazy import resolution across postobc.

Validates that module-level __getattr__ resolves exported symbols and
subpackages on access, and raises AttributeError for undefined names.
'''

# standard imports
import typing
# third-party imports
try:
    import pytest
except ImportError:
    pytest = None
# local imports
import postobc
import postobc.configs
import postobc.intersect
import postobc.merge
import postobc.visual


# ----- test cases
def test_postobc_top_level_lazy_imports() -> None:
    '''
    Validate top-level lazy import resolution for all exported symbols.

    Given:
        The top-level `postobc` package.
    When:
        Exported symbols are accessed as attributes.
    Then:
        The expected classes, functions, and subpackages resolve.
    '''
    # subpackages
    assert postobc.configs is not None
    assert postobc.intersect is not None
    assert postobc.merge is not None
    assert postobc.visual is not None

    # intersect symbols
    assert postobc.WorkflowConfig is not None
    assert callable(postobc.run_workflow)

    # merge symbols
    assert postobc.MergeConfig is not None
    assert postobc.MergeRule is not None
    assert postobc.MetricDifferenceRule is not None
    assert postobc.RuleSet is not None
    assert postobc.DefaultMergeRuleSet is not None
    assert callable(postobc.merge_intersected_polygons)
    assert callable(postobc.run_merge)

    # visual symbols
    assert isinstance(postobc.LANDCOVER_COLORS, dict)
    assert callable(postobc.generate_interactive_html)
    assert callable(postobc.plot_comparison_figure)
    assert callable(postobc.render_workflow_visualizations)


def test_postobc_subpackage_lazy_imports() -> None:
    '''
    Validate subpackage lazy import resolution.

    Given:
        The subpackages `postobc.intersect`, `merge`, and `visual`.
    When:
        Their exported symbols are accessed as attributes.
    Then:
        The expected classes and functions resolve properly.
    '''
    assert postobc.configs.RootConfig is not None
    assert callable(postobc.configs.load_config)

    assert postobc.intersect.WorkflowConfig is not None
    assert callable(postobc.intersect.run_workflow)

    assert postobc.merge.MergeConfig is not None
    assert postobc.merge.MergeRule is not None
    assert postobc.merge.MetricDifferenceRule is not None
    assert postobc.merge.RuleSet is not None
    assert postobc.merge.DefaultMergeRuleSet is not None
    assert callable(postobc.merge.merge_intersected_polygons)
    assert callable(postobc.merge.run_merge)
    assert callable(postobc.merge.run_workflow)

    assert isinstance(postobc.visual.LANDCOVER_COLORS, dict)
    assert callable(postobc.visual.generate_interactive_html)
    assert callable(postobc.visual.plot_comparison_figure)
    assert callable(postobc.visual.render_workflow_visualizations)


def test_postobc_invalid_attribute_raises() -> None:
    '''
    Validate that accessing missing attributes raises AttributeError.

    Given:
        The `postobc` package and its subpackages.
    When:
        An undefined attribute name is accessed.
    Then:
        AttributeError is raised with descriptive message.
    '''
    targets: typing.Sequence[typing.Any] = (
        postobc,
        postobc.configs,
        postobc.intersect,
        postobc.merge,
        postobc.visual,
    )
    for target in targets:
        try:
            _ = target.non_existent
        except AttributeError as err:
            assert "has no attribute 'non_existent'" in str(err)
        else:
            raise AssertionError(f"Expected AttributeError on {target}")
