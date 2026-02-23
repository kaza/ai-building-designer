"""Tests for spatial query tools."""

import pytest

from archicad_builder.generators.shell import generate_shell
from archicad_builder.generators.core import place_vertical_core
from archicad_builder.generators.corridor import carve_corridor
from archicad_builder.generators.apartments import subdivide_apartments
from archicad_builder.queries.spatial import (
    find_neighbors,
    find_above_below,
    extract_floor_context,
)


class TestFindNeighbors:
    """Tests for the spatial neighbor query."""

    def _make_building(self):
        b = generate_shell(num_floors=2, width=16, depth=12)
        place_vertical_core(b, core_x=6.75, core_y=3.5)
        carve_corridor(b, corridor_y=5.0, corridor_width=1.5)
        return b

    def test_wall_has_neighbors(self):
        b = self._make_building()
        # Get a wall from the ground floor
        wall = b.stories[0].walls[0]
        neighbors = find_neighbors(b, "Ground Floor", wall.global_id)
        assert len(neighbors) > 0

    def test_neighbors_sorted_by_distance(self):
        b = self._make_building()
        wall = b.stories[0].walls[0]
        neighbors = find_neighbors(b, "Ground Floor", wall.global_id)
        for i in range(len(neighbors) - 1):
            assert neighbors[i].distance <= neighbors[i + 1].distance

    def test_connected_walls_detected(self):
        b = generate_shell(num_floors=1, width=10, depth=8)
        # Corner walls should be connected
        south = next(w for w in b.stories[0].walls if "South" in w.name)
        neighbors = find_neighbors(b, "Ground Floor", south.global_id)
        connected = [n for n in neighbors if n.relationship == "connected"]
        assert len(connected) >= 1  # At least one corner connection

    def test_nonexistent_element_returns_empty(self):
        b = generate_shell(num_floors=1)
        neighbors = find_neighbors(b, "Ground Floor", "nonexistent_id")
        assert len(neighbors) == 0


class TestFindAboveBelow:
    """Tests for vertical alignment queries."""

    def test_bearing_walls_align(self):
        b = generate_shell(num_floors=3, width=16, depth=12)
        wall = b.stories[0].walls[0]  # South wall, floor 0
        matches = find_above_below(b, "Ground Floor", wall.global_id)
        assert len(matches) >= 2  # Should find same wall on floors 1 and 2

    def test_exact_alignment(self):
        b = generate_shell(num_floors=2, width=10, depth=8)
        wall = b.stories[0].walls[0]
        matches = find_above_below(b, "Ground Floor", wall.global_id)
        assert all(m.alignment_quality == "exact" for m in matches)

    def test_staircase_vertical_alignment(self):
        b = generate_shell(num_floors=3, width=16, depth=12)
        place_vertical_core(b, core_x=6, core_y=0)
        st = b.stories[0].staircases[0]
        matches = find_above_below(b, "Ground Floor", st.global_id)
        stair_matches = [m for m in matches if m.element_type == "staircase"]
        assert len(stair_matches) == 2  # floors 1 and 2


class TestExtractFloorContext:
    """Tests for floor context extraction."""

    def test_basic_context(self):
        b = generate_shell(num_floors=1, width=16, depth=12)
        ctx = extract_floor_context(b, "Ground Floor")
        assert ctx.story_name == "Ground Floor"
        assert ctx.wall_count == 4
        assert ctx.slab_count == 1
        assert abs(ctx.total_floor_area - 192.0) < 0.01

    def test_context_with_core(self):
        b = generate_shell(num_floors=1, width=16, depth=12)
        place_vertical_core(b, core_x=6, core_y=0)
        ctx = extract_floor_context(b, "Ground Floor")
        assert ctx.staircase_count == 1
        assert ctx.wall_count > 4

    def test_context_with_apartments(self):
        b = generate_shell(num_floors=1, width=16, depth=12)
        place_vertical_core(b, core_x=6.75, core_y=3.5)
        carve_corridor(b, corridor_y=5.0, corridor_width=1.5)
        subdivide_apartments(b, "Ground Floor", corridor_y=5.0)
        ctx = extract_floor_context(b, "Ground Floor")
        assert ctx.apartment_count == 4
        assert ctx.space_count == 16  # 4 apts × 4 rooms
        assert len(ctx.apartment_summaries) == 4

    def test_external_wall_names(self):
        b = generate_shell(num_floors=1, width=10, depth=8)
        ctx = extract_floor_context(b, "Ground Floor")
        assert "South Wall" in ctx.external_wall_names
        assert "North Wall" in ctx.external_wall_names
        assert len(ctx.external_wall_names) == 4

    def test_bearing_wall_names(self):
        b = generate_shell(num_floors=1, width=10, depth=8)
        place_vertical_core(b, core_x=3, core_y=0)
        ctx = extract_floor_context(b, "Ground Floor")
        assert len(ctx.bearing_wall_names) > 4  # Exterior + core walls
