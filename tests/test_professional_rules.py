"""Tests for professional design rule validators (W043-W045).

W043: Living room minimum façade width
W044: Kitchen minimum width
W045: WC minimum width
"""

import pytest

from archicad_builder.models import Building
from archicad_builder.models.spaces import (
    Apartment,
    Polygon2D,
    Point2D,
    RoomType,
    Space,
)
from archicad_builder.validators.phases import validate_phase5_rooms


def _make_building_with_apartment(
    apt_name: str, spaces: list[Space]
) -> Building:
    """Create a minimal building with one apartment containing the given spaces."""
    b = Building(name="Test Building")
    b.add_story("GF", height=2.89)
    story = b.stories[0]

    # Minimal shell so structural validators don't interfere
    b.add_wall("GF", (0, 0), (16, 0), height=2.89, thickness=0.25, name="South")
    b.add_wall("GF", (16, 0), (16, 12), height=2.89, thickness=0.25, name="East")
    b.add_wall("GF", (16, 12), (0, 12), height=2.89, thickness=0.25, name="North")
    b.add_wall("GF", (0, 12), (0, 0), height=2.89, thickness=0.25, name="West")
    b.add_slab("GF", [(0, 0), (16, 0), (16, 12), (0, 12)], name="Floor")

    apt = Apartment(
        name=apt_name,
        boundary=Polygon2D(vertices=[
            Point2D(x=0, y=0), Point2D(x=16, y=0),
            Point2D(x=16, y=12), Point2D(x=0, y=12),
        ]),
        spaces=spaces,
    )
    story.apartments.append(apt)
    return b


def _space(name: str, room_type: RoomType, x0: float, y0: float,
           x1: float, y1: float) -> Space:
    """Helper to create a rectangular Space."""
    return Space(
        name=name,
        room_type=room_type,
        boundary=Polygon2D(vertices=[
            Point2D(x=x0, y=y0), Point2D(x=x1, y=y0),
            Point2D(x=x1, y=y1), Point2D(x=x0, y=y1),
        ]),
    )


def _get_codes(errors: list, prefix: str) -> list[str]:
    """Extract error messages matching a code prefix."""
    return [e.message for e in errors if prefix in e.message]


# ═══════════════════════════════════════════════════════════════
# W043: Living Room Minimum Façade Width
# ═══════════════════════════════════════════════════════════════


