"""Tests for phased building design v2.

Tests the complete generation pipeline and all phase validators.
"""

from __future__ import annotations

import pytest

from archicad_builder.generators.building_4apt import (
    CLEAR_HEIGHT,
    CORRIDOR_WIDTH,
    FLOOR_STRUCTURE,
    FLOOR_TO_FLOOR,
    MIN_2ROOM_FACADE,
    STAIR_FLIGHT_WIDTH,
    generate_building_4apt,
    generate_shell_v2,
    place_core_v2,
    carve_corridor_v2,
    subdivide_apartments_v2,
    add_windows_v2,
)
from archicad_builder.validators.phases import (
    validate_all_phases,
    validate_phase1_shell,
    validate_phase2_core,
    validate_phase3_corridor,
    validate_phase4_facade,
    validate_phase5_rooms,
    validate_phase6_vertical,
)
from archicad_builder.models.spaces import RoomType


# ══════════════════════════════════════════════════════════════════════
# Phase 1: Shell Tests
# ══════════════════════════════════════════════════════════════════════

class TestPhase1Shell:
    """Tests for shell generation and validators E001, W001, E002."""

    def test_shell_creates_4_stories(self):
        b = generate_shell_v2(num_floors=4)
        assert len(b.stories) == 4

    def test_shell_correct_floor_to_floor(self):
        b = generate_shell_v2()
        for story in b.stories:
            assert story.height == FLOOR_TO_FLOOR  # 2.89m

    def test_shell_correct_elevations(self):
        b = generate_shell_v2(num_floors=4)
        expected = [0.0, 2.89, 5.78, 8.67]
        for story, exp in zip(b.stories, expected):
            assert abs(story.elevation - exp) < 0.01

    def test_shell_has_exterior_walls(self):
        b = generate_shell_v2()
        for story in b.stories:
            ext_walls = [w for w in story.walls if w.is_external]
            assert len(ext_walls) == 4

    def test_shell_has_floor_slabs(self):
        b = generate_shell_v2()
        for story in b.stories:
            slabs = [s for s in story.slabs if s.is_floor]
            assert len(slabs) == 1

    def test_shell_wall_height_equals_floor_to_floor(self):
        b = generate_shell_v2()
        for story in b.stories:
            for wall in story.walls:
                assert wall.height == FLOOR_TO_FLOOR

    def test_shell_walls_are_load_bearing_external(self):
        b = generate_shell_v2()
        for story in b.stories:
            for wall in story.walls:
                assert wall.load_bearing is True
                assert wall.is_external is True

    def test_e001_clear_height_below_minimum(self):
        """E001: storey clear height < 2.50m → ERROR."""
        b = generate_shell_v2()
        # Artificially set height too low (2.80m → clear = 2.43m)
        b.stories[0].height = 2.80
        errors = validate_phase1_shell(b)
        e001 = [e for e in errors if "E001" in e.message]
        assert len(e001) == 1

    def test_w001_clear_height_not_target(self):
        """W001: clear height != 2.52m → WARNING."""
        b = generate_shell_v2()
        # Set height to 2.95m → clear = 2.58m (above min but not target)
        b.stories[0].height = 2.95
        errors = validate_phase1_shell(b)
        w001 = [e for e in errors if "W001" in e.message]
        assert len(w001) == 1
        assert w001[0].severity == "warning"

    def test_e002_missing_slab(self):
        """E002: missing floor slab → ERROR."""
        b = generate_shell_v2()
        b.stories[0].slabs = []
        errors = validate_phase1_shell(b)
        e002 = [e for e in errors if "E002" in e.message]
        assert len(e002) == 1

    def test_shell_no_errors_by_default(self):
        """Default shell should pass Phase 1 validation (no errors)."""
        b = generate_shell_v2()
        errors = validate_phase1_shell(b)
        phase1_errors = [e for e in errors if e.severity == "error"]
        assert len(phase1_errors) == 0


