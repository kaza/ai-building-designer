"""Comprehensive tests for AI reasoning tools.

Tests connectivity graph, mermaid export, reachability validator,
wall-room relationships, building API extensions, and floor plan slice.

Fixtures:
- v3_building: the published 4apt-centered-core project ("4-Storey Building
  V3") — used for positive/structural assertions. NOTE: its space polygons
  overlap wall centerlines in places (e.g. S1 Kitchen extends past the
  bedroom wall), which swallows bedroom door edges in the graph — see the
  synthetic fixture for intent-preserving connectivity tests.
- defect_building: small synthetic building with deliberate defects
  (open-plan kitchen without door, apartment without entry) so the
  detection tests stay meaningful regardless of showcase-data evolution.
"""

from pathlib import Path

import pytest

from archicad_builder.models.building import Building
from archicad_builder.queries.connectivity import (
    ConnectivityGraph,
    _point_in_polygon,
    _point_in_polygon_with_tolerance,
    _synthesize_common_zones,
    build_connectivity_graph,
)
from archicad_builder.queries.mermaid import graph_to_mermaid, graph_to_mermaid_simple
from archicad_builder.queries.slice import extract_apartment
from archicad_builder.queries.wall_rooms import (
    get_room_exterior_walls,
    get_room_walls,
    get_room_windows,
    get_wall_rooms,
)
from archicad_builder.validators.reachability import validate_reachability

# ── Fixtures ─────────────────────────────────────────────────────────


V3_PATH = Path(__file__).parent.parent / "projects" / "4apt-centered-core" / "building.json"


@pytest.fixture
def v3_building() -> Building:
    """Load the v3 sample building."""
    return Building.load(V3_PATH)


@pytest.fixture
def ground_graph(v3_building: Building) -> ConnectivityGraph:
    """Connectivity graph for ground floor."""
    return build_connectivity_graph(v3_building, "Ground Floor")


@pytest.fixture
def first_floor_graph(v3_building: Building) -> ConnectivityGraph:
    """Connectivity graph for 1st floor."""
    return build_connectivity_graph(v3_building, "1st Floor")


@pytest.fixture
def defect_building() -> Building:
    """Synthetic single-storey building with deliberate defects.

    Apt A (west): reachable from corridor; Kitchen is open-plan (no door,
    E080); Bedroom reachable only through Living (Durchgangszimmer, W080).
    Apt B (east): has NO entry door from the corridor (E082).
    """
    from archicad_builder.models.geometry import Point2D, Polygon2D
    from archicad_builder.models.spaces import Apartment, RoomType, Space

    b = Building(name="Defect Fixture")
    b.add_story("Ground Floor", height=3.0)
    GF = "Ground Floor"

    def wall(name, s_, e_, thickness=0.25, external=False):
        return b.add_wall(GF, s_, e_, height=3.0, thickness=thickness,
                          name=name, is_external=external, load_bearing=external)

    wall("South Wall", (0, 0), (12, 0), external=True)
    wall("East Wall", (12, 0), (12, 8), external=True)
    wall("North Wall", (12, 8), (0, 8), external=True)
    wall("West Wall", (0, 8), (0, 0), external=True)
    wall("Corridor South Wall", (0, 5.25), (12, 5.25))
    wall("Corridor North Wall", (0, 6.75), (12, 6.75))
    wall("Apt A Vorraum West Wall", (2, 3.25), (2, 5.25), 0.12)
    wall("Apt A Vorraum South Wall", (2, 3.25), (4, 3.25), 0.12)
    wall("Apt A Bedroom Wall", (4, 0), (4, 5.25), 0.12)
    wall("Apt Divider Wall", (6, 0), (6, 5.25), 0.12)
    wall("Apt B Vorraum West Wall", (8, 3.25), (8, 5.25), 0.12)
    wall("Apt B Vorraum South Wall", (8, 3.25), (10, 3.25), 0.12)

    b.add_door(GF, "Corridor South Wall", position=2.6, width=0.9, height=2.1,
               name="Apt A Entry")
    b.add_door(GF, "Apt A Vorraum South Wall", position=0.55, width=0.9,
               height=2.1, name="Apt A Living Door")
    b.add_door(GF, "Apt A Bedroom Wall", position=1.3, width=0.8, height=2.1,
               name="Apt A Bedroom Door")
    # Apt B: internal door only — deliberately NO entry from the corridor
    b.add_door(GF, "Apt B Vorraum South Wall", position=0.55, width=0.9,
               height=2.1, name="Apt B Living Door")

    b.add_window(GF, "South Wall", position=4.5, width=1.2, height=1.4,
                 name="Apt A Bedroom Window")

    def rect(name, rt, x0, y0, x1, y1):
        return Space(name=name, room_type=rt, boundary=Polygon2D(vertices=[
            Point2D(x=x0, y=y0), Point2D(x=x1, y=y0),
            Point2D(x=x1, y=y1), Point2D(x=x0, y=y1)]))

    story = b.get_story(GF)
    story.apartments.append(Apartment(
        name="Apt A",
        boundary=Polygon2D(vertices=[Point2D(x=0, y=0), Point2D(x=6, y=0),
                                     Point2D(x=6, y=5.25), Point2D(x=0, y=5.25)]),
        spaces=[
            rect("Apt A Kitchen", RoomType.KITCHEN, 0, 0, 2, 3.25),
            rect("Apt A Living", RoomType.LIVING, 2, 0, 4, 3.25),
            rect("Apt A Vorraum", RoomType.HALLWAY, 2, 3.25, 4, 5.25),
            rect("Apt A Bedroom", RoomType.BEDROOM, 4, 0, 6, 5.25),
        ],
    ))
    story.apartments.append(Apartment(
        name="Apt B",
        boundary=Polygon2D(vertices=[Point2D(x=6, y=0), Point2D(x=12, y=0),
                                     Point2D(x=12, y=5.25), Point2D(x=6, y=5.25)]),
        spaces=[
            # Living spans the full south band so the vorraum door (center
            # x=9) actually lands in it — vorraum <-> living edge exists.
            rect("Apt B Living", RoomType.LIVING, 6, 0, 12, 3.25),
            rect("Apt B Vorraum", RoomType.HALLWAY, 8, 3.25, 10, 5.25),
        ],
    ))
    return b


