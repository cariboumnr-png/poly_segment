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
│   ├── generate_dummy_data.py
│   └── visualize.py
├── tests/
│   ├── conftest.py
│   ├── test_rules.py
│   ├── test_spatial.py
│   └── test_workflow.py
├── intersect_config.json      # Stage 1: Intersection workflow configuration
├── merge_config.json          # Stage 2: Merging workflow configuration
├── merge_sweep_config.json    # Stage 2: Multi-trial merge parameter sweep configuration
├── run_intersect.py           # CLI runner for Stage 1 (intersect)
├── run_merge.py               # CLI runner for Stage 2 (merge)
├── run_merge_sweep.py         # Multi-trial parameter sweep orchestrator
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
└── isi_mu780_postOBC_intersect_verdummy_001.gdb
```

## Generate the dummy source data

Run from the project root:

```bash
python scripts/generate_dummy_data.py --overwrite
```

By default (`--pattern organic`), the generator creates four realistic, multi-scale
organic polygon layers using Lloyd-relaxed Voronoi tessellations across a 1 km by 1 km
extent in `EPSG:26917`:

| Layer | Segmentation Scale | Feature count |
|---|---|---:|
| `segmented_objects_R1_1` | Level 1: Coarse management zones | 6 |
| `segmented_objects_R1_2` | Level 2: Stand compartments | 12 |
| `segmented_objects_R1_3` | Level 3: Sub-stands / Object merge level | 24 |
| `segmented_objects_R1_4` | Level 4: Fine micro-segments / tree clusters | 45 |

Traditional rectangular grids can also be generated using:

```bash
python scripts/generate_dummy_data.py --overwrite --pattern grid
```

### Color Mapping & Landcover Classes

Each polygon includes thematic landcover classification and embedded color codes:

| Landcover Class | Hex Color | RGB | Description |
|---|---|---|---|
| **Mature Conifer** | `#1e5631` | `(30, 86, 49)` | High canopy height (`zq95 ~ 24.5 m`), high density (`vci ~ 0.68`) |
| **Mixed Forest** | `#4c9a2a` | `(76, 154, 42)` | Medium-high canopy (`zq95 ~ 17.2 m`), medium density (`vci ~ 0.48`) |
| **Regenerating Forest** | `#8dc63f` | `(141, 198, 63)` | Young stand (`zq95 ~ 7.8 m`), open density (`vci ~ 0.31`) |
| **Wetland Meadow** | `#e5c158` | `(229, 193, 88)` | Low ground vegetation (`zq95 ~ 1.4 m`), sparse density (`vci ~ 0.12`) |

Attributes within the same landcover zone vary by less than `0.05`, allowing Stage 2
(`run_merge.py`) to dissolve over-segmented sub-polygons within each stand back into
cohesive forest stands while sharply preserving true boundaries.

## Visualization

A dedicated visualizer generates both static high-resolution graphics and an interactive HTML viewer:

```bash
python scripts/visualize.py
```

Outputs:
* **Comparison Image (PNG)**: `sandbox/output/workflow_visualization.png` (2x3 panel comparison of all 4 input levels, Stage 1 intersection, and Stage 2 merged stands).
* **Interactive Viewer (HTML)**: `sandbox/output/workflow_visualization.html` (interactive map with layer toggles and hover inspection of canopy height, VCI, and stand attributes).

## Run the workflow in sequence

Stage 1 (Intersection and neighbour difference analysis):

```bash
python run_intersect.py intersect_config.json
```

Stage 2 (Rule-based polygon merging):