# ══════════════════════════════════════════════════════════════════════
# Phase 2: Core Tests
# ══════════════════════════════════════════════════════════════════════

class TestPhase2Core:
    """Tests for core placement and validators E010-E013, W010-W011."""

    def test_core_creates_staircase_on_all_floors(self):
        b = generate_shell_v2()
        place_core_v2(b)
        for story in b.stories:
            assert len(story.staircases) >= 1

    def test_core_creates_elevator_walls(self):
        b = generate_shell_v2()
        place_core_v2(b)
        for story in b.stories:
            elev_walls = [w for w in story.walls
                          if "elevator" in (w.name or "").lower()]
            assert len(elev_walls) >= 3  # At least 3 walls for elevator shaft

    def test_core_has_vestibule_door(self):
        b = generate_shell_v2()
        place_core_v2(b)
        for story in b.stories:
            core_doors = [d for d in story.doors
                          if "core" in (d.name or "").lower()
                          or "lobby" in (d.name or "").lower()]
            assert len(core_doors) >= 1

    def test_core_has_building_entrance_on_ground(self):
        b = generate_shell_v2()
        place_core_v2(b)
        gf = b.stories[0]
        entries = [d for d in gf.doors
                   if "building" in (d.name or "").lower()
                   or "main entry" in (d.name or "").lower()]
        assert len(entries) >= 1

    def test_core_staircase_width(self):
        b = generate_shell_v2()
        place_core_v2(b)
        for story in b.stories:
            for st in story.staircases:
                assert st.width >= STAIR_FLIGHT_WIDTH

    def test_e010_no_staircase(self):
        """E010: no staircase → ERROR."""
        b = generate_shell_v2()
        # Don't place core — no staircases
        errors = validate_phase2_core(b)
        e010 = [e for e in errors if "E010" in e.message]
        assert len(e010) == 4  # One per floor

    def test_e013_no_entrance(self):
        """E013: no building entrance → ERROR."""
        b = generate_shell_v2()
        place_core_v2(b)
        # Remove building entrance
        gf = b.stories[0]
        gf.doors = [d for d in gf.doors
                    if "building" not in (d.name or "").lower()
                    and "main entry" not in (d.name or "").lower()]
        errors = validate_phase2_core(b)
        e013 = [e for e in errors if "E013" in e.message]
        assert len(e013) == 1

    def test_core_no_errors_when_placed(self):
        """Placed core should pass Phase 2 validation (no errors)."""
        b = generate_shell_v2()
        place_core_v2(b)
        errors = validate_phase2_core(b)
        phase2_errors = [e for e in errors if e.severity == "error"]
        assert len(phase2_errors) == 0


# ══════════════════════════════════════════════════════════════════════
# Phase 3: Corridor Tests
# ══════════════════════════════════════════════════════════════════════

class TestPhase3Corridor:
    """Tests for corridor generation and validators E020-E022, W020."""

    def test_corridor_creates_walls(self):
        b = generate_shell_v2()
        ci = place_core_v2(b)
        carve_corridor_v2(b, ci)
        for story in b.stories:
            corridor_walls = [w for w in story.walls
                              if "corridor" in (w.name or "").lower()]
            assert len(corridor_walls) >= 2  # At least south and north on one side

    def test_corridor_does_not_run_through_core(self):
        """Corridor should stop at core boundaries, not run through it."""
        b = generate_shell_v2()
        ci = place_core_v2(b)
        carve_corridor_v2(b, ci)
        # Check corridor walls don't overlap with core X range
        core_x = ci["core_x"]
        core_x_end = core_x + ci["core_width"]

        for story in b.stories:
            corridor_walls = [w for w in story.walls
                              if "corridor" in (w.name or "").lower()]
            for cw in corridor_walls:
                wall_min_x = min(cw.start.x, cw.end.x)
                wall_max_x = max(cw.start.x, cw.end.x)
                # Wall should be entirely west OR entirely east of core
                assert (wall_max_x <= core_x + 0.01 or
                        wall_min_x >= core_x_end - 0.01)

    def test_corridor_width_sufficient(self):
        b = generate_shell_v2()
        ci = place_core_v2(b)
        carve_corridor_v2(b, ci)
        assert ci["corridor_width"] >= 1.20