# ══════════════════════════════════════════════════════════════════════
# 1. CONNECTIVITY GRAPH TESTS
# ══════════════════════════════════════════════════════════════════════


class TestConnectivityGraph:
    """Tests for the room connectivity graph builder."""

    def test_ground_floor_has_all_node_types(self, ground_graph: ConnectivityGraph):
        """Ground floor should have corridor, lobby, core, elevator, staircase, exterior."""
        node_types = {n.node_type for n in ground_graph.nodes.values()}
        assert "corridor" in node_types
        assert "lobby" in node_types
        assert "vestibule" in node_types
        assert "elevator" in node_types
        assert "staircase" in node_types
        assert "exterior" in node_types

    def test_ground_floor_node_count(self, ground_graph: ConnectivityGraph):
        """Ground floor: 19 apartment rooms + 5 common areas + Exterior = 25."""
        assert len(ground_graph.nodes) == 25

    def test_first_floor_no_lobby(self, first_floor_graph: ConnectivityGraph):
        """1st floor should have no lobby (only ground floor has lobby)."""
        assert "Lobby" not in first_floor_graph.nodes

    def test_apartment_rooms_are_nodes(self, ground_graph: ConnectivityGraph):
        """Each apartment room should be a node (N apartments are 2-room)."""
        expected = {
            "Apt S1": ["Vorraum", "Bathroom", "Living", "Kitchen", "Bedroom"],
            "Apt S2": ["Vorraum", "Bathroom", "Living", "Kitchen", "Bedroom",
                       "Abstellraum"],
            "Apt N1": ["Vorraum", "Bathroom", "Living", "Kitchen"],
            "Apt N2": ["Vorraum", "Bathroom", "Living", "Kitchen"],
        }
        for apt_prefix, rooms in expected.items():
            for room in rooms:
                name = f"{apt_prefix} {room}"
                assert name in ground_graph.nodes, f"Missing node: {name}"

    def test_south_apartments_connected_to_corridor(self, ground_graph: ConnectivityGraph):
        """South apartments should be reachable from corridor (via entry doors)."""
        reachable = ground_graph.reachable_from("Corridor")
        # S1 and S2 vorraums reachable from corridor
        assert "Apt S1 Vorraum" in reachable
        assert "Apt S2 Vorraum" in reachable

    def test_core_connected_to_corridor(self, ground_graph: ConnectivityGraph):
        """Core vestibule should be connected to corridor."""
        reachable = ground_graph.reachable_from("Corridor")
        assert "Core Vestibule" in reachable

    def test_elevator_connected_via_vestibule(self, ground_graph: ConnectivityGraph):
        """Elevator should be connected to core vestibule."""
        neighbors = ground_graph.neighbors("Elevator")
        neighbor_names = [n for n, _ in neighbors]
        assert "Core Vestibule" in neighbor_names

    def test_staircase_connected_via_vestibule(self, ground_graph: ConnectivityGraph):
        """Staircase should be connected to core vestibule."""
        reachable = ground_graph.reachable_from("Core Vestibule")
        assert "Main Staircase" in reachable

    def test_exterior_connected_to_lobby(self, ground_graph: ConnectivityGraph):
        """Building main entry connects exterior to lobby."""
        neighbors = ground_graph.neighbors("Exterior")
        neighbor_names = [n for n, _ in neighbors]
        assert "Lobby" in neighbor_names

    def test_building_main_entry_width(self, ground_graph: ConnectivityGraph):
        """Building main entry should be 1.2m wide."""
        for edge in ground_graph.edges:
            if edge.door_name == "Building Main Entry":
                assert edge.door_width == 1.2
                return
        pytest.fail("Building Main Entry edge not found")

    def test_apartment_internal_connectivity(self, ground_graph: ConnectivityGraph):
        """Within each south apartment the Vorraum connects to the Living.

        NOTE: the Living->Bedroom edge is missing in the published data —
        S1/S2 Kitchen polygons overlap the bedroom wall, so the graph
        resolves both door sides to the kitchen and drops the edge. The
        bedroom-chain intent lives in TestDefectFixture (synthetic data).
        """
        for apt in ["Apt S1", "Apt S2"]:
            vorraum_neighbors = [n for n, _ in ground_graph.neighbors(f"{apt} Vorraum")]
            assert f"{apt} Living" in vorraum_neighbors

    def test_kitchen_not_connected(self, ground_graph: ConnectivityGraph):
        """Kitchen spaces are open-plan (no door) — not connected in graph."""
        for apt in ["Apt S1", "Apt S2", "Apt N1", "Apt N2"]:
            kitchen = f"{apt} Kitchen"
            neighbors = ground_graph.neighbors(kitchen)
            assert len(neighbors) == 0, f"{kitchen} should have no door connections"

    def test_has_path_within_apartment(self, ground_graph: ConnectivityGraph):
        """Path should exist from corridor into the S1 apartment."""
        assert ground_graph.has_path("Corridor", "Apt S1 Living")

    def test_has_path_returns_false_for_disconnected(self, ground_graph: ConnectivityGraph):
        """Open-plan kitchens have no door, so no graph path reaches them."""
        assert not ground_graph.has_path("Exterior", "Apt S1 Kitchen")
        assert not ground_graph.has_path("Corridor", "Apt S1 Kitchen")

    def test_reachable_from_exterior_limited(self, ground_graph: ConnectivityGraph):
        """From Exterior the lobby and corridor are reachable, kitchens not."""
        reachable = ground_graph.reachable_from("Exterior")
        assert "Lobby" in reachable
        assert "Corridor" in reachable
        assert "Apt S1 Kitchen" not in reachable

    def test_graph_edge_count(self, ground_graph: ConnectivityGraph):
        """Ground floor should have edges for most doors (some may be skipped)."""
        # 20 doors total, but some may connect same zone on both sides
        assert len(ground_graph.edges) >= 15

    def test_nonexistent_story_raises(self, v3_building: Building):
        """Building with wrong story name should raise."""
        with pytest.raises(ValueError):
            build_connectivity_graph(v3_building, "Basement")


