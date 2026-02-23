"""Cross-model structural validation.

Validates relationships between elements that Pydantic model validators
can't catch on their own (e.g., door fits in host wall, slab covers walls).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from archicad_builder.models.building import Story, Wall


@dataclass
class ValidationError:
    """A single validation issue."""

    severity: str  # "error" | "warning" | "optimization"
    element_type: str
    element_id: str
    message: str


def validate_story(story: Story) -> list[ValidationError]:
    """Validate all elements within a story for structural consistency."""
    errors: list[ValidationError] = []
    wall_ids = story.wall_ids()

    # Check doors reference existing walls
    for door in story.doors:
        if door.wall_id not in wall_ids:
            errors.append(
                ValidationError(
                    severity="error",
                    element_type="Door",
                    element_id=door.global_id,
                    message=f"Door references non-existent wall {door.wall_id}",
                )
            )
        else:
            wall = story.get_wall(door.wall_id)
            if wall:
                # Check door fits within wall length
                if door.position + door.width > wall.length + 1e-6:
                    errors.append(
                        ValidationError(
                            severity="error",
                            element_type="Door",
                            element_id=door.global_id,
                            message=(
                                f"Door extends past wall end "
                                f"(pos {door.position} + width {door.width} "
                                f"> wall length {wall.length:.2f})"
                            ),
                        )
                    )
                # Check door height fits wall
                if door.height > wall.height + 1e-6:
                    errors.append(
                        ValidationError(
                            severity="error",
                            element_type="Door",
                            element_id=door.global_id,
                            message=(
                                f"Door height {door.height}m exceeds "
                                f"wall height {wall.height}m"
                            ),
                        )
                    )

    # Check for overlapping doors on the same wall
    from collections import defaultdict

    doors_by_wall: dict[str, list] = defaultdict(list)
    for door in story.doors:
        if door.wall_id in wall_ids:
            doors_by_wall[door.wall_id].append(door)

    for wid, wall_doors in doors_by_wall.items():
        wall = story.get_wall(wid)
        wall_name = wall.name if wall else wid[:8]
        for i, d1 in enumerate(wall_doors):
            for d2 in wall_doors[i + 1 :]:
                s1, e1 = d1.position, d1.position + d1.width
                s2, e2 = d2.position, d2.position + d2.width
                overlap = min(e1, e2) - max(s1, s2)
                if overlap > 0.01:  # 1cm tolerance
                    errors.append(
                        ValidationError(
                            severity="error",
                            element_type="Door",
                            element_id=d1.global_id,
                            message=(
                                f"Door '{d1.name}' overlaps with '{d2.name}' "
                                f"by {overlap:.2f}m on wall '{wall_name}' "
                                f"(D1: {s1:.2f}-{e1:.2f}, D2: {s2:.2f}-{e2:.2f})"
                            ),
                        )
                    )

    # Check for overlapping windows on the same wall
    windows_by_wall: dict[str, list] = defaultdict(list)
    for window in story.windows:
        if window.wall_id in wall_ids:
            windows_by_wall[window.wall_id].append(window)

    for wid, wall_windows in windows_by_wall.items():
        wall = story.get_wall(wid)
        wall_name = wall.name if wall else wid[:8]
        for i, w1 in enumerate(wall_windows):
            for w2 in wall_windows[i + 1 :]:
                s1, e1 = w1.position, w1.position + w1.width
                s2, e2 = w2.position, w2.position + w2.width
                overlap = min(e1, e2) - max(s1, s2)
                if overlap > 0.01:
                    errors.append(
                        ValidationError(
                            severity="error",
                            element_type="Window",
                            element_id=w1.global_id,
                            message=(
                                f"Window '{w1.name}' overlaps with '{w2.name}' "
                                f"by {overlap:.2f}m on wall '{wall_name}' "
                                f"(W1: {s1:.2f}-{e1:.2f}, W2: {s2:.2f}-{e2:.2f})"
                            ),
                        )
                    )

    # Check for door-window overlaps on the same wall
    for wid in set(doors_by_wall.keys()) & set(windows_by_wall.keys()):
        wall = story.get_wall(wid)
        wall_name = wall.name if wall else wid[:8]
        for door in doors_by_wall[wid]:
            for window in windows_by_wall[wid]:
                sd, ed = door.position, door.position + door.width
                sw, ew = window.position, window.position + window.width
                overlap = min(ed, ew) - max(sd, sw)
                if overlap > 0.01:
                    errors.append(
                        ValidationError(
                            severity="error",
                            element_type="Door",
                            element_id=door.global_id,
                            message=(
                                f"Door '{door.name}' overlaps with window "
                                f"'{window.name}' by {overlap:.2f}m on wall "
                                f"'{wall_name}'"
                            ),
                        )
                    )

    # Check door/window openings don't cross perpendicular walls
    errors.extend(_check_openings_cross_walls(story))

    # Check non-core walls don't pass through core/staircase/elevator areas
    errors.extend(_check_walls_cross_core(story))

    # Check windows reference existing walls
    for window in story.windows:
        if window.wall_id not in wall_ids:
            errors.append(
                ValidationError(
                    severity="error",
                    element_type="Window",
                    element_id=window.global_id,
                    message=f"Window references non-existent wall {window.wall_id}",
                )
            )
        else:
            wall = story.get_wall(window.wall_id)
            if wall:
                # Check window fits within wall length
                if window.position + window.width > wall.length + 1e-6:
                    errors.append(
                        ValidationError(
                            severity="error",
                            element_type="Window",
                            element_id=window.global_id,
                            message=(
                                f"Window extends past wall end "
                                f"(pos {window.position} + width {window.width} "
                                f"> wall length {wall.length:.2f})"
                            ),
                        )
                    )
                # Check window top doesn't exceed wall height
                if window.sill_height + window.height > wall.height + 1e-6:
                    errors.append(
                        ValidationError(
                            severity="error",
                            element_type="Window",
                            element_id=window.global_id,
                            message=(
                                f"Window top ({window.sill_height + window.height}m) "
                                f"exceeds wall height ({wall.height}m)"
                            ),
                        )
                    )

    return errors


def _wall_point_at_offset(wall: Wall, offset: float) -> tuple[float, float]:
    """Get world-space (x, y) at given offset along wall."""
    dx = wall.end.x - wall.start.x
    dy = wall.end.y - wall.start.y
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-6:
        return (wall.start.x, wall.start.y)
    ratio = offset / length
    return (wall.start.x + dx * ratio, wall.start.y + dy * ratio)


def _point_on_segment(
    px: float,
    py: float,
    sx: float,
    sy: float,
    ex: float,
    ey: float,
    tol: float = 0.05,
) -> bool:
    """Check if point (px, py) lies on segment (sx, sy)-(ex, ey) within tolerance."""
    min_x, max_x = min(sx, ex) - tol, max(sx, ex) + tol
    min_y, max_y = min(sy, ey) - tol, max(sy, ey) + tol
    if not (min_x <= px <= max_x and min_y <= py <= max_y):
        return False
    dx, dy = ex - sx, ey - sy
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-6:
        return math.sqrt((px - sx) ** 2 + (py - sy) ** 2) < tol
    dist = abs(dy * px - dx * py + ex * sy - ey * sx) / length
    return dist < tol


def _check_openings_cross_walls(story: Story) -> list[ValidationError]:
    """Check that door/window openings don't cross through other walls.

    A door creates an opening in its host wall. If another wall's endpoint
    falls inside that opening, the door physically can't exist there.
    """
    errors: list[ValidationError] = []

    # Check doors
    for door in story.doors:
        host = story.get_wall(door.wall_id)
        if not host:
            continue
        p_start = _wall_point_at_offset(host, door.position)
        p_end = _wall_point_at_offset(host, door.position + door.width)

        for other in story.walls:
            if other.global_id == host.global_id:
                continue
            for pt_label, pt in [
                ("start", (other.start.x, other.start.y)),
                ("end", (other.end.x, other.end.y)),
            ]:
                if _point_on_segment(
                    pt[0], pt[1], p_start[0], p_start[1], p_end[0], p_end[1]
                ):
                    errors.append(
                        ValidationError(
                            severity="error",
                            element_type="Door",
                            element_id=door.global_id,
                            message=(
                                f"Door '{door.name}' opening crosses wall "
                                f"'{other.name}' ({pt_label} at "
                                f"{pt[0]:.1f},{pt[1]:.1f}) on host wall "
                                f"'{host.name}'"
                            ),
                        )
                    )

    # Check windows
    for window in story.windows:
        host = story.get_wall(window.wall_id)
        if not host:
            continue
        p_start = _wall_point_at_offset(host, window.position)
        p_end = _wall_point_at_offset(host, window.position + window.width)

        for other in story.walls:
            if other.global_id == host.global_id:
                continue
            for pt_label, pt in [
                ("start", (other.start.x, other.start.y)),
                ("end", (other.end.x, other.end.y)),
            ]:
                if _point_on_segment(
                    pt[0], pt[1], p_start[0], p_start[1], p_end[0], p_end[1]
                ):
                    errors.append(
                        ValidationError(
                            severity="error",
                            element_type="Window",
                            element_id=window.global_id,
                            message=(
                                f"Window '{window.name}' opening crosses wall "
                                f"'{other.name}' ({pt_label} at "
                                f"{pt[0]:.1f},{pt[1]:.1f}) on host wall "
                                f"'{host.name}'"
                            ),
                        )
                    )

    return errors


def _check_walls_cross_core(story: Story) -> list[ValidationError]:
    """Check that non-core walls don't pass through core areas.

    Core areas (elevator shaft, staircase) are defined by walls whose names
    contain keywords like 'elevator', 'staircase', 'core', 'divider'.
    Non-core walls (apartment partitions, bathroom walls, etc.) must not
    physically intersect these areas.
    """
    errors: list[ValidationError] = []
    CORE_KEYWORDS = {"elevator", "staircase", "core", "divider"}

    # Identify core walls and compute core bounding boxes
    core_walls = [
        w for w in story.walls
        if w.name and any(kw in w.name.lower() for kw in CORE_KEYWORDS)
    ]
    if not core_walls:
        return errors

    # Build core bounding box from core walls
    core_xs = [w.start.x for w in core_walls] + [w.end.x for w in core_walls]
    core_ys = [w.start.y for w in core_walls] + [w.end.y for w in core_walls]
    core_x_min, core_x_max = min(core_xs), max(core_xs)
    core_y_min, core_y_max = min(core_ys), max(core_ys)

    # Also identify sub-zones: elevator and staircase separately
    elev_walls = [w for w in core_walls if w.name and "elevator" in w.name.lower()]
    stair_walls = [w for w in core_walls if w.name and "staircase" in w.name.lower()]

    zones: list[tuple[str, float, float, float, float]] = []

    if elev_walls:
        ex = [w.start.x for w in elev_walls] + [w.end.x for w in elev_walls]
        ey = [w.start.y for w in elev_walls] + [w.end.y for w in elev_walls]
        zones.append(("elevator", min(ex), max(ex), min(ey), max(ey)))

    if stair_walls:
        sx = [w.start.x for w in stair_walls] + [w.end.x for w in stair_walls]
        sy = [w.start.y for w in stair_walls] + [w.end.y for w in stair_walls]
        zones.append(("staircase", min(sx), max(sx), min(sy), max(sy)))

    # Also add overall core zone
    zones.append(("core", core_x_min, core_x_max, core_y_min, core_y_max))

    # Shrink zones by small margin to avoid false positives at boundaries
    MARGIN = 0.05

    # Check each non-core wall
    non_core_walls = [
        w for w in story.walls
        if w.name and not any(kw in w.name.lower() for kw in CORE_KEYWORDS)
        and "corridor" not in w.name.lower()  # corridor walls border the core
        and "vestibule" not in w.name.lower()  # vestibule walls are part of core
    ]

    for wall in non_core_walls:
        wx_min = min(wall.start.x, wall.end.x)
        wx_max = max(wall.start.x, wall.end.x)
        wy_min = min(wall.start.y, wall.end.y)
        wy_max = max(wall.start.y, wall.end.y)

        for zone_name, zx_min, zx_max, zy_min, zy_max in zones:
            # Check if wall segment crosses through the interior of the zone
            # Wall must overlap with zone in BOTH x and y dimensions
            x_overlap = wx_max > zx_min + MARGIN and wx_min < zx_max - MARGIN
            y_overlap = wy_max > zy_min + MARGIN and wy_min < zy_max - MARGIN

            if x_overlap and y_overlap:
                # Exclude walls that only touch the zone boundary
                # (their start or end is on the zone edge)
                is_boundary = (
                    abs(wx_min - zx_min) < MARGIN or abs(wx_max - zx_max) < MARGIN
                    or abs(wy_min - zy_min) < MARGIN or abs(wy_max - zy_max) < MARGIN
                )
                # For vertical walls: x must be strictly inside zone
                is_vertical = abs(wall.start.x - wall.end.x) < 0.01
                is_horizontal = abs(wall.start.y - wall.end.y) < 0.01

                if is_vertical:
                    x_inside = zx_min + MARGIN < wall.start.x < zx_max - MARGIN
                    if not x_inside:
                        continue
                elif is_horizontal:
                    y_inside = zy_min + MARGIN < wall.start.y < zy_max - MARGIN
                    if not y_inside:
                        continue

                errors.append(
                    ValidationError(
                        severity="error",
                        element_type="Wall",
                        element_id=wall.global_id,
                        message=(
                            f"Wall '{wall.name}' crosses through {zone_name} area "
                            f"({zx_min:.1f},{zy_min:.1f})→({zx_max:.1f},{zy_max:.1f})"
                        ),
                    )
                )
                break  # One error per wall is enough

    return errors
