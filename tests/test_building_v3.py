"""Tests for phased building design v3.

Tests v3 improvements: lobby, interior walls, interior doors, new validators.
"""

from __future__ import annotations

import pytest

from archicad_builder.generators.building_4apt import (
    BEDROOM_WIDTH_V3,
    DOOR_BATHROOM,
    DOOR_BUILDING,
    DOOR_ROOM,
    LOBBY_WIDTH,
    PARTITION_THICKNESS,
    SERVICE_DEPTH,
    generate_building_4apt_interior,
    place_core_v3,
    carve_corridor_v3,
    subdivide_apartments_v3,
    add_windows_v3,
)
from archicad_builder.generators.building_4apt import (
    FLOOR_TO_FLOOR,
    generate_shell_v2,
)
from archicad_builder.validators.phases import (
    validate_all_phases,
    validate_core_integrity,
    validate_interior_enclosure,
    validate_phase1_shell,
    validate_phase2_core,
    validate_phase5_rooms,
)
from archicad_builder.models.building import Building
from archicad_builder.models.spaces import RoomType


# ══════════════════════════════════════════════════════════════════════
# v3 Full Pipeline Tests
# ══════════════════════════════════════════════════════════════════════

class TestV3FullPipeline:
    """Tests for the complete v3 generation pipeline."""

    @pytest.fixture
    def building(self):
        return generate_building_4apt_interior(num_floors=2)

    def test_creates_2_stories(self, building):
        assert len(building.stories) == 2

    def test_ground_floor_has_lobby(self, building):
        """Ground floor must have lobby walls."""
        gf = building.stories[0]
        lobby_walls = [w for w in gf.walls if "lobby" in (w.name or "").lower()]
        assert len(lobby_walls) >= 2, "Ground floor needs at least 2 lobby walls"

    def test_ground_floor_has_entrance(self, building):
        """Ground floor must have building main entrance."""
        gf = building.stories[0]
        entries = [d for d in gf.doors if "building" in (d.name or "").lower()
                   or "main entry" in (d.name or "").lower()]
        assert len(entries) >= 1

    def test_upper_floor_no_entrance(self, building):
        """1st floor should NOT have a building entrance."""
        first = building.stories[1]
        entries = [d for d in first.doors if "building" in (d.name or "").lower()
                   and "main entry" in (d.name or "").lower()]
        assert len(entries) == 0

    def test_4_apartments_per_floor(self, building):
        for story in building.stories:
            assert len(story.apartments) == 4, f"{story.name} should have 4 apartments"

    def test_entrance_door_width(self, building):
        """Building entrance door should be standard width (1.00-1.40m)."""
        gf = building.stories[0]
        entries = [d for d in gf.doors if "building" in (d.name or "").lower()]
        for d in entries:
            assert 1.00 <= d.width <= 1.40, f"Entrance door width {d.width}m is non-standard"

    def test_no_phase_errors_v3(self, building):
        """v3 building should pass ALL validators (v2 + v3) with zero errors."""
        errors = validate_all_phases(building)
        phase_errors = [e for e in errors if e.severity == "error"]
        if phase_errors:
            msgs = "\n".join(f"  {e.message}" for e in phase_errors)
            pytest.fail(f"Phase validation errors:\n{msgs}")


# ══════════════════════════════════════════════════════════════════════
# Ground Floor Lobby Tests
# ══════════════════════════════════════════════════════════════════════

class TestGroundFloorLobby:
    """Tests for ground floor lobby placement."""

    @pytest.fixture
    def building(self):
        return generate_building_4apt_interior(num_floors=2)

    def test_lobby_walls_exist(self, building):
        gf = building.stories[0]
        west_lobby = gf.get_wall_by_name("Lobby West Wall")
        east_lobby = gf.get_wall_by_name("Lobby East Wall")
        assert west_lobby is not None, "Missing Lobby West Wall"
        assert east_lobby is not None, "Missing Lobby East Wall"

    def test_lobby_centered(self, building):
        """Lobby should be centered on the building."""
        gf = building.stories[0]
        west = gf.get_wall_by_name("Lobby West Wall")
        east = gf.get_wall_by_name("Lobby East Wall")
        lobby_center = (west.start.x + east.start.x) / 2
        building_center = 16.0 / 2  # Default width
        assert abs(lobby_center - building_center) < 0.1

    def test_lobby_width(self, building):
        """Lobby should be approximately LOBBY_WIDTH wide."""
        gf = building.stories[0]
        west = gf.get_wall_by_name("Lobby West Wall")
        east = gf.get_wall_by_name("Lobby East Wall")
        width = abs(east.start.x - west.start.x)
        assert abs(width - LOBBY_WIDTH) < 0.1

    def test_lobby_connects_entrance_to_corridor(self, building):
        """Lobby walls should run from y=0 (south wall) to corridor."""
        gf = building.stories[0]
        west = gf.get_wall_by_name("Lobby West Wall")
        assert min(west.start.y, west.end.y) < 0.1, "Lobby wall should start near y=0"
        assert max(west.start.y, west.end.y) > 4.0, "Lobby wall should reach corridor"