class TestConnectivityGraphHelpers:
    """Tests for helper functions."""

    def test_point_in_polygon_simple_square(self):
        """Point inside a unit square."""
        square = [(0, 0), (1, 0), (1, 1), (0, 1)]
        assert _point_in_polygon(0.5, 0.5, square)
        assert not _point_in_polygon(1.5, 0.5, square)
        assert not _point_in_polygon(-0.1, 0.5, square)

    def test_point_in_polygon_l_shape(self):
        """Point in an L-shaped polygon."""
        # L-shape: (0,0)-(2,0)-(2,1)-(1,1)-(1,2)-(0,2)
        l_shape = [(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)]
        assert _point_in_polygon(0.5, 0.5, l_shape)  # In bottom-left
        assert _point_in_polygon(1.5, 0.5, l_shape)  # In bottom-right
        assert _point_in_polygon(0.5, 1.5, l_shape)  # In top-left
        assert not _point_in_polygon(1.5, 1.5, l_shape)  # Outside (top-right corner)

    def test_point_in_polygon_with_tolerance(self):
        """Point near edge should match with tolerance."""
        square = [(0, 0), (1, 0), (1, 1), (0, 1)]
        # Just outside the edge
        assert not _point_in_polygon(-0.05, 0.5, square)
        assert _point_in_polygon_with_tolerance(-0.05, 0.5, square, tolerance=0.1)

    def test_synthesize_common_zones(self, v3_building: Building):
        """Common zones should be created for corridor, lobby, etc."""
        story = v3_building.get_story("Ground Floor")
        zones = _synthesize_common_zones(story)
        zone_names = {z.name for z in zones}
        assert "Corridor" in zone_names
        assert "Lobby" in zone_names
        assert "Core Vestibule" in zone_names
        assert "Elevator" in zone_names

    def test_corridor_zone_dimensions(self, v3_building: Building):
        """Corridor should span full building width."""
        story = v3_building.get_story("Ground Floor")
        zones = _synthesize_common_zones(story)
        corridor = next(z for z in zones if z.name == "Corridor")
        xs = [v[0] for v in corridor.vertices]
        ys = [v[1] for v in corridor.vertices]
        assert min(xs) == pytest.approx(0.0)
        assert max(xs) == pytest.approx(12.5)
        assert min(ys) == pytest.approx(5.25)
        assert max(ys) == pytest.approx(6.75)

    def test_vestibule_zone_correct_bounds(self, v3_building: Building):
        """Core vestibule should NOT extend into corridor area."""
        story = v3_building.get_story("Ground Floor")
        zones = _synthesize_common_zones(story)
        vestibule = next(z for z in zones if z.name == "Core Vestibule")
        ys = [v[1] for v in vestibule.vertices]
        # Vestibule starts at corridor north wall (y=6.75), not at y=5.25
        assert min(ys) == pytest.approx(6.75)
        assert max(ys) == pytest.approx(8.25)


