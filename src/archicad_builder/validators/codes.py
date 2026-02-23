"""Building code validators.

Encodes Austrian/EU residential building norms:
- Corridor minimum width (OIB RL 4: ≥ 1.20m for multi-unit buildings)
- Fire escape distance (OIB RL 2: max ~25-40m to staircase depending on category)
- Staircase dimensions (OIB RL 4: min width 1.20m, max rise 0.20m, min going 0.23m)
- Door minimum widths (OIB RL 4: 0.80m rooms, 0.90m apt entry, 1.00m building entry)
- Ceiling height minimum (OIB RL 3: ≥ 2.50m for habitable rooms)

Sources:
- OIB-Richtlinie 2: Brandschutz
- OIB-Richtlinie 3: Hygiene, Gesundheit und Umweltschutz
- OIB-Richtlinie 4: Nutzungssicherheit und Barrierefreiheit
"""

from __future__ import annotations

import math

from archicad_builder.models.building import Building, Story
from archicad_builder.models.geometry import Point2D
from archicad_builder.validators.structural import ValidationError


def validate_building_codes(building: Building) -> list[ValidationError]:
    """Run all building code validators."""
    errors: list[ValidationError] = []
    errors.extend(validate_corridor_width(building))
    errors.extend(validate_fire_escape_distance(building))
    errors.extend(validate_staircase_dimensions(building))
    errors.extend(validate_door_widths(building))
    errors.extend(validate_ceiling_height(building))
    return errors


def validate_corridor_width(
    building: Building,
    min_width: float = 1.20,
) -> list[ValidationError]:
    """Check corridor width meets minimum (OIB RL 4: ≥ 1.20m).

    Detects corridor walls (named "Corridor *") and checks the
    perpendicular distance between parallel corridor walls.
    """
    errors: list[ValidationError] = []

    for story in building.stories:
        south_walls = [w for w in story.walls if "Corridor South" in (w.name or "")]
        north_walls = [w for w in story.walls if "Corridor North" in (w.name or "")]

        for sw in south_walls:
            for nw in north_walls:
                # Check if they're parallel and compute distance
                # Assuming horizontal corridors: distance is |y_north - y_south|
                sy = (sw.start.y + sw.end.y) / 2
                ny = (nw.start.y + nw.end.y) / 2
                corridor_width = abs(ny - sy)

                # Subtract wall thicknesses (clear width)
                clear_width = corridor_width - sw.thickness / 2 - nw.thickness / 2

                if clear_width < min_width - 0.01:  # 1cm tolerance
                    errors.append(
                        ValidationError(
                            severity="error",
                            element_type="Corridor",
                            element_id=sw.global_id,
                            message=(
                                f"Corridor on '{story.name}' has clear width "
                                f"{clear_width:.2f}m — minimum is {min_width:.2f}m "
                                f"(OIB RL 4)."
                            ),
                        )
                    )

    return errors


def validate_fire_escape_distance(
    building: Building,
    max_distance: float = 35.0,
) -> list[ValidationError]:
    """Check max distance from apartment entry to nearest staircase (OIB RL 2).

    In multi-unit residential buildings, the walking distance from any
    apartment door to the nearest staircase should not exceed ~35m
    (simplified; actual code depends on building class and fire resistance).
    """
    errors: list[ValidationError] = []

    for story in building.stories:
        if not story.staircases:
            continue  # has_staircase validator handles this

        # Find staircase centers
        stair_centers = []
        for st in story.staircases:
            cx = sum(v.x for v in st.outline.vertices) / len(st.outline.vertices)
            cy = sum(v.y for v in st.outline.vertices) / len(st.outline.vertices)
            stair_centers.append(Point2D(x=cx, y=cy))

        # Check each apartment entry door
        for apt in story.apartments:
            apt_center = Point2D(
                x=sum(v.x for v in apt.boundary.vertices) / len(apt.boundary.vertices),
                y=sum(v.y for v in apt.boundary.vertices) / len(apt.boundary.vertices),
            )

            min_dist = min(
                _distance(apt_center, sc) for sc in stair_centers
            )

            if min_dist > max_distance:
                errors.append(
                    ValidationError(
                        severity="error",
                        element_type="Apartment",
                        element_id=apt.global_id,
                        message=(
                            f"'{apt.name}' on '{story.name}' is {min_dist:.1f}m "
                            f"from nearest staircase — max allowed is {max_distance:.1f}m "
                            f"(OIB RL 2 fire escape)."
                        ),
                    )
                )

    return errors


