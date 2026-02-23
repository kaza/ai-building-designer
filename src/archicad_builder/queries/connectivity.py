"""Room connectivity graph builder.

Builds a graph where nodes = rooms/spaces and edges = doors.
This is the foundation for AI reasoning about building layout:
reachability, adjacency, pathfinding.

The hardest part: determining which two rooms each door connects.
Strategy: geometric containment — for each door, step to both sides
of the host wall and check which space contains that point.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from archicad_builder.models.building import Building, Story
from archicad_builder.models.elements import Door, Wall
from archicad_builder.models.geometry import Point2D
from archicad_builder.models.spaces import Apartment, RoomType, Space


# ── Graph data structures ────────────────────────────────────────────


@dataclass
class GraphNode:
    """A node in the connectivity graph (a room or space)."""

    name: str
    node_type: str  # room type or special: 'corridor', 'lobby', 'vestibule', 'elevator', 'staircase', 'exterior'
    area: float
    storey: str


@dataclass
class GraphEdge:
    """An edge in the connectivity graph (a door connecting two nodes)."""

    door_name: str
    door_width: float
    from_node: str
    to_node: str


@dataclass
class ConnectivityGraph:
    """Room connectivity graph for one storey.

    Nodes represent rooms/spaces. Edges represent doors.
    The graph is undirected (doors connect bidirectionally).
    """

    storey: str
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)

    def neighbors(self, node_name: str) -> list[tuple[str, GraphEdge]]:
        """Get all neighbors of a node with their connecting edges."""
        result = []
        for edge in self.edges:
            if edge.from_node == node_name:
                result.append((edge.to_node, edge))
            elif edge.to_node == node_name:
                result.append((edge.from_node, edge))
        return result

    def has_path(self, start: str, end: str) -> bool:
        """Check if a path exists between two nodes (BFS)."""
        if start not in self.nodes or end not in self.nodes:
            return False
        if start == end:
            return True
        visited = {start}
        queue = [start]
        while queue:
            current = queue.pop(0)
            for neighbor, _ in self.neighbors(current):
                if neighbor == end:
                    return True
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return False

    def reachable_from(self, start: str) -> set[str]:
        """Get all nodes reachable from a starting node (BFS)."""
        if start not in self.nodes:
            return set()
        visited = {start}
        queue = [start]
        while queue:
            current = queue.pop(0)
            for neighbor, _ in self.neighbors(current):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return visited


# ── Zone: intermediate representation for spatial matching ───────────


@dataclass
class _Zone:
    """A bounded area used for point-in-polygon containment tests."""

    name: str
    zone_type: str
    vertices: list[tuple[float, float]]  # polygon vertices as (x, y) tuples
    area: float


def _point_in_polygon(px: float, py: float, vertices: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test.

    Returns True if point (px, py) is inside the polygon defined by vertices.
    Vertices should be ordered (CW or CCW).
    """
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


def _point_in_polygon_with_tolerance(
    px: float, py: float, vertices: list[tuple[float, float]], tolerance: float = 0.05
) -> bool:
    """Point-in-polygon with edge tolerance.

    Also returns True if the point is within `tolerance` of any edge.
    """
    if _point_in_polygon(px, py, vertices):
        return True
    # Check distance to edges
    n = len(vertices)
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        dist = _point_to_segment_distance(px, py, x1, y1, x2, y2)
        if dist <= tolerance:
            return True
    return False


def _point_to_segment_distance(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> float:
    """Distance from point (px,py) to line segment (x1,y1)-(x2,y2)."""
    dx = x2 - x1
    dy = y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-12:
        return math.sqrt((px - x1) ** 2 + (py - y1) ** 2)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_sq))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)


# ── Zone synthesis from walls ────────────────────────────────────────