# ══════════════════════════════════════════════════════════════════════
# Interior Walls Tests
# ══════════════════════════════════════════════════════════════════════

class TestInteriorWalls:
    """Tests for interior partition walls in apartments."""

    @pytest.fixture
    def building(self):
        return generate_building_4apt_interior(num_floors=2)

    def test_bedroom_wall_exists(self, building):
        """Every apartment should have a bedroom wall."""
        for story in building.stories:
            for apt in story.apartments:
                bed_walls = [w for w in story.walls
                             if apt.name.lower() in (w.name or "").lower()
                             and "bedroom" in (w.name or "").lower()]
                assert len(bed_walls) >= 1, (
                    f"{apt.name} on {story.name} has no bedroom wall"
                )

    def test_bathroom_walls_exist(self, building):
        """Every apartment should have bathroom enclosure walls."""
        for story in building.stories:
            for apt in story.apartments:
                bath_walls = [w for w in story.walls
                              if apt.name.lower() in (w.name or "").lower()
                              and ("bathroom" in (w.name or "").lower()
                                   or "bath" in (w.name or "").lower())]
                assert len(bath_walls) >= 1, (
                    f"{apt.name} on {story.name} has no bathroom walls"
                )

    def test_interior_walls_are_partition(self, building):
        """Interior apartment walls should be non-load-bearing partitions."""
        for story in building.stories:
            for wall in story.walls:
                name = (wall.name or "").lower()
                if any(kw in name for kw in ["bedroom wall", "bathroom", "vorraum",
                                              "bath-vorraum"]):
                    assert not wall.load_bearing, (
                        f"Wall '{wall.name}' should be non-load-bearing partition"
                    )
                    assert wall.thickness <= 0.15, (
                        f"Partition wall '{wall.name}' is {wall.thickness}m thick"
                    )


# ══════════════════════════════════════════════════════════════════════
# Interior Doors Tests
# ══════════════════════════════════════════════════════════════════════

class TestInteriorDoors:
    """Tests for interior doors in apartments."""

    @pytest.fixture
    def building(self):
        return generate_building_4apt_interior(num_floors=2)

    def test_bedroom_door_exists(self, building):
        """Every apartment should have a bedroom door."""
        for story in building.stories:
            for apt in story.apartments:
                bed_doors = [d for d in story.doors
                             if apt.name.lower() in (d.name or "").lower()
                             and "bedroom" in (d.name or "").lower()]
                assert len(bed_doors) >= 1, (
                    f"{apt.name} on {story.name} has no bedroom door"
                )

    def test_bathroom_door_exists(self, building):
        """Every apartment should have a bathroom door."""
        for story in building.stories:
            for apt in story.apartments:
                bath_doors = [d for d in story.doors
                              if apt.name.lower() in (d.name or "").lower()
                              and "bathroom" in (d.name or "").lower()]
                assert len(bath_doors) >= 1, (
                    f"{apt.name} on {story.name} has no bathroom door"
                )

    def test_apartment_entry_door_exists(self, building):
        """Every apartment should have an entry door from corridor."""
        for story in building.stories:
            for apt in story.apartments:
                entry_doors = [d for d in story.doors
                               if apt.name.lower() in (d.name or "").lower()
                               and "entry" in (d.name or "").lower()]
                assert len(entry_doors) >= 1, (
                    f"{apt.name} on {story.name} has no entry door"
                )

    def test_door_widths_standard(self, building):
        """All doors should have standard widths (0.70-1.40m)."""
        for story in building.stories:
            for door in story.doors:
                assert 0.70 <= door.width <= 1.40, (
                    f"Door '{door.name}' width {door.width}m is non-standard"
                )


# ══════════════════════════════════════════════════════════════════════
# Room Sizing Tests
# ══════════════════════════════════════════════════════════════════════

