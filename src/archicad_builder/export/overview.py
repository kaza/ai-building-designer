"""Building overview rendering — all stories side by side.

Generates a single image showing all floor plans in a grid layout.
Useful for quick visual validation of multi-storey buildings.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from archicad_builder.models.building import Building
from archicad_builder.export.floorplan import render_floorplan


def render_overview(
    building: Building,
    output_path: str | Path,
    dpi: int = 150,
    max_cols: int = 4,
) -> Path:
    """Render all floor plans in a grid layout.

    Args:
        building: Building to render.
        output_path: Output image path.
        dpi: Image resolution.
        max_cols: Maximum columns in the grid.

    Returns:
        Path to the output image.
    """
    output_path = Path(output_path)
    n = len(building.stories)
    if n == 0:
        raise ValueError("Building has no stories to render")

    cols = min(n, max_cols)
    rows = math.ceil(n / cols)

    # Render each floor to a temp file, then compose
    import tempfile
    temp_dir = Path(tempfile.mkdtemp())
    temp_paths = []
    for i, story in enumerate(building.stories):
        temp_path = temp_dir / f"floor_{i}.png"
        render_floorplan(
            story, temp_path,
            title=f"{story.name} (elev {story.elevation}m)",
            dpi=dpi,
            show_labels=True,
            show_dimensions=False,  # Less clutter in overview
            show_info_box=False,
        )
        temp_paths.append(temp_path)

    # Compose grid
    fig, axes = plt.subplots(rows, cols, figsize=(6 * cols, 5 * rows))
    fig.suptitle(f"{building.name} — Building Overview", fontsize=16, fontweight="bold")

    # Handle axes shape
    if rows == 1 and cols == 1:
        axes = [[axes]]
    elif rows == 1:
        axes = [axes]
    elif cols == 1:
        axes = [[ax] for ax in axes]

    for i, temp_path in enumerate(temp_paths):
        row = i // cols
        col = i % cols
        ax = axes[row][col]
        img = plt.imread(str(temp_path))
        ax.imshow(img)
        ax.axis("off")

    # Hide empty axes
    for i in range(n, rows * cols):
        row = i // cols
        col = i % cols
        axes[row][col].axis("off")

    plt.tight_layout()
    fig.savefig(str(output_path), dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    # Cleanup
    for tp in temp_paths:
        tp.unlink()
    temp_dir.rmdir()

    return output_path