def _synthesize_common_zones(story: Story) -> list[_Zone]:
    """Create zones for common areas (corridor, core, lobby) from wall geometry.

    Groups walls by keyword and computes bounding-box zones.
    Uses precise keyword matching to avoid false positives.
    """
    zones: list[_Zone] = []

    # Group walls by area type — use precise matching
    corridor_walls = [w for w in story.walls
                     if (w.name or "").lower().startswith("corridor")]
    lobby_walls = [w for w in story.walls
                  if (w.name or "").lower().startswith("lobby")]
    elevator_walls = [w for w in story.walls
                     if (w.name or "").lower().startswith("elevator")]
    vestibule_walls = [w for w in story.walls
                      if "vestibule" in (w.name or "").lower()]

    # Corridor zone
    if corridor_walls:
        zone = _zone_from_walls(corridor_walls, "Corridor", "corridor")
        if zone:
            zones.append(zone)

    # Lobby zone (ground floor)
    if lobby_walls:
        all_xs = []
        all_ys = []
        for w in lobby_walls:
            all_xs.extend([w.start.x, w.end.x])
            all_ys.extend([w.start.y, w.end.y])
        min_y = 0.0  # Lobby starts at ground level
        zone = _Zone(
            name="Lobby",
            zone_type="lobby",
            vertices=[
                (min(all_xs), min_y),
                (max(all_xs), min_y),
                (max(all_xs), max(all_ys)),
                (min(all_xs), max(all_ys)),
            ],
            area=(max(all_xs) - min(all_xs)) * (max(all_ys) - min_y),
        )
        zones.append(zone)

    # Core vestibule zone — ONLY from walls with "vestibule" in name
    # These walls define the vestibule boundary precisely
    if vestibule_walls:
        zone = _zone_from_walls(vestibule_walls, "Core Vestibule", "vestibule")
        if zone:
            zones.append(zone)

    # Elevator zone
    if elevator_walls:
        divider_walls = [w for w in story.walls
                        if (w.name or "").lower().startswith("core divider")]
        combined = elevator_walls + [w for w in divider_walls
                                     if w not in elevator_walls]
        zone = _zone_from_walls(combined, "Elevator", "elevator")
        if zone:
            zones.append(zone)

    # Staircase zone — use staircase outline if available
    for st in story.staircases:
        verts = [(v.x, v.y) for v in st.outline.vertices]
        zones.append(_Zone(
            name=st.name or "Staircase",
            zone_type="staircase",
            vertices=verts,
            area=st.area,
        ))

    return zones


def _zone_from_walls(walls: list[Wall], name: str, zone_type: str) -> Optional[_Zone]:
    """Create a rectangular zone from the bounding box of a set of walls."""
    if not walls:
        return None
    all_xs = []
    all_ys = []
    for w in walls:
        all_xs.extend([w.start.x, w.end.x])
        all_ys.extend([w.start.y, w.end.y])
    min_x, max_x = min(all_xs), max(all_xs)
    min_y, max_y = min(all_ys), max(all_ys)
    width = max_x - min_x
    height = max_y - min_y
    if width < 0.01 or height < 0.01:
        return None
    return _Zone(
        name=name,
        zone_type=zone_type,
        vertices=[
            (min_x, min_y),
            (max_x, min_y),
            (max_x, max_y),
            (min_x, max_y),
        ],
        area=width * height,
    )


# ── Door-to-zone matching ───────────────────────────────────────────


def _door_center_2d(door: Door, wall: Wall) -> tuple[float, float]:
    """Compute the 2D position of a door's center on its host wall."""
    dx = wall.end.x - wall.start.x
    dy = wall.end.y - wall.start.y
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-9:
        return (wall.start.x, wall.start.y)
    # Door center is at (position + width/2) along the wall
    t = (door.position + door.width / 2) / length
    return (
        wall.start.x + dx * t,
        wall.start.y + dy * t,
    )


def _wall_normal(wall: Wall) -> tuple[float, float]:
    """Compute the unit normal of a wall (perpendicular, left-hand side)."""
    dx = wall.end.x - wall.start.x
    dy = wall.end.y - wall.start.y
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-9:
        return (0.0, 1.0)
    # Normal is perpendicular: (-dy, dx) normalized
    return (-dy / length, dx / length)


def _find_zone_at_point(
    px: float,
    py: float,
    zones: list[_Zone],
    tolerance: float = 0.15,
    prefer_common: bool = False,
) -> Optional[str]:
    """Find which zone contains a given point.

    When multiple zones overlap, uses preference order:
    1. If prefer_common=True, prefer common-area zones (corridor, vestibule, etc.)
    2. Otherwise, prefer the smallest (most specific) zone.

    Args:
        px, py: Point to check.
        zones: List of zones to search.
        tolerance: Edge tolerance.
        prefer_common: When True, prefer common-area zones over apartment spaces.
                       Use this for doors on common-area walls.
    """
    _COMMON_TYPES = {"corridor", "vestibule", "lobby", "elevator", "staircase"}

    # Collect all matching zones
    matches: list[_Zone] = []
    for zone in zones:
        if _point_in_polygon(px, py, zone.vertices):
            matches.append(zone)

    if not matches:
        for zone in zones:
            if _point_in_polygon_with_tolerance(px, py, zone.vertices, tolerance):
                matches.append(zone)

    if not matches:
        return None

    if len(matches) == 1:
        return matches[0].name

    # Multiple matches — resolve ambiguity
    if prefer_common:
        # Prefer common-area zones for doors on common-area walls
        common = [z for z in matches if z.zone_type in _COMMON_TYPES]
        if common:
            common.sort(key=lambda z: z.area)
            return common[0].name

    # Default: prefer smallest zone (most specific)
    matches.sort(key=lambda z: z.area)
    return matches[0].name


# ── Main graph builder ───────────────────────────────────────────────