class TestRoomSizing:
    """Tests for room dimensions (v3 improvements)."""

    @pytest.fixture
    def building(self):
        return generate_building_4apt_interior(num_floors=2)

    def test_upper_floor_bedroom_width(self, building):
        """Upper floor bedrooms should be ≥ BEDROOM_WIDTH_V3 (3.50m)."""
        first_floor = building.stories[1]
        for apt in first_floor.apartments:
            for sp in apt.spaces:
                if sp.room_type == RoomType.BEDROOM:
                    verts = sp.boundary.vertices
                    w = max(v.x for v in verts) - min(v.x for v in verts)
                    assert w >= BEDROOM_WIDTH_V3 - 0.01, (
                        f"{sp.name} width {w:.2f}m < {BEDROOM_WIDTH_V3}m"
                    )

    def test_upper_floor_bedroom_ratio(self, building):
        """Upper floor bedrooms should have aspect ratio ≤ 1.50."""
        first_floor = building.stories[1]
        for apt in first_floor.apartments:
            for sp in apt.spaces:
                if sp.room_type == RoomType.BEDROOM:
                    verts = sp.boundary.vertices
                    w = max(v.x for v in verts) - min(v.x for v in verts)
                    h = max(v.y for v in verts) - min(v.y for v in verts)
                    ratio = max(w, h) / min(w, h) if min(w, h) > 0 else 99
                    assert ratio <= 1.51, (
                        f"{sp.name} ratio {ratio:.2f} > 1.50"
                    )

    def test_upper_floor_bathroom_area(self, building):
        """Upper floor bathrooms should be ≥ 5m²."""
        first_floor = building.stories[1]
        for apt in first_floor.apartments:
            for sp in apt.spaces:
                if sp.room_type == RoomType.BATHROOM:
                    assert sp.area >= 5.0 - 0.01, (
                        f"{sp.name} area {sp.area:.1f}m² < 5.0m²"
                    )

    def test_bedroom_area_minimum(self, building):
        """All bedrooms should be ≥ 12m² (master)."""
        for story in building.stories:
            for apt in story.apartments:
                for sp in apt.spaces:
                    if sp.room_type == RoomType.BEDROOM:
                        assert sp.area >= 12.0 - 0.01, (
                            f"{sp.name} area {sp.area:.1f}m² < 12.0m²"
                        )


# ══════════════════════════════════════════════════════════════════════
# Core Integrity Validators Tests
# ══════════════════════════════════════════════════════════════════════

class TestCoreIntegrityValidators:
    """Tests for E060, E061, W060 validators."""

    def test_e060_wide_core_door(self):
        """E060: Door on core wall > 1.20m should be an error."""
        b = Building(name="Test")
        b.add_story("GF", height=FLOOR_TO_FLOOR)
        w = b.add_wall("GF", (0, 0), (10, 0), height=2.89, thickness=0.20, name="Core South Wall")
        w.load_bearing = True
        # Add oversized door on core wall
        b.add_door("GF", wall_name="Core South Wall", position=2.0, width=2.00, height=2.10,
                    name="Bad Core Door")

        errors = validate_core_integrity(b)
        e060 = [e for e in errors if "E060" in e.message]
        assert len(e060) >= 1, "Should catch oversized core door"

    def test_e060_normal_core_door(self):
        """Normal core door (0.90m) should not trigger E060."""
        b = Building(name="Test")
        b.add_story("GF", height=FLOOR_TO_FLOOR)
        w = b.add_wall("GF", (0, 0), (10, 0), height=2.89, thickness=0.20, name="Core South Wall")
        w.load_bearing = True
        b.add_door("GF", wall_name="Core South Wall", position=2.0, width=0.90, height=2.10,
                    name="Core Entry")

        errors = validate_core_integrity(b)
        e060 = [e for e in errors if "E060" in e.message]
        assert len(e060) == 0

    def test_e061_window_on_core_wall(self):
        """E061: Window on core wall should be an error."""
        b = Building(name="Test")
        b.add_story("GF", height=FLOOR_TO_FLOOR)
        w = b.add_wall("GF", (0, 0), (10, 0), height=2.89, thickness=0.20,
                        name="Staircase North Wall")
        w.load_bearing = True
        b.add_window("GF", wall_name="Staircase North Wall",
                      position=2.0, width=1.20, height=1.50, name="Bad Window")

        errors = validate_core_integrity(b)
        e061 = [e for e in errors if "E061" in e.message]
        assert len(e061) >= 1, "Should catch window on staircase wall"

    def test_e061_window_on_exterior_ok(self):
        """Window on exterior wall should not trigger E061."""
        b = Building(name="Test")
        b.add_story("GF", height=FLOOR_TO_FLOOR)
        w = b.add_wall("GF", (0, 0), (10, 0), height=2.89, thickness=0.30, name="South Wall")
        w.is_external = True
        b.add_window("GF", wall_name="South Wall",
                      position=2.0, width=1.20, height=1.50, name="Good Window")

        errors = validate_core_integrity(b)
        e061 = [e for e in errors if "E061" in e.message]
        assert len(e061) == 0

    def test_w060_suspicious_wide_door(self):
        """W060: Door > 1.20m should get a warning."""
        b = Building(name="Test")
        b.add_story("GF", height=FLOOR_TO_FLOOR)
        b.add_wall("GF", (0, 0), (10, 0), height=2.89, thickness=0.30, name="South Wall")
        b.add_door("GF", wall_name="South Wall", position=2.0, width=1.50, height=2.10,
                    name="Wide Door")

        errors = validate_core_integrity(b)
        w060 = [e for e in errors if "W060" in e.message]
        assert len(w060) >= 1


