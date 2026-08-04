"""Architectural floor plan WITH furniture overlay.

Reuses the repo's floorplan renderer, keeps the matplotlib figure alive
(plt.close is suppressed during the call), then draws furniture.json boxes
on top and saves a second PNG.

Run: .venv/bin/python projects/villa-maketa/render_furnished_plan.py
"""

import json
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from archicad_builder.export import floorplan
from archicad_builder.models import Building

HERE = Path(__file__).parent
OUT = HERE / "output" / "floor_ground_floor_furnished.png"

STYLE = {
    # type: (face color, edge color)
    "sofa": ("#D7CCC8", "#8D6E63"),
    "wood": ("#BCAAA4", "#6D4C41"),
    "counter": ("#CFD8DC", "#546E7A"),
    "bed": ("#EFEBE9", "#8D6E63"),
    "wardrobe": ("#A1887F", "#5D4037"),
    "ceramic": ("#E1F5FE", "#0277BD"),
}

building = Building.load(HERE / "building.json")
furniture = json.loads((HERE / "furniture.json").read_text())

# Render the base plan but keep the figure open so we can draw on it
story = building.get_story("Ground Floor")
with patch.object(floorplan.plt, "close", lambda *a, **k: None):
    floorplan.render_floorplan(story, OUT, title="Ground Floor — furnished")

fig = plt.gcf()
ax = fig.axes[0]

for item in furniture["items"]:
    x0, y0, x1, y1 = item["bounds"]
    face, edge = STYLE[item["type"]]
    ax.add_patch(Rectangle(
        (x0, y0), x1 - x0, y1 - y0,
        facecolor=face, edgecolor=edge, linewidth=1.0, zorder=6, alpha=0.9,
    ))
    # Label larger pieces so proportions read at a glance
    if (x1 - x0) * (y1 - y0) >= 1.0:
        ax.text((x0 + x1) / 2, (y0 + y1) / 2, item["name"],
                ha="center", va="center", fontsize=6, style="italic",
                color="#4E342E", zorder=7)

fig.savefig(OUT, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"Saved {OUT}")
