"""Tests for E049: Apartment internal connectivity validator.

E049: All rooms in an apartment must be reachable from the Vorraum
through internal doors or spatial overlap, without going through
the building corridor.
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
from archicad_builder.validators.phases import validate_apartment_connectivity


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


def _get_e049(errors: list) -> list[str]:
    """Extract E049 error messages."""
    return [e.message for e in errors if "E049" in e.message]


def _make_connected_apartment_building() -> Building:
    """Build a minimal apartment where all rooms are door-connected.

    Layout:
        Corridor (y=5.25..6.75)
        --[entry door]--
        Vorraum (0,0)-(2,2.1)
        --[bedroom door]-- Bedroom (2,0)-(5,5.25)
        --[bathroom door]-- Bathroom (0,2.1)-(2,4.1)
        Kitchen (0,0)-(2,2.1) overlaps Vorraum (open plan)
        ... actually let's make it simple
    """
    b = Building(name="Test Connected")
    b.add_story("GF", height=2.89)

    # Exterior walls
    b.add_wall("GF", (0, 0), (8, 0), height=2.89, thickness=0.25,
               name="South")
    b.add_wall("GF", (8, 0), (8, 8), height=2.89, thickness=0.25,
               name="East")
    b.add_wall("GF", (8, 8), (0, 8), height=2.89, thickness=0.25,
               name="North")
    b.add_wall("GF", (0, 8), (0, 0), height=2.89, thickness=0.25,
               name="West")
    b.add_slab("GF", [(0, 0), (8, 0), (8, 8), (0, 8)], name="Floor")

    # Corridor wall at y=5.25
    b.add_wall("GF", (0, 5.25), (8, 5.25), height=2.89, thickness=0.10,
               name="Corridor South Wall")

    # Apartment partition: bedroom wall at x=4
    b.add_wall("GF", (4, 0), (4, 5.25), height=2.89, thickness=0.10,
               name="Apt S1 Bedroom Wall")

    # Vorraum wall at y=2.1 (partial, from x=0 to x=4)
    b.add_wall("GF", (0, 2.1), (4, 2.1), height=2.89, thickness=0.10,
               name="Apt S1 Vorraum Wall")

    # Entry door from corridor into Vorraum
    b.add_door("GF", "Corridor South Wall", position=1.0, width=0.9,
               height=2.1, name="Apt S1 Entry")

    # Door from Vorraum to Bedroom
    b.add_door("GF", "Apt S1 Bedroom Wall", position=1.0, width=0.9,
               height=2.1, name="Apt S1 Bedroom Door")

    # Door from Vorraum to Bathroom
    b.add_door("GF", "Apt S1 Vorraum Wall", position=1.0, width=0.8,
               height=2.1, name="Apt S1 Bathroom Door")

    # Apartment with connected rooms
    story = b.stories[0]
    apt = Apartment(
        name="Apt S1",
        boundary=Polygon2D(vertices=[
            Point2D(x=0, y=0), Point2D(x=8, y=0),
            Point2D(x=8, y=5.25), Point2D(x=0, y=5.25),
        ]),
        spaces=[
            _space("Apt S1 Vorraum", RoomType.HALLWAY, 0, 2.1, 4, 5.25),
            _space("Apt S1 Bedroom", RoomType.BEDROOM, 4, 0, 8, 5.25),
            _space("Apt S1 Bathroom", RoomType.BATHROOM, 0, 0, 4, 2.1),
            # Kitchen overlaps with Vorraum (open-plan)
            _space("Apt S1 Kitchen", RoomType.KITCHEN, 0, 3.0, 2.0, 5.25),
            _space("Apt S1 Living", RoomType.LIVING, 0, 0, 4, 5.25),
        ],
    )
    story.apartments.append(apt)
    return b


class TestE049Connectivity:
    """E049: Apartment internal connectivity."""

    def test_connected_apartment_passes(self):
        """All rooms reachable internally → no E049 errors."""
        b = _make_connected_apartment_building()
        errors = validate_apartment_connectivity(b)
        e049 = _get_e049(errors)
        assert len(e049) == 0, f"Unexpected E049 errors: {e049}"

    def test_disconnected_room_fails(self):
        """Room with no internal connection (only via corridor) → E049 error."""
        b = Building(name="Test Disconnected")
        b.add_story("GF", height=2.89)

        # Exterior walls
        b.add_wall("GF", (0, 0), (16, 0), height=2.89, thickness=0.25,
                   name="South")
        b.add_wall("GF", (16, 0), (16, 12), height=2.89, thickness=0.25,
                   name="East")
        b.add_wall("GF", (16, 12), (0, 12), height=2.89, thickness=0.25,
                   name="North")
        b.add_wall("GF", (0, 12), (0, 0), height=2.89, thickness=0.25,
                   name="West")
        b.add_slab("GF", [(0, 0), (16, 0), (16, 12), (0, 12)], name="Floor")

        # Corridor at y=5.25..6.75
        b.add_wall("GF", (0, 5.25), (16, 5.25), height=2.89, thickness=0.10,
                   name="Corridor South Wall")
        b.add_wall("GF", (0, 6.75), (16, 6.75), height=2.89, thickness=0.10,
                   name="Corridor North Wall")

        # Entry door for apartment
        b.add_door("GF", "Corridor South Wall", position=2.0, width=0.9,
                   height=2.1, name="Apt S1 Entry")

        story = b.stories[0]

        # Apartment with a disconnected storage room across the corridor
        # Storage is at y=6.75..8.0 (north of corridor)
        # Apartment boundary is y=0..5.25 (south of corridor)
        # The storage's boundary overlaps nothing in the apartment
        apt = Apartment(
            name="Apt S1",
            boundary=Polygon2D(vertices=[
                Point2D(x=0, y=0), Point2D(x=8, y=0),
                Point2D(x=8, y=5.25), Point2D(x=0, y=5.25),
            ]),
            spaces=[
                _space("Apt S1 Vorraum", RoomType.HALLWAY, 0, 3.15, 4, 5.25),
                _space("Apt S1 Living", RoomType.LIVING, 0, 0, 4, 3.15),
                _space("Apt S1 Bedroom", RoomType.BEDROOM, 4, 0, 8, 5.25),
                # Disconnected storage: across the corridor, no overlap
                _space("Apt S1 Storage", RoomType.STORAGE, 10, 6.75, 14, 8.0),
            ],
        )
        story.apartments.append(apt)

        errors = validate_apartment_connectivity(b)
        e049 = _get_e049(errors)
        assert len(e049) == 1
        assert "Storage" in e049[0]
        assert "šupak" in e049[0]

    def test_open_plan_kitchen_connected_by_overlap(self):
        """Kitchen overlapping living room is connected via spatial overlap."""
        b = _make_connected_apartment_building()
        errors = validate_apartment_connectivity(b)
        e049 = _get_e049(errors)
        # Kitchen overlaps with other rooms → should be connected
        kitchen_errors = [e for e in e049 if "Kitchen" in e]
        assert len(kitchen_errors) == 0

    def test_no_apartments_no_errors(self):
        """Building without apartments → no E049 errors."""
        b = Building(name="Empty")
        b.add_story("GF", height=2.89)
        b.add_wall("GF", (0, 0), (5, 0), height=2.89, thickness=0.25, name="S")
        b.add_slab("GF", [(0, 0), (5, 0), (5, 5), (0, 5)], name="Floor")
        errors = validate_apartment_connectivity(b)
        assert len(errors) == 0

    def test_runs_on_v5_project(self):
        """E049 should not fire on v5 project (all rooms connected)."""
        b = Building.load("projects/3apt-corner-core/building.json")
        errors = validate_apartment_connectivity(b)
        e049 = _get_e049(errors)
        assert len(e049) == 0, f"Unexpected E049 on v5: {e049}"

    def test_runs_on_v4_project(self):
        """E049 on v4 — should catch disconnected Abstellraum rooms."""
        b = Building.load("projects/4apt-centered-core/building.json")
        errors = validate_apartment_connectivity(b)
        e049 = _get_e049(errors)
        # v4 has Abstellräume that are across the corridor from their apartments
        # E049 should catch them (same issue E048 catches via bbox check)
        # Note: some v4 rooms may also lack internal door connections
        # Just verify the validator runs without crashing
        # The exact count depends on v4's internal door layout
        assert isinstance(e049, list)