# ══════════════════════════════════════════════════════════════════════
# Interior Enclosure Validators Tests
# ══════════════════════════════════════════════════════════════════════

class TestInteriorEnclosureValidators:
    """Tests for E070, E071, E041b validators."""

    def _make_apartment_building(self, has_walls=True, has_doors=True, bath_area=6.0):
        """Helper to create a minimal building with one apartment."""
        from archicad_builder.models.spaces import Apartment, Space
        from archicad_builder.models.geometry import Point2D, Polygon2D

        b = Building(name="Test")
        story = b.add_story("GF", height=FLOOR_TO_FLOOR)

        # Exterior walls
        for start, end, name in [
            ((0, 0), (10, 0), "South Wall"),
            ((10, 0), (10, 8), "East Wall"),
            ((10, 8), (0, 8), "North Wall"),
            ((0, 8), (0, 0), "West Wall"),
        ]:
            w = b.add_wall("GF", start, end, height=2.89, thickness=0.30, name=name)
            w.is_external = True
            w.load_bearing = True

        b.add_slab("GF", [(0, 0), (10, 0), (10, 8), (0, 8)], name="Floor")

        # Apartment occupies full floor
        apt_boundary = Polygon2D(vertices=[
            Point2D(x=0, y=0), Point2D(x=10, y=0),
            Point2D(x=10, y=8), Point2D(x=0, y=8),
        ])

        bath_w = bath_area / 2.0  # 2m deep bathroom
        bath_d = 2.0

        spaces = [
            Space(name="Test Apt Bedroom", room_type=RoomType.BEDROOM,
                  boundary=Polygon2D(vertices=[
                      Point2D(x=6, y=0), Point2D(x=10, y=0),
                      Point2D(x=10, y=8), Point2D(x=6, y=8),
                  ])),
            Space(name="Test Apt Bathroom", room_type=RoomType.BATHROOM,
                  boundary=Polygon2D(vertices=[
                      Point2D(x=0, y=6), Point2D(x=bath_w, y=6),
                      Point2D(x=bath_w, y=8), Point2D(x=0, y=8),
                  ])),
            Space(name="Test Apt Living", room_type=RoomType.LIVING,
                  boundary=Polygon2D(vertices=[
                      Point2D(x=0, y=0), Point2D(x=6, y=0),
                      Point2D(x=6, y=6), Point2D(x=0, y=6),
                  ])),
        ]

        apt = Apartment(name="Test Apt", boundary=apt_boundary, spaces=spaces)
        story.apartments.append(apt)

        if has_walls:
            # Bedroom wall
            bw = b.add_wall("GF", (6, 0), (6, 8), height=2.89, thickness=0.10,
                            name="Test Apt Bedroom Wall")
            bw.load_bearing = False

            # Bathroom walls
            bw1 = b.add_wall("GF", (0, 6), (bath_w, 6), height=2.89, thickness=0.10,
                             name="Test Apt Bathroom Outer Wall")
            bw1.load_bearing = False
            bw2 = b.add_wall("GF", (bath_w, 6), (bath_w, 8), height=2.89, thickness=0.10,
                             name="Test Apt Bath-Vorraum Wall")
            bw2.load_bearing = False

        if has_doors:
            if has_walls:
                b.add_door("GF", wall_name="Test Apt Bedroom Wall",
                           position=2.0, width=0.80, height=2.10,
                           name="Test Apt Bedroom Door")
                b.add_door("GF", wall_name="Test Apt Bath-Vorraum Wall",
                           position=0.30, width=0.80, height=2.10,
                           name="Test Apt Bathroom Door")

        return b

    def test_e070_room_with_door_passes(self):
        """Room with a door should not trigger E070."""
        b = self._make_apartment_building(has_walls=True, has_doors=True)
        errors = validate_interior_enclosure(b)
        e070 = [e for e in errors if "E070" in e.message]
        assert len(e070) == 0, f"Unexpected E070: {[e.message for e in e070]}"

    def test_e070_room_without_door(self):
        """Room without a door should trigger E070."""
        b = self._make_apartment_building(has_walls=True, has_doors=False)
        errors = validate_interior_enclosure(b)
        e070 = [e for e in errors if "E070" in e.message]
        assert len(e070) >= 1, "Should catch room without door"

    def test_e071_bathroom_with_walls_passes(self):
        """Bathroom with walls should not trigger E071."""
        b = self._make_apartment_building(has_walls=True, has_doors=True)
        errors = validate_interior_enclosure(b)
        e071 = [e for e in errors if "E071" in e.message]
        assert len(e071) == 0, f"Unexpected E071: {[e.message for e in e071]}"

    def test_e071_bathroom_without_walls(self):
        """Bathroom without walls should trigger E071."""
        b = self._make_apartment_building(has_walls=False, has_doors=False)
        errors = validate_interior_enclosure(b)
        e071 = [e for e in errors if "E071" in e.message]
        assert len(e071) >= 1, "Should catch bathroom without walls"

    def test_e041b_small_bathroom(self):
        """Bathroom < 5m² should trigger E041b warning."""
        b = self._make_apartment_building(has_walls=True, has_doors=True, bath_area=3.5)
        errors = validate_interior_enclosure(b)
        e041b = [e for e in errors if "E041b" in e.message]
        assert len(e041b) >= 1, "Should warn about small bathroom"

    def test_e041b_good_bathroom(self):
        """Bathroom ≥ 5m² should not trigger E041b."""
        b = self._make_apartment_building(has_walls=True, has_doors=True, bath_area=6.0)
        errors = validate_interior_enclosure(b)
        e041b = [e for e in errors if "E041b" in e.message]
        assert len(e041b) == 0


