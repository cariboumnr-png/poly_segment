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
Attribute reading, validation, and aggregation for polygon merging.

Provides extraction of numeric attributes from source layers and
area-weighted attribute aggregation across merged polygon clusters.

Public APIs:
    - `read_source_attributes`: Read and validate numeric attributes.
    - `aggregate_attributes_area_weighted`: Compute averages.
'''

# standard imports
from __future__ import annotations
import logging
import pathlib
import typing
# third-party imports
import numpy
import pandas
import pyogrio

LOGGER = logging.getLogger("poly_segment_merge")


# ----- public functions
def read_source_attributes(
    source_dataset: pathlib.Path,
    layer_name: str,
    attribute_fields: typing.Sequence[str],
) -> pandas.DataFrame:
    '''
    Read and validate numeric attributes from a source layer.

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
            f"Layer {layer_name!r} is missing required attributes: "
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


def aggregate_attributes_area_weighted(
    records_df: pandas.DataFrame,
    areas: numpy.ndarray,
    numeric_columns: typing.Sequence[str],
    id_columns: typing.Sequence[str] | None = None,
) -> dict[str, object]:
    '''
    Compute area-weighted averages for numeric columns across a cluster.

    For ID columns, keeps the ID associated with the largest area part.

    Args:
        records_df:
            DataFrame containing attributes for member features.
        areas:
            Array of polygon surface areas in square metres.
        numeric_columns:
            Sequence of column names to average with area weighting.
        id_columns:
            Optional sequence of ID or classification columns.

    Returns:
        dict[str, object]:
            Aggregated attribute dictionary for the merged polygon.
    '''
    total_area = float(numpy.sum(areas))
    aggregated: dict[str, object] = {
        "num_merged_parts": int(len(records_df)),
        "merged_area_m2": total_area,
    }

    if total_area > 0:
        weights = areas / total_area
        for col in numeric_columns:
            vals = records_df[col].to_numpy(dtype="float64")
            valid = ~numpy.isnan(vals)
            if numpy.any(valid):
                # normalize weights of valid values
                val_weights = weights[valid]
                sum_w = numpy.sum(val_weights)
                if sum_w > 0:
                    weighted_val = numpy.sum(vals[valid] * val_weights) / sum_w
                    aggregated[col] = float(weighted_val)
                else:
                    aggregated[col] = float("nan")
            else:
                aggregated[col] = float("nan")
    else:
        for col in numeric_columns:
            aggregated[col] = float(records_df[col].mean())

    if id_columns:
        largest_part_idx = int(numpy.argmax(areas))
        for col in id_columns:
            aggregated[col] = records_df[col].iloc[largest_part_idx]

    return aggregated