# ══════════════════════════════════════════════════════════════════════
# 2. MERMAID DIAGRAM TESTS
# ══════════════════════════════════════════════════════════════════════


class TestMermaidExport:
    """Tests for Mermaid diagram export."""

    def test_mermaid_starts_with_flowchart(self, ground_graph: ConnectivityGraph):
        """Mermaid output should start with flowchart directive."""
        output = graph_to_mermaid(ground_graph)
        assert output.startswith("flowchart LR")

    def test_mermaid_contains_nodes(self, ground_graph: ConnectivityGraph):
        """Mermaid output should contain all node definitions."""
        output = graph_to_mermaid(ground_graph)
        assert "Corridor" in output
        assert "Exterior" in output
        assert "Apt_S1_Living" in output

    def test_mermaid_contains_edges(self, ground_graph: ConnectivityGraph):
        """Mermaid output should contain edge connections."""
        output = graph_to_mermaid(ground_graph)
        assert "-->" in output
        assert "Building Main Entry" in output

    def test_mermaid_shows_areas(self, ground_graph: ConnectivityGraph):
        """When show_area=True, areas should appear in labels."""
        output = graph_to_mermaid(ground_graph, show_area=True)
        assert "m²" in output

    def test_mermaid_no_areas(self, ground_graph: ConnectivityGraph):
        """When show_area=False, no areas in labels."""
        output = graph_to_mermaid(ground_graph, show_area=False)
        # Edges may contain "m" (for door width), but nodes shouldn't have "m²"
        node_lines = [l for l in output.split("\n") if "-->" not in l and "m²" in l]
        assert len(node_lines) == 0

    def test_mermaid_simple_format(self, ground_graph: ConnectivityGraph):
        """Simple mermaid format should have comment and edges."""
        output = graph_to_mermaid_simple(ground_graph)
        assert output.startswith("%% Ground Floor")
        assert "flowchart LR" in output

    def test_mermaid_direction_parameter(self, ground_graph: ConnectivityGraph):
        """Direction parameter should change flowchart direction."""
        output_tb = graph_to_mermaid(ground_graph, direction="TB")
        assert output_tb.startswith("flowchart TB")

    def test_mermaid_node_shapes(self, ground_graph: ConnectivityGraph):
        """Different node types should have different Mermaid shapes."""
        output = graph_to_mermaid(ground_graph)
        # Exterior uses stadium shape ([" "])
        assert '(["Exterior"])' in output
        # Corridor uses subroutine shape [["..."]]
        assert "[[" in output


# ══════════════════════════════════════════════════════════════════════
# 3. REACHABILITY VALIDATOR TESTS
# ══════════════════════════════════════════════════════════════════════


