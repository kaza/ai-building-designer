"""Wall-room relationship queries.

For each room: which walls form its boundary?
For each wall: which rooms are on each side?
These are the spatial queries needed for AI reasoning about
how to fix wall positions, add doors, etc.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from archicad_builder.models.building import Building, Story
from archicad_builder.models.elements import Wall, Window
from archicad_builder.models.geometry import Point2D
from archicad_builder.models.spaces import Apartment, RoomType, Space


@dataclass
class WallRoomRelation:
    """Relationship between a wall and the rooms on each side."""

    wall_name: str
    wall_id: str
    side_a: Optional[str]  # Room name on positive-normal side, or None
    side_b: Optional[str]  # Room name on negative-normal side, or None


def get_room_walls(
    building: Building,
    storey_name: str,
    room_name: str,
    tolerance: float = 0.25,
) -> list[Wall]:
    """Get all walls that form the boundary of a room.

    Checks if a wall edge overlaps with the room boundary.

    Args:
        building: The building model.
        storey_name: Storey to search.
        room_name: Name of the room/space.
        tolerance: Distance tolerance for wall-to-boundary matching.

    Returns:
        List of walls that form the room's boundary.
    """
    story = building._require_story(storey_name)
    space = _find_space(story, room_name)
    if space is None:
        return []

    boundary_edges = _get_polygon_edges(space.boundary.vertices)
    result: list[Wall] = []

    for wall in story.walls:
        if _wall_touches_boundary(wall, boundary_edges, tolerance):
            result.append(wall)

    return result


def get_wall_rooms(
    building: Building,
    storey_name: str,
    wall_name: str,
    step_distance: float = 0.3,
) -> tuple[Optional[str], Optional[str]]:
    """Get the rooms on each side of a wall.

    Steps to both sides of the wall center and checks which
    room/space contains that point.

    Args:
        building: The building model.
        storey_name: Storey to search.
        wall_name: Name of the wall.
        step_distance: How far to step from the wall.

    Returns:
        Tuple of (room_on_positive_normal_side, room_on_negative_normal_side).
        Either can be None if no room is found on that side.
    """
    story = building._require_story(storey_name)
    wall = story.get_wall_by_name(wall_name)
    if wall is None:
        return (None, None)

    # Compute wall center and normal
    cx = (wall.start.x + wall.end.x) / 2
    cy = (wall.start.y + wall.end.y) / 2
    dx = wall.end.x - wall.start.x
    dy = wall.end.y - wall.start.y
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-9:
        return (None, None)
    nx, ny = -dy / length, dx / length  # Normal (perpendicular)

    # Step to both sides
    side_a = (cx + nx * step_distance, cy + ny * step_distance)
    side_b = (cx - nx * step_distance, cy - ny * step_distance)

    # Check all spaces
    all_spaces = _collect_all_spaces(story)
    room_a = _find_containing_space(side_a[0], side_a[1], all_spaces)
    room_b = _find_containing_space(side_b[0], side_b[1], all_spaces)

    return (room_a, room_b)


def get_room_exterior_walls(
    building: Building,
    storey_name: str,
    room_name: str,
    tolerance: float = 0.25,
) -> list[Wall]:
    """Get exterior (facade) walls that form part of a room's boundary.

    Args:
        building: The building model.
        storey_name: Storey to search.
        room_name: Name of the room/space.
        tolerance: Distance tolerance for matching.

    Returns:
        List of exterior walls on the room's boundary.
    """
    walls = get_room_walls(building, storey_name, room_name, tolerance)
    return [w for w in walls if w.is_external]


def get_room_windows(
    building: Building,
    storey_name: str,
    room_name: str,
    tolerance: float = 0.25,
) -> list[Window]:
    """Get all windows in walls that form a room's boundary.

    Filters windows by checking that the window's 2D position
    on the wall falls within the room's boundary polygon.

    Args:
        building: The building model.
        storey_name: Storey to search.
        room_name: Name of the room/space.
        tolerance: Distance tolerance for matching.

    Returns:
        List of windows on the room's boundary walls.
    """
    story = building._require_story(storey_name)
    space = _find_space(story, room_name)
    if space is None:
        return []

    walls = get_room_walls(building, storey_name, room_name, tolerance)
    wall_map = {w.global_id: w for w in walls}

    result: list[Window] = []
    room_verts = [(v.x, v.y) for v in space.boundary.vertices]

    for window in story.windows:
        wall = wall_map.get(window.wall_id)
        if wall is None:
            continue
        # Check if the window's center position falls within the room
        win_center = _element_center_on_wall(
            wall, window.position, window.width
        )
        if win_center and _point_in_polygon_with_tolerance(
            win_center[0], win_center[1], room_verts, tolerance
        ):
            result.append(window)

    return result


def _element_center_on_wall(
    wall: Wall, position: float, width: float
) -> tuple[float, float] | None:
    """Compute the 2D center of an element placed on a wall."""
    dx = wall.end.x - wall.start.x
    dy = wall.end.y - wall.start.y
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-9:
        return None
    t = (position + width / 2) / length
    return (wall.start.x + dx * t, wall.start.y + dy * t)


def _point_in_polygon_with_tolerance(
    px: float, py: float, vertices: list[tuple[float, float]], tolerance: float
) -> bool:
    """Point-in-polygon with edge tolerance."""
    if _point_in_polygon(px, py, vertices):
        return True
    # Check distance to edges
    n = len(vertices)
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        dist = _point_to_segment_dist(px, py, x1, y1, x2, y2)
        if dist <= tolerance:
            return True
    return False


def _point_to_segment_dist(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> float:
    """Distance from point to line segment."""
    dx = x2 - x1
    dy = y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-12:
        return math.sqrt((px - x1) ** 2 + (py - y1) ** 2)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_sq))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)


# ── Internal helpers ─────────────────────────────────────────────────


def _find_space(story: Story, room_name: str) -> Optional[Space]:
    """Find a space by name in a story (including inside apartments)."""
    for space in story.spaces:
        if space.name.lower() == room_name.lower():
            return space
    for apt in story.apartments:
        for space in apt.spaces:
            if space.name.lower() == room_name.lower():
                return space
    return None


def _collect_all_spaces(story: Story) -> list[Space]:
    """Collect all spaces from a story (top-level + apartment rooms)."""
    spaces = list(story.spaces)
    for apt in story.apartments:
        spaces.extend(apt.spaces)
    return spaces


def _get_polygon_edges(
    vertices: list[Point2D],
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Get edges of a polygon as list of ((x1,y1), (x2,y2)) tuples."""
    n = len(vertices)
    edges = []
    for i in range(n):
        j = (i + 1) % n
        edges.append((
            (vertices[i].x, vertices[i].y),
            (vertices[j].x, vertices[j].y),
        ))
    return edges