```bash
python run_merge.py merge_config.json
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

### Rule Evaluation & Tolerances

By default, the merge rule set performs an absolute difference comparison across
all standard metrics (`zq95`, `vci_1m`, and `LMoments 1-4`). Merging between
candidate neighbours $A$ and $B$ is permitted if and only if **all** evaluated
metrics are within tolerance:

$$|v_m(A) - v_m(B)| \le c_m \quad \forall m \in M$$

where $M$ is the evaluated metric set and $c_m$ is the tolerance for metric $m$
(defaulting to global `threshold = 0.10`).

Users can select any subset of attributes to compare and configure per-metric
tolerance levels via JSON configuration, Python API, or CLI:

```json
{
  "metrics": ["zq95", "vci_1m"],
  "threshold": 0.10,
  "per_metric_thresholds": {
    "zq95": 0.15,
    "vci_1m": 0.05
  }
}
```

CLI flags:

```bash
python run_merge.py merge_config.json --metrics zq95,vci_1m --per-metric-thresholds zq95=0.15,vci_1m=0.05
```

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
    source_gdb_name="isi_mu780_postOBC_intersect_verdummy_001",
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

---

# Merge Parameter Sweeps (`run_merge_sweep.py`)

`run_merge_sweep.py` orchestrates multi-trial parameter sweeps across structural
metrics and tolerance thresholds. It writes all trial outputs into a dedicated
sweep geodatabase (`isi_mu{mu}_postOBC_merge_sweep_ver{version}.gdb`), writes
summary statistics to `sweep_summary.json`, and renders extended multi-panel
visualizations (PNG graphic + interactive HTML viewer).

Public API:

```python
from run_merge_sweep import (
    SweepConfig,
    SweepTrial,
    DEFAULT_SWEEP_TRIALS,
    load_sweep_config,
    run_merge_sweep,
)
```

### Configuration File (`merge_sweep_config.json`)

`merge_sweep_config.json` exposes all base geodatabase parameters, output visual
paths, and the complete array of parameter trials:

```json
{
  "mu": 780,
  "source_folder": "sandbox/output",
  "source_gdb_name": "isi_mu780_postOBC_intersect_verdummy_001",
  "source_layer": "intersected_dummy_001",
  "destination_folder": "sandbox/output",
  "destination_gdb_name": "isi_mu780_postOBC_merge_sweep_verdummy_001.gdb",
  "visualize": true,
  "trials": [
    {
      "name": "all_standard",
      "label": "Trial 1: All Metrics (Standard)",
      "description": "All 6 structural metrics at 10% tolerance",
      "threshold": 0.10,
      "metrics": null,
      "per_metric_thresholds": null
    },
    {
      "name": "canopy_only",
      "label": "Trial 2: Canopy Height Only",
      "description": "Canopy height (ZQ95) at 10% tolerance",
      "threshold": 0.10,
      "metrics": ["zq95"]
    },
    {
      "name": "canopy_strict_vci",
      "label": "Trial 3: Canopy + Strict VCI",
      "description": "Relaxed ZQ95 (15%) + strict foliage density (3%)",
      "threshold": 0.10,
      "metrics": ["zq95", "vci_1m"],
      "per_metric_thresholds": {"zq95": 0.15, "vci_1m": 0.03}
    },
    {
      "name": "strict_structural",
      "label": "Trial 4: Strict Structural",
      "description": "Ultra-tight 2% tolerance preserving sub-stand variations",
      "threshold": 0.02,
      "metrics": ["zq95", "vci_1m"]
    }
  ]
}
```

### Predefined Demonstration Trials

The default demonstration suite evaluates four forestry / remote sensing scenarios:

| Trial | Name | Metrics | Thresholds | Output Stands | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Trial 1** | `all_standard` | All (6) | Global: 0.10 | 4 stands | Balanced multi-metric dissolve baseline |
| **Trial 2** | `canopy_only` | `zq95` | Global: 0.10 | 4 stands | Tree height structure only |
| **Trial 3** | `canopy_strict_vci` | `zq95`, `vci_1m` | ZQ95: 0.15, VCI: 0.03 | 6 stands | Relaxed canopy height + strict foliage density |
| **Trial 4** | `strict_structural` | `zq95`, `vci_1m` | Global: 0.02 | 14 stands | High-sensitivity micro-stand clustering |

### Running the Sweep Orchestrator

```bash
# Run with default merge_sweep_config.json
python run_merge_sweep.py

# Or specify a custom sweep configuration file
python run_merge_sweep.py merge_sweep_config.json
```

Output artifacts generated:
- `sandbox/output/isi_mu780_postOBC_merge_sweep_verdummy_001.gdb`: Multi-layer sweep geodatabase.
- `sandbox/output/sweep_summary.json`: JSON document detailing stand counts, metrics, tolerances, and runtimes.
- `sandbox/output/sweep_visualization.png`: Extended 9-panel static figure (4 raw segmentation levels, Stage 1 intersected sub-polygons, and the 4 dissolved merge trials with metrics legend banners).
- `sandbox/output/sweep_visualization.html`: Interactive SVG map with tab toggles for each trial and hover attribute cards displaying stand parameters and trial configuration.
