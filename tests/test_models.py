"""Tests for building element models."""

import pytest

from archicad_builder.models import (
    Building,
    Door,
    Point2D,
    Polygon2D,
    Roof,
    RoofType,
    Slab,
    Story,
    VirtualElement,
    Wall,
    Window,
    generate_ifc_id,
)


class TestWall:
    def test_create_simple(self):
        wall = Wall(
            start=Point2D(x=0, y=0),
            end=Point2D(x=5, y=0),
            height=3.0,
            thickness=0.2,
        )
        assert wall.length == 5.0
        assert len(wall.global_id) == 22

    def test_diagonal_wall(self):
        wall = Wall(
            start=Point2D(x=0, y=0),
            end=Point2D(x=3, y=4),
            height=3.0,
            thickness=0.2,
        )
        assert abs(wall.length - 5.0) < 1e-6

    def test_zero_length_rejected(self):
        with pytest.raises(ValueError, match="must be different"):
            Wall(
                start=Point2D(x=1, y=1),
                end=Point2D(x=1, y=1),
                height=3.0,
                thickness=0.2,
            )

    def test_negative_height_rejected(self):
        with pytest.raises(ValueError):
            Wall(
                start=Point2D(x=0, y=0),
                end=Point2D(x=5, y=0),
                height=-1.0,
                thickness=0.2,
            )

    def test_zero_thickness_rejected(self):
        with pytest.raises(ValueError):
            Wall(
                start=Point2D(x=0, y=0),
                end=Point2D(x=5, y=0),
                height=3.0,
                thickness=0.0,
            )

    def test_has_description(self):
        wall = Wall(
            start=Point2D(x=0, y=0),
            end=Point2D(x=5, y=0),
            height=3.0,
            thickness=0.2,
            description="Load-bearing exterior wall",
        )
        assert wall.description == "Load-bearing exterior wall"

    def test_load_bearing_and_external(self):
        wall = Wall(
            start=Point2D(x=0, y=0),
            end=Point2D(x=5, y=0),
            height=3.0,
            thickness=0.3,
            load_bearing=True,
            is_external=True,
        )
        assert wall.load_bearing is True
        assert wall.is_external is True

    def test_defaults_non_structural(self):
        wall = Wall(
            start=Point2D(x=0, y=0),
            end=Point2D(x=5, y=0),
            height=3.0,
            thickness=0.1,
        )
        assert wall.load_bearing is False
        assert wall.is_external is False


class TestSlab:
    def test_create(self):
        slab = Slab(
            outline=Polygon2D(
                vertices=[
                    Point2D(x=0, y=0),
                    Point2D(x=10, y=0),
                    Point2D(x=10, y=8),
                    Point2D(x=0, y=8),
                ]
            ),
            thickness=0.25,
        )
        assert slab.area == 80.0
        assert slab.is_floor is True


class TestDoor:
    def test_create(self):
        wall_id = generate_ifc_id()
        door = Door(
            wall_id=wall_id,
            position=1.0,
            width=0.9,
            height=2.1,
        )
        assert door.wall_id == wall_id

    def test_unreasonable_width(self):
        with pytest.raises(ValueError, match="unreasonable"):
            Door(wall_id=generate_ifc_id(), position=0, width=6.0, height=2.1)

    def test_unreasonable_height(self):
        with pytest.raises(ValueError, match="unreasonable"):
            Door(wall_id=generate_ifc_id(), position=0, width=0.9, height=5.0)


class TestWindow:
    def test_create_with_sill(self):
        window = Window(
            wall_id=generate_ifc_id(),
            position=2.0,
            width=1.2,
            height=1.5,
            sill_height=0.9,
        )
        assert window.sill_height == 0.9

    def test_default_sill(self):
        window = Window(
            wall_id=generate_ifc_id(),
            position=0,
            width=1.0,
            height=1.0,
        )
        assert window.sill_height == 0.9


