"""Building-level validators.

Cross-story validation that checks the building as a whole:
- Load-bearing wall vertical alignment
- Building has staircase (multi-storey)
- Slab completeness (every story has a floor slab)
- Wall closure (exterior walls form a closed perimeter)

These complement the per-story validators in structural.py and connectivity.py.
"""

from __future__ import annotations

import math
from collections import defaultdict

from archicad_builder.models.building import Building, Story
from archicad_builder.models.geometry import Point2D
from archicad_builder.validators.structural import ValidationError


def validate_building(building: Building) -> list[ValidationError]:
    """Run all building-level validators. Returns list of errors."""
    errors: list[ValidationError] = []
    errors.extend(validate_bearing_wall_alignment(building))
    errors.extend(validate_has_staircase(building))
    errors.extend(validate_slab_completeness(building))
    errors.extend(validate_wall_closure(building))
    return errors


def validate_bearing_wall_alignment(
    building: Building,
    tolerance: float = 0.1,
) -> list[ValidationError]:
    """Check that load-bearing walls on floor N align with floor N-1.

    A bearing wall on an upper floor must have a corresponding bearing wall
    directly below it (same start/end coordinates within tolerance).
    Without this, the structure is unsound — loads can't transfer to foundation.

    Args:
        building: Building to validate.
        tolerance: Max distance between wall endpoints to consider aligned (meters).

    Returns:
        Validation errors for misaligned bearing walls.
    """
    errors: list[ValidationError] = []
    stories = sorted(building.stories, key=lambda s: s.elevation)

    for i in range(1, len(stories)):
        upper = stories[i]
        lower = stories[i - 1]

        upper_bearing = [w for w in upper.walls if w.load_bearing]
        lower_bearing = [w for w in lower.walls if w.load_bearing]

        for wall in upper_bearing:
            if not _has_aligned_wall(wall, lower_bearing, tolerance):
                errors.append(
                    ValidationError(
                        severity="error",
                        element_type="Wall",
                        element_id=wall.global_id,
                        message=(
                            f"Load-bearing wall '{wall.name}' on '{upper.name}' "
                            f"has no aligned bearing wall below on '{lower.name}'. "
                            f"Wall at ({wall.start.x:.1f},{wall.start.y:.1f})→"
                            f"({wall.end.x:.1f},{wall.end.y:.1f})"
                        ),
                    )
                )

    return errors


def _has_aligned_wall(
    wall,
    candidates: list,
    tolerance: float,
) -> bool:
    """Check if a wall has a vertically aligned counterpart in the candidate list."""
    for other in candidates:
        # Check both orientations (wall could be defined start↔end either way)
        if (_points_close(wall.start, other.start, tolerance)
                and _points_close(wall.end, other.end, tolerance)):
            return True
        if (_points_close(wall.start, other.end, tolerance)
                and _points_close(wall.end, other.start, tolerance)):
            return True
    return False


def _points_close(p1: Point2D, p2: Point2D, tolerance: float) -> bool:
    """Check if two points are within tolerance distance."""
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2) <= tolerance


def validate_has_staircase(building: Building) -> list[ValidationError]:
    """Check that multi-storey buildings have at least one staircase.

    A building with 2+ stories must have a staircase on every floor
    for vertical circulation. Single-story buildings are exempt.

    Returns:
        Validation errors for missing staircases.
    """
    errors: list[ValidationError] = []

    if len(building.stories) < 2:
        return errors  # Single-storey doesn't need stairs

    for story in building.stories:
        if len(story.staircases) == 0:
            errors.append(
                ValidationError(
                    severity="error",
                    element_type="Building",
                    element_id=building.global_id,
                    message=(
                        f"Multi-storey building has no staircase on '{story.name}'. "
                        f"Every floor needs vertical circulation."
                    ),
                )
            )

    return errors


def validate_slab_completeness(building: Building) -> list[ValidationError]:
    """Check that every story has at least one floor slab.

    A floor slab is essential for structural integrity and spatial
    definition. Every story should have at least one slab with is_floor=True.

    Returns:
        Validation errors for stories missing floor slabs.
    """
    errors: list[ValidationError] = []

    for story in building.stories:
        floor_slabs = [s for s in story.slabs if s.is_floor]
        if len(floor_slabs) == 0:
            errors.append(
                ValidationError(
                    severity="error",
                    element_type="Story",
                    element_id=story.global_id,
                    message=f"Story '{story.name}' has no floor slab.",
                )
            )

    return errors


def validate_wall_closure(
    building: Building,
    tolerance: float = 0.05,
) -> list[ValidationError]:
    """Check that exterior walls form a closed perimeter on each story.

    Exterior walls (is_external=True) should form a closed loop — every
    exterior wall endpoint should connect to another exterior wall endpoint.
    Gaps in the exterior envelope are structural/weatherproofing failures.

    Args:
        building: Building to validate.
        tolerance: Max gap between endpoints to consider connected (meters).

    Returns:
        Validation errors for gaps in exterior wall perimeter.
    """
    errors: list[ValidationError] = []

    for story in building.stories:
        external_walls = [w for w in story.walls if w.is_external]
        if len(external_walls) < 3:
            if external_walls:  # Has some external walls but not enough for closure
                errors.append(
                    ValidationError(
                        severity="warning",
                        element_type="Story",
                        element_id=story.global_id,
                        message=(
                            f"Story '{story.name}' has only {len(external_walls)} "
                            f"external walls — not enough for a closed perimeter."
                        ),
                    )
                )
            continue

        # Collect all endpoints of external walls
        endpoints: list[tuple[Point2D, str, str]] = []  # (point, wall_name, "start"/"end")
        for wall in external_walls:
            endpoints.append((wall.start, wall.name or wall.global_id, "start"))
            endpoints.append((wall.end, wall.name or wall.global_id, "end"))

        # Each endpoint should be close to exactly one other endpoint
        for point, wall_name, end_type in endpoints:
            matches = 0
            for other_point, other_name, other_end in endpoints:
                if wall_name == other_name and end_type == other_end:
                    continue  # Skip self
                if _points_close(point, other_point, tolerance):
                    matches += 1

            if matches == 0:
                errors.append(
                    ValidationError(
                        severity="error",
                        element_type="Wall",
                        element_id=wall_name,
                        message=(
                            f"External wall '{wall_name}' {end_type} endpoint "
                            f"({point.x:.2f}, {point.y:.2f}) is not connected to "
                            f"any other external wall on '{story.name}'."
                        ),
                    )
                )

    return errors
