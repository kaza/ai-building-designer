"""Wall connectivity validation.

Checks that walls form a connected structure:
- Every wall endpoint connects to another wall (endpoint or body)
- No orphan endpoints (interior walls floating in space)
- Detects gaps between walls that should connect

Follows IFC conventions: wall connections map to IfcRelConnectsPathElements.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from archicad_builder.models.building import Story
from archicad_builder.models.geometry import Point2D
from archicad_builder.validators.structural import ValidationError


def _distance(p1: Point2D, p2: Point2D) -> float:
    """Euclidean distance between two points."""
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)


def _point_to_segment_distance(
    point: Point2D,
    seg_start: Point2D,
    seg_end: Point2D,
) -> float:
    """Distance from a point to a line segment (wall body).

    Returns the perpendicular distance if the projection falls on the segment,
    otherwise the distance to the nearest endpoint.
    """
    dx = seg_end.x - seg_start.x
    dy = seg_end.y - seg_start.y
    length_sq = dx * dx + dy * dy

    if length_sq < 1e-12:
        return _distance(point, seg_start)

    # Project point onto the line, clamped to [0, 1]
    t = ((point.x - seg_start.x) * dx + (point.y - seg_start.y) * dy) / length_sq
    t = max(0.0, min(1.0, t))

    proj = Point2D(
        x=seg_start.x + t * dx,
        y=seg_start.y + t * dy,
    )
    return _distance(point, proj)


@dataclass
class WallConnection:
    """A detected connection between two walls."""

    wall1_tag: str
    wall1_end: str  # "start" or "end"
    wall2_tag: str
    wall2_end: str  # "start", "end", or "body" (T-junction)
    distance: float  # how far apart (0.0 = exact match)


def find_connections(
    story: Story,
    tolerance: float = 0.02,
) -> tuple[list[WallConnection], list[ValidationError]]:
    """Find wall-to-wall connections and detect gaps.

    An endpoint is "connected" if it's within tolerance of:
    - Another wall's endpoint (L-junction or corner)
    - Another wall's body (T-junction)

    Args:
        story: Story to analyze.
        tolerance: Maximum distance to consider connected (meters).

    Returns:
        Tuple of (connections found, validation errors for gaps).
    """
    story.ensure_tags()
    walls = story.walls
    connections: list[WallConnection] = []
    errors: list[ValidationError] = []

    for i, wall in enumerate(walls):
        for end_name, endpoint in [("start", wall.start), ("end", wall.end)]:
            best_dist = float("inf")
            best_connection: WallConnection | None = None

            for j, other in enumerate(walls):
                if i == j:
                    continue

                # Check endpoint-to-endpoint
                for other_end_name, other_endpoint in [
                    ("start", other.start),
                    ("end", other.end),
                ]:
                    d = _distance(endpoint, other_endpoint)
                    if d < best_dist:
                        best_dist = d
                        best_connection = WallConnection(
                            wall1_tag=wall.tag,
                            wall1_end=end_name,
                            wall2_tag=other.tag,
                            wall2_end=other_end_name,
                            distance=d,
                        )

                # Check endpoint-to-body (T-junction)
                d_body = _point_to_segment_distance(endpoint, other.start, other.end)
                if d_body < best_dist:
                    best_dist = d_body
                    best_connection = WallConnection(
                        wall1_tag=wall.tag,
                        wall1_end=end_name,
                        wall2_tag=other.tag,
                        wall2_end="body",
                        distance=d_body,
                    )

            if best_connection and best_dist <= tolerance:
                connections.append(best_connection)
            elif best_connection and best_dist > tolerance:
                errors.append(
                    ValidationError(
                        severity="warning",
                        element_type="Wall",
                        element_id=wall.global_id,
                        message=(
                            f"{wall.tag} {end_name} ({endpoint.x:.2f}, {endpoint.y:.2f}) "
                            f"has no connection — nearest is {best_connection.wall2_tag} "
                            f"{best_connection.wall2_end} at {best_dist:.3f}m"
                        ),
                    )
                )

    return connections, errors


def validate_connectivity(
    story: Story,
    tolerance: float = 0.02,
) -> list[ValidationError]:
    """Validate wall connectivity. Returns errors for unconnected endpoints.

    This is the main entry point for the connectivity validator.
    """
    _, errors = find_connections(story, tolerance)
    return errors
