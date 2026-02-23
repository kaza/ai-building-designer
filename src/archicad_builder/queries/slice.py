"""Floor plan slice — extract one apartment's data.

When the AI needs to reason about a single apartment, it shouldn't
have to process the entire building. This module extracts just the
walls, doors, windows, and rooms for one apartment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from archicad_builder.models.building import Building, Story
from archicad_builder.models.elements import Door, Wall, Window
from archicad_builder.models.geometry import Point2D
from archicad_builder.models.spaces import Apartment, Space


@dataclass
class ApartmentSlice:
    """Extracted data for one apartment — minimal context for AI reasoning."""

    apartment_name: str
    storey_name: str
    area: float
    rooms: list[dict[str, Any]] = field(default_factory=list)
    walls: list[dict[str, Any]] = field(default_factory=list)
    doors: list[dict[str, Any]] = field(default_factory=list)
    windows: list[dict[str, Any]] = field(default_factory=list)
    boundary: list[tuple[float, float]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to plain dict for JSON serialization."""
        return {
            "apartment_name": self.apartment_name,
            "storey_name": self.storey_name,
            "area": self.area,
            "boundary": self.boundary,
            "rooms": self.rooms,
            "walls": self.walls,
            "doors": self.doors,
            "windows": self.windows,
        }

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [f"🏠 {self.apartment_name} ({self.storey_name})"]
        lines.append(f"   Area: {self.area:.1f}m²")
        lines.append(f"   Rooms: {len(self.rooms)}")
        for room in self.rooms:
            lines.append(f"     - {room['name']} ({room['type']}) {room['area']:.1f}m²")
        lines.append(f"   Walls: {len(self.walls)}")
        lines.append(f"   Doors: {len(self.doors)}")
        lines.append(f"   Windows: {len(self.windows)}")
        return "\n".join(lines)


def extract_apartment(
    building: Building,
    storey_name: str,
    apartment_name: str,
    include_shared_walls: bool = True,
    tolerance: float = 0.3,
) -> ApartmentSlice:
    """Extract one apartment's data from the building.

    Finds all walls, doors, and windows that belong to or border
    the specified apartment. This gives the AI minimal context for
    reasoning about one apartment without full building noise.

    Args:
        building: The building model.
        storey_name: Storey containing the apartment.
        apartment_name: Name of the apartment to extract.
        include_shared_walls: Include walls shared with neighbors
                              (exterior walls, corridor walls).
        tolerance: Distance tolerance for wall matching.

    Returns:
        ApartmentSlice with the apartment's data.

    Raises:
        ValueError: If storey or apartment not found.
    """
    story = building._require_story(storey_name)

    # Find the apartment
    apt = None
    for a in story.apartments:
        if a.name.lower() == apartment_name.lower():
            apt = a
            break
    if apt is None:
        available = [a.name for a in story.apartments]
        raise ValueError(
            f"Apartment '{apartment_name}' not found in '{storey_name}'. "
            f"Available: {available}"
        )

    # Get apartment bounding box
    verts = apt.boundary.vertices
    min_x = min(v.x for v in verts) - tolerance
    max_x = max(v.x for v in verts) + tolerance
    min_y = min(v.y for v in verts) - tolerance
    max_y = max(v.y for v in verts) + tolerance

    # Find walls within or touching the apartment boundary
    apt_walls: list[Wall] = []
    for wall in story.walls:
        if _wall_in_bbox(wall, min_x, max_x, min_y, max_y):
            # Check if this wall is interior to the apartment
            # or a boundary wall (shared with neighbors/exterior)
            is_apt_wall = _is_apartment_wall(wall, apt, tolerance)
            is_boundary = wall.is_external or _is_corridor_wall(wall)

            if is_apt_wall or (include_shared_walls and is_boundary):
                apt_walls.append(wall)

    # Find doors on the apartment's walls
    wall_ids = {w.global_id for w in apt_walls}
    apt_doors: list[Door] = []
    for door in story.doors:
        if door.wall_id in wall_ids:
            apt_doors.append(door)

    # Find windows on the apartment's walls
    apt_windows: list[Window] = []
    for window in story.windows:
        if window.wall_id in wall_ids:
            apt_windows.append(window)

    # Build rooms list
    rooms = []
    for space in apt.spaces:
        rooms.append({
            "name": space.name,
            "type": space.room_type.value,
            "area": round(space.area, 1),
            "boundary": [(v.x, v.y) for v in space.boundary.vertices],
        })

    # Build walls list
    walls = []
    for wall in apt_walls:
        walls.append({
            "name": wall.name,
            "start": (wall.start.x, wall.start.y),
            "end": (wall.end.x, wall.end.y),
            "thickness": wall.thickness,
            "is_external": wall.is_external,
            "load_bearing": wall.load_bearing,
            "length": round(wall.length, 2),
        })

    # Build doors list
    doors = []
    for door in apt_doors:
        wall_name = next(
            (w.name for w in apt_walls if w.global_id == door.wall_id), "?"
        )
        doors.append({
            "name": door.name,
            "wall": wall_name,
            "position": door.position,
            "width": door.width,
            "height": door.height,
        })

    # Build windows list
    windows = []
    for window in apt_windows:
        wall_name = next(
            (w.name for w in apt_walls if w.global_id == window.wall_id), "?"
        )
        windows.append({
            "name": window.name,
            "wall": wall_name,
            "position": window.position,
            "width": window.width,
            "height": window.height,
            "sill_height": window.sill_height,
        })

    return ApartmentSlice(
        apartment_name=apt.name,
        storey_name=storey_name,
        area=round(apt.area, 1),
        rooms=rooms,
        walls=walls,
        doors=doors,
        windows=windows,
        boundary=[(v.x, v.y) for v in verts],
    )


# ── Helpers ──────────────────────────────────────────────────────────


def _wall_in_bbox(
    wall: Wall, min_x: float, max_x: float, min_y: float, max_y: float
) -> bool:
    """Check if any part of a wall is within a bounding box."""
    # Wall is in bbox if either endpoint is inside, or the wall crosses the bbox
    def point_in_bbox(x: float, y: float) -> bool:
        return min_x <= x <= max_x and min_y <= y <= max_y

    if point_in_bbox(wall.start.x, wall.start.y):
        return True
    if point_in_bbox(wall.end.x, wall.end.y):
        return True
    # Check midpoint too
    mid_x = (wall.start.x + wall.end.x) / 2
    mid_y = (wall.start.y + wall.end.y) / 2
    return point_in_bbox(mid_x, mid_y)


def _is_apartment_wall(wall: Wall, apt: Apartment, tolerance: float) -> bool:
    """Check if a wall belongs to a specific apartment.

    A wall belongs to the apartment if it's an interior partition wall
    whose name matches the apartment name, or if it's geometrically
    contained within the apartment boundary.
    """
    apt_name_lower = apt.name.lower()
    wall_name_lower = (wall.name or "").lower()

    # Name-based match
    if apt_name_lower in wall_name_lower:
        return True

    # Geometric containment: wall midpoint inside apartment boundary
    mid_x = (wall.start.x + wall.end.x) / 2
    mid_y = (wall.start.y + wall.end.y) / 2
    verts = [(v.x, v.y) for v in apt.boundary.vertices]
    return _point_in_polygon(mid_x, mid_y, verts)


def _is_corridor_wall(wall: Wall) -> bool:
    """Check if a wall is a corridor wall."""
    return "corridor" in (wall.name or "").lower()


def _point_in_polygon(px: float, py: float, vertices: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test."""
    n = len(vertices)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = vertices[i]
        xj, yj = vertices[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside
