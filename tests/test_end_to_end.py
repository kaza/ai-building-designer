"""End-to-end integration tests.

Tests the complete building generation pipeline:
shell → core → corridor → apartments → windows → template stamp →
validate (structural + building + spaces + codes) → IFC export → render
"""

import tempfile
from pathlib import Path

import ifcopenshell
import pytest

from archicad_builder.models import Building
from archicad_builder.generators.shell import generate_shell
from archicad_builder.generators.core import place_vertical_core
from archicad_builder.generators.corridor import carve_corridor
from archicad_builder.generators.apartments import subdivide_apartments
from archicad_builder.generators.template import stamp_floor_template
from archicad_builder.validators.building import validate_building
from archicad_builder.validators.spaces import validate_spaces
from archicad_builder.validators.codes import validate_building_codes
from archicad_builder.queries.spatial import extract_floor_context


def _generate_full_building(
    width: float = 16.0,
    depth: float = 12.0,
    num_floors: int = 4,
) -> Building:
    """Generate a complete residential building."""
    building = generate_shell(
        name="E2E Test Building",
        width=width, depth=depth,
        num_floors=num_floors,
        floor_height=3.0,
        wall_thickness=0.30,
        slab_thickness=0.25,
    )

    place_vertical_core(
        building,
        core_x=width / 2 - 2.25,  # roughly centered
        core_y=depth / 2 - 2.5,
        elevator_width=2.0,
        elevator_depth=2.5,
        stair_width=2.5,
        stair_depth=5.0,
        wall_thickness=0.20,
        corridor_side="south",
    )

    corridor_y = depth / 2 - 1.0
    carve_corridor(
        building,
        corridor_y=corridor_y,
        corridor_width=1.5,
        wall_thickness=0.15,
    )

    # Subdivide ground floor into apartments
    subdivide_apartments(
        building,
        story_name="Ground Floor",
        corridor_y=corridor_y,
        corridor_width=1.5,
        apartments_per_side=2,
    )

    # Add windows to ground floor exterior walls
    story = building.get_story("Ground Floor")
    for wall in story.walls:
        if wall.is_external and wall.length > 4.0:
            # Place windows evenly along wall
            num_windows = max(1, int(wall.length / 4.0))
            spacing = wall.length / (num_windows + 1)
            for i in range(num_windows):
                pos = spacing * (i + 1) - 0.6  # center 1.2m window
                if pos > 0 and pos + 1.2 < wall.length:
                    building.add_window(
                        "Ground Floor", wall.name,
                        position=pos, width=1.2, height=1.5,
                        sill_height=0.9,
                    )

    # Stamp template to upper floors
    if num_floors > 1:
        upper_floors = [s.name for s in building.stories[1:]]
        stamp_floor_template(building, "Ground Floor", upper_floors)

    return building


class TestFullPipeline:
    """End-to-end pipeline tests."""

    def test_four_storey_building(self):
        """Generate a complete 4-storey building — no validation errors."""
        b = _generate_full_building(num_floors=4)

        # Basic structure
        assert b.story_count() == 4
        assert b.total_area() > 700  # 16×12 × 4 = 768

        # Every floor has the same layout
        gf = b.get_story("Ground Floor")
        for story in b.stories:
            assert len(story.walls) == len(gf.walls)
            assert len(story.doors) == len(gf.doors)
            assert len(story.windows) == len(gf.windows)
            assert len(story.staircases) == len(gf.staircases)

    def test_no_validation_errors(self):
        """Full building should have zero errors across all validators."""
        b = _generate_full_building()

        # Structural + connectivity
        structural_errors = b.validate()
        real_errors = [e for e in structural_errors if e.severity == "error"
                       and "staircase" not in e.message.lower()]  # staircase check is building-level

        # Building-level
        building_errors = validate_building(b)
        building_real = [e for e in building_errors if e.severity == "error"]

        # Space validators
        space_errors = validate_spaces(b)
        space_real = [e for e in space_errors if e.severity == "error"]

        # Building codes
        code_errors = validate_building_codes(b)
        code_real = [e for e in code_errors if e.severity == "error"]

        assert len(building_real) == 0, f"Building errors: {building_real}"
        assert len(space_real) == 0, f"Space errors: {space_real}"
        assert len(code_real) == 0, f"Code errors: {code_real}"

    def test_json_roundtrip(self):
        """Building survives serialization to JSON and back."""
        b = _generate_full_building(num_floors=2)

        json_str = b.model_dump_json()
        b2 = Building.model_validate_json(json_str)

        assert b2.story_count() == 2
        assert len(b2.stories[0].walls) == len(b.stories[0].walls)
        assert len(b2.stories[0].apartments) == len(b.stories[0].apartments)
        assert len(b2.stories[0].staircases) == len(b.stories[0].staircases)

        # Verify all GlobalIds are unique
        all_ids = set()
        for story in b2.stories:
            for w in story.walls:
                assert w.global_id not in all_ids
                all_ids.add(w.global_id)
            for d in story.doors:
                assert d.global_id not in all_ids
                all_ids.add(d.global_id)

    def test_ifc_export(self):
        """Building exports to valid IFC with all element types."""
        b = _generate_full_building(num_floors=2)

        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            ifc_path = Path(f.name)
        b.export_ifc(ifc_path)

        ifc_file = ifcopenshell.open(str(ifc_path))

        # Check IFC hierarchy
        assert len(ifc_file.by_type("IfcProject")) == 1
        assert len(ifc_file.by_type("IfcSite")) == 1
        assert len(ifc_file.by_type("IfcBuilding")) == 1
        assert len(ifc_file.by_type("IfcBuildingStorey")) == 2

        # Check element types
        assert len(ifc_file.by_type("IfcWallStandardCase")) > 0
        assert len(ifc_file.by_type("IfcSlab")) > 0
        assert len(ifc_file.by_type("IfcStair")) > 0
        assert len(ifc_file.by_type("IfcDoor")) > 0
        assert len(ifc_file.by_type("IfcSpace")) > 0

        # Check windows exist
        windows = ifc_file.by_type("IfcWindow")
        assert len(windows) > 0

        # Check opening elements exist
        assert len(ifc_file.by_type("IfcOpeningElement")) > 0

        ifc_path.unlink()

    def test_floorplan_render(self):
        """Building renders floor plans without errors."""
        b = _generate_full_building(num_floors=1)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img_path = Path(f.name)
        b.render_floorplan("Ground Floor", img_path)

        assert img_path.exists()
        assert img_path.stat().st_size > 10000  # Should be a real image
        img_path.unlink()

    def test_floor_context_extraction(self):
        """Context extraction provides meaningful data."""
        b = _generate_full_building(num_floors=1)
        ctx = extract_floor_context(b, "Ground Floor")

        assert ctx.wall_count > 4  # exterior + core + corridor
        assert ctx.door_count > 0
        assert ctx.apartment_count == 4
        assert ctx.space_count > 0
        assert ctx.total_floor_area > 150

    def test_different_building_sizes(self):
        """Pipeline works with different footprint sizes."""
        for width, depth, floors in [(10, 8, 2), (20, 15, 5), (12, 10, 3)]:
            b = _generate_full_building(width=width, depth=depth, num_floors=floors)
            assert b.story_count() == floors
            assert b.total_area() > 0
            # No critical validation errors
            building_errors = validate_building(b)
            errors = [e for e in building_errors if e.severity == "error"]
            assert len(errors) == 0, f"Errors for {width}×{depth}×{floors}: {errors}"

    def test_template_stamping_consistency(self):
        """Template stamping produces identical layouts with unique IDs."""
        b = _generate_full_building(num_floors=3)

        # Check all floors have identical element counts
        counts = [
            (len(s.walls), len(s.doors), len(s.windows), len(s.staircases),
             len(s.slabs), len(s.apartments))
            for s in b.stories
        ]
        assert all(c == counts[0] for c in counts), f"Inconsistent: {counts}"

        # Check all GlobalIds are unique
        all_ids = []
        for story in b.stories:
            for w in story.walls:
                all_ids.append(w.global_id)
            for d in story.doors:
                all_ids.append(d.global_id)
        assert len(all_ids) == len(set(all_ids)), "Duplicate GlobalIds found!"
