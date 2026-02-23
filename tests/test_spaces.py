"""Tests for Space/Apartment models and apartment subdivision."""

import pytest

from archicad_builder.models import (
    Building, Point2D, Polygon2D, Space, Apartment, RoomType,
)
from archicad_builder.models.spaces import MIN_ROOM_AREAS
from archicad_builder.generators.shell import generate_shell
from archicad_builder.generators.core import place_vertical_core
from archicad_builder.generators.corridor import carve_corridor
from archicad_builder.generators.apartments import subdivide_apartments
from archicad_builder.validators.spaces import (
    validate_room_sizes,
    validate_apartment_requirements,
    validate_spaces,
)


class TestSpaceModel:
    """Tests for the Space model."""

    def test_create_space(self):
        s = Space(
            name="Living Room",
            room_type=RoomType.LIVING,
            boundary=Polygon2D(vertices=[
                Point2D(x=0, y=0), Point2D(x=5, y=0),
                Point2D(x=5, y=4), Point2D(x=0, y=4),
            ]),
        )
        assert abs(s.area - 20.0) < 0.01
        assert s.room_type == RoomType.LIVING

    def test_space_perimeter(self):
        s = Space(
            room_type=RoomType.BEDROOM,
            boundary=Polygon2D(vertices=[
                Point2D(x=0, y=0), Point2D(x=3, y=0),
                Point2D(x=3, y=4), Point2D(x=0, y=4),
            ]),
        )
        assert abs(s.perimeter - 14.0) < 0.01

    def test_space_serialization(self):
        s = Space(
            name="Kitchen",
            room_type=RoomType.KITCHEN,
            boundary=Polygon2D(vertices=[
                Point2D(x=0, y=0), Point2D(x=3, y=0),
                Point2D(x=3, y=2), Point2D(x=0, y=2),
            ]),
        )
        json_str = s.model_dump_json()
        s2 = Space.model_validate_json(json_str)
        assert s2.room_type == RoomType.KITCHEN
        assert abs(s2.area - 6.0) < 0.01


class TestApartmentModel:
    """Tests for the Apartment model."""

    def test_create_apartment(self):
        apt = Apartment(
            name="Apt 1",
            boundary=Polygon2D(vertices=[
                Point2D(x=0, y=0), Point2D(x=8, y=0),
                Point2D(x=8, y=5), Point2D(x=0, y=5),
            ]),
        )
        assert abs(apt.area - 40.0) < 0.01
        assert apt.room_count == 0

    def test_apartment_with_rooms(self):
        apt = Apartment(
            name="Apt 1",
            boundary=Polygon2D(vertices=[
                Point2D(x=0, y=0), Point2D(x=8, y=0),
                Point2D(x=8, y=5), Point2D(x=0, y=5),
            ]),
            spaces=[
                Space(name="Living", room_type=RoomType.LIVING,
                      boundary=Polygon2D(vertices=[
                          Point2D(x=0, y=0), Point2D(x=5, y=0),
                          Point2D(x=5, y=5), Point2D(x=0, y=5),
                      ])),
                Space(name="Bath", room_type=RoomType.BATHROOM,
                      boundary=Polygon2D(vertices=[
                          Point2D(x=5, y=0), Point2D(x=8, y=0),
                          Point2D(x=8, y=2.5), Point2D(x=5, y=2.5),
                      ])),
                Space(name="Hall", room_type=RoomType.HALLWAY,
                      boundary=Polygon2D(vertices=[
                          Point2D(x=5, y=2.5), Point2D(x=8, y=2.5),
                          Point2D(x=8, y=5), Point2D(x=5, y=5),
                      ])),
            ],
        )
        assert apt.room_count == 2  # living + bath (hallway excluded)
        assert apt.has_bathroom()
        assert not apt.has_kitchen()

    def test_get_space_by_type(self):
        apt = Apartment(
            name="Test",
            boundary=Polygon2D(vertices=[
                Point2D(x=0, y=0), Point2D(x=6, y=0),
                Point2D(x=6, y=4), Point2D(x=0, y=4),
            ]),
            spaces=[
                Space(name="BR1", room_type=RoomType.BEDROOM,
                      boundary=Polygon2D(vertices=[
                          Point2D(x=0, y=0), Point2D(x=3, y=0),
                          Point2D(x=3, y=4), Point2D(x=0, y=4),
                      ])),
                Space(name="BR2", room_type=RoomType.BEDROOM,
                      boundary=Polygon2D(vertices=[
                          Point2D(x=3, y=0), Point2D(x=6, y=0),
                          Point2D(x=6, y=4), Point2D(x=3, y=4),
                      ])),
            ],
        )
        bedrooms = apt.get_space_by_type(RoomType.BEDROOM)
        assert len(bedrooms) == 2


