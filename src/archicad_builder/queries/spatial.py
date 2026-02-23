"""Spatial query tools for building context extraction.

When a validator fails, these tools help pull the surrounding context
needed to understand and fix the issue.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from archicad_builder.models.building import Building, Story
from archicad_builder.models.elements import Wall, Door, Window, Slab, Staircase
from archicad_builder.models.geometry import Point2D
from archicad_builder.models.spaces import Apartment, Space


@dataclass
class Neighbor:
    """A neighboring element."""
    element_type: str  # "wall", "door", "window", "staircase", "space", "apartment"
    element_id: str
    element_name: str
    distance: float
    relationship: str  # "connected", "adjacent", "overlapping", "nearby"


@dataclass
class VerticalMatch:
    """An element aligned vertically across floors."""
    story_name: str
    element_type: str
    element_id: str
    element_name: str
    alignment_quality: str  # "exact", "close", "offset"


@dataclass
class FloorContext:
    """Extracted context about a floor's state."""
    story_name: str
    elevation: float
    wall_count: int
    door_count: int
    window_count: int
    slab_count: int
    staircase_count: int
    apartment_count: int
    space_count: int
    total_floor_area: float
    external_wall_names: list[str] = field(default_factory=list)
    bearing_wall_names: list[str] = field(default_factory=list)
    apartment_summaries: list[str] = field(default_factory=list)


def find_neighbors(
    building: Building,
    story_name: str,
    element_id: str,
    max_distance: float = 2.0,
) -> list[Neighbor]:
    """Find elements near a given element on the same floor.

    Searches walls, doors, windows, staircases, spaces, and apartments
    within max_distance of the target element.

    Args:
        building: Building to search.
        story_name: Story containing the target element.
        element_id: GlobalId of the target element.
        max_distance: Maximum distance to consider (meters).

    Returns:
        List of neighboring elements, sorted by distance.
    """
    story = building._require_story(story_name)
    neighbors: list[Neighbor] = []

    # Find the target element and its reference point
    target_center = _find_element_center(story, element_id)
    if target_center is None:
        return []

    # Search walls — use minimum distance from any reference point
    # (target could be a center or endpoint of a long wall)
    target_ref_points = _get_element_ref_points(story, element_id)

    for wall in story.walls:
        if wall.global_id == element_id:
            continue

        # Check minimum distance from any target ref point to any wall point
        wall_points = [wall.start, wall.end, Point2D(
            x=(wall.start.x + wall.end.x) / 2,
            y=(wall.start.y + wall.end.y) / 2,
        )]

        min_d = float("inf")
        for tp in target_ref_points:
            for wp in wall_points:
                d = _distance(tp, wp)
                if d < min_d:
                    min_d = d

        if min_d <= max_distance:
            # Check for endpoint connections (shared corners)
            endpoint_dist = float("inf")
            for tp in target_ref_points:
                for wp in [wall.start, wall.end]:
                    d = _distance(tp, wp)
                    if d < endpoint_dist:
                        endpoint_dist = d

            rel = "nearby"
            if endpoint_dist < 0.05:
                rel = "connected"
            elif min_d < 0.5:
                rel = "adjacent"

            neighbors.append(Neighbor(
                element_type="wall",
                element_id=wall.global_id,
                element_name=wall.name,
                distance=min_d,
                relationship=rel,
            ))

    # Search spaces
    all_spaces = list(story.spaces)
    for apt in story.apartments:
        all_spaces.extend(apt.spaces)

    for space in all_spaces:
        if space.global_id == element_id:
            continue
        space_center = _polygon_center(space.boundary.vertices)
        d = _distance(target_center, space_center)
        if d <= max_distance:
            neighbors.append(Neighbor(
                element_type="space",
                element_id=space.global_id,
                element_name=space.name,
                distance=d,
                relationship="adjacent" if d < 1.0 else "nearby",
            ))

    # Search staircases
    for staircase in story.staircases:
        if staircase.global_id == element_id:
            continue
        sc = _polygon_center(staircase.outline.vertices)
        d = _distance(target_center, sc)
        if d <= max_distance:
            neighbors.append(Neighbor(
                element_type="staircase",
                element_id=staircase.global_id,
                element_name=staircase.name,
                distance=d,
                relationship="nearby",
            ))

    neighbors.sort(key=lambda n: n.distance)
    return neighbors


