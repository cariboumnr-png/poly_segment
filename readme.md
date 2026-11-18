# Polygon Neighbour Analysis

This module intersects four polygon segmentation levels, identifies spatial
neighbours in the resulting polygons, and calculates attribute differences
between neighbouring objects.

The workflow is exposed through the public API:

```python
from app import WorkflowConfig
from app import run_workflow
```

A JSON-based runner is included so the workflow can be executed without
constructing `WorkflowConfig` directly in Python.

## Purpose

The workflow performs the following operations:

1. Validates a source File Geodatabase and four required polygon layers.
2. Intersects the four segmentation levels while retaining source feature IDs.
3. Identifies polygons that share an edge or point.
4. Creates bidirectional neighbour relationships.
5. Joins selected attributes from one configured segmentation level.
6. Calculates symmetric absolute relative differences between neighbours.
7. Writes the intersection layer and neighbour table to a File Geodatabase or
   GeoPackage.

## Project layout

```text
project-root/
├── intersect/                 # Stage 1: Four-layer intersection and neighbour difference analysis
│   ├── __init__.py
│   ├── attributes.py
│   ├── configs.py
│   ├── executor.py
│   └── spatial.py
├── merge/                     # Stage 2: Injectable rule-based polygon layer merging
│   ├── __init__.py
│   ├── attributes.py
│   ├── configs.py
│   ├── executor.py
│   ├── rules.py
│   └── spatial.py
├── scripts/
│   └── generate_dummy_data.py
├── tests/
│   ├── conftest.py
│   ├── test_rules.py
│   ├── test_spatial.py
│   └── test_workflow.py
├── intersect_config.json      # Stage 1: Intersection workflow configuration
├── merge_config.json          # Stage 2: Merging workflow configuration
├── run_intersect.py           # CLI runner for Stage 1 (intersect)
├── run_merge.py               # CLI runner for Stage 2 (merge)
└── README.md
```

## Input requirements

The configured source dataset must be a File Geodatabase containing four
polygon layers:

```text
<source_layer_prefix>_1
<source_layer_prefix>_2
<source_layer_prefix>_3
<source_layer_prefix>_4
```

All four layers must:

- contain only polygon or multipolygon geometries;
- contain no null or empty geometries;
- use the same projected coordinate reference system;
- have unique OGR feature IDs; and
- overlap spatially.

The layer selected by `object_level_merge` must contain these numeric fields:

```text
Mean_S2_Peak2
Mean_S2_PreLeaf
Mean_S2_Senes
Mean_TPI
Mean_vci_1m
Mean_ZQ95
```

The source dataset is currently required to be a File Geodatabase. The
destination can be either a File Geodatabase or GeoPackage.

## JSON configuration

`dummy_config.json` supplies the workflow configuration:

```json
{
  "mu": 780,
  "source_folder": "dummy_workflow/input",
  "source_gdb_name": "segmentation_R1",
  "source_layer_prefix": "segmented_objects_R1",
  "object_level_merge": 3,
  "destination_folder": "dummy_workflow/output",
  "gdb_version": "dummy_001",
  "table_version": "dummy_001",
  "output_format": "filegdb",
  "overwrite": true
}
```

Relative paths are resolved from the directory containing the JSON file.

With this configuration, the source dataset is:

```text
dummy_workflow/input/segmentation_R1.gdb
```

The selected attribute layer is:

```text
segmented_objects_R1_3
```

The destination dataset is:

```text
dummy_workflow/output/
└── isi_mu780_postOBC_process_verdummy_001.gdb
```

## Generate the dummy source data

Run from the project root:

```bash
python generate_dummy_data.py --overwrite
```

The generator creates four polygon grid layers:

| Layer | Grid | Feature count |
|---|---:|---:|
| `segmented_objects_R1_1` | 2 by 2 | 4 |
| `segmented_objects_R1_2` | 3 by 3 | 9 |
| `segmented_objects_R1_3` | 4 by 4 | 16 |
| `segmented_objects_R1_4` | 5 by 5 | 25 |

All layers cover the same 1 km by 1 km extent in `EPSG:26917`. Their different
grid resolutions create meaningful polygon intersections, shared edges, and
point contacts.

The dummy attributes vary by segmentation level, row, and column. `Mean_TPI`
also includes signed values to exercise the symmetric relative-difference
calculation.

The generator only creates input data. It does not execute the application
workflow.

## Run the workflow

Run with the default configuration:

```bash
python run_from_config.py
```

Or specify the configuration explicitly:

```bash
python run_from_config.py dummy_config.json
```

The runner:

1. reads and validates the JSON configuration;
2. resolves relative paths from the JSON file location;
3. constructs `WorkflowConfig`; and
4. calls `run_workflow(config)` through the public package API.

## Expected dummy execution results

For the unchanged dummy generator and configuration, the workflow is expected
to produce:

```text
100 intersection polygons
684 directed neighbour relationships
```

The destination dataset contains:

```text
intersected_dummy_001
polygon_neighbour_table_dummy_001
```

The intersection layer is expected to contain approximately:

```text
100 records
53 columns
```

The neighbour table is expected to contain approximately:

```text
684 records
28 columns
```

Exact counts should be treated as fixture-specific. They can change if the
dummy grid definitions, geometry handling, source attributes, or spatial
library behavior changes.

## Output contents

### Intersection layer

The intersection layer contains:

- polygon geometries created from the four-layer intersection;
- one `FID_*` field for each source segmentation layer; and
- source attributes prefixed by segmentation level, such as `L1_`, `L2_`,
  `L3_`, and `L4_`.

### Neighbour table

The neighbour table contains:

- `src_FID_*` fields identifying the source side;
- `nbr_FID_*` fields identifying the neighbour side;
- `LENGTH`, containing shared boundary length in metres;
- `NODE_COUNT`, containing the number of point-only contacts;
- `src_<attribute>` values;
- `nbr_<attribute>` values; and
- `src_nbr_abs_ratio_<attribute>` comparison values.

Neighbour relationships are bidirectional. If polygon A is a neighbour of
polygon B, the table contains both A-to-B and B-to-A records.

The comparison calculation is:

```text
abs(source - neighbour)
------------------------------------
(abs(source) + abs(neighbour)) / 2
```

The result is undefined when both values are zero or when either value is
missing. These cases are written as null values.

## Output behavior

If the destination already exists:

- `overwrite: false` skips execution when both expected output layers exist;
- `overwrite: false` raises an error when the destination is incomplete; and
- `overwrite: true` replaces the existing destination after the new output has
  been written successfully.

Outputs are first written to a temporary dataset. The temporary dataset is
published only after both output layers have been created successfully.

## Using another dataset

Create another JSON file using the same fields and point it to a compatible
source File Geodatabase:

```bash
python run_from_config.py production_config.json
```

No code changes are required when the source layer names, feature geometry,
coordinate reference system, and required attributes satisfy the documented
input contract.

## Runtime requirements

The workflow requires:

- Python 3.10 or later;
- GeoPandas;
- pandas;
- Pyogrio;
- PyProj;
- Shapely; and
- GDAL with the required output driver.

File Geodatabase writing through `OpenFileGDB` requires GDAL 3.6 or later.
GDAL 3.9 or later is recommended when preserving 64-bit integer fields for
recent ArcGIS Pro versions.

---

# Polygon Merging Module (`merge/`)

The `merge/` module intersects four polygon segmentation levels, evaluates spatial
neighbours against an **injectable rule set**, and dissolves qualifying adjacent
polygons into a single output polygon layer.

Public API:

```python
from merge import MergeConfig, run_merge, DefaultMergeRuleSet, MetricDifferenceRule
```

### Starting Rule Set

The starting rule set performs a direct absolute difference comparison across six metrics:
`zq95`, `vci_1m`, and `LMoments (1-4)`. Merging between candidate neighbours $A$ and $B$
is permitted if and only if:

$$|v_m(A) - v_m(B)| \le c \quad \forall m \in \{\text{zq95}, \text{vci\_1m}, \text{LMoment1}, \text{LMoment2}, \text{LMoment3}, \text{LMoment4}\}$$

where $c$ is a constant threshold (default `0.10`).

### Running the Merge Workflow

Run with JSON configuration:

```bash
python run_merge.py merge_config.json
```

Or execute via Python:

```python
import pathlib
from merge import MergeConfig, run_merge, DefaultMergeRuleSet

# Stage 2: Directly consumes Stage 1's intersected output
config = MergeConfig(
    mu=780,
    source_folder=pathlib.Path("sandbox/output"),
    source_gdb_name="isi_mu780_postOBC_process_verdummy_001",
    source_layer="intersected_dummy_001",
    object_level_merge=3,
    destination_folder=pathlib.Path("sandbox/output"),
    gdb_version="dummy_001",
    layer_version="dummy_001",
    threshold=0.10,
    overwrite=True,
)

merged_gdf = run_merge(config)
```