class TestReachabilityValidator:
    """Tests for reachability validation."""

    def test_catches_unreachable_kitchens(self, v3_building: Building):
        """E080: All kitchens are open-plan (no door) — should be flagged."""
        errors = validate_reachability(v3_building, "Ground Floor")
        e080s = [e for e in errors if "E080" in e.message]
        kitchen_errors = [e for e in e080s if "Kitchen" in e.message]
        assert len(kitchen_errors) == 4  # 4 apartments, each has an open-plan kitchen

    def test_all_apartments_reachable(self, v3_building: Building):
        """All published-building apartments are reachable — no E082.

        (E082 detection itself is covered by TestDefectFixture.)
        """
        errors = validate_reachability(v3_building, "Ground Floor")
        e082s = [e for e in errors if "E082" in e.message]
        assert e082s == []

    def test_south_apartments_reachable(self, v3_building: Building):
        """South apartments should be reachable from corridor — no E082."""
        errors = validate_reachability(v3_building, "Ground Floor")
        e082s = [e for e in errors if "E082" in e.message]
        s_errors = [e for e in e082s if "S1" in e.message or "S2" in e.message]
        assert len(s_errors) == 0

    def test_staircase_reachable_from_corridor(self, v3_building: Building):
        """Staircase should be reachable from corridor (no E081)."""
        errors = validate_reachability(v3_building, "Ground Floor")
        e081s = [e for e in errors if "E081" in e.message]
        assert len(e081s) == 0

    def test_first_floor_staircase_reachable(self, v3_building: Building):
        """1st floor staircase should also be reachable from corridor."""
        errors = validate_reachability(v3_building, "1st Floor")
        e081s = [e for e in errors if "E081" in e.message]
        assert len(e081s) == 0

    def test_durchgangszimmer_warnings(self, v3_building: Building):
        """W080: Rooms only reachable through habitable rooms."""
        errors = validate_reachability(v3_building, "Ground Floor")
        w080s = [e for e in errors if "W080" in e.message]
        assert len(w080s) > 0

    def test_prebuilt_graph_accepted(self, v3_building: Building, ground_graph: ConnectivityGraph):
        """Validator should accept a pre-built graph."""
        errors = validate_reachability(v3_building, "Ground Floor", graph=ground_graph)
        assert isinstance(errors, list)

    def test_severity_types(self, v3_building: Building):
        """Errors should have correct severity values."""
        errors = validate_reachability(v3_building, "Ground Floor")
        for error in errors:
            assert error.severity in ("error", "warning")


# ══════════════════════════════════════════════════════════════════════
# 4. WALL-ROOM RELATIONSHIP TESTS
# ══════════════════════════════════════════════════════════════════════


class TestWallRoomRelationships:
    """Tests for wall-room queries."""

    def test_bedroom_has_walls(self, v3_building: Building):
        """Bedroom should have bounding walls."""
        walls = get_room_walls(v3_building, "1st Floor", "Apt S1 Bedroom")
        assert len(walls) >= 3  # At least exterior, corridor, and partition walls
        wall_names = [w.name for w in walls]
        assert "Apt S1 Bedroom Wall" in wall_names

    def test_bedroom_wall_separates_rooms(self, v3_building: Building):
        """The bedroom wall should separate Living and Bedroom."""
        side_a, side_b = get_wall_rooms(
            v3_building, "1st Floor", "Apt S1 Bedroom Wall"
        )
        rooms = {side_a, side_b}
        assert "Apt S1 Living" in rooms or "Apt S1 Bedroom" in rooms

    def test_exterior_wall_of_bedroom(self, v3_building: Building):
        """Bedroom should have at least one exterior wall."""
        ext_walls = get_room_exterior_walls(
            v3_building, "1st Floor", "Apt S1 Bedroom"
        )
        assert len(ext_walls) >= 1
        # South Wall should be one of them
        ext_names = [w.name for w in ext_walls]
        assert "South Wall" in ext_names

    def test_living_windows_belong_to_apartment(self, v3_building: Building):
        """Living room windows all belong to the same apartment.

        (Published-data quirk: overlapping space polygons shuffle WHICH
        S1 window lands in which S1 room — exact name matching lives in
        TestDefectFixture on clean synthetic data.)
        """
        windows = get_room_windows(v3_building, "1st Floor", "Apt S1 Living")
        assert len(windows) >= 1
        assert all(w.name.startswith("Apt S1") for w in windows)

    def test_living_room_windows(self, v3_building: Building):
        """Living room should have windows."""
        windows = get_room_windows(v3_building, "1st Floor", "Apt S1 Living")
        assert len(windows) >= 1
        # Should NOT include other apartments' windows
        for w in windows:
            assert "S2" not in w.name
            assert "N1" not in w.name

    def test_nonexistent_room(self, v3_building: Building):
        """Nonexistent room should return empty list."""
        walls = get_room_walls(v3_building, "1st Floor", "Nonexistent Room")
        assert walls == []

    def test_wall_rooms_for_corridor_wall(self, v3_building: Building):
        """Corridor south wall should have corridor on one side."""
        side_a, side_b = get_wall_rooms(
            v3_building, "1st Floor", "Corridor South Wall West"
        )
        # One side should be an apartment space, the other corridor-adjacent
        assert side_a is not None or side_b is not None

    def test_wall_rooms_nonexistent_wall(self, v3_building: Building):
        """Nonexistent wall returns (None, None)."""
        result = get_wall_rooms(v3_building, "1st Floor", "No Such Wall")
        assert result == (None, None)


