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
Visual comparison graphics and interactive HTML for workflow stages.

Produces multi-panel comparison plots and interactive SVG/HTML viewers
to inspect raw segmentation levels, Stage 1 intersections, and Stage 2
merged polygon stands (supporting both single runs and merge sweeps).

Public APIs:
    - `LANDCOVER_COLORS`: Mapping of vegetation classes to hex colors.
    - `plot_comparison_figure`: Render multi-panel comparison graphic.
    - `generate_interactive_html`: Render self-contained HTML viewer.
    - `parse_args`: Parse command-line arguments.
    - `main`: Entry point for script execution.
'''

# standard imports
from __future__ import annotations
import argparse
import json
import logging
import math
import os
import pathlib
import tempfile
import typing
# third-party imports
import geopandas
import pyogrio

LOGGER = logging.getLogger("poly_segment_visualize")

DEFAULT_SOURCE_GDB = pathlib.Path("sandbox/input/segmentation_R1.gdb")
DEFAULT_INTERSECT_GDB = pathlib.Path(
    "sandbox/output/isi_mu780_postOBC_intersect_verdummy_001.gdb"
)
DEFAULT_MERGE_GDB = pathlib.Path(
    "sandbox/output/isi_mu780_postOBC_merge_verdummy_001.gdb"
)
DEFAULT_OUTPUT_GDB = pathlib.Path(
    "sandbox/output/isi_mu780_postOBC_process_verdummy_001.gdb"
)
DEFAULT_PNG_PATH = pathlib.Path("sandbox/output/workflow_visualization.png")
DEFAULT_HTML_PATH = pathlib.Path("sandbox/output/workflow_visualization.html")

LANDCOVER_COLORS = {
    "Mature Conifer": "#1e5631",
    "Mixed Forest": "#4c9a2a",
    "Regenerating Forest": "#8dc63f",
    "Wetland Meadow": "#e5c158",
}


# ----- public functions
def parse_args(
    argv: typing.Sequence[str] | None = None,
) -> argparse.Namespace:
    '''
    Parse command-line arguments.

    Args:
        argv:
            Optional sequence of command-line argument strings.

    Returns:
        argparse.Namespace:
            Parsed command-line arguments.
    '''
    parser = argparse.ArgumentParser(
        description=(
            "Visualize polygon segmentation, intersection, and merging stages."
        )
    )
    parser.add_argument(
        "--source-gdb",
        type=pathlib.Path,
        default=DEFAULT_SOURCE_GDB,
        help="Path to source File Geodatabase with raw layers.",
    )
    parser.add_argument(
        "--intersect-gdb",
        type=pathlib.Path,
        default=DEFAULT_INTERSECT_GDB,
        help="Path to Stage 1 intersection File Geodatabase.",
    )
    parser.add_argument(
        "--merge-gdb",
        type=pathlib.Path,
        default=DEFAULT_MERGE_GDB,
        help="Path to Stage 2 merged File Geodatabase.",
    )
    parser.add_argument(
        "--output-gdb",
        type=pathlib.Path,
        default=None,
        help="Path to optional combined output File Geodatabase.",
    )
    parser.add_argument(
        "--output-image",
        type=pathlib.Path,
        default=DEFAULT_PNG_PATH,
        help="Path to export comparison PNG graphic.",
    )
    parser.add_argument(
        "--output-html",
        type=pathlib.Path,
        default=DEFAULT_HTML_PATH,
        help="Path to export interactive HTML visualizer.",
    )
    return parser.parse_args(argv)


def plot_comparison_figure(
    raw_layers: dict[int, geopandas.GeoDataFrame],
    intersected_gdf: geopandas.GeoDataFrame,
    merged_gdf: (
        geopandas.GeoDataFrame
        | dict[str, tuple[geopandas.GeoDataFrame, str]]
        | list[tuple[str, geopandas.GeoDataFrame, str]]
    ),
    output_png: pathlib.Path,
) -> None:
    '''
    Render a comparison graphic showing workflow progression.

    Supports both single Stage 2 merged layers (2x3 panel) and multi-trial
    parameter sweeps (with dynamic rows and metrics legend annotations).

    Args:
        raw_layers:
            Mapping of level index to raw input GeoDataFrames.
        intersected_gdf:
            Stage 1 intersected polygons GeoDataFrame.
        merged_gdf:
            Stage 2 merged polygons GeoDataFrame or list/dict of trials.
        output_png:
            Target image file path on disk.
    '''
    os.environ.setdefault("MPLCONFIGDIR", tempfile.gettempdir())
    # pylint: disable=import-outside-toplevel
    import matplotlib.patches
    import matplotlib.pyplot
    # pylint: enable=import-outside-toplevel

    merge_items = _normalize_merge_inputs(merged_gdf)
    total_panels = 5 + len(merge_items)
    ncols = 3
    nrows = math.ceil(total_panels / ncols)

    fig, axes = matplotlib.pyplot.subplots(
        nrows, ncols, figsize=(18, 5.5 * nrows), dpi=200
    )
    axes_flat = list(axes.flat) if hasattr(axes, "flat") else [axes]

    suptitle_text = (
        "Multi-Scale Segmentation, Intersection & Rule-Based Merge Sweep"
        if len(merge_items) > 1
        else (
            "Multi-Scale Polygon Segmentation, Intersection & "
            "Rule-Based Merging"
        )
    )
    fig.suptitle(
        suptitle_text,
        fontsize=16,
        fontweight="bold",
        y=0.98 if nrows > 2 else 0.97,
    )

    panels: list[
        tuple[
            typing.Any,
            geopandas.GeoDataFrame,
            str,
            int,
            bool,
            str | None,
        ]
    ] = [
        (
            axes_flat[0],
            raw_layers[1],
            f"Level 1: Coarse Segments ({len(raw_layers[1])} polygons)",
            1,
            False,
            None,
        ),
        (
            axes_flat[1],
            raw_layers[2],
            f"Level 2: Medium-Coarse ({len(raw_layers[2])} polygons)",
            2,
            False,
            None,
        ),
        (
            axes_flat[2],
            raw_layers[3],
            f"Level 3: Object Merge Level ({len(raw_layers[3])} polygons)",
            3,
            False,
            None,
        ),
        (
            axes_flat[3],
            raw_layers[4],
            f"Level 4: Fine Segments ({len(raw_layers[4])} polygons)",
            4,
            False,
            None,
        ),
        (
            axes_flat[4],
            intersected_gdf,
            f"Stage 1: Intersected ({len(intersected_gdf)} sub-polygons)",
            3,
            True,
            None,
        ),
    ]

    for trial_idx, (trial_title, trial_gdf, trial_desc) in enumerate(
        merge_items
    ):
        panel_ax = axes_flat[5 + trial_idx]
        title_str = (
            f"{trial_title} ({len(trial_gdf)} dissolved stands)"
            if "merged" in trial_title.lower() or "trial" in trial_title.lower()
            else f"Stage 2: {trial_title} ({len(trial_gdf)} dissolved stands)"
        )
        panels.append(
            (panel_ax, trial_gdf, title_str, 3, False, trial_desc)
        )

    for i in range(total_panels, len(axes_flat)):
        axes_flat[i].set_visible(False)

    for idx, (ax, gdf, title, lvl, show_dense, desc) in enumerate(panels):
        ax.set_title(title, fontsize=12, fontweight="semibold", pad=8)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])

        colors = [
            _resolve_layer_color(row, level=lvl)
            for _, row in gdf.iterrows()
        ]

        edge_color = "black" if not show_dense else "#222222"
        linewidth = 0.5 if not show_dense else 0.8
        alpha = 0.88 if not show_dense else 0.75

        gdf.plot(
            ax=ax,
            color=colors,
            edgecolor=edge_color,
            linewidth=linewidth,
            alpha=alpha,
        )

        if desc:
            ax.text(
                0.5,
                0.96,
                desc,
                transform=ax.transAxes,
                ha="center",
                va="top",
                fontsize=8.5,
                fontweight="bold",
                color="#0f172a",
                bbox=dict(
                    boxstyle="round,pad=0.25",
                    fc="#e2e8f0",
                    ec="#64748b",
                    alpha=0.92,
                ),
            )

        if idx >= 5:
            for _, row in gdf.iterrows():
                centroid = row.geometry.centroid
                parts = row.get("num_merged_parts", 1)
                name = row.get("landcover", "Stand")
                area_ha = row.geometry.area / 10_000.0
                label = f"{name}\n({parts} merged parts\n{area_ha:.1f} ha)"
                ax.annotate(
                    label,
                    xy=(centroid.x, centroid.y),
                    ha="center",
                    va="center",
                    fontsize=8.0 if len(merge_items) > 1 else 8.5,
                    fontweight="bold",
                    color="white",
                    bbox=dict(
                        boxstyle="round,pad=0.25",
                        fc="black",
                        ec="none",
                        alpha=0.65,
                    ),
                )

    legend_patches = [
        matplotlib.patches.Patch(color=col, label=label)
        for label, col in LANDCOVER_COLORS.items()
    ]
    fig.legend(
        handles=legend_patches,
        loc="lower center",
        ncol=4,
        frameon=True,
        fontsize=11,
        title="Landcover / Forest Stand Classification",
        title_fontsize=11,
    )

    output_png.parent.mkdir(parents=True, exist_ok=True)
    matplotlib.pyplot.savefig(output_png, bbox_inches="tight")
    matplotlib.pyplot.close(fig)
    LOGGER.info("Comparison figure saved to %s", output_png)


def generate_interactive_html(
    raw_layers: dict[int, geopandas.GeoDataFrame],
    intersected_gdf: geopandas.GeoDataFrame,
    merged_gdf: (
        geopandas.GeoDataFrame
        | dict[str, tuple[geopandas.GeoDataFrame, str]]
        | list[tuple[str, geopandas.GeoDataFrame, str]]
    ),
    output_html: pathlib.Path,
) -> None:
    '''
    Generate interactive SVG visualizer with toggles and tooltips.

    Supports toggling across raw segmentation levels, Stage 1 intersections,
    and all Stage 2 merged trial runs.

    Args:
        raw_layers:
            Mapping of level index to raw input GeoDataFrames.
        intersected_gdf:
            Stage 1 intersected polygons GeoDataFrame.
        merged_gdf:
            Stage 2 merged polygons GeoDataFrame or list/dict of trials.
        output_html:
            Target HTML file path on disk.
    '''
    merge_items = _normalize_merge_inputs(merged_gdf)

    extent_minx = min(
        raw_layers[1].total_bounds[0],
        intersected_gdf.total_bounds[0],
    )
    extent_miny = min(
        raw_layers[1].total_bounds[1],
        intersected_gdf.total_bounds[1],
    )
    extent_maxx = max(
        raw_layers[1].total_bounds[2],
        intersected_gdf.total_bounds[2],
    )
    extent_maxy = max(
        raw_layers[1].total_bounds[3],
        intersected_gdf.total_bounds[3],
    )

    width_m = extent_maxx - extent_minx
    height_m = extent_maxy - extent_miny
    svg_size = 560

    def to_svg_poly(geom: typing.Any) -> list[str]:
        if geom.is_empty:
            return []
        if geom.geom_type in ("MultiPolygon", "GeometryCollection"):
            geoms = geom.geoms
        else:
            geoms = [geom]
        paths = []
        for g in geoms:
            if g.geom_type != "Polygon":
                continue
            pts = []
            for x, y in g.exterior.coords:
                sx = (x - extent_minx) / width_m * svg_size
                sy = (extent_maxy - y) / height_m * svg_size
                pts.append(f"{sx:.1f},{sy:.1f}")
            paths.append(f'<polygon points="{" ".join(pts)}"')
        return paths

    layers_data: dict[str, list[dict[str, object]]] = {}

    dataset_pairs: list[
        tuple[str, geopandas.GeoDataFrame, int, str | None]
    ] = [
        ("Level 1 (Coarse)", raw_layers[1], 1, None),
        ("Level 4 (Fine)", raw_layers[4], 4, None),
        ("Stage 1: Intersected", intersected_gdf, 3, None),
    ]

    for title, gdf, desc in merge_items:
        prefix = "Stage 2: " if not title.startswith("Stage 2") else ""
        dataset_pairs.append((f"{prefix}{title}", gdf, 3, desc))

    for layer_name, gdf, lvl, desc in dataset_pairs:
        items = []
        for _, row in gdf.iterrows():
            poly_tags = to_svg_poly(row.geometry)
            color = _resolve_layer_color(row, level=lvl)
            landcover = str(
                row.get("landcover", row.get(f"L{lvl}_landcover", "Stand"))
            )
            zq95 = float(
                row.get("Mean_ZQ95", row.get(f"L{lvl}_Mean_ZQ95", 0.0))
            )
            vci = float(
                row.get("Mean_vci_1m", row.get(f"L{lvl}_Mean_vci_1m", 0.0))
            )
            parts = int(row.get("num_merged_parts", 1))
            area_m2 = float(row.geometry.area)

            for tag in poly_tags:
                items.append({
                    "svg_tag": tag,
                    "color": color,
                    "landcover": landcover,
                    "zq95": f"{zq95:.2f} m",
                    "vci": f"{vci:.3f}",
                    "parts": parts,
                    "area": f"{area_m2:.0f} m² ({area_m2 / 10000:.2f} ha)",
                    "config": desc or "Default",
                })
        layers_data[layer_name] = items

    legend_items_html = "".join(
        f'<div class="legend-item"><div class="legend-color" '
        f'style="background:{col};"></div><span>{label}</span></div>'
        for label, col in LANDCOVER_COLORS.items()
    )

    initial_layer = list(layers_data.keys())[-1]

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Polygon Segmentation, Intersection & Merging Visualizer</title>
<style>
  body {{
    font-family:
      -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin: 0; padding: 24px; background: #0f172a; color: #f8fafc;
  }}
  h1 {{ font-size: 22px; margin-bottom: 6px; font-weight: 700; }}
  p.subtitle {{ color: #94a3b8; font-size: 14px; margin: 0 0 20px 0; }}
  .container {{ display: flex; gap: 24px; max-width: 1200px; margin: 0 auto; }}
  .map-card {{
    background: #1e293b; border-radius: 12px; padding: 16px;
    border: 1px solid #334155; box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  }}
  .controls {{
    display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px;
  }}
  button.tab-btn {{
    background: #334155; color: #cbd5e1; border: none; padding: 7px 12px;
    border-radius: 6px; cursor: pointer; font-size: 12.5px; font-weight: 500;
  }}
  button.tab-btn.active {{ background: #3b82f6; color: white; }}
  svg.map-svg {{
    background: #090d16; border-radius: 8px; border: 1px solid #475569;
    cursor: crosshair; display: block;
  }}
  polygon {{
    stroke: #0f172a; stroke-width: 1; fill-opacity: 0.85;
    transition: fill-opacity 0.1s, stroke-width 0.1s;
  }}
  polygon:hover {{ fill-opacity: 1.0; stroke: #ffffff; stroke-width: 2.5; }}
  .info-panel {{
    width: 380px; background: #1e293b; border-radius: 12px; padding: 20px;
    border: 1px solid #334155; display: flex; flex-direction: column;
    justify-content: space-between;
  }}
  .info-card h3 {{
    margin-top: 0; font-size: 16px; color: #60a5fa;
    border-bottom: 1px solid #334155; padding-bottom: 8px;
  }}
  .info-row {{
    display: flex; justify-content: space-between;
    margin-bottom: 8px; font-size: 13px;
  }}
  .info-label {{ color: #94a3b8; }}
  .info-value {{ font-weight: 600; color: #f1f5f9; }}
  .legend {{ margin-top: 20px; }}
  .legend h4 {{
    margin: 0 0 10px 0; font-size: 13px; color: #94a3b8;
    text-transform: uppercase; letter-spacing: 0.5px;
  }}
  .legend-item {{
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 6px; font-size: 13px;
  }}
  .legend-color {{
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid rgba(255,255,255,0.2);
  }}
</style>
</head>
<body>
<div style="max-width: 1200px; margin: 0 auto;">
  <h1>Interactive Polygon Segmentation & Merge Visualizer</h1>
  <p class="subtitle">
    Hover over polygons to inspect attributes. Toggle between raw
    segmentation levels, Stage 1 intersections, and Stage 2 merge runs.
  </p>
</div>
<div class="container">
  <div class="map-card">
    <div class="controls" id="btn-group"></div>
    <svg class="map-svg" width="{svg_size}" height="{svg_size}"
         id="svg-map"></svg>
  </div>
  <div class="info-panel">
    <div class="info-card">
      <h3 id="info-title">Hover over a polygon</h3>
      <div id="info-body">
        <p style="color:#64748b; font-size:13px;">
          Move mouse over any polygon on the map to see height, density,
          landcover, and merge trial details.
        </p>
      </div>
    </div>
    <div class="legend">
      <h4>Stand Classes</h4>
      {legend_items_html}
    </div>
  </div>
</div>

<script>
const layersData = {json.dumps(layers_data)};
const layerNames = Object.keys(layersData);
const svgMap = document.getElementById("svg-map");
const btnGroup = document.getElementById("btn-group");

let currentLayer = {json.dumps(initial_layer)};

function renderControls() {{
  btnGroup.innerHTML = "";
  layerNames.forEach(name => {{
    const btn = document.createElement("button");
    btn.className = "tab-btn" + (name === currentLayer ? " active" : "");
    btn.innerText = name;
    btn.onclick = () => {{
      currentLayer = name;
      renderControls();
      renderMap();
    }};
    btnGroup.appendChild(btn);
  }});
}}

function renderMap() {{
  svgMap.innerHTML = "";
  const items = layersData[currentLayer] || [];
  items.forEach((item, idx) => {{
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.innerHTML = item.svg_tag + ' fill="' + item.color + '" data-idx="' +
      idx + '"></polygon>';
    const poly = g.firstChild;
    poly.onmouseenter = () => updateInfo(item);
    svgMap.appendChild(poly);
  }});
}}

function updateInfo(item) {{
  document.getElementById("info-title").innerText = item.landcover;
  let html = `
    <div class="info-row"><span class="info-label">Canopy (ZQ95):</span>
      <span class="info-value">${{item.zq95}}</span></div>
    <div class="info-row"><span class="info-label">Density (VCI):</span>
      <span class="info-value">${{item.vci}}</span></div>
    <div class="info-row"><span class="info-label">Merged Sub-Parts:</span>
      <span class="info-value">${{item.parts}}</span></div>
    <div class="info-row"><span class="info-label">Total Area:</span>
      <span class="info-value">${{item.area}}</span></div>
    <div class="info-row"><span class="info-label">Current Stage:</span>
      <span class="info-value">${{currentLayer}}</span></div>
  `;
  if (item.config && item.config !== "Default") {{
    html += `
      <div class="info-row"><span class="info-label">Trial Config:</span>
        <span class="info-value" style="color:#60a5fa;">${{item.config}}</span>
      </div>`;
  }}
  document.getElementById("info-body").innerHTML = html;
}}

renderControls();
renderMap();
</script>
</body>
</html>
"""
    output_html.parent.mkdir(parents=True, exist_ok=True)
    with output_html.open("w", encoding="utf-8") as f:
        f.write(html_content)
    LOGGER.info("Interactive HTML visualizer saved to %s", output_html)


def main(argv: typing.Sequence[str] | None = None) -> None:
    '''
    Run the visualization generator.

    Args:
        argv:
            Optional sequence of command-line argument strings.
    '''
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    LOGGER.info("Loading raw layers from %s...", args.source_gdb)
    avail_raw = {name for name, _ in pyogrio.list_layers(args.source_gdb)}
    raw_layers: dict[int, geopandas.GeoDataFrame] = {}
    for lvl in range(1, 5):
        matched = [
            n for n in avail_raw
            if n.endswith(f"_{lvl}") or n == f"level_{lvl}"
        ]
        layer_to_read = matched[0] if matched else f"segmented_objects_R1_{lvl}"
        raw_layers[lvl] = pyogrio.read_dataframe(
            args.source_gdb,
            layer=layer_to_read,
        )

    intersect_gdb = args.output_gdb or args.intersect_gdb
    if not intersect_gdb.exists() and args.output_gdb is None:
        intersect_gdb = DEFAULT_OUTPUT_GDB

    merge_gdb = args.output_gdb or args.merge_gdb
    if not merge_gdb.exists() and args.output_gdb is None:
        merge_gdb = DEFAULT_OUTPUT_GDB

    LOGGER.info("Loading intersected layer from %s...", intersect_gdb)
    if not intersect_gdb.exists():
        raise FileNotFoundError(
            f"Intersect dataset not found: {intersect_gdb}"
        )
    avail_intersect = {
        name for name, _ in pyogrio.list_layers(intersect_gdb)
    }
    intersect_candidates = [
        n for n in avail_intersect if n.startswith("intersected_")
    ]
    if not intersect_candidates:
        raise ValueError(f"No intersected layer found in {intersect_gdb}")

    LOGGER.info("Loading merged layers from %s...", merge_gdb)
    if not merge_gdb.exists():
        raise FileNotFoundError(f"Merge dataset not found: {merge_gdb}")
    avail_merge = {name for name, _ in pyogrio.list_layers(merge_gdb)}
    merge_candidates = sorted([
        n for n in avail_merge if n.startswith("merged_")
    ])
    if not merge_candidates:
        raise ValueError(f"No merged layer found in {merge_gdb}")

    intersected_gdf = pyogrio.read_dataframe(
        intersect_gdb, layer=intersect_candidates[0]
    )

    if len(merge_candidates) == 1:
        merged_input: (
            geopandas.GeoDataFrame
            | list[tuple[str, geopandas.GeoDataFrame, str]]
        ) = pyogrio.read_dataframe(merge_gdb, layer=merge_candidates[0])
    else:
        merged_trials: list[tuple[str, geopandas.GeoDataFrame, str]] = []
        for cand in merge_candidates:
            df = pyogrio.read_dataframe(merge_gdb, layer=cand)
            title = cand.replace("merged_trial_", "").replace("merged_", "")
            title = title.replace("_", " ").title()
            merged_trials.append((title, df, f"Layer: {cand}"))
        merged_input = merged_trials

    LOGGER.info(
        "Loaded %d intersection sub-polygons and %d merge candidate(s).",
        len(intersected_gdf),
        len(merge_candidates),
    )

    plot_comparison_figure(
        raw_layers=raw_layers,
        intersected_gdf=intersected_gdf,
        merged_gdf=merged_input,
        output_png=args.output_image,
    )

    generate_interactive_html(
        raw_layers=raw_layers,
        intersected_gdf=intersected_gdf,
        merged_gdf=merged_input,
        output_html=args.output_html,
    )


# ----- private helpers
def _normalize_merge_inputs(
    merged_input: (
        geopandas.GeoDataFrame
        | dict[str, tuple[geopandas.GeoDataFrame, str]]
        | list[tuple[str, geopandas.GeoDataFrame, str]]
    ),
) -> list[tuple[str, geopandas.GeoDataFrame, str | None]]:
    '''Normalize varied merged inputs into standard title-gdf-desc tuples.'''
    items: list[tuple[str, geopandas.GeoDataFrame, str | None]] = []
    if isinstance(merged_input, geopandas.GeoDataFrame):
        items.append(("Merged Product", merged_input, None))
    elif isinstance(merged_input, dict):
        for title, val in merged_input.items():
            if isinstance(val, (tuple, list)) and len(val) >= 2:
                items.append((str(title), val[0], str(val[1])))
            else:
                items.append((str(title), val, None))
    elif isinstance(merged_input, (list, tuple)):
        for entry in merged_input:
            if isinstance(entry, (tuple, list)):
                if len(entry) >= 3:
                    items.append(
                        (str(entry[0]), entry[1], str(entry[2]))
                    )
                elif len(entry) == 2:
                    items.append((str(entry[0]), entry[1], None))
                else:
                    items.append(("Merged Stand", entry[0], None))
            else:
                items.append(("Merged Stand", entry, None))
    return items


def _resolve_layer_color(row: typing.Any, level: int | None = None) -> str:
    '''Extract hex color from row or map from landcover label.'''
    if level is not None and f"L{level}_hex_color" in row:
        return str(row[f"L{level}_hex_color"])
    if "hex_color" in row and str(row["hex_color"]).startswith("#"):
        return str(row["hex_color"])
    for col in ("landcover", f"L{level}_landcover" if level else "landcover"):
        if col in row and row[col] in LANDCOVER_COLORS:
            return LANDCOVER_COLORS[str(row[col])]
    return "#5c7cfa"


if __name__ == "__main__":
    main()
