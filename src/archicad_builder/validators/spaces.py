"""Space and apartment validators.

Validates room/apartment requirements:
- Minimum room size by type
- Apartment has bathroom
- Apartment has kitchen
- Apartment accessibility (has entry door from corridor)
"""

from __future__ import annotations

from shapely.geometry import Polygon as ShapelyPolygon
from shapely.validation import make_valid

from archicad_builder.models.building import Building, Story
from archicad_builder.models.spaces import MIN_ROOM_AREAS, Space
from archicad_builder.validators.structural import ValidationError


def validate_spaces(building: Building) -> list[ValidationError]:
    """Run all space/apartment validators. Returns list of errors."""
    errors: list[ValidationError] = []
    for story in building.stories:
        errors.extend(validate_room_sizes(story))
        errors.extend(validate_apartment_requirements(story))
    return errors


# Shared edges and half-thickness slivers (face vs centerline drawing) are
# fine; anything bigger corrupts geometric queries (specs/space-overlap.md).
OVERLAP_TOLERANCE_M2 = 0.05


def validate_space_overlaps(building: Building) -> list[ValidationError]:
    """E090: no two spaces on a story may overlap (specs/space-overlap.md).

    Overlapping space polygons silently corrupt every geometric tool
    downstream (connectivity graph, window/wall attribution), so this is
    an error-severity data invariant.
    """
    errors: list[ValidationError] = []
    for story in building.stories:
        spaces: list[Space] = list(story.spaces)
        for apt in story.apartments:
            spaces.extend(apt.spaces)

        polys = []
        for sp in spaces:
            verts = [(v.x, v.y) for v in sp.boundary.vertices]
            if len(verts) < 3:
                continue  # degenerate — nothing to overlap
            poly = make_valid(ShapelyPolygon(verts))  # repairs invalid rings
            if poly.is_empty:
                continue
            polys.append((sp, poly))

        for i in range(len(polys)):
            for j in range(i + 1, len(polys)):
                sp_a, poly_a = polys[i]
                sp_b, poly_b = polys[j]
                if not poly_a.intersects(poly_b):
                    continue  # fast path: disjoint
                overlap = poly_a.intersection(poly_b).area
                if overlap > OVERLAP_TOLERANCE_M2:
                    errors.append(ValidationError(
                        severity="error",
                        element_type="Space",
                        element_id=sp_a.global_id,
                        message=(
                            f"E090: Spaces '{sp_a.name}' and '{sp_b.name}' "
                            f"on '{story.name}' overlap by {overlap:.1f}m². "
                            f"Space polygons must not intersect — this "
                            f"corrupts connectivity and window queries."
                        ),
                    ))
    return errors


def validate_room_sizes(story: Story) -> list[ValidationError]:
    """Check that rooms meet minimum area requirements by type.

    Uses Austrian residential norms as baseline.
    """
    errors: list[ValidationError] = []

    all_spaces = list(story.spaces)
    for apt in story.apartments:
        all_spaces.extend(apt.spaces)

    for space in all_spaces:
        min_area = MIN_ROOM_AREAS.get(space.room_type)
        if min_area is not None and space.area < min_area:
            errors.append(
                ValidationError(
                    severity="warning",
                    element_type="Space",
                    element_id=space.global_id,
                    message=(
                        f"Room '{space.name}' ({space.room_type.value}) is "
                        f"{space.area:.1f}m² — minimum is {min_area:.1f}m² "
                        f"for {space.room_type.value} rooms."
                    ),
                )
            )

    return errors


def validate_apartment_requirements(story: Story) -> list[ValidationError]:
    """Check that each apartment has required rooms (bathroom, kitchen)."""
    errors: list[ValidationError] = []

    for apt in story.apartments:
        if not apt.has_bathroom():
            errors.append(
                ValidationError(
                    severity="error",
                    element_type="Apartment",
                    element_id=apt.global_id,
                    message=(
                        f"Apartment '{apt.name}' has no bathroom or toilet. "
                        f"Every dwelling unit needs at least one."
                    ),
                )
            )

        if not apt.has_kitchen():
            errors.append(
                ValidationError(
                    severity="warning",
                    element_type="Apartment",
                    element_id=apt.global_id,
                    message=(
                        f"Apartment '{apt.name}' has no kitchen. "
                        f"Consider adding a kitchen or kitchenette."
                    ),
                )
            )

    return errors