class TestW043LivingRoomWidth:
    """Living room minimum façade width validator."""

    def test_2room_apt_living_ok(self):
        """2-room apartment with 3.60m+ living room → no warning."""
        spaces = [
            _space("Living", RoomType.LIVING, 0, 0, 3.8, 5.0),
            _space("Bedroom", RoomType.BEDROOM, 4, 0, 7, 5.0),
            _space("Kitchen", RoomType.KITCHEN, 0, 5, 3, 7.5),
            _space("Bathroom", RoomType.BATHROOM, 3, 5, 6, 7.5),
            _space("Vorraum", RoomType.HALLWAY, 6, 5, 8, 7.5),
        ]
        b = _make_building_with_apartment("Test Apt", spaces)
        errors = validate_phase5_rooms(b)
        w043 = _get_codes(errors, "W043")
        assert len(w043) == 0

    def test_2room_apt_living_too_narrow(self):
        """2-room apartment with <3.60m living room → warning."""
        spaces = [
            _space("Living", RoomType.LIVING, 0, 0, 3.4, 3.0),  # 3.4m × 3.0m — max=3.4m < 3.6m
            _space("Bedroom", RoomType.BEDROOM, 4, 0, 7, 5.0),
            _space("Kitchen", RoomType.KITCHEN, 0, 5, 3, 7.5),
            _space("Bathroom", RoomType.BATHROOM, 3, 5, 6, 7.5),
            _space("Vorraum", RoomType.HALLWAY, 6, 5, 8, 7.5),
        ]
        b = _make_building_with_apartment("Test Apt", spaces)
        errors = validate_phase5_rooms(b)
        w043 = _get_codes(errors, "W043")
        assert len(w043) == 1
        assert "3.40m" in w043[0]
        assert "3.60m" in w043[0]

    def test_3room_apt_living_needs_4m(self):
        """3-room apartment (2 bedrooms) with <4.00m living → warning."""
        spaces = [
            _space("Living", RoomType.LIVING, 0, 0, 3.8, 3.0),  # 3.8m × 3.0m — max=3.8m < 4.0m
            _space("Master", RoomType.BEDROOM, 4, 0, 7, 5.0),
            _space("Child", RoomType.BEDROOM, 7, 0, 10, 5.0),
            _space("Kitchen", RoomType.KITCHEN, 0, 5, 3, 7.5),
            _space("Bathroom", RoomType.BATHROOM, 3, 5, 6, 7.5),
            _space("Vorraum", RoomType.HALLWAY, 6, 5, 8, 7.5),
        ]
        b = _make_building_with_apartment("Test Apt", spaces)
        errors = validate_phase5_rooms(b)
        w043 = _get_codes(errors, "W043")
        assert len(w043) == 1
        assert "4.00m" in w043[0]
        assert "3+ room" in w043[0]

    def test_3room_apt_living_4m_ok(self):
        """3-room apartment with 4.00m+ living → no warning."""
        spaces = [
            _space("Living", RoomType.LIVING, 0, 0, 4.2, 5.0),  # 4.2m ≥ 4.0m
            _space("Master", RoomType.BEDROOM, 5, 0, 8, 5.0),
            _space("Child", RoomType.BEDROOM, 8, 0, 11, 5.0),
            _space("Kitchen", RoomType.KITCHEN, 0, 5, 3, 7.5),
            _space("Bathroom", RoomType.BATHROOM, 3, 5, 6, 7.5),
            _space("Vorraum", RoomType.HALLWAY, 6, 5, 8, 7.5),
        ]
        b = _make_building_with_apartment("Test Apt", spaces)
        errors = validate_phase5_rooms(b)
        w043 = _get_codes(errors, "W043")
        assert len(w043) == 0

    def test_studio_no_bedroom_uses_360(self):
        """Studio (0 bedrooms) uses 3.60m threshold."""
        spaces = [
            _space("Living", RoomType.LIVING, 0, 0, 3.4, 3.0),  # 3.4m × 3.0m — max=3.4m < 3.6m
            _space("Kitchen", RoomType.KITCHEN, 0, 5, 3, 7.5),
            _space("Bathroom", RoomType.BATHROOM, 3, 5, 6, 7.5),
            _space("Vorraum", RoomType.HALLWAY, 6, 5, 8, 7.5),
        ]
        b = _make_building_with_apartment("Studio", spaces)
        errors = validate_phase5_rooms(b)
        w043 = _get_codes(errors, "W043")
        assert len(w043) == 1
        assert "3.60m" in w043[0]


# ═══════════════════════════════════════════════════════════════
# W044: Kitchen Minimum Width
# ═══════════════════════════════════════════════════════════════


class TestW044KitchenWidth:
    """Kitchen minimum width validator."""

    def test_kitchen_wide_enough(self):
        """Kitchen ≥2.20m wide → no warning."""
        spaces = [
            _space("Living", RoomType.LIVING, 0, 0, 5, 5),
            _space("Kitchen", RoomType.KITCHEN, 0, 5, 2.4, 8),  # 2.4m wide
            _space("Bathroom", RoomType.BATHROOM, 3, 5, 6, 8),
            _space("Vorraum", RoomType.HALLWAY, 6, 5, 8, 8),
        ]
        b = _make_building_with_apartment("Test Apt", spaces)
        errors = validate_phase5_rooms(b)
        w044 = _get_codes(errors, "W044")
        assert len(w044) == 0

    def test_kitchen_too_narrow(self):
        """Kitchen <2.20m wide → warning."""
        spaces = [
            _space("Living", RoomType.LIVING, 0, 0, 5, 5),
            _space("Kitchen", RoomType.KITCHEN, 0, 5, 1.8, 8),  # 1.8m < 2.20m
            _space("Bathroom", RoomType.BATHROOM, 3, 5, 6, 8),
            _space("Vorraum", RoomType.HALLWAY, 6, 5, 8, 8),
        ]
        b = _make_building_with_apartment("Test Apt", spaces)
        errors = validate_phase5_rooms(b)
        w044 = _get_codes(errors, "W044")
        assert len(w044) == 1
        assert "1.80m" in w044[0]
        assert "2.20m" in w044[0]

    def test_kitchen_exactly_220(self):
        """Kitchen exactly 2.20m → no warning (boundary ok)."""
        spaces = [
            _space("Living", RoomType.LIVING, 0, 0, 5, 5),
            _space("Kitchen", RoomType.KITCHEN, 0, 5, 2.2, 8),  # exactly 2.20m
            _space("Bathroom", RoomType.BATHROOM, 3, 5, 6, 8),
            _space("Vorraum", RoomType.HALLWAY, 6, 5, 8, 8),
        ]
        b = _make_building_with_apartment("Test Apt", spaces)
        errors = validate_phase5_rooms(b)
        w044 = _get_codes(errors, "W044")
        assert len(w044) == 0

    def test_narrow_kitchen_tall_direction(self):
        """Kitchen 1.5m × 3.0m — width is 1.5m (narrower dim) → warning."""
        spaces = [
            _space("Living", RoomType.LIVING, 0, 0, 5, 5),
            _space("Kitchen", RoomType.KITCHEN, 0, 5, 1.5, 8),  # 1.5m × 3.0m
            _space("Bathroom", RoomType.BATHROOM, 3, 5, 6, 8),
            _space("Vorraum", RoomType.HALLWAY, 6, 5, 8, 8),
        ]
        b = _make_building_with_apartment("Test Apt", spaces)
        errors = validate_phase5_rooms(b)
        w044 = _get_codes(errors, "W044")
        assert len(w044) == 1


