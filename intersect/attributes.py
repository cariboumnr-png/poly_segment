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
Attribute reading and enrichment for polygon neighbour analysis.

Reads source layer numeric attributes and enriches neighbour pairs
with symmetric absolute difference ratios.

Public APIs:
    - `read_comparison_attributes`: Read and validate attributes.
    - `enrich_neighbours_with_attributes`: Enrich neighbour pairs with
      attribute ratios.
'''

# standard imports
import pathlib
import typing
# third-party imports
import pandas
import pyogrio


# ----- public functions
def read_comparison_attributes(
    source_dataset: pathlib.Path,
    layer_name: str,
    attribute_fields: typing.Sequence[str],
) -> pandas.DataFrame:
    '''
    Read and validate numeric attributes used in neighbour comparison.

    Args:
        source_dataset:
            Path to the source geospatial dataset.
        layer_name:
            Target layer name containing attributes.
        attribute_fields:
            Sequence of numeric attribute field names to read.

    Returns:
        pandas.DataFrame:
            Table of numeric attributes indexed by feature ID.

    Raises:
        ValueError:
            If required attributes are missing or feature IDs invalid.
        TypeError:
            If attribute columns contain non-numeric values.
    '''
    attributes = pyogrio.read_dataframe(
        source_dataset,
        layer=layer_name,
        columns=list(attribute_fields),
        read_geometry=False,
        fid_as_index=True,
    )

    missing_fields = set(attribute_fields) - set(attributes.columns)
    if missing_fields:
        raise ValueError(
            f"Layer {layer_name!r} is missing attributes: "
            + ", ".join(sorted(missing_fields))
        )

    if not attributes.index.is_unique or attributes.index.hasnans:
        raise ValueError(
            f"Layer {layer_name!r} has invalid or non-unique OGR feature IDs."
        )

    for field in attribute_fields:
        numeric_values = pandas.to_numeric(attributes[field], errors="coerce")
        invalid_values = attributes[field].notna() & numeric_values.isna()
        if invalid_values.any():
            examples = attributes.loc[invalid_values, field].head(5).tolist()
            raise TypeError(
                f"Attribute {field!r} in layer {layer_name!r} contains "
                f"non-numeric values, e.g. {examples}."
            )
        attributes[field] = numeric_values.astype("float64")

    return attributes


def enrich_neighbours_with_attributes(
    neighbours: pandas.DataFrame,
    attributes: pandas.DataFrame,
    object_id_field: str,
    attribute_fields: typing.Sequence[str],
) -> pandas.DataFrame:
    '''
    Join attributes to both sides of pair and compute ratios.

    Args:
        neighbours:
            Table containing source and neighbour identifier columns.
        attributes:
            Table of numeric attributes indexed by feature ID.
        object_id_field:
            Column name prefix representing object identifier.
        attribute_fields:
            Sequence of numeric attribute names to compare.

    Returns:
        pandas.DataFrame:
            Neighbour table enriched with attribute columns and ratios.

    Raises:
        ValueError:
            If neighbour object IDs cannot be resolved to attributes.
    '''
    result = neighbours.copy()
    attribute_lookup = attributes.copy().reset_index(drop=True)
    attribute_lookup.insert(0, "_object_id", attributes.index.to_numpy())

    for side in ("src", "nbr"):
        join_field = f"{side}_{object_id_field}"
        lookup = attribute_lookup.rename(
            columns={field: f"{side}_{field}" for field in attribute_fields}
        )

        result = result.merge(
            lookup,
            how="left",
            left_on=join_field,
            right_on="_object_id",
            validate="many_to_one",
            indicator="_join_status",
        )

        unmatched = result["_join_status"] != "both"
        if unmatched.any():
            missing_ids = result.loc[unmatched, join_field].drop_duplicates()
            examples = missing_ids.head(5).tolist()
            raise ValueError(
                f"Some {side} object IDs could not be joined to the source "
                f"layer {object_id_field!r}; examples: {examples}."
            )

        result = result.drop(columns=["_object_id", "_join_status"])

    for field in attribute_fields:
        source_values = result[f"src_{field}"]
        neighbour_values = result[f"nbr_{field}"]

        # use mean absolute magnitude as denominator. This keeps the
        # symmetric relative difference non-negative for signed values
        # (e.g. `Mean_TPI`) and leaves both-zero pairs undefined.
        denominator = (source_values.abs() + neighbour_values.abs()) / 2.0
        denominator = denominator.mask(denominator == 0)
        result[f"src_nbr_abs_ratio_{field}"] = (
            source_values.sub(neighbour_values).abs().div(denominator)
        )

    return result