# ══════════════════════════════════════════════════════════════════════
# 5. BUILDING API EXTENSION TESTS
# ══════════════════════════════════════════════════════════════════════


class TestBuildingAPIExtensions:
    """Tests for new building API methods."""

    def test_resize_door(self, v3_building: Building):
        """resize_door should change door width."""
        old_door = v3_building.get_story("Ground Floor").get_door_by_name(
            "Building Main Entry"
        )
        assert old_door.width == 1.2

        new_door = v3_building.resize_door("Ground Floor", "Building Main Entry", 1.5)
        assert new_door.width == 1.5
        assert new_door.name == "Building Main Entry"

        # Verify the door in the story is updated
        updated = v3_building.get_story("Ground Floor").get_door_by_name(
            "Building Main Entry"
        )
        assert updated.width == 1.5

    def test_resize_door_nonexistent(self, v3_building: Building):
        """resize_door with bad name should raise ValueError."""
        with pytest.raises(ValueError, match="not found"):
            v3_building.resize_door("Ground Floor", "No Such Door", 1.0)

    def test_resize_window(self, v3_building: Building):
        """resize_window should change window dimensions."""
        new_win = v3_building.resize_window(
            "Ground Floor", "Apt S1 Living Window", new_width=1.5
        )
        assert new_win.width == 1.5

    def test_resize_window_height(self, v3_building: Building):
        """resize_window should handle height changes."""
        new_win = v3_building.resize_window(
            "Ground Floor", "Apt S1 Living Window", new_height=1.8
        )
        assert new_win.height == 1.8

    def test_resize_window_nonexistent(self, v3_building: Building):
        """resize_window with bad name should raise ValueError."""
        with pytest.raises(ValueError, match="not found"):
            v3_building.resize_window("Ground Floor", "No Such Window", new_width=1.0)

    def test_remove_wall_cascades(self, v3_building: Building):
        """remove_wall should also remove hosted doors and windows."""
        story = v3_building.get_story("Ground Floor")
        # Get the S1 bedroom wall and its door
        wall = story.get_wall_by_name("Apt S1 Bedroom Wall")
        wall_id = wall.global_id
        doors_on_wall = [d for d in story.doors if d.wall_id == wall_id]
        assert len(doors_on_wall) > 0

        v3_building.remove_wall("Ground Floor", "Apt S1 Bedroom Wall")

        # Wall should be gone
        assert story.get_wall_by_name("Apt S1 Bedroom Wall") is None
        # Door should also be gone
        remaining_doors = [d for d in story.doors if d.wall_id == wall_id]
        assert len(remaining_doors) == 0

    def test_move_wall(self, v3_building: Building):
        """move_wall should update wall endpoints."""
        wall = v3_building.move_wall(
            "Ground Floor", "Apt S1 Bedroom Wall",
            new_start=(3.0, 0.0), new_end=(3.0, 5.25)
        )
        assert wall.start.x == 3.0
        assert wall.end.x == 3.0

    def test_move_wall_updates_room_boundaries(self, v3_building: Building):
        """move_wall should auto-update space boundaries that touch the wall.

        When a wall moves, rooms on either side must resize automatically.
        Room boundaries must NOT be hardcoded — they derive from walls.
        """
        story = v3_building.get_story("Ground Floor")
        # Find the bedroom wall and the spaces on either side
        wall = story.get_wall_by_name("Apt S1 Bedroom Wall")
        assert wall is not None
        old_x = wall.start.x  # Vertical wall — x coordinate is what changes

        # Find spaces that have boundary vertices at the old wall x
        apt = story.apartments[0]
        touching_spaces = []
        for sp in apt.spaces:
            for v in sp.boundary.vertices:
                if abs(v.x - old_x) < 0.02:
                    touching_spaces.append(sp.name)
                    break
        assert len(touching_spaces) > 0, "No spaces touch this wall"

        # Move wall by 0.5m
        new_x = old_x + 0.5
        v3_building.move_wall(
            "Ground Floor", "Apt S1 Bedroom Wall",
            new_start=(new_x, wall.start.y),
            new_end=(new_x, wall.end.y),
        )

        # Verify: spaces that touched old wall now touch new position
        for sp in apt.spaces:
            if sp.name in touching_spaces:
                xs = [v.x for v in sp.boundary.vertices]
                assert any(abs(x - new_x) < 0.02 for x in xs), (
                    f"Space '{sp.name}' boundary did NOT update after wall move "
                    f"(vertices x: {xs}, expected {new_x})"
                )
                assert not any(abs(x - old_x) < 0.02 for x in xs), (
                    f"Space '{sp.name}' still has old wall position {old_x}"
                )

    def test_existing_remove_door(self, v3_building: Building):
        """remove_door should work for existing doors."""
        story = v3_building.get_story("Ground Floor")
        assert story.get_door_by_name("Apt S1 Bedroom Door") is not None
        v3_building.remove_door("Ground Floor", "Apt S1 Bedroom Door")
        assert story.get_door_by_name("Apt S1 Bedroom Door") is None

    def test_existing_remove_window(self, v3_building: Building):
        """remove_window should work for existing windows."""
        story = v3_building.get_story("Ground Floor")
        assert story.get_window_by_name("Apt S1 Living Window") is not None
        v3_building.remove_window("Ground Floor", "Apt S1 Living Window")
        assert story.get_window_by_name("Apt S1 Living Window") is None