class TestSubdivideApartments:
    """Tests for the apartment subdivision generator."""

    def _make_building(self):
        """Create a standard building with shell + core + corridor."""
        b = generate_shell(num_floors=1, width=16, depth=12)
        place_vertical_core(b, core_x=6.75, core_y=3.5)
        carve_corridor(b, corridor_y=5.0, corridor_width=1.5)
        return b

    def test_creates_apartments(self):
        b = self._make_building()
        apts = subdivide_apartments(
            b, "Ground Floor",
            corridor_y=5.0, corridor_width=1.5,
            apartments_per_side=2,
        )
        assert len(apts) == 4  # 2 per side × 2 sides

    def test_apartment_boundaries(self):
        b = self._make_building()
        apts = subdivide_apartments(
            b, "Ground Floor",
            corridor_y=5.0, corridor_width=1.5,
            apartments_per_side=2,
        )
        # Each apartment should have non-zero area
        for apt in apts:
            assert apt.area > 10

    def test_apartments_have_rooms(self):
        b = self._make_building()
        apts = subdivide_apartments(
            b, "Ground Floor",
            corridor_y=5.0, corridor_width=1.5,
            apartments_per_side=2,
        )
        for apt in apts:
            assert len(apt.spaces) > 0

    def test_apartments_have_bathroom(self):
        b = self._make_building()
        apts = subdivide_apartments(
            b, "Ground Floor",
            corridor_y=5.0, corridor_width=1.5,
            apartments_per_side=2,
        )
        for apt in apts:
            assert apt.has_bathroom()

    def test_adds_partition_walls(self):
        b = self._make_building()
        walls_before = len(b.stories[0].walls)
        subdivide_apartments(
            b, "Ground Floor",
            corridor_y=5.0, corridor_width=1.5,
            apartments_per_side=2,
        )
        walls_after = len(b.stories[0].walls)
        # Should add partition walls between apartments
        # 2 partitions (1 south side, 1 north side)
        assert walls_after == walls_before + 2

    def test_adds_entry_doors(self):
        b = self._make_building()
        doors_before = len(b.stories[0].doors)
        subdivide_apartments(
            b, "Ground Floor",
            corridor_y=5.0, corridor_width=1.5,
            apartments_per_side=2,
        )
        doors_after = len(b.stories[0].doors)
        # Should add entry doors for apartments
        assert doors_after > doors_before

    def test_serialization_roundtrip(self):
        b = self._make_building()
        subdivide_apartments(
            b, "Ground Floor",
            corridor_y=5.0, corridor_width=1.5,
        )
        json_str = b.model_dump_json()
        b2 = Building.model_validate_json(json_str)
        assert len(b2.stories[0].apartments) == 4


class TestSpaceValidators:
    """Tests for space/apartment validators."""

    def test_room_size_warning(self):
        """Room below minimum area triggers warning."""
        b = Building(name="Test")
        story = b.add_story("GF", height=3.0)
        story.spaces.append(Space(
            name="Tiny Bath",
            room_type=RoomType.BATHROOM,
            boundary=Polygon2D(vertices=[
                Point2D(x=0, y=0), Point2D(x=1, y=0),
                Point2D(x=1, y=1), Point2D(x=0, y=1),
            ]),  # 1m² — below 4m² minimum
        ))
        errors = validate_room_sizes(story)
        assert len(errors) == 1
        assert "minimum" in errors[0].message

    def test_room_size_ok(self):
        """Room meeting minimum area → no warning."""
        b = Building(name="Test")
        story = b.add_story("GF", height=3.0)
        story.spaces.append(Space(
            name="Good Bath",
            room_type=RoomType.BATHROOM,
            boundary=Polygon2D(vertices=[
                Point2D(x=0, y=0), Point2D(x=2, y=0),
                Point2D(x=2, y=2.5), Point2D(x=0, y=2.5),
            ]),  # 5m² — above 4m² minimum
        ))
        errors = validate_room_sizes(story)
        assert len(errors) == 0

    def test_apartment_missing_bathroom(self):
        b = Building(name="Test")
        story = b.add_story("GF", height=3.0)
        story.apartments.append(Apartment(
            name="Bad Apt",
            boundary=Polygon2D(vertices=[
                Point2D(x=0, y=0), Point2D(x=8, y=0),
                Point2D(x=8, y=5), Point2D(x=0, y=5),
            ]),
            spaces=[
                Space(name="Living", room_type=RoomType.LIVING,
                      boundary=Polygon2D(vertices=[
                          Point2D(x=0, y=0), Point2D(x=8, y=0),
                          Point2D(x=8, y=5), Point2D(x=0, y=5),
                      ])),
            ],
        ))
        errors = validate_apartment_requirements(story)
        assert any("bathroom" in e.message.lower() for e in errors)

    def test_apartment_with_bathroom_passes(self):
        b = Building(name="Test")
        story = b.add_story("GF", height=3.0)
        story.apartments.append(Apartment(
            name="Good Apt",
            boundary=Polygon2D(vertices=[
                Point2D(x=0, y=0), Point2D(x=8, y=0),
                Point2D(x=8, y=5), Point2D(x=0, y=5),
            ]),
            spaces=[
                Space(name="Bath", room_type=RoomType.BATHROOM,
                      boundary=Polygon2D(vertices=[
                          Point2D(x=5, y=0), Point2D(x=8, y=0),
                          Point2D(x=8, y=2), Point2D(x=5, y=2),
                      ])),
            ],
        ))
        errors = validate_apartment_requirements(story)
        bathroom_errors = [e for e in errors if "bathroom" in e.message.lower()]
        assert len(bathroom_errors) == 0

    def test_generated_building_spaces(self):
        """Full generated building with apartments should pass space validation."""
        b = generate_shell(num_floors=1, width=16, depth=12)
        place_vertical_core(b, core_x=6.75, core_y=3.5)
        carve_corridor(b, corridor_y=5.0, corridor_width=1.5)
        subdivide_apartments(b, "Ground Floor", corridor_y=5.0, corridor_width=1.5)
        errors = validate_spaces(b)
        # Should have no errors (maybe some size warnings)
        real_errors = [e for e in errors if e.severity == "error"]
        assert len(real_errors) == 0
