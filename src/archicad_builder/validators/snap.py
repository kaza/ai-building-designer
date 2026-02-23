"""Wall endpoint snapping — auto-fix small gaps between walls.

Merges wall endpoints that are within a tolerance distance,
ensuring walls form a properly connected structure.

This runs BEFORE validation, fixing the most common Gemini
coordinate drift issues.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from archicad_builder.models.building import Story
from archicad_builder.models.geometry import Point2D


def _distance(p1: Point2D, p2: Point2D) -> float:
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)


@dataclass
class SnapResult:
    """Result of snapping an endpoint."""

    wall_tag: str
    end: str  # "start" or "end"
    old: tuple[float, float]
    new: tuple[float, float]
    snapped_to_wall: str
    snapped_to_end: str


def snap_endpoints(
    story: Story,
    tolerance: float = 0.02,
) -> list[SnapResult]:
    """Snap wall endpoints that are within tolerance of each other.

    When two endpoints are close but not identical, moves the second
    one to match the first (first wall in list wins). Also snaps
    endpoints to wall bodies for T-junctions.

    Args:
        story: Story to modify (mutated in place).
        tolerance: Maximum distance to snap (meters). Default 2cm.

    Returns:
        List of snaps performed.
    """
    story.ensure_tags()
    walls = story.walls
    snaps: list[SnapResult] = []

    # Collect all unique endpoint positions (first occurrence wins)
    # This ensures consistency: if A snaps to B, C also snaps to B's position
    canonical_points: list[tuple[Point2D, str, str]] = []  # (point, wall_tag, end)

    for wall in walls:
        for end_name, endpoint in [("start", wall.start), ("end", wall.end)]:
            canonical_points.append((endpoint, wall.tag, end_name))

    # For each endpoint, check if it should snap to an earlier canonical point
    for i, wall in enumerate(walls):
        for end_name in ["start", "end"]:
            endpoint = wall.start if end_name == "start" else wall.end

            best_dist = float("inf")
            best_target: tuple[Point2D, str, str] | None = None

            # Check against all other walls' endpoints
            for j, other in enumerate(walls):
                if i == j:
                    continue
                for other_end in ["start", "end"]:
                    other_point = other.start if other_end == "start" else other.end
                    d = _distance(endpoint, other_point)
                    if 1e-10 < d < best_dist:  # Skip exact matches (already connected)
                        best_dist = d
                        best_target = (other_point, other.tag, other_end)

            # Check against wall bodies (T-junction snapping)
            for j, other in enumerate(walls):
                if i == j:
                    continue
                proj = _project_onto_segment(endpoint, other.start, other.end)
                if proj is not None:
                    d = _distance(endpoint, proj)
                    if 1e-10 < d < best_dist:
                        best_dist = d
                        best_target = (proj, other.tag, "body")

            if best_target and best_dist <= tolerance:
                target_point, target_tag, target_end = best_target
                old = (endpoint.x, endpoint.y)

                # Snap: update the endpoint
                if end_name == "start":
                    wall.start = Point2D(x=target_point.x, y=target_point.y)
                else:
                    wall.end = Point2D(x=target_point.x, y=target_point.y)

                snaps.append(SnapResult(
                    wall_tag=wall.tag,
                    end=end_name,
                    old=old,
                    new=(target_point.x, target_point.y),
                    snapped_to_wall=target_tag,
                    snapped_to_end=target_end,
                ))

    return snaps


def _project_onto_segment(
    point: Point2D,
    seg_start: Point2D,
    seg_end: Point2D,
) -> Point2D | None:
    """Project a point onto a line segment.

    Returns the projected point if it falls strictly inside the segment
    (not at endpoints — those are handled by endpoint-to-endpoint snapping).
    Returns None if projection falls outside the segment.
    """
    dx = seg_end.x - seg_start.x
    dy = seg_end.y - seg_start.y
    length_sq = dx * dx + dy * dy

    if length_sq < 1e-12:
        return None

    t = ((point.x - seg_start.x) * dx + (point.y - seg_start.y) * dy) / length_sq

    # Only T-junctions (strictly inside, not at endpoints)
    if t <= 0.01 or t >= 0.99:
        return None

    return Point2D(
        x=seg_start.x + t * dx,
        y=seg_start.y + t * dy,
    )