class TestRoof:
    def test_flat_roof(self):
        roof = Roof(
            outline=Polygon2D(
                vertices=[
                    Point2D(x=0, y=0),
                    Point2D(x=10, y=0),
                    Point2D(x=10, y=8),
                    Point2D(x=0, y=8),
                ]
            ),
            roof_type=RoofType.FLAT,
            pitch=0,
        )
        assert roof.pitch == 0

    def test_gable_roof(self):
        roof = Roof(
            outline=Polygon2D(
                vertices=[
                    Point2D(x=0, y=0),
                    Point2D(x=10, y=0),
                    Point2D(x=10, y=8),
                    Point2D(x=0, y=8),
                ]
            ),
            roof_type=RoofType.GABLE,
            pitch=30,
        )
        assert roof.pitch == 30

    def test_flat_with_pitch_rejected(self):
        with pytest.raises(ValueError, match="pitch=0"):
            Roof(
                outline=Polygon2D(
                    vertices=[
                        Point2D(x=0, y=0),
                        Point2D(x=10, y=0),
                        Point2D(x=10, y=8),
                        Point2D(x=0, y=8),
                    ]
                ),
                roof_type=RoofType.FLAT,
                pitch=15,
            )

    def test_gable_zero_pitch_rejected(self):
        with pytest.raises(ValueError, match="pitch > 0"):
            Roof(
                outline=Polygon2D(
                    vertices=[
                        Point2D(x=0, y=0),
                        Point2D(x=10, y=0),
                        Point2D(x=10, y=8),
                        Point2D(x=0, y=8),
                    ]
                ),
                roof_type=RoofType.GABLE,
                pitch=0,
            )


class TestVirtualElement:
    def test_create(self):
        ve = VirtualElement(
            name="Kitchen-Living Boundary",
            start=Point2D(x=3, y=0),
            end=Point2D(x=3, y=4),
        )
        assert ve.length == 4.0
        assert len(ve.global_id) == 22

    def test_zero_length_rejected(self):
        with pytest.raises(ValueError, match="must be different"):
            VirtualElement(
                start=Point2D(x=1, y=1),
                end=Point2D(x=1, y=1),
            )

    def test_no_physical_properties(self):
        """VirtualElement has no thickness, load_bearing, etc."""
        ve = VirtualElement(start=Point2D(x=0, y=0), end=Point2D(x=5, y=0))
        assert not hasattr(ve, "thickness")
        assert not hasattr(ve, "load_bearing")


class TestStory:
    def test_create_with_elements(self):
        wall = Wall(
            start=Point2D(x=0, y=0),
            end=Point2D(x=5, y=0),
            height=3.0,
            thickness=0.2,
        )
        story = Story(
            name="Ground Floor",
            height=3.0,
            walls=[wall],
        )
        assert story.name == "Ground Floor"
        assert len(story.walls) == 1
        assert wall.global_id in story.wall_ids()

    def test_get_wall(self):
        wall = Wall(
            start=Point2D(x=0, y=0),
            end=Point2D(x=5, y=0),
            height=3.0,
            thickness=0.2,
        )
        story = Story(name="GF", height=3.0, walls=[wall])
        assert story.get_wall(wall.global_id) is not None
        assert story.get_wall(generate_ifc_id()) is None


class TestBuilding:
    def test_create_empty(self):
        b = Building(name="Test House")
        assert b.story_count() == 0
        assert b.total_area() == 0

    def test_with_stories(self):
        slab = Slab(
            outline=Polygon2D(
                vertices=[
                    Point2D(x=0, y=0),
                    Point2D(x=10, y=0),
                    Point2D(x=10, y=8),
                    Point2D(x=0, y=8),
                ]
            ),
            thickness=0.25,
        )
        story = Story(name="Ground Floor", height=3.0, slabs=[slab])
        building = Building(name="Test House", stories=[story])
        assert building.story_count() == 1
        assert building.total_area() == 80.0

    def test_get_story_by_name(self):
        story = Story(name="Ground Floor", height=3.0)
        building = Building(stories=[story])
        assert building.get_story("ground floor") is not None
        assert building.get_story("Basement") is None

    def test_only_meters(self):
        with pytest.raises(ValueError, match="meters"):
            Building(units="feet")

    def test_json_roundtrip(self):
        """Building serializes to JSON and back without data loss."""
        wall = Wall(
            start=Point2D(x=0, y=0),
            end=Point2D(x=5, y=0),
            height=3.0,
            thickness=0.2,
        )
        story = Story(name="GF", height=3.0, walls=[wall])
        building = Building(name="Roundtrip Test", stories=[story])

        json_str = building.model_dump_json()
        restored = Building.model_validate_json(json_str)

        assert restored.name == building.name
        assert len(restored.stories) == 1
        assert len(restored.stories[0].walls) == 1
        assert restored.stories[0].walls[0].length == wall.length
        # GlobalIds preserved through serialization
        assert restored.global_id == building.global_id
        assert restored.stories[0].global_id == story.global_id
        assert restored.stories[0].walls[0].global_id == wall.global_id