def build_connectivity_graph(
    building: Building,
    storey_name: str,
    step_distance: float = 0.3,
) -> ConnectivityGraph:
    """Build a room connectivity graph for one storey.

    Nodes = rooms/spaces (apartment rooms, corridor, core, exterior).
    Edges = doors connecting two spaces.

    Args:
        building: The building model.
        storey_name: Name of the storey to analyze.
        step_distance: How far to step from each side of a wall
                       when probing for room containment (meters).

    Returns:
        ConnectivityGraph with nodes and edges.
    """
    story = building._require_story(storey_name)
    graph = ConnectivityGraph(storey=storey_name)

    # 1. Collect all zones
    zones: list[_Zone] = []

    # Apartment room spaces
    for apt in story.apartments:
        for space in apt.spaces:
            verts = [(v.x, v.y) for v in space.boundary.vertices]
            zones.append(_Zone(
                name=space.name,
                zone_type=space.room_type.value,
                vertices=verts,
                area=space.area,
            ))

    # Top-level spaces (if any)
    for space in story.spaces:
        verts = [(v.x, v.y) for v in space.boundary.vertices]
        zones.append(_Zone(
            name=space.name,
            zone_type=space.room_type.value,
            vertices=verts,
            area=space.area,
        ))

    # Synthesize common area zones from wall geometry
    common_zones = _synthesize_common_zones(story)
    zones.extend(common_zones)

    # 2. Create graph nodes for all zones
    for zone in zones:
        graph.nodes[zone.name] = GraphNode(
            name=zone.name,
            node_type=zone.zone_type,
            area=zone.area,
            storey=storey_name,
        )

    # Always add Exterior node
    graph.nodes["Exterior"] = GraphNode(
        name="Exterior",
        node_type="exterior",
        area=0.0,
        storey=storey_name,
    )

    # 3. Build wall ID -> Wall lookup
    wall_map = {w.global_id: w for w in story.walls}

    # 4. For each door, find which two zones it connects
    _COMMON_WALL_KEYWORDS = {"core", "corridor", "staircase", "elevator", "vestibule", "lobby"}

    for door in story.doors:
        wall = wall_map.get(door.wall_id)
        if wall is None:
            continue

        # Compute door center and wall normal
        cx, cy = _door_center_2d(door, wall)
        nx, ny = _wall_normal(wall)

        # Step to both sides of the wall
        side_a = (cx + nx * step_distance, cy + ny * step_distance)
        side_b = (cx - nx * step_distance, cy - ny * step_distance)

        # For doors on common-area walls, prefer common-area zones
        # when resolving overlap ambiguities
        wall_name_lower = (wall.name or "").lower()
        is_common_wall = any(kw in wall_name_lower for kw in _COMMON_WALL_KEYWORDS)

        zone_a = _find_zone_at_point(side_a[0], side_a[1], zones, prefer_common=is_common_wall)
        zone_b = _find_zone_at_point(side_b[0], side_b[1], zones, prefer_common=is_common_wall)

        # If a side has no zone, check if it's exterior
        # (the point is outside the building footprint)
        if zone_a is None:
            if _is_outside_building(side_a[0], side_a[1], story):
                zone_a = "Exterior"
        if zone_b is None:
            if _is_outside_building(side_b[0], side_b[1], story):
                zone_b = "Exterior"

        # Create edge if we found two different zones
        from_node = zone_a or "Unknown"
        to_node = zone_b or "Unknown"

        if from_node == to_node:
            # Door connects the same space on both sides — skip or flag
            continue

        # Ensure both nodes exist in the graph
        if from_node not in graph.nodes and from_node != "Unknown":
            graph.nodes[from_node] = GraphNode(
                name=from_node, node_type="unknown", area=0.0, storey=storey_name
            )
        if to_node not in graph.nodes and to_node != "Unknown":
            graph.nodes[to_node] = GraphNode(
                name=to_node, node_type="unknown", area=0.0, storey=storey_name
            )

        if from_node != "Unknown" and to_node != "Unknown":
            graph.edges.append(GraphEdge(
                door_name=door.name or "unnamed",
                door_width=door.width,
                from_node=from_node,
                to_node=to_node,
            ))

    return graph


def _is_outside_building(px: float, py: float, story: Story) -> bool:
    """Check if a point is outside the building footprint.

    Uses the exterior walls to determine the building outline.
    Falls back to checking against all slab outlines.
    """
    # Try using exterior walls bounding box
    ext_walls = [w for w in story.walls if w.is_external]
    if ext_walls:
        all_xs = []
        all_ys = []
        for w in ext_walls:
            all_xs.extend([w.start.x, w.end.x])
            all_ys.extend([w.start.y, w.end.y])
        min_x, max_x = min(all_xs), max(all_xs)
        min_y, max_y = min(all_ys), max(all_ys)
        # Point is outside if beyond the exterior wall bounding box
        margin = 0.01
        return (px < min_x - margin or px > max_x + margin or
                py < min_y - margin or py > max_y + margin)

    # Fallback: use floor slab outlines
    for slab in story.slabs:
        if slab.is_floor:
            verts = [(v.x, v.y) for v in slab.outline.vertices]
            if _point_in_polygon(px, py, verts):
                return False
    return True