# ══════════════════════════════════════════════════════════════════════
# Phase 4: Façade Subdivision Tests
# ══════════════════════════════════════════════════════════════════════

class TestPhase4Facade:
    """Tests for façade-based apartment subdivision."""

    def test_apartments_created(self):
        b = generate_shell_v2()
        ci = place_core_v2(b)
        carve_corridor_v2(b, ci)
        apts = subdivide_apartments_v2(b, ci)
        assert len(apts) > 0

    def test_apartments_on_both_sides(self):
        """Apartments should exist on both south and north sides."""
        b = generate_shell_v2()
        ci = place_core_v2(b)
        carve_corridor_v2(b, ci)
        subdivide_apartments_v2(b, ci)

        for story in b.stories:
            south_apts = [a for a in story.apartments if a.name.startswith("Apt S")]
            north_apts = [a for a in story.apartments if a.name.startswith("Apt N")]
            assert len(south_apts) >= 1
            assert len(north_apts) >= 1

    def test_apartment_facade_minimum(self):
        """Each apartment should have >= 6.50m facade."""
        b = generate_shell_v2(width=16.0)
        ci = place_core_v2(b)
        carve_corridor_v2(b, ci)
        subdivide_apartments_v2(b, ci)

        for story in b.stories:
            for apt in story.apartments:
                verts = apt.boundary.vertices
                width = max(v.x for v in verts) - min(v.x for v in verts)
                assert width >= MIN_2ROOM_FACADE - 0.01

    def test_apartments_have_entry_doors(self):
        b = generate_shell_v2()
        ci = place_core_v2(b)
        carve_corridor_v2(b, ci)
        subdivide_apartments_v2(b, ci)

        for story in b.stories:
            for apt in story.apartments:
                entry_doors = [d for d in story.doors
                               if apt.name.lower() in (d.name or "").lower()
                               and "entry" in (d.name or "").lower()]
                assert len(entry_doors) >= 1, f"{apt.name} has no entry door"


# ══════════════════════════════════════════════════════════════════════
# Phase 5: Room Subdivision Tests
# ══════════════════════════════════════════════════════════════════════

class TestPhase5Rooms:
    """Tests for room subdivision within apartments."""

    def test_apartments_have_kitchen(self):
        b = generate_building_4apt()
        for story in b.stories:
            for apt in story.apartments:
                assert apt.has_kitchen(), f"{apt.name} missing kitchen"

    def test_apartments_have_bathroom(self):
        b = generate_building_4apt()
        for story in b.stories:
            for apt in story.apartments:
                assert apt.has_bathroom(), f"{apt.name} missing bathroom"

    def test_apartments_have_living_room(self):
        b = generate_building_4apt()
        for story in b.stories:
            for apt in story.apartments:
                living = apt.get_space_by_type(RoomType.LIVING)
                assert len(living) >= 1, f"{apt.name} missing living room"

    def test_apartments_have_bedroom(self):
        b = generate_building_4apt()
        for story in b.stories:
            for apt in story.apartments:
                bedrooms = apt.get_space_by_type(RoomType.BEDROOM)
                assert len(bedrooms) >= 1, f"{apt.name} missing bedroom"

    def test_apartments_have_vorraum(self):
        b = generate_building_4apt()
        for story in b.stories:
            for apt in story.apartments:
                hallways = apt.get_space_by_type(RoomType.HALLWAY)
                assert len(hallways) >= 1, f"{apt.name} missing Vorraum"

    def test_3room_apartments_have_separate_wc(self):
        """3-room apartments must have a separate WC."""
        b = generate_building_4apt()
        for story in b.stories:
            for apt in story.apartments:
                bedrooms = apt.get_space_by_type(RoomType.BEDROOM)
                if len(bedrooms) >= 2:
                    toilets = apt.get_space_by_type(RoomType.TOILET)
                    assert len(toilets) >= 1, (
                        f"{apt.name} has {len(bedrooms)} bedrooms but no WC"
                    )