# ══════════════════════════════════════════════════════════════════════
# v3 Building Specific Checks
# ══════════════════════════════════════════════════════════════════════

class TestV3BuildingSpecific:
    """Tests specific to v3 generated building quality."""

    @pytest.fixture
    def building(self):
        return generate_building_4apt_interior(num_floors=2)

    def test_core_doors_standard_width(self, building):
        """Core doors should all be ≤ 1.20m (fire-rated)."""
        for story in building.stories:
            core_walls = {w.global_id for w in story.walls
                          if any(kw in (w.name or "").lower()
                                 for kw in ["core", "elevator", "staircase"])}
            for door in story.doors:
                if door.wall_id in core_walls:
                    assert door.width <= 1.20, (
                        f"Core door '{door.name}' width {door.width}m > 1.20m"
                    )

    def test_no_windows_on_core_walls(self, building):
        """No windows should be placed on core walls."""
        for story in building.stories:
            core_walls = {w.global_id for w in story.walls
                          if any(kw in (w.name or "").lower()
                                 for kw in ["core", "elevator", "staircase", "divider"])}
            for window in story.windows:
                assert window.wall_id not in core_walls, (
                    f"Window '{window.name}' on core wall!"
                )

    def test_ground_floor_south_apts_smaller(self, building):
        """Ground floor south apartments should be smaller (lobby takes space)."""
        gf = building.stories[0]
        first = building.stories[1]

        gf_south = [a for a in gf.apartments if a.name.startswith("Apt S")]
        f1_south = [a for a in first.apartments if a.name.startswith("Apt S")]

        if gf_south and f1_south:
            gf_area = sum(a.area for a in gf_south)
            f1_area = sum(a.area for a in f1_south)
            assert gf_area < f1_area, "Ground floor south should be smaller due to lobby"

    def test_save_and_load(self, building, tmp_path):
        path = tmp_path / "building.json"
        building.save(str(path))
        loaded = Building.load(str(path))
        assert loaded.name == building.name
        assert len(loaded.stories) == len(building.stories)
