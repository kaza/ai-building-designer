"""Tests for building generation tools."""

import pytest

from archicad_builder.models import Building, Staircase, StaircaseType
from archicad_builder.generators.shell import generate_shell
from archicad_builder.generators.core import place_vertical_core
from archicad_builder.generators.corridor import carve_corridor
from archicad_builder.generators.template import stamp_floor_template


class TestGenerateShell:
    """Tests for the building shell generator."""

    def test_basic_shell(self):
        b = generate_shell(name="Test", width=16, depth=12, num_floors=4)
        assert b.name == "Test"
        assert b.story_count() == 4

    def test_story_names(self):
        b = generate_shell(num_floors=4)
        names = [s.name for s in b.stories]
        assert names == ["Ground Floor", "1st Floor", "2nd Floor", "3rd Floor"]

    def test_story_elevations(self):
        b = generate_shell(num_floors=3, floor_height=3.0)
        elevations = [s.elevation for s in b.stories]
        assert elevations == [0.0, 3.0, 6.0]

    def test_four_walls_per_story(self):
        b = generate_shell(num_floors=2)
        for story in b.stories:
            assert len(story.walls) == 4

    def test_walls_are_external_load_bearing(self):
        b = generate_shell(num_floors=1)
        for wall in b.stories[0].walls:
            assert wall.load_bearing is True
            assert wall.is_external is True

    def test_wall_names(self):
        b = generate_shell(num_floors=1)
        names = sorted(w.name for w in b.stories[0].walls)
        assert names == ["East Wall", "North Wall", "South Wall", "West Wall"]

    def test_one_slab_per_story(self):
        b = generate_shell(num_floors=3)
        for story in b.stories:
            assert len(story.slabs) == 1
            assert story.slabs[0].is_floor is True

    def test_slab_area(self):
        b = generate_shell(width=16, depth=12, num_floors=1)
        assert abs(b.stories[0].slabs[0].area - 192.0) < 0.01

    def test_custom_ground_floor_name(self):
        b = generate_shell(num_floors=1, ground_floor_name="EG")
        assert b.stories[0].name == "EG"

    def test_total_area(self):
        b = generate_shell(width=10, depth=8, num_floors=3)
        assert abs(b.total_area() - 240.0) < 0.01  # 80 * 3

    def test_wall_dimensions(self):
        b = generate_shell(width=16, depth=12, num_floors=1, wall_thickness=0.30)
        story = b.stories[0]
        south = next(w for w in story.walls if "South" in w.name)
        east = next(w for w in story.walls if "East" in w.name)
        assert abs(south.length - 16.0) < 0.01
        assert abs(east.length - 12.0) < 0.01
        assert south.thickness == 0.30

    def test_validates_clean(self):
        b = generate_shell(num_floors=2)
        errors = b.validate()
        # Filter out building-level errors (staircase missing is expected for bare shell)
        structural_errors = [
            e for e in errors
            if e.severity == "error" and "staircase" not in e.message.lower()
        ]
        assert len(structural_errors) == 0


class TestPlaceVerticalCore:
    """Tests for vertical core placement."""

    def test_core_adds_walls(self):
        b = generate_shell(num_floors=2, width=16, depth=12)
        walls_before = len(b.stories[0].walls)
        place_vertical_core(b, core_x=6, core_y=0)
        walls_after = len(b.stories[0].walls)
        # Should add elevator walls + divider + staircase walls
        assert walls_after > walls_before

    def test_core_adds_staircases(self):
        b = generate_shell(num_floors=3, width=16, depth=12)
        place_vertical_core(b, core_x=6, core_y=0)
        for story in b.stories:
            assert len(story.staircases) == 1
            assert story.staircases[0].name == "Main Staircase"

    def test_core_adds_doors(self):
        b = generate_shell(num_floors=2, width=16, depth=12)
        place_vertical_core(b, core_x=6, core_y=0, corridor_side="south")
        for story in b.stories:
            door_names = [d.name for d in story.doors]
            assert "Elevator Door" in door_names
            assert "Staircase Door" in door_names

    def test_core_walls_are_load_bearing(self):
        b = generate_shell(num_floors=1, width=16, depth=12)
        shell_walls = len(b.stories[0].walls)
        place_vertical_core(b, core_x=6, core_y=0)
        core_walls = b.stories[0].walls[shell_walls:]
        for wall in core_walls:
            assert wall.load_bearing is True
            assert wall.is_external is False

    def test_core_consistent_across_floors(self):
        b = generate_shell(num_floors=4, width=16, depth=12)
        place_vertical_core(b, core_x=6, core_y=0)
        # Same number of core elements on each floor
        core_wall_counts = [len(s.walls) for s in b.stories]
        assert len(set(core_wall_counts)) == 1  # all same

    def test_validates_no_errors(self):
        b = generate_shell(num_floors=2, width=16, depth=12)
        place_vertical_core(b, core_x=6, core_y=0)
        errors = b.validate()
        real_errors = [e for e in errors if e.severity == "error"]
        assert len(real_errors) == 0