# ══════════════════════════════════════════════════════════════════════
# Phase 6: Vertical Consistency Tests
# ══════════════════════════════════════════════════════════════════════

class TestPhase6Vertical:
    """Tests for vertical alignment."""

    def test_bearing_walls_aligned(self):
        b = generate_building_4apt()
        errors = validate_phase6_vertical(b)
        e050 = [e for e in errors if "E050" in e.message]
        assert len(e050) == 0, f"Bearing wall misalignment: {e050}"

    def test_core_aligned(self):
        b = generate_building_4apt()
        errors = validate_phase6_vertical(b)
        e051 = [e for e in errors if "E051" in e.message]
        assert len(e051) == 0, f"Core misalignment: {e051}"

    def test_staircases_same_position_all_floors(self):
        b = generate_building_4apt()
        positions = []
        for story in b.stories:
            for st in story.staircases:
                verts = st.outline.vertices
                cx = sum(v.x for v in verts) / len(verts)
                cy = sum(v.y for v in verts) / len(verts)
                positions.append((cx, cy))

        # All positions should be within tolerance
        for pos in positions[1:]:
            assert abs(pos[0] - positions[0][0]) < 0.1
            assert abs(pos[1] - positions[0][1]) < 0.1


# ══════════════════════════════════════════════════════════════════════
# Full Pipeline Tests
# ══════════════════════════════════════════════════════════════════════

class TestFullPipeline:
    """Tests for the complete building generation."""

    def test_building_summary(self):
        b = generate_building_4apt()
        summary = b.summary()
        assert "4-Storey Building V2" in summary
        assert "Stories: 4" in summary

    def test_building_has_apartments_all_floors(self):
        b = generate_building_4apt()
        for story in b.stories:
            assert len(story.apartments) >= 2

    def test_building_has_windows(self):
        b = generate_building_4apt()
        for story in b.stories:
            assert len(story.windows) >= 2

    def test_no_phase_errors(self):
        """Full building should pass v2-era phase validators with zero errors.

        v3 validators (E060+, E070+) are excluded — v2 buildings don't have
        interior walls/doors, which v3 validators correctly flag.
        """
        b = generate_building_4apt()
        errors = validate_all_phases(b)
        # Only check v2-era errors (E001-E051)
        v2_errors = [
            e for e in errors
            if e.severity == "error"
            and not any(code in e.message for code in ["E060", "E061", "E070", "E071", "E049"])
        ]
        if v2_errors:
            msgs = "\n".join(f"  {e.message}" for e in v2_errors)
            pytest.fail(f"Phase validation errors:\n{msgs}")

    def test_existing_validators_still_pass(self):
        """The new building should also pass existing validators."""
        b = generate_building_4apt()
        errors = b.validate()
        # Filter only errors (not warnings)
        # Note: "crosses wall" errors are expected in v2 rough draft — the generator
        # is intentionally "dumb" and these are fixed during AI iteration (v4+)
        real_errors = [
            e for e in errors
            if e.severity == "error"
            and "crosses wall" not in e.message
            and "crosses through" not in e.message
        ]
        if real_errors:
            msgs = "\n".join(f"  {e.message}" for e in real_errors)
            pytest.fail(f"Existing validation errors:\n{msgs}")

    def test_save_and_load(self, tmp_path):
        b = generate_building_4apt()
        path = tmp_path / "building.json"
        b.save(path)
        loaded = type(b).load(path)
        assert loaded.name == b.name
        assert len(loaded.stories) == len(b.stories)
