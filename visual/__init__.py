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
Multi-scale polygon segmentation visualization module.

Provides publication-quality static comparison graphics and interactive
HTML SVG viewers for inspecting raw segmentation levels, Stage 1
intersections, and Stage 2 merged polygon stands.

Public APIs:
    - `LANDCOVER_COLORS`: Mapping of vegetation classes to hex colors.
    - `plot_comparison_figure`: Render multi-panel comparison graphic.
    - `generate_interactive_html`: Render self-contained HTML viewer.
    - `render_workflow_visualizations`: Load layers and render both.
'''

# local imports
from visual.renderer import LANDCOVER_COLORS
from visual.renderer import generate_interactive_html
from visual.renderer import plot_comparison_figure
from visual.renderer import render_workflow_visualizations

__all__ = [
    "LANDCOVER_COLORS",
    "generate_interactive_html",
    "plot_comparison_figure",
    "render_workflow_visualizations",
]