class TestCarveCorridor:
    """Tests for corridor carving."""

    def test_adds_two_walls_per_story(self):
        b = generate_shell(num_floors=2, width=16, depth=12)
        walls_before = len(b.stories[0].walls)
        carve_corridor(b, corridor_y=5.0, corridor_width=1.5)
        assert len(b.stories[0].walls) == walls_before + 2

    def test_corridor_walls_are_partition(self):
        b = generate_shell(num_floors=1, width=16, depth=12)
        shell_count = len(b.stories[0].walls)
        carve_corridor(b, corridor_y=5.0)
        corridor_walls = b.stories[0].walls[shell_count:]
        for wall in corridor_walls:
            assert wall.load_bearing is False
            assert wall.is_external is False

    def test_corridor_width(self):
        b = generate_shell(num_floors=1, width=16, depth=12)
        carve_corridor(b, corridor_y=5.0, corridor_width=1.5)
        south = next(w for w in b.stories[0].walls if w.name == "Corridor South Wall")
        north = next(w for w in b.stories[0].walls if w.name == "Corridor North Wall")
        assert abs(south.start.y - 5.0) < 0.01
        assert abs(north.start.y - 6.5) < 0.01

    def test_auto_detect_width(self):
        b = generate_shell(num_floors=1, width=16, depth=12)
        carve_corridor(b, corridor_y=5.0)
        south = next(w for w in b.stories[0].walls if w.name == "Corridor South Wall")
        assert abs(south.length - 16.0) < 0.01


class TestStampFloorTemplate:
    """Tests for floor template stamping."""

    def test_stamps_walls(self):
        b = generate_shell(num_floors=3, width=10, depth=8)
        place_vertical_core(b, core_x=3, core_y=0)
        # Template is ground floor, stamp to 1st and 2nd
        stamp_floor_template(b, "Ground Floor", ["1st Floor", "2nd Floor"])
        gf = b.get_story("Ground Floor")
        f1 = b.get_story("1st Floor")
        assert len(f1.walls) == len(gf.walls)

    def test_stamps_doors(self):
        b = generate_shell(num_floors=2, width=10, depth=8)
        place_vertical_core(b, core_x=3, core_y=0)
        stamp_floor_template(b, "Ground Floor", ["1st Floor"])
        gf = b.get_story("Ground Floor")
        f1 = b.get_story("1st Floor")
        assert len(f1.doors) == len(gf.doors)

    def test_stamps_staircases(self):
        b = generate_shell(num_floors=2, width=10, depth=8)
        place_vertical_core(b, core_x=3, core_y=0)
        stamp_floor_template(b, "Ground Floor", ["1st Floor"])
        assert len(b.get_story("1st Floor").staircases) == 1

    def test_new_global_ids(self):
        b = generate_shell(num_floors=2, width=10, depth=8)
        place_vertical_core(b, core_x=3, core_y=0)
        stamp_floor_template(b, "Ground Floor", ["1st Floor"])
        gf_ids = {w.global_id for w in b.get_story("Ground Floor").walls}
        f1_ids = {w.global_id for w in b.get_story("1st Floor").walls}
        assert gf_ids.isdisjoint(f1_ids)  # no shared IDs

    def test_wall_refs_remapped(self):
        b = generate_shell(num_floors=2, width=10, depth=8)
        place_vertical_core(b, core_x=3, core_y=0)
        stamp_floor_template(b, "Ground Floor", ["1st Floor"])
        f1 = b.get_story("1st Floor")
        f1_wall_ids = {w.global_id for w in f1.walls}
        for door in f1.doors:
            assert door.wall_id in f1_wall_ids  # refs point to f1's walls

    def test_target_must_exist(self):
        b = generate_shell(num_floors=1)
        with pytest.raises(ValueError, match="not found"):
            stamp_floor_template(b, "Ground Floor", ["Nonexistent"])


class TestStaircaseModel:
    """Tests for the Staircase element type."""

    def test_create_staircase(self):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        st = b.add_staircase("GF", vertices=[(0, 0), (2.5, 0), (2.5, 5), (0, 5)])
        assert isinstance(st, Staircase)
        assert abs(st.area - 12.5) < 0.01

    def test_staircase_defaults(self):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        st = b.add_staircase("GF", vertices=[(0, 0), (2, 0), (2, 4), (0, 4)])
        assert st.width == 1.2
        assert st.riser_height == 0.175
        assert st.tread_length == 0.28
        assert st.stair_type == StaircaseType.STRAIGHT_RUN_STAIR

    def test_staircase_serialization(self):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        b.add_staircase("GF", vertices=[(0, 0), (2, 0), (2, 4), (0, 4)], name="ST1")
        json_str = b.model_dump_json()
        b2 = Building.model_validate_json(json_str)
        assert len(b2.stories[0].staircases) == 1
        assert b2.stories[0].staircases[0].name == "ST1"

    def test_staircase_tags(self):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        b.add_staircase("GF", vertices=[(0, 0), (2, 0), (2, 4), (0, 4)])
        b.add_staircase("GF", vertices=[(3, 0), (5, 0), (5, 4), (3, 4)])
        b.stories[0].ensure_tags()
        tags = [st.tag for st in b.stories[0].staircases]
        assert tags == ["ST1", "ST2"]