def _wall_touches_boundary(
    wall: Wall,
    boundary_edges: list[tuple[tuple[float, float], tuple[float, float]]],
    tolerance: float,
) -> bool:
    """Check if a wall segment overlaps with any boundary edge.

    A wall "touches" a boundary if:
    1. The wall is approximately parallel to a boundary edge
    2. The wall is within tolerance distance of the edge
    3. There is significant overlap in the parallel direction
    """
    wall_seg = ((wall.start.x, wall.start.y), (wall.end.x, wall.end.y))

    for edge in boundary_edges:
        if _segments_overlap(wall_seg, edge, tolerance):
            return True
    return False


def _segments_overlap(
    seg1: tuple[tuple[float, float], tuple[float, float]],
    seg2: tuple[tuple[float, float], tuple[float, float]],
    tolerance: float,
) -> bool:
    """Check if two line segments are roughly parallel, close, and overlapping.

    Works for axis-aligned and general segments.
    """
    (x1a, y1a), (x1b, y1b) = seg1
    (x2a, y2a), (x2b, y2b) = seg2

    # Check if both segments are approximately horizontal
    if abs(y1a - y1b) < tolerance and abs(y2a - y2b) < tolerance:
        # Both horizontal — check y-distance and x-overlap
        if abs((y1a + y1b) / 2 - (y2a + y2b) / 2) > tolerance:
            return False
        # Check x-overlap
        min1, max1 = min(x1a, x1b), max(x1a, x1b)
        min2, max2 = min(x2a, x2b), max(x2a, x2b)
        overlap = min(max1, max2) - max(min1, min2)
        return overlap > tolerance * 0.5

    # Check if both segments are approximately vertical
    if abs(x1a - x1b) < tolerance and abs(x2a - x2b) < tolerance:
        # Both vertical — check x-distance and y-overlap
        if abs((x1a + x1b) / 2 - (x2a + x2b) / 2) > tolerance:
            return False
        # Check y-overlap
        min1, max1 = min(y1a, y1b), max(y1a, y1b)
        min2, max2 = min(y2a, y2b), max(y2a, y2b)
        overlap = min(max1, max2) - max(min1, min2)
        return overlap > tolerance * 0.5

    # General case: check if midpoints are close
    mid1 = ((x1a + x1b) / 2, (y1a + y1b) / 2)
    mid2 = ((x2a + x2b) / 2, (y2a + y2b) / 2)
    dist = math.sqrt((mid1[0] - mid2[0]) ** 2 + (mid1[1] - mid2[1]) ** 2)
    return dist < tolerance


def _find_containing_space(
    px: float, py: float, spaces: list[Space]
) -> Optional[str]:
    """Find which space contains a given point."""
    for space in spaces:
        verts = [(v.x, v.y) for v in space.boundary.vertices]
        if _point_in_polygon(px, py, verts):
            return space.name
    return None


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