# ═══════════════════════════════════════════════════════════════
# W045: WC Minimum Width
# ═══════════════════════════════════════════════════════════════


class TestW045WCWidth:
    """WC (separate toilet) minimum width validator."""

    def test_wc_wide_enough(self):
        """WC ≥0.90m wide → no warning."""
        spaces = [
            _space("Living", RoomType.LIVING, 0, 0, 5, 5),
            _space("Master", RoomType.BEDROOM, 5, 0, 8, 5),
            _space("Child", RoomType.BEDROOM, 8, 0, 11, 5),
            _space("Kitchen", RoomType.KITCHEN, 0, 5, 3, 8),
            _space("Bathroom", RoomType.BATHROOM, 3, 5, 6, 8),
            _space("Vorraum", RoomType.HALLWAY, 6, 5, 8, 8),
            _space("WC", RoomType.TOILET, 8, 5, 9.0, 7),  # 1.0m wide
        ]
        b = _make_building_with_apartment("Test Apt", spaces)
        errors = validate_phase5_rooms(b)
        w045 = _get_codes(errors, "W045")
        assert len(w045) == 0

    def test_wc_too_narrow(self):
        """WC <0.90m wide → warning."""
        spaces = [
            _space("Living", RoomType.LIVING, 0, 0, 5, 5),
            _space("Master", RoomType.BEDROOM, 5, 0, 8, 5),
            _space("Child", RoomType.BEDROOM, 8, 0, 11, 5),
            _space("Kitchen", RoomType.KITCHEN, 0, 5, 3, 8),
            _space("Bathroom", RoomType.BATHROOM, 3, 5, 6, 8),
            _space("Vorraum", RoomType.HALLWAY, 6, 5, 8, 8),
            _space("WC", RoomType.TOILET, 8, 5, 8.6, 7),  # 0.6m < 0.9m
        ]
        b = _make_building_with_apartment("Test Apt", spaces)
        errors = validate_phase5_rooms(b)
        w045 = _get_codes(errors, "W045")
        assert len(w045) == 1
        assert "0.60m" in w045[0]
        assert "0.90m" in w045[0]

    def test_wc_exactly_90cm(self):
        """WC exactly 0.90m → no warning."""
        spaces = [
            _space("Living", RoomType.LIVING, 0, 0, 5, 5),
            _space("Master", RoomType.BEDROOM, 5, 0, 8, 5),
            _space("Child", RoomType.BEDROOM, 8, 0, 11, 5),
            _space("Kitchen", RoomType.KITCHEN, 0, 5, 3, 8),
            _space("Bathroom", RoomType.BATHROOM, 3, 5, 6, 8),
            _space("Vorraum", RoomType.HALLWAY, 6, 5, 8, 8),
            _space("WC", RoomType.TOILET, 8, 5, 8.9, 7),  # 0.9m exactly
        ]
        b = _make_building_with_apartment("Test Apt", spaces)
        errors = validate_phase5_rooms(b)
        w045 = _get_codes(errors, "W045")
        assert len(w045) == 0

    def test_no_wc_no_warning(self):
        """Apartment without WC → no W045 (WC presence is E045's job)."""
        spaces = [
            _space("Living", RoomType.LIVING, 0, 0, 5, 5),
            _space("Bedroom", RoomType.BEDROOM, 5, 0, 8, 5),
            _space("Kitchen", RoomType.KITCHEN, 0, 5, 3, 8),
            _space("Bathroom", RoomType.BATHROOM, 3, 5, 6, 8),
            _space("Vorraum", RoomType.HALLWAY, 6, 5, 8, 8),
        ]
        b = _make_building_with_apartment("Test Apt", spaces)
        errors = validate_phase5_rooms(b)
        w045 = _get_codes(errors, "W045")
        assert len(w045) == 0