def find_above_below(
    building: Building,
    story_name: str,
    element_id: str,
    tolerance: float = 0.5,
) -> list[VerticalMatch]:
    """Find vertically aligned elements on other floors.

    Useful for checking bearing wall alignment, staircase continuity,
    and shaft alignment.

    Args:
        building: Building to search.
        story_name: Story containing the target element.
        element_id: GlobalId of the target element.
        tolerance: Max XY distance for alignment (meters).

    Returns:
        List of vertically aligned elements on other floors.
    """
    target_story = building._require_story(story_name)
    target_center = _find_element_center(target_story, element_id)
    if target_center is None:
        return []

    matches: list[VerticalMatch] = []

    for story in building.stories:
        if story.name == story_name:
            continue

        # Check walls
        for wall in story.walls:
            wall_center = Point2D(
                x=(wall.start.x + wall.end.x) / 2,
                y=(wall.start.y + wall.end.y) / 2,
            )
            d = _distance(target_center, wall_center)
            if d <= tolerance:
                quality = "exact" if d < 0.05 else ("close" if d < 0.2 else "offset")
                matches.append(VerticalMatch(
                    story_name=story.name,
                    element_type="wall",
                    element_id=wall.global_id,
                    element_name=wall.name,
                    alignment_quality=quality,
                ))

        # Check staircases
        for staircase in story.staircases:
            sc = _polygon_center(staircase.outline.vertices)
            d = _distance(target_center, sc)
            if d <= tolerance:
                quality = "exact" if d < 0.05 else "close"
                matches.append(VerticalMatch(
                    story_name=story.name,
                    element_type="staircase",
                    element_id=staircase.global_id,
                    element_name=staircase.name,
                    alignment_quality=quality,
                ))

    return matches


def extract_floor_context(
    building: Building,
    story_name: str,
) -> FloorContext:
    """Extract a summary context of a floor's state.

    Provides a quick overview of what's on a floor — useful for
    understanding the current state when fixing validation errors.

    Args:
        building: Building to query.
        story_name: Story to extract context for.

    Returns:
        FloorContext with element counts and summaries.
    """
    story = building._require_story(story_name)

    external_walls = [w.name for w in story.walls if w.is_external and w.name]
    bearing_walls = [w.name for w in story.walls if w.load_bearing and w.name]
    floor_area = sum(s.area for s in story.slabs if s.is_floor)

    apt_summaries = []
    for apt in story.apartments:
        room_types = [s.room_type.value for s in apt.spaces]
        apt_summaries.append(
            f"{apt.name}: {apt.area:.1f}m², {len(apt.spaces)} rooms ({', '.join(room_types)})"
        )

    all_spaces = list(story.spaces)
    for apt in story.apartments:
        all_spaces.extend(apt.spaces)

    return FloorContext(
        story_name=story.name,
        elevation=story.elevation,
        wall_count=len(story.walls),
        door_count=len(story.doors),
        window_count=len(story.windows),
        slab_count=len(story.slabs),
        staircase_count=len(story.staircases),
        apartment_count=len(story.apartments),
        space_count=len(all_spaces),
        total_floor_area=floor_area,
        external_wall_names=external_walls,
        bearing_wall_names=bearing_walls,
        apartment_summaries=apt_summaries,
    )


def _get_element_ref_points(story: Story, element_id: str) -> list[Point2D]:
    """Get reference points for an element (endpoints + center for walls)."""
    for wall in story.walls:
        if wall.global_id == element_id:
            return [
                wall.start,
                wall.end,
                Point2D(x=(wall.start.x + wall.end.x) / 2,
                        y=(wall.start.y + wall.end.y) / 2),
            ]
    center = _find_element_center(story, element_id)
    return [center] if center else []


def _find_element_center(story: Story, element_id: str) -> Point2D | None:
    """Find the center point of an element by its GlobalId."""
    for wall in story.walls:
        if wall.global_id == element_id:
            return Point2D(
                x=(wall.start.x + wall.end.x) / 2,
                y=(wall.start.y + wall.end.y) / 2,
            )
    for staircase in story.staircases:
        if staircase.global_id == element_id:
            return _polygon_center(staircase.outline.vertices)
    for space in story.spaces:
        if space.global_id == element_id:
            return _polygon_center(space.boundary.vertices)
    for apt in story.apartments:
        if apt.global_id == element_id:
            return _polygon_center(apt.boundary.vertices)
        for space in apt.spaces:
            if space.global_id == element_id:
                return _polygon_center(space.boundary.vertices)
    return None


def _polygon_center(vertices: list[Point2D]) -> Point2D:
    """Centroid of a polygon's vertices."""
    cx = sum(v.x for v in vertices) / len(vertices)
    cy = sum(v.y for v in vertices) / len(vertices)
    return Point2D(x=cx, y=cy)


def _distance(p1: Point2D, p2: Point2D) -> float:
    """Euclidean distance between two points."""
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)
