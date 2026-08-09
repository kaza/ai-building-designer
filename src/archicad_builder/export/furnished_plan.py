"""Architectural floor plan WITH furniture symbols.

Promoted from projects/villa-maketa/render_furnished_plan.py on
2026-08-09: 280 lines that mentioned the villa exactly once. The symbol
drawers (sofa, bed, toilet, bathtub, ...) are generic; WHICH furniture a
building has, and where, is project data in furniture.json.

Reuses the repo's floorplan renderer, keeps the matplotlib figure alive
(plt.close is suppressed during the call), then draws architectural furniture
symbols from furniture.json on top and saves a second PNG.

Symbols are drawn directly in data coordinates, parametrized by the item's
N/S/E/W facing (axis-aligned by construction) — no affine rotation involved.

"""

import json
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Ellipse, FancyBboxPatch, Rectangle

from archicad_builder.export import floorplan
from archicad_builder.models import Building


STYLE = {
    # type: (face color, edge color)
    "sofa": ("#D7CCC8", "#6D4C41"),
    "wood": ("#EFEBE9", "#6D4C41"),
    "counter": ("#ECEFF1", "#546E7A"),
    "bed": ("#FAF8F6", "#6D4C41"),
    "wardrobe": ("#D7CCC8", "#5D4037"),
    "ceramic": ("#FFFFFF", "#0277BD"),
    "sunbed": ("#EFEBE9", "#8D6E63"),  # pool loungers (feedback #031)
}
LW = 0.9  # symbol line width
Z = 6     # draw above the base plan


def edge_strip(x0, y0, x1, y1, side, t):
    """Rect (x, y, w, h) of a strip of thickness t hugging the given side."""
    return {
        "N": (x0, y1 - t, x1 - x0, t),
        "S": (x0, y0, x1 - x0, t),
        "E": (x1 - t, y0, t, y1 - y0),
        "W": (x0, y0, t, y1 - y0),
    }[side]


OPPOSITE = {"N": "S", "S": "N", "E": "W", "W": "E"}


def base_rect(ax, x0, y0, x1, y1, face, edge, **kw):
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor=face,
                           edgecolor=edge, linewidth=LW, zorder=Z, **kw))


def strip(ax, rect, edge):
    x, y, w, h = rect
    ax.add_patch(Rectangle((x, y), w, h, facecolor="none", edgecolor=edge,
                           linewidth=LW * 0.8, zorder=Z + 1))


def draw_sofa(ax, x0, y0, x1, y1, facing, face, edge):
    base_rect(ax, x0, y0, x1, y1, face, edge)
    back = OPPOSITE[facing]
    t = min(0.15, (x1 - x0) * 0.25, (y1 - y0) * 0.25)
    strip(ax, edge_strip(x0, y0, x1, y1, back, t), edge)
    # seat cushion divisions, perpendicular to the backrest and stopping at it
    seat = {"N": (y0, y1 - t), "S": (y0 + t, y1),
            "E": (x0, x1 - t), "W": (x0 + t, x1)}[back]
    if back in ("N", "S"):
        n = max(1, round((x1 - x0) / 0.7))
        for i in range(1, n):
            x = x0 + (x1 - x0) * i / n
            ax.add_line(Line2D([x, x], list(seat), color=edge, lw=LW * 0.6, zorder=Z + 1))
    else:
        n = max(1, round((y1 - y0) / 0.7))
        for i in range(1, n):
            y = y0 + (y1 - y0) * i / n
            ax.add_line(Line2D(list(seat), [y, y], color=edge, lw=LW * 0.6, zorder=Z + 1))


def draw_chair(ax, x0, y0, x1, y1, facing, face, edge):
    base_rect(ax, x0, y0, x1, y1, face, edge)
    strip(ax, edge_strip(x0, y0, x1, y1, OPPOSITE[facing], 0.07), edge)


def draw_bed(ax, x0, y0, x1, y1, face, edge, head="N"):
    base_rect(ax, x0, y0, x1, y1, face, edge)
    w, d = x1 - x0, y1 - y0
    # two pillows along the head edge, blanket fold line 1/3 up from the foot
    if head in ("N", "S"):
        py = (y1 - 0.45) if head == "N" else (y0 + 0.10)
        for i in (0, 1):
            ax.add_patch(FancyBboxPatch(
                (x0 + 0.08 + i * w / 2, py), w / 2 - 0.12, 0.35,
                boxstyle="round,pad=0.02,rounding_size=0.06",
                facecolor="white", edgecolor=edge, linewidth=LW * 0.7, zorder=Z + 1))
        fy = y0 + d * (0.33 if head == "N" else 0.67)
        for off in (0.0, 0.07):
            ax.add_line(Line2D([x0, x1], [fy - off, fy - off], color=edge,
                               lw=LW * 0.7 if off == 0 else LW * 0.5, zorder=Z + 1))
    else:
        px = (x1 - 0.45) if head == "E" else (x0 + 0.10)
        for i in (0, 1):
            ax.add_patch(FancyBboxPatch(
                (px, y0 + 0.08 + i * d / 2), 0.35, d / 2 - 0.12,
                boxstyle="round,pad=0.02,rounding_size=0.06",
                facecolor="white", edgecolor=edge, linewidth=LW * 0.7, zorder=Z + 1))
        fx = x0 + w * (0.33 if head == "E" else 0.67)
        for off in (0.0, 0.07):
            ax.add_line(Line2D([fx - off, fx - off], [y0, y1], color=edge,
                               lw=LW * 0.7 if off == 0 else LW * 0.5, zorder=Z + 1))


