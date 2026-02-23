"""2D floor plan rendering using matplotlib.

Generates architectural-style top-down views:
- Walls as thick lines with hatching
- Doors shown as arcs (swing indication)
- Windows shown as double lines (glass indication)
- Dimensions and labels
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless rendering
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.patheffects as pe
from matplotlib.patches import Arc, FancyArrowPatch
import numpy as np

# Halo effect for text readability on any background
_TEXT_HALO = [pe.withStroke(linewidth=3, foreground="black")]

from archicad_builder.models.building import Building, Story
from archicad_builder.models.elements import DoorOperationType, Staircase, Wall, Door, Window
from archicad_builder.models.spaces import Apartment, RoomType, Space


def _wall_direction(wall: Wall) -> tuple[float, float]:
    """Unit direction vector of a wall."""
    dx = wall.end.x - wall.start.x
    dy = wall.end.y - wall.start.y
    length = wall.length
    return (dx / length, dy / length)


def _wall_normal(wall: Wall) -> tuple[float, float]:
    """Left-hand normal of wall direction."""
    dx, dy = _wall_direction(wall)
    return (-dy, dx)


def render_floorplan(
    story: Story,
    output_path: str | Path,
    title: str | None = None,
    dpi: int = 150,
    show_dimensions: bool = True,
    show_labels: bool = True,
    show_names: bool = True,
    show_title: bool = True,
    show_info_box: bool = True,
) -> Path:
    """Render a 2D floor plan of a story to PNG.

    Args:
        story: The story to render.
        output_path: Output image path.
        title: Plot title (defaults to story name).
        dpi: Image resolution.
        show_dimensions: Show wall length dimensions.
        show_labels: Show element tags (W1, D1, etc.).
        show_names: Show element names (long text). Only if show_labels is True.
        show_title: Show title bar at top.
        show_info_box: Show info overlay (floor area, wall count).

    Returns:
        Path to the output image.
    """
    output_path = Path(output_path)
    fig, ax = plt.subplots(1, 1, figsize=(12, 10))

    ax.set_aspect("equal")
    ax.set_facecolor("#FAFAFA")
    fig.patch.set_facecolor("white")

    # Draw slabs (floor fill)
    for slab in story.slabs:
        if slab.is_floor:
            xs = [v.x for v in slab.outline.vertices]
            ys = [v.y for v in slab.outline.vertices]
            ax.fill(xs, ys, color="#F0F0F0", zorder=1)

    # Auto-generate tags if needed
    story.ensure_tags()

    # Draw apartment fills (each apartment gets a distinct color)
    _APT_COLORS = [
        "#BBDEFB",  # blue
        "#C8E6C9",  # green
        "#FFE0B2",  # orange
        "#E1BEE7",  # purple
        "#FFCCBC",  # salmon
        "#B2EBF2",  # teal
        "#FFF9C4",  # yellow
        "#D7CCC8",  # brown
    ]
    for i, apt in enumerate(story.apartments):
        apt_color = _APT_COLORS[i % len(_APT_COLORS)]
        # Fill apartment boundary
        bv = apt.boundary.vertices
        bx = [v.x for v in bv]
        by = [v.y for v in bv]
        ax.fill(bx, by, color=apt_color, alpha=0.25, zorder=2)
        ax.plot(bx + [bx[0]], by + [by[0]], color=apt_color,
                linewidth=2.0, alpha=0.6, zorder=3)
        # Label apartment name at centroid
        cx = sum(bx) / len(bx)
        cy = sum(by) / len(by)
        ax.text(cx, cy, apt.name, fontsize=9, ha="center", va="center",
                fontweight="bold", color="#424242", alpha=0.7, zorder=4)
        # Draw individual rooms
        for space in apt.spaces:
            _draw_space(ax, space, show_labels, apt_color=apt_color)

    # Draw story-level spaces (not in apartments)
    for space in story.spaces:
        _draw_space(ax, space, show_labels)

    # Draw walls
    for wall in story.walls:
        _draw_wall(ax, wall, show_dimensions, show_labels, show_names)

    # Draw doors
    for door in story.doors:
        host_wall = story.get_wall(door.wall_id)
        if host_wall:
            _draw_door(ax, door, host_wall, show_labels, show_dimensions)

    # Draw staircases
    for staircase in story.staircases:
        _draw_staircase(ax, staircase, show_labels)

    # Draw windows
    for window in story.windows:
        host_wall = story.get_wall(window.wall_id)
        if host_wall:
            _draw_window(ax, window, host_wall, show_labels, show_dimensions)

    # Title
    if show_title:
        ax.set_title(
            title or story.name,
            fontsize=16,
            fontweight="bold",
            pad=20,
        )

    # Grid and labels
    ax.grid(True, alpha=0.2, linestyle="--")
    ax.set_xlabel("X (meters)", fontsize=10)
    ax.set_ylabel("Y (meters)", fontsize=10)

    # Auto-pad the view
    margin = 1.5
    all_x = []
    all_y = []
    for wall in story.walls:
        all_x.extend([wall.start.x, wall.end.x])
        all_y.extend([wall.start.y, wall.end.y])
    if all_x and all_y:
        ax.set_xlim(min(all_x) - margin, max(all_x) + margin)
        ax.set_ylim(min(all_y) - margin, max(all_y) + margin)

    # Info box
    if show_info_box:
        lb_count = sum(1 for w in story.walls if w.load_bearing)
        part_count = len(story.walls) - lb_count
        info_lines = [
            f"Floor area: {sum(s.area for s in story.slabs if s.is_floor):.1f} m²",
            f"Walls: {len(story.walls)} ({lb_count} load-bearing [green], {part_count} partition [yellow])",
            f"Doors: {len(story.doors)}",
            f"Windows: {len(story.windows)}",
            f"Staircases: {len(story.staircases)}" if story.staircases else "",
            f"Wall height: {story.walls[0].height:.1f}m" if story.walls else "",
        ]
        info_text = "\n".join(line for line in info_lines if line)
        ax.text(
            0.02, 0.98, info_text,
            transform=ax.transAxes,
            fontsize=8,
            verticalalignment="top",
            fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="white", alpha=0.8, edgecolor="#CCCCCC"),
            zorder=100,
        )

    plt.tight_layout()
    fig.savefig(str(output_path), dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    return output_path


def _wall_color(wall: Wall) -> tuple[str, str]:
    """Return (fill_color, outline_color) based on wall type.

    Load-bearing: green (like architectural plans)
    Partition: amber/yellow
    """
    if wall.load_bearing:
        return "#2E7D32", "#1B5E20"  # green
    return "#F9A825", "#F57F17"  # amber/yellow


def _draw_wall(
    ax: plt.Axes,
    wall: Wall,
    show_dimensions: bool,
    show_labels: bool,
    show_names: bool = True,
) -> None:
    """Draw a wall as a thick filled rectangle, colored by type."""
    dx, dy = _wall_direction(wall)
    nx, ny = _wall_normal(wall)
    t = wall.thickness / 2
    fill_color, outline_color = _wall_color(wall)

    # Four corners of the wall rectangle
    corners_x = [
        wall.start.x + nx * t,
        wall.end.x + nx * t,
        wall.end.x - nx * t,
        wall.start.x - nx * t,
    ]
    corners_y = [
        wall.start.y + ny * t,
        wall.end.y + ny * t,
        wall.end.y - ny * t,
        wall.start.y - ny * t,
    ]

    # Fill wall
    ax.fill(corners_x, corners_y, color=fill_color, zorder=10)

    # Wall outline
    ax.plot(
        corners_x + [corners_x[0]],
        corners_y + [corners_y[0]],
        color=outline_color,
        linewidth=0.5,
        zorder=11,
    )

    mid_x = (wall.start.x + wall.end.x) / 2
    mid_y = (wall.start.y + wall.end.y) / 2

    # Tag label (prominent, on the wall)
    if show_labels and wall.tag:
        ax.text(
            mid_x,
            mid_y,
            wall.tag,
            fontsize=8,
            ha="center",
            va="center",
            color="white",
            fontweight="bold",
            rotation=math.degrees(math.atan2(dy, dx)),
            path_effects=_TEXT_HALO,
            zorder=25,
        )

    # Dimension text
    if show_dimensions:
        offset = 0.4
        ax.text(
            mid_x + nx * offset,
            mid_y + ny * offset,
            f"{wall.length:.1f}m",
            fontsize=7,
            ha="center",
            va="center",
            color="#CCCCCC",
            rotation=math.degrees(math.atan2(dy, dx)),
            path_effects=_TEXT_HALO,
            zorder=20,
        )

    # Name label (below wall, subtle)
    if show_labels and show_names and wall.name:
        ax.text(
            mid_x - nx * 0.4,
            mid_y - ny * 0.4,
            wall.name,
            fontsize=5,
            ha="center",
            va="center",
            color="#DDDDDD",
            style="italic",
            rotation=math.degrees(math.atan2(dy, dx)),
            path_effects=_TEXT_HALO,
            zorder=20,
        )


def _draw_door(
    ax: plt.Axes,
    door: Door,
    wall: Wall,
    show_labels: bool,
    show_dimensions: bool = True,
) -> None:
    """Draw a door as a gap in the wall with an arc swing.

    Uses door.operation_type (hinge side) and door.swing_inward (direction)
    to draw the correct arc. Follows IFC conventions:
    - SINGLE_SWING_LEFT: hinge at door start (left viewed from normal side)
    - SINGLE_SWING_RIGHT: hinge at door end (right viewed from normal side)
    - swing_inward=True: swings toward wall normal side
    - swing_inward=False: swings away from wall normal side
    """
    dx, dy = _wall_direction(wall)
    nx, ny = _wall_normal(wall)
    t = wall.thickness / 2

    # Door position along wall
    door_start_x = wall.start.x + dx * door.position
    door_start_y = wall.start.y + dy * door.position
    door_end_x = door_start_x + dx * door.width
    door_end_y = door_start_y + dy * door.width

    # Clear the wall area where the door is (white rectangle)
    corners_x = [
        door_start_x + nx * (t + 0.02),
        door_end_x + nx * (t + 0.02),
        door_end_x - nx * (t + 0.02),
        door_start_x - nx * (t + 0.02),
    ]
    corners_y = [
        door_start_y + ny * (t + 0.02),
        door_end_y + ny * (t + 0.02),
        door_end_y - ny * (t + 0.02),
        door_start_y - ny * (t + 0.02),
    ]
    ax.fill(corners_x, corners_y, color="#FAFAFA", zorder=12)

    # Determine hinge position from operation_type
    is_right = door.operation_type == DoorOperationType.SINGLE_SWING_RIGHT

    if is_right:
        hinge_x, hinge_y = door_end_x, door_end_y
        # Closed position: door panel points back toward door start (-wall direction)
        closed_dx, closed_dy = -dx, -dy
    else:
        hinge_x, hinge_y = door_start_x, door_start_y
        # Closed position: door panel points toward door end (wall direction)
        closed_dx, closed_dy = dx, dy

    # Determine swing direction
    swing_sign = 1 if door.swing_inward else -1
    open_dx = swing_sign * nx
    open_dy = swing_sign * ny

    # Compute arc angles (matplotlib Arc uses CCW from theta1 to theta2)
    angle_closed = math.degrees(math.atan2(closed_dy, closed_dx))
    angle_open = math.degrees(math.atan2(open_dy, open_dx))

    # Ensure 90° arc going the short way
    diff = (angle_open - angle_closed) % 360
    if diff > 180:
        theta1, theta2 = angle_open, angle_open + (360 - diff)
    else:
        theta1, theta2 = angle_closed, angle_closed + diff

    arc = Arc(
        (hinge_x, hinge_y),
        door.width * 2,
        door.width * 2,
        angle=0,
        theta1=theta1,
        theta2=theta2,
        color="#2196F3",
        linewidth=1.0,
        linestyle="--",
        zorder=15,
    )
    ax.add_patch(arc)

    # Door leaf line (open position)
    leaf_x = hinge_x + open_dx * door.width
    leaf_y = hinge_y + open_dy * door.width
    ax.plot(
        [hinge_x, leaf_x],
        [hinge_y, leaf_y],
        color="#2196F3",
        linewidth=1.5,
        zorder=15,
    )

    # Tag label
    if show_labels and door.tag:
        ax.text(
            (door_start_x + door_end_x) / 2 + nx * 0.6,
            (door_start_y + door_end_y) / 2 + ny * 0.6,
            door.tag,
            fontsize=7,
            ha="center",
            va="center",
            color="#64B5F6",
            fontweight="bold",
            path_effects=_TEXT_HALO,
            zorder=20,
        )

    # Door dimension (width)
    if show_dimensions:
        ax.text(
            (door_start_x + door_end_x) / 2 - nx * 0.4,
            (door_start_y + door_end_y) / 2 - ny * 0.4,
            f"{door.width:.2f}m",
            fontsize=6,
            ha="center",
            va="center",
            color="#90CAF9",
            path_effects=_TEXT_HALO,
            zorder=20,
        )


def _draw_window(
    ax: plt.Axes,
    window: Window,
    wall: Wall,
    show_labels: bool,
    show_dimensions: bool = True,
) -> None:
    """Draw a window as a gap with double lines (glass symbol)."""
    dx, dy = _wall_direction(wall)
    nx, ny = _wall_normal(wall)
    t = wall.thickness / 2

    # Window position along wall
    win_start_x = wall.start.x + dx * window.position
    win_start_y = wall.start.y + dy * window.position
    win_end_x = win_start_x + dx * window.width
    win_end_y = win_start_y + dy * window.width

    # Clear wall where window is
    corners_x = [
        win_start_x + nx * (t + 0.02),
        win_end_x + nx * (t + 0.02),
        win_end_x - nx * (t + 0.02),
        win_start_x - nx * (t + 0.02),
    ]
    corners_y = [
        win_start_y + ny * (t + 0.02),
        win_end_y + ny * (t + 0.02),
        win_end_y - ny * (t + 0.02),
        win_start_y - ny * (t + 0.02),
    ]
    ax.fill(corners_x, corners_y, color="#FAFAFA", zorder=12)

    # Double lines for glass
    glass_offset = t * 0.3
    for sign in [-1, 1]:
        line_x = [
            win_start_x + nx * glass_offset * sign,
            win_end_x + nx * glass_offset * sign,
        ]
        line_y = [
            win_start_y + ny * glass_offset * sign,
            win_end_y + ny * glass_offset * sign,
        ]
        ax.plot(line_x, line_y, color="#4CAF50", linewidth=1.5, zorder=15)

    # Connecting lines at ends
    for sx, sy in [(win_start_x, win_start_y), (win_end_x, win_end_y)]:
        ax.plot(
            [sx + nx * glass_offset, sx - nx * glass_offset],
            [sy + ny * glass_offset, sy - ny * glass_offset],
            color="#4CAF50",
            linewidth=1.0,
            zorder=15,
        )

    # Tag label
    if show_labels and window.tag:
        ax.text(
            (win_start_x + win_end_x) / 2 + nx * 0.5,
            (win_start_y + win_end_y) / 2 + ny * 0.5,
            window.tag,
            fontsize=7,
            ha="center",
            va="center",
            color="#81C784",
            fontweight="bold",
            path_effects=_TEXT_HALO,
            zorder=20,
        )

    # Window dimension (width)
    if show_dimensions:
        ax.text(
            (win_start_x + win_end_x) / 2 - nx * 0.4,
            (win_start_y + win_end_y) / 2 - ny * 0.4,
            f"{window.width:.2f}m",
            fontsize=6,
            ha="center",
            va="center",
            color="#A5D6A7",
            path_effects=_TEXT_HALO,
            zorder=20,
        )


def _draw_staircase(
    ax: plt.Axes,
    staircase: Staircase,
    show_labels: bool,
) -> None:
    """Draw a staircase as a hatched polygon with diagonal lines (stair symbol).

    Standard architectural convention: diagonal parallel lines inside
    the staircase outline indicate steps, with an arrow showing direction of ascent.
    """
    vertices = staircase.outline.vertices
    xs = [v.x for v in vertices]
    ys = [v.y for v in vertices]

    # Fill with light purple/blue
    ax.fill(xs, ys, color="#E1BEE7", alpha=0.5, zorder=5)

    # Outline
    ax.plot(
        xs + [xs[0]], ys + [ys[0]],
        color="#7B1FA2", linewidth=1.0, zorder=11,
    )

    # Draw diagonal lines (step indication)
    # Get bounding box
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    w = max_x - min_x
    h = max_y - min_y

    # Draw horizontal step lines across the staircase
    num_lines = int(h / 0.3)  # ~0.3m per step visualization
    for i in range(1, num_lines):
        line_y = min_y + i * (h / num_lines)
        ax.plot(
            [min_x, max_x], [line_y, line_y],
            color="#7B1FA2", linewidth=0.3, alpha=0.5, zorder=6,
        )

    # Arrow showing ascent direction (up = +Y)
    ax.annotate(
        "", xy=(cx, max_y - 0.2), xytext=(cx, min_y + 0.2),
        arrowprops=dict(arrowstyle="->", color="#7B1FA2", lw=1.5),
        zorder=12,
    )

    # Tag label
    if show_labels and staircase.tag:
        ax.text(
            cx, cy, staircase.tag,
            fontsize=8, ha="center", va="center",
            color="#7B1FA2", fontweight="bold",
            path_effects=_TEXT_HALO,
            zorder=25,
        )


# Room type → (fill_color, alpha)
_ROOM_COLORS: dict[RoomType, tuple[str, float]] = {
    RoomType.LIVING: ("#BBDEFB", 0.3),    # light blue
    RoomType.BEDROOM: ("#C8E6C9", 0.3),   # light green
    RoomType.KITCHEN: ("#FFE0B2", 0.3),    # light orange
    RoomType.BATHROOM: ("#B3E5FC", 0.4),   # cyan
    RoomType.TOILET: ("#B3E5FC", 0.4),     # cyan
    RoomType.HALLWAY: ("#F5F5F5", 0.3),    # light grey
    RoomType.CORRIDOR: ("#EEEEEE", 0.2),   # very light grey
    RoomType.STORAGE: ("#D7CCC8", 0.3),    # beige
}


def _draw_space(
    ax: plt.Axes,
    space: Space,
    show_labels: bool,
    apt_color: str | None = None,
) -> None:
    """Draw a space/room as a colored filled polygon with label."""
    vertices = space.boundary.vertices
    xs = [v.x for v in vertices]
    ys = [v.y for v in vertices]

    if apt_color:
        # Use apartment color with room-type-specific alpha
        _, base_alpha = _ROOM_COLORS.get(space.room_type, ("#E0E0E0", 0.2))
        color = apt_color
        alpha = base_alpha + 0.15  # slightly more opaque for rooms
    else:
        color, alpha = _ROOM_COLORS.get(space.room_type, ("#E0E0E0", 0.2))

    # Fill
    ax.fill(xs, ys, color=color, alpha=alpha, zorder=2)

    # Outline (subtle dashed)
    ax.plot(
        xs + [xs[0]], ys + [ys[0]],
        color="#9E9E9E", linewidth=0.5, linestyle=":", zorder=3,
    )

    # Label
    if show_labels:
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        label = space.room_type.value.capitalize()
        if space.name:
            label = space.name.split()[-1]  # Last word (e.g., "Living" from "Apt 1 Living")
        ax.text(
            cx, cy, label,
            fontsize=6, ha="center", va="center",
            color="#616161", style="italic",
            zorder=4,
        )
