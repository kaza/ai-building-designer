"""Tests for building-level validators."""

import pytest

from archicad_builder.models import Building, Point2D, Wall, Slab, Staircase
from archicad_builder.models.geometry import Polygon2D
from archicad_builder.models.ifc_id import generate_ifc_id
from archicad_builder.validators.building import (
    validate_bearing_wall_alignment,
    validate_has_staircase,
    validate_slab_completeness,
    validate_wall_closure,
    validate_building,
)
from archicad_builder.generators.shell import generate_shell
from archicad_builder.generators.core import place_vertical_core


class TestBearingWallAlignment:
    """Tests for load-bearing wall vertical alignment validator."""

    def test_aligned_walls_pass(self):
        """Identical bearing walls on two floors → no errors."""
        b = generate_shell(num_floors=2, width=10, depth=8)
        errors = validate_bearing_wall_alignment(b)
        assert len(errors) == 0

    def test_misaligned_wall_fails(self):
        """Bearing wall on upper floor with no match below → error."""
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        b.add_story("1F", height=3.0)

        # GF: wall at y=0
        w1 = b.add_wall("GF", (0, 0), (10, 0), 3.0, 0.25, name="South")
        w1.load_bearing = True

        # 1F: wall at y=2 (different position!)
        w2 = b.add_wall("1F", (0, 2), (10, 2), 3.0, 0.25, name="Shifted")
        w2.load_bearing = True

        errors = validate_bearing_wall_alignment(b)
        assert len(errors) == 1
        assert "no aligned bearing wall" in errors[0].message

    def test_partition_walls_ignored(self):
        """Non-bearing walls don't need vertical alignment."""
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        b.add_story("1F", height=3.0)

        # GF: bearing wall
        w1 = b.add_wall("GF", (0, 0), (10, 0), 3.0, 0.25, name="South")
        w1.load_bearing = True

        # 1F: same bearing wall + extra partition at different position
        w2 = b.add_wall("1F", (0, 0), (10, 0), 3.0, 0.25, name="South")
        w2.load_bearing = True
        w3 = b.add_wall("1F", (0, 5), (10, 5), 3.0, 0.10, name="Partition")
        w3.load_bearing = False  # not bearing, no alignment needed

        errors = validate_bearing_wall_alignment(b)
        assert len(errors) == 0

    def test_reversed_wall_direction_ok(self):
        """Wall defined start↔end reversed should still match."""
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        b.add_story("1F", height=3.0)

        w1 = b.add_wall("GF", (0, 0), (10, 0), 3.0, 0.25)
        w1.load_bearing = True
        # Same wall but reversed direction
        w2 = b.add_wall("1F", (10, 0), (0, 0), 3.0, 0.25)
        w2.load_bearing = True

        errors = validate_bearing_wall_alignment(b)
        assert len(errors) == 0

    def test_single_story_no_check(self):
        """Single-storey building has nothing to align."""
        b = generate_shell(num_floors=1)
        errors = validate_bearing_wall_alignment(b)
        assert len(errors) == 0

    def test_generated_building_passes(self):
        """A properly generated multi-storey building should pass."""
        b = generate_shell(num_floors=4, width=16, depth=12)
        place_vertical_core(b, core_x=6, core_y=0)
        errors = validate_bearing_wall_alignment(b)
        assert len(errors) == 0


class TestHasStaircase:
    """Tests for the staircase presence validator."""

    def test_single_storey_no_staircase_ok(self):
        b = generate_shell(num_floors=1)
        errors = validate_has_staircase(b)
        assert len(errors) == 0

    def test_multi_storey_no_staircase_fails(self):
        b = generate_shell(num_floors=3)
        errors = validate_has_staircase(b)
        assert len(errors) == 3  # one per story

    def test_multi_storey_with_staircase_passes(self):
        b = generate_shell(num_floors=3)
        place_vertical_core(b, core_x=6, core_y=0)
        errors = validate_has_staircase(b)
        assert len(errors) == 0

    def test_partial_staircase_fails(self):
        """Staircase on some floors but not all → errors for missing floors."""
        b = generate_shell(num_floors=3)
        # Only add staircase to ground floor
        b.add_staircase("Ground Floor", vertices=[(0, 0), (2, 0), (2, 4), (0, 4)])
        errors = validate_has_staircase(b)
        assert len(errors) == 2  # 1st and 2nd floor missing


class TestSlabCompleteness:
    """Tests for slab completeness validator."""

    def test_generated_building_passes(self):
        b = generate_shell(num_floors=3)
        errors = validate_slab_completeness(b)
        assert len(errors) == 0

    def test_missing_slab_fails(self):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        # No slab added
        errors = validate_slab_completeness(b)
        assert len(errors) == 1
        assert "no floor slab" in errors[0].message

    def test_ceiling_slab_not_counted(self):
        """A ceiling slab (is_floor=False) doesn't count as floor slab."""
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        b.add_slab("GF", [(0, 0), (10, 0), (10, 8), (0, 8)], is_floor=False)
        errors = validate_slab_completeness(b)
        assert len(errors) == 1  # ceiling doesn't count


class TestWallClosure:
    """Tests for exterior wall closure validator."""

    def test_closed_rectangle_passes(self):
        b = generate_shell(num_floors=1, width=10, depth=8)
        errors = validate_wall_closure(b)
        assert len(errors) == 0

    def test_gap_in_perimeter_fails(self):
        """External walls that don't connect → error."""
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        # Three walls, leaving a gap
        w1 = b.add_wall("GF", (0, 0), (10, 0), 3.0, 0.25, name="South")
        w1.is_external = True
        w2 = b.add_wall("GF", (10, 0), (10, 8), 3.0, 0.25, name="East")
        w2.is_external = True
        w3 = b.add_wall("GF", (10, 8), (0, 8), 3.0, 0.25, name="North")
        w3.is_external = True
        # Missing west wall → gap between (0,8) and (0,0)
        errors = validate_wall_closure(b)
        assert len(errors) >= 1
        assert any("not connected" in e.message for e in errors)

    def test_no_external_walls_ok(self):
        """Story with only internal walls → no exterior closure needed."""
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        w = b.add_wall("GF", (0, 0), (5, 0), 3.0, 0.15, name="Partition")
        w.is_external = False
        errors = validate_wall_closure(b)
        assert len(errors) == 0

    def test_multi_storey_all_checked(self):
        b = generate_shell(num_floors=3)
        errors = validate_wall_closure(b)
        assert len(errors) == 0


class TestValidateBuildingIntegration:
    """Integration test: validate_building runs all building-level checks."""

    def test_full_building_passes(self):
        b = generate_shell(num_floors=4, width=16, depth=12)
        place_vertical_core(b, core_x=6, core_y=0)
        errors = validate_building(b)
        assert len(errors) == 0

    def test_building_validate_method_includes_building_level(self):
        """Building.validate() should catch building-level issues too."""
        b = generate_shell(num_floors=2)
        # No staircase → building-level error
        all_errors = b.validate()
        staircase_errors = [e for e in all_errors if "staircase" in e.message.lower()]
        assert len(staircase_errors) > 0