def draw_table(ax, x0, y0, x1, y1, face, edge):
    base_rect(ax, x0, y0, x1, y1, face, edge)
    m = 0.05
    ax.add_patch(Rectangle((x0 + m, y0 + m), x1 - x0 - 2 * m, y1 - y0 - 2 * m,
                           facecolor="none", edgecolor=edge, linewidth=LW * 0.5,
                           zorder=Z + 1))


def draw_counter(ax, x0, y0, x1, y1, face, edge):
    base_rect(ax, x0, y0, x1, y1, face, edge)
    # depth line marks the worktop edge
    if (x1 - x0) >= (y1 - y0):
        ax.add_line(Line2D([x0, x1], [y0 + (y1 - y0) * 0.15] * 2, color=edge,
                           lw=LW * 0.5, zorder=Z + 1))
    else:
        ax.add_line(Line2D([x0 + (x1 - x0) * 0.15] * 2, [y0, y1], color=edge,
                           lw=LW * 0.5, zorder=Z + 1))


def draw_wardrobe(ax, x0, y0, x1, y1, face, edge):
    base_rect(ax, x0, y0, x1, y1, face, edge)
    # rail along the long axis + a few hanger ticks
    if (x1 - x0) >= (y1 - y0):
        cy = (y0 + y1) / 2
        ax.add_line(Line2D([x0, x1], [cy, cy], color=edge, lw=LW * 0.5, zorder=Z + 1))
        n = max(2, int((x1 - x0) / 0.18))
        for i in range(1, n):
            x = x0 + (x1 - x0) * i / n
            ax.add_line(Line2D([x, x], [cy - 0.08, cy + 0.08], color=edge,
                               lw=LW * 0.4, zorder=Z + 1))
    else:
        cx = (x0 + x1) / 2
        ax.add_line(Line2D([cx, cx], [y0, y1], color=edge, lw=LW * 0.5, zorder=Z + 1))
        n = max(2, int((y1 - y0) / 0.18))
        for i in range(1, n):
            y = y0 + (y1 - y0) * i / n
            ax.add_line(Line2D([cx - 0.08, cx + 0.08], [y, y], color=edge,
                               lw=LW * 0.4, zorder=Z + 1))


def draw_toilet(ax, x0, y0, x1, y1, facing, edge):
    """Tank hugs the wall behind (OPPOSITE of facing); bowl points at facing."""
    w, d = x1 - x0, y1 - y0
    back = OPPOSITE[facing]
    tank_t = (d if back in ("N", "S") else w) * 0.3
    tx, ty, tw, th = edge_strip(x0, y0, x1, y1, back, tank_t)
    ax.add_patch(Rectangle((tx, ty), tw, th, facecolor="white",
                           edgecolor=edge, linewidth=LW, zorder=Z))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    bowl = {
        "S": ((cx, y0 + d * 0.38), w * 0.7, d * 0.62),
        "N": ((cx, y1 - d * 0.38), w * 0.7, d * 0.62),
        "W": ((x0 + w * 0.38, cy), w * 0.62, d * 0.7),
        "E": ((x1 - w * 0.38, cy), w * 0.62, d * 0.7),
    }[facing]
    ax.add_patch(Ellipse(bowl[0], bowl[1], bowl[2], facecolor="white",
                         edgecolor=edge, linewidth=LW, zorder=Z + 1))


def draw_sink(ax, x0, y0, x1, y1, face, edge):
    base_rect(ax, x0, y0, x1, y1, face, edge)
    ax.add_patch(Ellipse(((x0 + x1) / 2, (y0 + y1) / 2), (x1 - x0) * 0.65,
                         (y1 - y0) * 0.65, facecolor="none", edgecolor=edge,
                         linewidth=LW * 0.8, zorder=Z + 1))


