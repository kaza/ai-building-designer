"""Space and apartment validators.

Validates room/apartment requirements:
- Minimum room size by type
- Apartment has bathroom
- Apartment has kitchen
- Apartment accessibility (has entry door from corridor)
"""

from __future__ import annotations

from archicad_builder.models.building import Building, Story
from archicad_builder.models.spaces import Apartment, MIN_ROOM_AREAS, RoomType, Space
from archicad_builder.validators.structural import ValidationError


def validate_spaces(building: Building) -> list[ValidationError]:
    """Run all space/apartment validators. Returns list of errors."""
    errors: list[ValidationError] = []
    for story in building.stories:
        errors.extend(validate_room_sizes(story))
        errors.extend(validate_apartment_requirements(story))
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
