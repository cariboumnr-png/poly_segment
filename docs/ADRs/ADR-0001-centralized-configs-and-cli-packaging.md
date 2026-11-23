# ADR-0001: Centralized Configuration Management, Unified CLI, and Package Architecture

**Status:** Accepted — Implemented
**Date:** 2026-11-23

---

## Context & Problem Statement

The repository previously relied on standalone execution scripts in the root directory (`run_intersect.py`, `run_merge.py`, `run_merge_sweep.py`) accompanied by ad-hoc modules (`intersect/`, `merge/`, `visual/`). While functional for initial prototyping, this layout exhibited several architectural and operational deficiencies:

1. **Scattered Configuration Management**: Configuration parameters were fragmented across multiple disparate JSON manifests (`intersect_config.json`, `merge_config.json`, `merge_sweep_config.json`) and redundant `argparse` definitions.
2. **Coupled Stage Execution**: Parameter validation was monolithic; running a single stage (e.g., polygon intersection or pairwise merging) required resolving and validating parameters for unrelated pipeline stages.
3. **Absence of Standard Packaging**: The project lacked a standard `src/` distribution layout, preventing the codebase from being installed as an editable or distributed package with formal entry points.
4. **Environment Isolation Issues**: Dependencies were not formally declared in packaging manifests, and lack of lazy import decoupling caused spatial library loading errors in non-GIS environments.

---

## Decision Drivers

* **Stage Decoupling**: Enable independent execution of Stage 1 (`intersect`), Stage 2 (`merge`), and full end-to-end (`e2e`) runs without cross-stage configuration contamination.
* **Human-Readable Configurations**: Centralize all configurable knobs into flat, schema-validated dataclasses with support for external JSON specification and sensible defaults.
* **Reproducible Developer Experience**: Ship a turnkey default configuration referencing verified synthetic datasets (`sandbox/input/segmentation_R1.gdb`) and establish unified CLI entry points (`postobc`).
* **Strict Repository Hygiene**: Adhere fully to Ontario Crown Copyright, line length budgets, 10.00/10 Pylint quality standards, and comprehensive static typing.

---

## Considered Options

1. **Option 1: In-Place Modification of Legacy Scripts**
   *Modify existing root scripts and ad-hoc modules in place.*
   *Rejected*: Risked breaking ongoing research experiments and failed to establish a clean package namespace.
2. **Option 2: Monolithic Configuration Schema**
   *Create a single large configuration class that validates all stages simultaneously.*
   *Rejected*: Violated stage decoupling requirements; users executing only the merge stage would be blocked by missing raw intersection inputs.
3. **Option 3: Layered `src/` Package with Decoupled Stage Validators & Unified CLI (Chosen)**
   *Establish a first-class `postobc` package under `src/` with dedicated `configs/` subsystem, stage-decoupled validation, unified CLI dispatching, and formal packaging manifests.*

---

## Decision Outcome

We adopted **Option 3**. The codebase was structured as follows:

### 1. `src/` Package Architecture
* Migrated business modules into a canonical `src/postobc` package layout (`postobc.intersect`, `postobc.merge`, `postobc.visual`, `postobc.configs`).
* Preserved existing root scripts (`run*.py`) and legacy directories untouched for backward compatibility during the migration phase.
* Configured top-level lazy exports in `src/postobc/__init__.py` using relative `from` imports and `__getattr__` dispatchers, preventing premature GDAL/Pyogrio binary initialization.

### 2. Centralized `postobc.configs` Subsystem
* **Schemas (`schemas.py`)**: Introduced flat, immutable dataclasses (`CommonConfig`, `IntersectConfig`, `MergeConfig`, `VisualConfig`, `RootConfig`) with `slots=True` and clear field typing.
* **Validators (`validators.py`)**: Implemented decoupled stage validators (`validate_intersect`, `validate_merge`, `validate_visual`, `validate_common`). When running an individual stage, only the relevant stage block and `common` parameters are validated.
* **Parsers (`parsers.py`)**: Provided deterministic JSON loading (`load_config`, `parse_dict`) with relative path resolution anchored to configuration file locations.
* **Stage Adapters**: Added converter methods (`to_stage1_config`, `to_stage2_config`) to translate high-level root configurations into execution-specific workflow parameters.

### 3. Unified CLI Entry Point
* Implemented `postobc.cli` exposed via `[project.scripts]` in `pyproject.toml` and callable via `python -m postobc`.
* Supports decoupled subcommands:
  * `postobc intersect --config postobc_config.json`
  * `postobc merge --config postobc_config.json`
  * `postobc e2e --config postobc_config.json`
* Included optional CLI overrides (`--mu`, `--overwrite`, `--threshold`, `--verbose`) that layer over JSON configuration values.

### 4. Root Configuration Manifest
* Shipped a default root `postobc_config.json` configured with verified synthetic dummy dataset paths:
  * Input: `sandbox/input/segmentation_R1.gdb`
  * Output: `sandbox/output/`
  * Stage 1: `isi_mu780_postOBC_intersect_verdummy_001.gdb`
  * Stage 2: `isi_mu780_postOBC_merge_verdummy_001.gdb`

### 5. Repository & Code Hygiene
* Configured `.pylintrc` and verified zero linter warnings (10.00/10 rating across the package).
* Enforced explicit import lineage (`import postobc.xxx.yyy as yyy`) in business modules.
* Maintained strict compliance with line length limits ($\le 80$ characters for code, $\le 72$ characters for docstrings/comments) and verbatim 20-line Crown Copyright headers.
* Fully documented all public and private symbols with Google-style and concise docstrings.

---

## Consequences & Trade-Offs

### Positive
* **Independent Stage Execution**: Developers and automated pipelines can run Stage 1 or Stage 2 in isolation without providing dummy values for unexecuted stages.
* **Standardized Packaging**: `postobc` can be installed in editable mode (`pip install -e .`) with standard entry points.
* **Robust Test Coverage**: 29 unit and workflow integration tests validate decoupled execution, CLI parameter parsing, and geospatial algorithms with a 100% pass rate.
* **Type Safety**: Fully typed with Mypy passing cleanly across all 20 source files.

### Negative / Mitigations
* **Import Linters**: Explicit module aliases (`import postobc.xxx as xxx`) trigger default Pylint warnings (`consider-using-from-import`, `useless-import-alias`), mitigated cleanly by repository-wide configuration in `.pylintrc`.
* **Coexistence Period**: Retaining root `run*.py` scripts introduces temporary code duplication with `src/postobc`, which will be resolved in a subsequent deprecation phase once all downstream workflows adopt the `postobc` CLI.