def draw_bathtub(ax, x0, y0, x1, y1, face, edge):
    base_rect(ax, x0, y0, x1, y1, face, edge)
    m = 0.09
    ax.add_patch(FancyBboxPatch(
        (x0 + m, y0 + m), x1 - x0 - 2 * m, y1 - y0 - 2 * m,
        boxstyle="round,pad=0.02,rounding_size=0.12", facecolor="none",
        edgecolor=edge, linewidth=LW * 0.8, zorder=Z + 1))
    # drain sits at one short end of the tub
    if (x1 - x0) >= (y1 - y0):
        drain = (x0 + (x1 - x0) * 0.18, (y0 + y1) / 2)
    else:
        drain = ((x0 + x1) / 2, y0 + (y1 - y0) * 0.18)
    ax.add_patch(Ellipse(drain, 0.1, 0.1, facecolor="none", edgecolor=edge,
                         linewidth=LW * 0.7, zorder=Z + 2))


def draw_shower(ax, x0, y0, x1, y1, face, edge):
    base_rect(ax, x0, y0, x1, y1, "none", edge)
    ax.add_line(Line2D([x0, x1], [y0, y1], color=edge, lw=LW * 0.5, zorder=Z + 1))
    ax.add_line(Line2D([x0, x1], [y1, y0], color=edge, lw=LW * 0.5, zorder=Z + 1))


def draw_lounger(ax, x0, y0, x1, y1, face, edge):
    """Sunbed: rounded outline, head cushion at the far-from-pool end, slats."""
    ax.add_patch(FancyBboxPatch(
        (x0 + 0.03, y0 + 0.03), x1 - x0 - 0.06, y1 - y0 - 0.06,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        facecolor=face, edgecolor=edge, linewidth=LW, zorder=Z))
    # head cushion at the south end, slat lines across the rest
    ax.add_patch(Rectangle((x0 + 0.08, y0 + 0.1), (x1 - x0) - 0.16, 0.25,
                           facecolor="white", edgecolor=edge,
                           linewidth=LW * 0.7, zorder=Z + 1))
    n = max(2, int((y1 - y0 - 0.5) / 0.22))
    for i in range(1, n):
        y = y0 + 0.45 + (y1 - y0 - 0.55) * i / n
        ax.add_line(Line2D([x0 + 0.08, x1 - 0.08], [y, y], color=edge,
                           lw=LW * 0.4, zorder=Z + 1))


def draw_item(ax, item):
    x0, y0, x1, y1 = item["bounds"]
    t = item["type"]
    name = item["name"].lower()
    face, edge = STYLE[t]
    facing = item.get("facing", "S")
    area = (x1 - x0) * (y1 - y0)
    if t == "ceramic":
        if "toilet" in name:
            draw_toilet(ax, x0, y0, x1, y1, facing, edge)
        elif "sink" in name:
            draw_sink(ax, x0, y0, x1, y1, face, edge)
        elif "tub" in name:
            draw_bathtub(ax, x0, y0, x1, y1, face, edge)
        elif "shower" in name:
            draw_shower(ax, x0, y0, x1, y1, face, edge)
        else:
            base_rect(ax, x0, y0, x1, y1, face, edge)
    elif t == "sofa":
        draw_sofa(ax, x0, y0, x1, y1, facing, face, edge)
    elif t == "bed":
        draw_bed(ax, x0, y0, x1, y1, face, edge, head=item.get("head", "N"))
    elif t == "wardrobe":
        draw_wardrobe(ax, x0, y0, x1, y1, face, edge)
    elif t == "counter":
        draw_counter(ax, x0, y0, x1, y1, face, edge)
    elif t == "wood" and "lounger" in name:
        draw_lounger(ax, x0, y0, x1, y1, face, edge)
    elif t == "wood" and area < 0.25:
        draw_chair(ax, x0, y0, x1, y1, facing, face, edge)
    elif t == "wood":
        draw_table(ax, x0, y0, x1, y1, face, edge)
    else:
        base_rect(ax, x0, y0, x1, y1, face, edge)
    # Label larger pieces so proportions read at a glance
    if area >= 1.0:
        ax.text((x0 + x1) / 2, (y0 + y1) / 2, item["name"],
                ha="center", va="center", fontsize=6, style="italic",
                color="#4E342E", zorder=Z + 3)


def render_furnished_plan(story, furniture_items, out_path, title=None):
    """Base plan + furniture symbols on top, saved as one PNG.

    The base renderer closes its figure; we suppress that so the symbols
    can be drawn onto the same axes before saving.
    """
    with patch.object(floorplan.plt, "close", lambda *a, **k: None):
        floorplan.render_floorplan(
            story, out_path, title=title or f"{story.name} — furnished")
    fig = plt.gcf()
    ax = fig.axes[0]
    for item in furniture_items:
        draw_item(ax, item)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