# ══════════════════════════════════════════════════════════════════════
# 6. FLOOR PLAN SLICE TESTS
# ══════════════════════════════════════════════════════════════════════


class TestFloorPlanSlice:
    """Tests for apartment data extraction."""

    def test_extract_apartment_basic(self, v3_building: Building):
        """extract_apartment should return complete apartment data."""
        sl = extract_apartment(v3_building, "1st Floor", "Apt S1")
        assert sl.apartment_name == "Apt S1"
        assert sl.storey_name == "1st Floor"
        assert sl.area > 0

    def test_extract_apartment_rooms(self, v3_building: Building):
        """Extracted apartment should have all 5 room types."""
        sl = extract_apartment(v3_building, "1st Floor", "Apt S1")
        room_types = {r["type"] for r in sl.rooms}
        assert "hallway" in room_types
        assert "bathroom" in room_types
        assert "living" in room_types
        assert "kitchen" in room_types
        assert "bedroom" in room_types

    def test_extract_apartment_has_walls(self, v3_building: Building):
        """Extracted apartment should have walls."""
        sl = extract_apartment(v3_building, "1st Floor", "Apt S1")
        assert len(sl.walls) > 0
        # Should include apartment interior walls
        wall_names = [w["name"] for w in sl.walls]
        assert "Apt S1 Bedroom Wall" in wall_names

    def test_extract_apartment_has_doors(self, v3_building: Building):
        """Extracted apartment should have doors."""
        sl = extract_apartment(v3_building, "1st Floor", "Apt S1")
        assert len(sl.doors) > 0
        door_names = [d["name"] for d in sl.doors]
        assert "Apt S1 Bedroom Door" in door_names

    def test_extract_apartment_has_windows(self, v3_building: Building):
        """Extracted apartment should have windows."""
        sl = extract_apartment(v3_building, "1st Floor", "Apt S1")
        assert len(sl.windows) > 0

    def test_extract_apartment_has_boundary(self, v3_building: Building):
        """Extracted apartment should have boundary polygon."""
        sl = extract_apartment(v3_building, "1st Floor", "Apt S1")
        assert len(sl.boundary) >= 4  # At least a rectangle

    def test_extract_apartment_to_dict(self, v3_building: Building):
        """to_dict() should return a plain dictionary."""
        sl = extract_apartment(v3_building, "1st Floor", "Apt S1")
        d = sl.to_dict()
        assert isinstance(d, dict)
        assert "apartment_name" in d
        assert "rooms" in d
        assert "walls" in d

    def test_extract_apartment_summary(self, v3_building: Building):
        """summary() should produce readable text."""
        sl = extract_apartment(v3_building, "1st Floor", "Apt S1")
        s = sl.summary()
        assert "Apt S1" in s
        assert "m²" in s

    def test_extract_nonexistent_apartment(self, v3_building: Building):
        """Nonexistent apartment should raise ValueError."""
        with pytest.raises(ValueError, match="not found"):
            extract_apartment(v3_building, "1st Floor", "Apt Z99")

    def test_extract_apartment_case_insensitive(self, v3_building: Building):
        """Apartment name matching should be case-insensitive."""
        sl = extract_apartment(v3_building, "1st Floor", "apt s1")
        assert sl.apartment_name == "Apt S1"

    def test_all_apartments_extractable(self, v3_building: Building):
        """Every apartment on every floor should be extractable."""
        for story in v3_building.stories:
            for apt in story.apartments:
                sl = extract_apartment(v3_building, story.name, apt.name)
                assert sl.apartment_name == apt.name
                assert len(sl.rooms) > 0


# ══════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ══════════════════════════════════════════════════════════════════════