def validate_staircase_dimensions(building: Building) -> list[ValidationError]:
    """Check staircase flight dimensions (OIB RL 4).

    - Min clear width: 1.20m (multi-unit residential)
    - Max riser height: 0.20m
    - Min tread depth (going): 0.23m
    - Stufenformel (step formula): 2h + g = 0.59-0.65m
    """
    errors: list[ValidationError] = []

    for story in building.stories:
        for st in story.staircases:
            # Width check
            if st.width < 1.20:
                errors.append(
                    ValidationError(
                        severity="error",
                        element_type="Staircase",
                        element_id=st.global_id,
                        message=(
                            f"Staircase '{st.name}' on '{story.name}' has width "
                            f"{st.width:.2f}m — minimum is 1.20m (OIB RL 4)."
                        ),
                    )
                )

            # Riser height check
            if st.riser_height > 0.20:
                errors.append(
                    ValidationError(
                        severity="error",
                        element_type="Staircase",
                        element_id=st.global_id,
                        message=(
                            f"Staircase '{st.name}' riser height {st.riser_height:.3f}m "
                            f"exceeds maximum 0.200m (OIB RL 4)."
                        ),
                    )
                )

            # Tread depth check
            if st.tread_length < 0.23:
                errors.append(
                    ValidationError(
                        severity="error",
                        element_type="Staircase",
                        element_id=st.global_id,
                        message=(
                            f"Staircase '{st.name}' tread depth {st.tread_length:.3f}m "
                            f"is below minimum 0.230m (OIB RL 4)."
                        ),
                    )
                )

            # Step formula: 2h + g should be 0.59-0.65m
            step_sum = 2 * st.riser_height + st.tread_length
            if step_sum < 0.59 or step_sum > 0.65:
                errors.append(
                    ValidationError(
                        severity="warning",
                        element_type="Staircase",
                        element_id=st.global_id,
                        message=(
                            f"Staircase '{st.name}' step formula: "
                            f"2×{st.riser_height:.3f} + {st.tread_length:.3f} = "
                            f"{step_sum:.3f}m — should be 0.59-0.65m (comfort range)."
                        ),
                    )
                )

    return errors


def validate_door_widths(building: Building) -> list[ValidationError]:
    """Check door widths meet minimums (OIB RL 4).

    - Room doors: ≥ 0.80m
    - Apartment entry: ≥ 0.90m (identified by name containing "Entry")
    - Building entry: ≥ 1.00m (identified by name containing "Building" or "Main")
    """
    errors: list[ValidationError] = []

    for story in building.stories:
        for door in story.doors:
            name = (door.name or "").lower()

            if "building" in name or "main entry" in name:
                min_width = 1.00
                door_type = "building entry"
            elif "entry" in name:
                min_width = 0.90
                door_type = "apartment entry"
            else:
                min_width = 0.80
                door_type = "room"

            if door.width < min_width - 0.01:
                errors.append(
                    ValidationError(
                        severity="error",
                        element_type="Door",
                        element_id=door.global_id,
                        message=(
                            f"Door '{door.name}' on '{story.name}' is "
                            f"{door.width:.2f}m wide — minimum for {door_type} "
                            f"door is {min_width:.2f}m (OIB RL 4)."
                        ),
                    )
                )

    return errors


def validate_ceiling_height(
    building: Building,
    min_height: float = 2.50,
) -> list[ValidationError]:
    """Check ceiling height for habitable rooms (OIB RL 3: ≥ 2.50m).

    Uses story height minus slab thickness as proxy for clear room height.
    """
    errors: list[ValidationError] = []

    for story in building.stories:
        slab_thickness = max(
            (s.thickness for s in story.slabs if s.is_floor),
            default=0.0,
        )
        clear_height = story.height - slab_thickness

        if clear_height < min_height - 0.01:
            errors.append(
                ValidationError(
                    severity="error",
                    element_type="Story",
                    element_id=story.global_id,
                    message=(
                        f"Story '{story.name}' has clear height "
                        f"{clear_height:.2f}m (floor height {story.height}m "
                        f"minus slab {slab_thickness:.2f}m) — minimum is "
                        f"{min_height:.2f}m for habitable rooms (OIB RL 3)."
                    ),
                )
            )

    return errors


def _distance(p1: Point2D, p2: Point2D) -> float:
    """Euclidean distance between two points."""
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)
