"""W100: furniture must not block door swings (specs/furniture-door-clearance.md).

`door_swing_geometry` is the single source of swing truth — the 2D floorplan
renderer consumes it too, so plan arcs and this validator cannot drift apart.
W100 is a conservative plan-view check: furniture height is ignored.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import Polygon, box

from archicad_builder.models.building import Story
from archicad_builder.models.elements import Door, DoorOperationType, Wall
from archicad_builder.validators.structural import ValidationError

# Below-threshold overlaps are noise (matches the E090 precedent's spirit;
# swing overlaps read slightly tighter than room overlaps).
OVERLAP_TOLERANCE_M2 = 0.02
MIN_DOOR_WIDTH_M = 0.05
ARC_SEGMENTS = 16

_SUPPORTED = {
    DoorOperationType.SINGLE_SWING_LEFT,
    DoorOperationType.SINGLE_SWING_RIGHT,
}


@dataclass(frozen=True)
class SwingGeometry:
    """Hinge point, closed/open unit rays, and the swept sector polygon."""

    hinge: tuple[float, float]
    closed_ray: tuple[float, float]
    open_ray: tuple[float, float]
    sector: Polygon


@dataclass(frozen=True)
class FurnitureFootprint:
    """Plan-view footprint of one furniture item (framework-side contract).

    The framework has no furniture data model; projects map their own
    furniture representation onto this. `id` must be stable and unique —
    findings are ordered by it.
    """

    id: str
    name: str
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError(f"footprint id must be a non-empty string, got {self.id!r}")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(f"footprint '{self.id}': name must be a non-empty string")
        vals = (self.min_x, self.min_y, self.max_x, self.max_y)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in vals):
            raise ValueError(f"footprint '{self.id}': bounds must be numbers, got {vals!r}")
        if any(not math.isfinite(v) for v in vals):
            raise ValueError(f"footprint '{self.id}': non-finite bounds {vals}")
        if self.min_x > self.max_x or self.min_y > self.max_y:
            raise ValueError(f"footprint '{self.id}': min > max in bounds {vals}")


def door_swing_geometry(door: Door, wall: Wall) -> SwingGeometry | None:
    """The swing geometry of a single-swing door, or None when there is none.

    None means "this door type/geometry has no computable swing" (sliding,
    double, degenerate width, zero-length wall) — never a guess.
    """
    if door.operation_type not in _SUPPORTED:
        return None
    if door.width <= MIN_DOOR_WIDTH_M or wall.length < 1e-6:
        return None

    dx = (wall.end.x - wall.start.x) / wall.length
    dy = (wall.end.y - wall.start.y) / wall.length
    nx, ny = -dy, dx  # left-hand normal — same convention as the renderer

    door_start = (wall.start.x + dx * door.position,
                  wall.start.y + dy * door.position)
    door_end = (door_start[0] + dx * door.width, door_start[1] + dy * door.width)

    if door.operation_type == DoorOperationType.SINGLE_SWING_RIGHT:
        hinge, closed = door_end, (-dx, -dy)
    else:
        hinge, closed = door_start, (dx, dy)
    sign = 1.0 if door.swing_inward else -1.0
    open_ray = (sign * nx, sign * ny)

    # Sweep the 90° sector from the closed ray to the open ray the short way.
    a0 = math.atan2(closed[1], closed[0])
    a1 = math.atan2(open_ray[1], open_ray[0])
    diff = (a1 - a0) % (2 * math.pi)
    if diff > math.pi:
        diff -= 2 * math.pi  # go the other way — this is the 270°-wrap case
    r = door.width
    points = [hinge]
    for i in range(ARC_SEGMENTS + 1):
        a = a0 + diff * i / ARC_SEGMENTS
        points.append((hinge[0] + r * math.cos(a), hinge[1] + r * math.sin(a)))
    sector = Polygon(points)
    return SwingGeometry(hinge=hinge, closed_ray=closed, open_ray=open_ray,
                         sector=sector)


def check_furniture_clearance(
    story: Story, footprints: list[FurnitureFootprint]
) -> list[ValidationError]:
    """W100 for every (door, footprint) pair overlapping above tolerance."""
    walls_by_id = {w.global_id: w for w in story.walls}
    findings: list[ValidationError] = []
    # compound key from AUTHORED data only — wall_id is a regenerated IFC id
    # and would flip ordering between rebuilds of identical geometry
    doors = sorted(story.doors, key=lambda d: (d.name, d.position, d.width))
    for door in doors:
        wall = walls_by_id.get(door.wall_id)
        if wall is None:
            continue
        geom = door_swing_geometry(door, wall)
        if geom is None:
            continue
        for fp in sorted(footprints, key=lambda f: f.id):
            rect = box(fp.min_x, fp.min_y, fp.max_x, fp.max_y)
            overlap = geom.sector.intersection(rect).area
            # epsilon guard: float jitter must not make mirrored geometry
            # behave differently at exactly the threshold
            if overlap > OVERLAP_TOLERANCE_M2 + 1e-9:
                findings.append(ValidationError(
                    severity="warning",
                    element_type="door",
                    element_id=door.name,
                    message=(
                        f"W100: Furniture '{fp.name}' blocks door "
                        f"'{door.name}' swing (overlap {overlap:.2f}m²)."
                    ),
                ))
    return findings