class TestDefectFixture:
    """Detection intents on synthetic data with deliberate defects.

    These preserve the original v3-sample test intents (unreachable
    apartment, bedroom chain, Durchgangszimmer) independent of how the
    published showcase data evolves.
    """

    def test_bedroom_chain_connected(self, defect_building: Building):
        g = build_connectivity_graph(defect_building, "Ground Floor")
        assert g.has_path("Corridor", "Apt A Bedroom")
        living_neighbors = [n for n, _ in g.neighbors("Apt A Living")]
        assert "Apt A Bedroom" in living_neighbors

    def test_open_plan_kitchen_not_connected(self, defect_building: Building):
        g = build_connectivity_graph(defect_building, "Ground Floor")
        assert not g.neighbors("Apt A Kitchen")

    def test_apartment_without_entry_unreachable(self, defect_building: Building):
        g = build_connectivity_graph(defect_building, "Ground Floor")
        # Apt B is internally connected (vorraum <-> living)...
        assert g.has_path("Apt B Vorraum", "Apt B Living")
        # ...but has no entry from the corridor.
        assert not g.has_path("Corridor", "Apt B Vorraum")

    def test_e082_flags_apartment_without_entry(self, defect_building: Building):
        errors = validate_reachability(defect_building, "Ground Floor")
        e082s = [e for e in errors if "E082" in e.message]
        assert any("Apt B" in e.message for e in e082s)
        assert not any("Apt A" in e.message for e in e082s)

    def test_e080_flags_open_plan_kitchen(self, defect_building: Building):
        errors = validate_reachability(defect_building, "Ground Floor")
        e080s = [e for e in errors if "E080" in e.message]
        assert any("Apt A Kitchen" in e.message for e in e080s)

    def test_w080_durchgangszimmer(self, defect_building: Building):
        """Bedroom reachable only through the Living room -> W080.

        Exact-set assertion so validator behavior changes surface loudly.
        NOTE: 'Apt A Kitchen' (isolated, no door) and 'Apt B Living'
        (apartment without entry) also get W080 — a known validator
        false positive: rooms with NO path at all are not
        Durchgangszimmer. If the validator is fixed, shrink this set.
        """
        errors = validate_reachability(defect_building, "Ground Floor")
        w080_rooms = {
            e.message.split("'")[1] for e in errors if "W080" in e.message
        }
        assert w080_rooms == {"Apt A Bedroom", "Apt A Kitchen", "Apt B Living"}

    def test_bedroom_window_by_name(self, defect_building: Building):
        windows = get_room_windows(defect_building, "Ground Floor", "Apt A Bedroom")
        assert [w.name for w in windows] == ["Apt A Bedroom Window"]


class TestIntegration:
    """End-to-end integration tests."""

    def test_graph_reveals_building_issues(self, v3_building: Building):
        """The connectivity graph reveals real issues in the published data."""
        g = build_connectivity_graph(v3_building, "Ground Floor")

        # Issue 1: open-plan kitchens have no door edge
        for apt in ["Apt S1", "Apt S2", "Apt N1", "Apt N2"]:
            assert not g.neighbors(f"{apt} Kitchen")

        # Issue 2: bedroom door edges swallowed by overlapping kitchen
        # polygons (S1/S2 Kitchen crosses the bedroom wall centerline)
        assert not g.neighbors("Apt S1 Bedroom")

    def test_validator_catches_graph_issues(self, v3_building: Building):
        """Reachability validator flags the open-plan kitchens the graph shows."""
        errors = validate_reachability(v3_building, "Ground Floor")
        error_codes = [e.message[:4] for e in errors]
        assert "E080" in error_codes  # rooms without any door

    def test_mermaid_from_graph(self, ground_graph: ConnectivityGraph):
        """Full pipeline: graph → mermaid should produce valid output."""
        mermaid = graph_to_mermaid(ground_graph)
        lines = mermaid.strip().split("\n")
        assert len(lines) > 10  # Substantial output
        # All edges should have the --> syntax
        edge_lines = [l for l in lines if "-->" in l]
        assert len(edge_lines) > 0

    def test_wall_room_and_slice_consistent(self, v3_building: Building):
        """Wall-room queries and apartment slice should agree on room walls."""
        sl = extract_apartment(v3_building, "1st Floor", "Apt S1")
        walls_from_slice = {w["name"] for w in sl.walls}

        walls_from_query = get_room_walls(
            v3_building, "1st Floor", "Apt S1 Bedroom"
        )
        query_names = {w.name for w in walls_from_query}

        # The bedroom wall should appear in both
        assert "Apt S1 Bedroom Wall" in walls_from_slice
        assert "Apt S1 Bedroom Wall" in query_names
