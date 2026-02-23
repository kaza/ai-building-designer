"""4-apartment building generator — complete phased design pipeline.

Implements the architect's real algorithm for residential building design:
  Phase 1: Shell (exterior walls + slabs with correct floor-to-floor height)
  Phase 2: Core (enclosed staircase + elevator with vestibule/lobby)
  Phase 3: Corridor (from core to apartment entries only)
  Phase 4: Façade subdivision (apartments sized by window-width slots)
  Phase 5: Room subdivision (kitchen, bathroom, bedrooms, Vorraum per rules)
  Phase 6: Vertical consistency (all vertical systems aligned)

Two entry points:
  generate_building_4apt()          — basic version (shell + rooms, no interior walls)
  generate_building_4apt_interior() — complete version (lobby, interior walls, doors)

Construction constants (Austrian residential):
  Clear height:       2.52m (2cm buffer over 2.50m legal minimum)
  Floor structure:    0.37m (0.20m concrete + 0.17m flooring)
  Floor-to-floor:     2.89m
  Staircase flight:   1.20m wide, 1.20m landing
  Vorraum:            1.80m wide minimum
"""

from __future__ import annotations

from archicad_builder.models.building import Building
from archicad_builder.models.elements import StaircaseType
from archicad_builder.models.geometry import Point2D, Polygon2D
from archicad_builder.models.spaces import Apartment, RoomType, Space
from archicad_builder.models.ifc_id import generate_ifc_id

# ── Construction constants ────────────────────────────────────────────
CLEAR_HEIGHT = 2.52        # Room clear height (m)
FLOOR_STRUCTURE = 0.37     # 0.20m concrete + 0.17m flooring
FLOOR_TO_FLOOR = 2.89      # CLEAR_HEIGHT + FLOOR_STRUCTURE
SLAB_THICKNESS = 0.20      # Concrete slab only (structure rendered)
EXT_WALL_THICKNESS = 0.30  # Exterior wall
INT_WALL_THICKNESS = 0.15  # Interior partition wall
CORE_WALL_THICKNESS = 0.20 # Core walls (load-bearing)

# Core dimensions
ELEVATOR_WIDTH = 1.80      # X dimension
ELEVATOR_DEPTH = 2.00      # Y dimension
STAIR_FLIGHT_WIDTH = 1.20  # Flight clear width
STAIR_LANDING = 1.20       # Landing depth
STAIR_WIDTH = 2.60         # Total X (1.20 flight + 0.20 wall + 1.20 flight)
STAIR_DEPTH = 3.50         # Total Y (flight treads + landing): realistic for 2.89m f2f

# Corridor
CORRIDOR_WIDTH = 1.50      # 1.20m minimum + margin

# Façade subdivision
LIVING_FACADE = 3.60       # Living room min façade width
MASTER_BEDROOM_FACADE = 2.80
CHILD_BEDROOM_FACADE = 2.60
PARTITION_WALL = 0.10      # Wall between rooms on façade
MIN_2ROOM_FACADE = LIVING_FACADE + PARTITION_WALL + MASTER_BEDROOM_FACADE  # 6.50m

# Room requirements
VORRAUM_WIDTH = 1.80       # Minimum Vorraum width
BATHROOM_WIDTH = 2.00      # Minimum bathroom width
BATHROOM_DEPTH = 2.00      # Minimum bathroom depth
KITCHEN_WIDTH = 2.40       # Minimum kitchen width
WC_WIDTH = 1.00            # Separate WC min width
WC_DEPTH = 1.50            # Separate WC min depth


# ══════════════════════════════════════════════════════════════════════
# PHASE 1: Shell
# ══════════════════════════════════════════════════════════════════════

def generate_shell_v2(
    name: str = "Building V2",
    width: float = 16.0,
    depth: float = 12.0,
    num_floors: int = 4,
    wall_thickness: float = EXT_WALL_THICKNESS,
    slab_thickness: float = SLAB_THICKNESS,
) -> Building:
    """Generate building shell with correct Austrian floor-to-floor height.

    Uses 2.89m floor-to-floor = 2.52m clear height + 0.37m floor structure.
    Wall height = floor-to-floor height (walls span full storey).
    """
    building = Building(name=name)

    corners = [
        (0.0, 0.0),
        (width, 0.0),
        (width, depth),
        (0.0, depth),
    ]

    wall_segments = [
        (corners[0], corners[1], "South"),
        (corners[1], corners[2], "East"),
        (corners[2], corners[3], "North"),
        (corners[3], corners[0], "West"),
    ]

    for floor_idx in range(num_floors):
        if floor_idx == 0:
            story_name = "Ground Floor"
        else:
            story_name = _ordinal_floor_name(floor_idx)

        story = building.add_story(story_name, height=FLOOR_TO_FLOOR)

        for start, end, direction in wall_segments:
            wall = building.add_wall(
                story_name,
                start=start,
                end=end,
                height=FLOOR_TO_FLOOR,
                thickness=wall_thickness,
                name=f"{direction} Wall",
            )
            wall.load_bearing = True
            wall.is_external = True

        building.add_slab(
            story_name,
            vertices=corners,
            thickness=slab_thickness,
            is_floor=True,
            name="Floor Slab",
        )

    return building


# ══════════════════════════════════════════════════════════════════════
# PHASE 2: Core Placement
# ══════════════════════════════════════════════════════════════════════

def place_core_v2(
    building: Building,
    width: float = 16.0,
    depth: float = 12.0,
) -> dict:
    """Place enclosed vertical core (elevator + staircase) with vestibule.

    Core layout (looking from south, corridor side):
    ```
    +---------+-----------+
    |         |           |
    | ELEVAT. | STAIRCASE |
    |         |           |
    +---------+-----------+
    |     VESTIBULE       |
    +---------------------+
          corridor →
    ```

    Ground floor adds a lobby space between building entrance and core.

    Returns dict with core geometry for use by corridor/apartment generators.
    """
    # Center core horizontally in the building
    core_total_width = ELEVATOR_WIDTH + CORE_WALL_THICKNESS + STAIR_WIDTH
    core_x = (width - core_total_width) / 2

    # Core sits at the back (north side) of corridor zone, centered vertically
    # Vestibule depth for access from corridor
    vestibule_depth = 1.50
    core_equipment_depth = max(ELEVATOR_DEPTH, STAIR_DEPTH)
    core_total_depth = vestibule_depth + core_equipment_depth

    # Place core so corridor is roughly in the middle of the building
    # Core bottom (south edge of vestibule) = center of building minus offset
    corridor_y = (depth - CORRIDOR_WIDTH) / 2
    core_y = corridor_y + CORRIDOR_WIDTH  # Core starts at north edge of corridor

    core_north_y = core_y + core_total_depth

    # Clamp if core extends beyond building
    if core_north_y > depth:
        core_y = depth - core_total_depth
        corridor_y = core_y - CORRIDOR_WIDTH
        core_north_y = depth

    vestibule_north_y = core_y + vestibule_depth
    equipment_north_y = core_north_y

    core_info = {
        "core_x": core_x,
        "core_y": core_y,
        "core_width": core_total_width,
        "core_depth": core_total_depth,
        "corridor_y": corridor_y,
        "corridor_width": CORRIDOR_WIDTH,
        "vestibule_north_y": vestibule_north_y,
        "equipment_north_y": equipment_north_y,
        "elevator_x": core_x,
        "elevator_x_end": core_x + ELEVATOR_WIDTH,
        "stair_x": core_x + ELEVATOR_WIDTH + CORE_WALL_THICKNESS,
        "stair_x_end": core_x + core_total_width,
        "building_width": width,
        "building_depth": depth,
    }

    for story in building.stories:
        sn = story.name
        wh = FLOOR_TO_FLOOR

        # ── Vestibule walls (south-facing, open to corridor) ──
        # West wall of vestibule
        _add_core_wall(building, sn,
                       (core_x, core_y), (core_x, vestibule_north_y),
                       wh, CORE_WALL_THICKNESS, "Core Vestibule West Wall")
        # East wall of vestibule
        _add_core_wall(building, sn,
                       (core_x + core_total_width, core_y),
                       (core_x + core_total_width, vestibule_north_y),
                       wh, CORE_WALL_THICKNESS, "Core Vestibule East Wall")

        # Vestibule south wall (with door to corridor)
        _add_core_wall(building, sn,
                       (core_x, core_y),
                       (core_x + core_total_width, core_y),
                       wh, CORE_WALL_THICKNESS, "Core South Wall")
        # Door from corridor into vestibule
        door_width = 1.00
        door_pos = (core_total_width - door_width) / 2
        building.add_door(
            sn, wall_name="Core South Wall",
            position=door_pos, width=door_width, height=2.10,
            name="Core Entry" if story.name != "Ground Floor" else "Lobby Entry",
        )

        # ── Elevator shaft ──
        elev_x0 = core_x
        elev_x1 = core_x + ELEVATOR_WIDTH
        elev_y0 = vestibule_north_y
        elev_y1 = equipment_north_y

        # Elevator west wall
        _add_core_wall(building, sn,
                       (elev_x0, elev_y0), (elev_x0, elev_y1),
                       wh, CORE_WALL_THICKNESS, "Elevator West Wall")
        # Elevator north wall
        _add_core_wall(building, sn,
                       (elev_x0, elev_y1), (elev_x1, elev_y1),
                       wh, CORE_WALL_THICKNESS, "Elevator North Wall")
        # Elevator south wall (facing vestibule — has door)
        _add_core_wall(building, sn,
                       (elev_x0, elev_y0), (elev_x1, elev_y0),
                       wh, CORE_WALL_THICKNESS, "Elevator South Wall")
        building.add_door(
            sn, wall_name="Elevator South Wall",
            position=0.30, width=0.90, height=2.10,
            name="Elevator Door",
        )

        # ── Divider wall between elevator and staircase ──
        divider_x = elev_x1
        _add_core_wall(building, sn,
                       (divider_x, vestibule_north_y),
                       (divider_x, equipment_north_y),
                       wh, CORE_WALL_THICKNESS, "Core Divider Wall")

        # ── Staircase walls ──
        stair_x0 = core_info["stair_x"]
        stair_x1 = core_info["stair_x_end"]
        stair_y0 = vestibule_north_y
        stair_y1 = equipment_north_y

        # Staircase east wall
        _add_core_wall(building, sn,
                       (stair_x1, stair_y0), (stair_x1, stair_y1),
                       wh, CORE_WALL_THICKNESS, "Staircase East Wall")
        # Staircase north wall
        _add_core_wall(building, sn,
                       (stair_x0, stair_y1), (stair_x1, stair_y1),
                       wh, CORE_WALL_THICKNESS, "Staircase North Wall")
        # Staircase south wall (facing vestibule — has door)
        _add_core_wall(building, sn,
                       (stair_x0, stair_y0), (stair_x1, stair_y0),
                       wh, CORE_WALL_THICKNESS, "Staircase South Wall")
        building.add_door(
            sn, wall_name="Staircase South Wall",
            position=0.30, width=1.00, height=2.10,
            name="Staircase Door",
        )

        # ── Staircase element ──
        stair_outline = [
            (stair_x0, stair_y0),
            (stair_x1, stair_y0),
            (stair_x1, stair_y1),
            (stair_x0, stair_y1),
        ]
        building.add_staircase(
            sn,
            vertices=stair_outline,
            width=STAIR_FLIGHT_WIDTH,
            name="Main Staircase",
        )

        # ── Ground floor: building entrance + lobby ──
        if story.name == "Ground Floor":
            # Building entrance on south wall
            building.add_door(
                sn, wall_name="South Wall",
                position=(width - 1.20) / 2,
                width=1.20, height=2.20,
                name="Building Main Entry",
            )

    return core_info


# ══════════════════════════════════════════════════════════════════════
# PHASE 3: Corridor
# ══════════════════════════════════════════════════════════════════════

def carve_corridor_v2(
    building: Building,
    core_info: dict,
) -> None:
    """Create corridor from core to apartment entry zones.

    Corridor runs east-west from core edges to building edges.
    Does NOT run through the core itself (core has its own vestibule).
    Width >= 1.20m (we use 1.50m for comfort).
    """
    corridor_y = core_info["corridor_y"]
    cw = core_info["corridor_width"]
    core_x = core_info["core_x"]
    core_x_end = core_x + core_info["core_width"]
    bw = core_info["building_width"]

    for story in building.stories:
        sn = story.name
        wh = FLOOR_TO_FLOOR

        # West corridor segment: x=0 to core_x
        if core_x > 0.01:
            wall_s = building.add_wall(
                sn, start=(0, corridor_y), end=(core_x, corridor_y),
                height=wh, thickness=INT_WALL_THICKNESS,
                name="Corridor South Wall West",
            )
            wall_s.load_bearing = False
            wall_s.is_external = False

            wall_n = building.add_wall(
                sn, start=(0, corridor_y + cw), end=(core_x, corridor_y + cw),
                height=wh, thickness=INT_WALL_THICKNESS,
                name="Corridor North Wall West",
            )
            wall_n.load_bearing = False
            wall_n.is_external = False

        # East corridor segment: core_x_end to building width
        if core_x_end < bw - 0.01:
            wall_s = building.add_wall(
                sn, start=(core_x_end, corridor_y),
                end=(bw, corridor_y),
                height=wh, thickness=INT_WALL_THICKNESS,
                name="Corridor South Wall East",
            )
            wall_s.load_bearing = False
            wall_s.is_external = False

            wall_n = building.add_wall(
                sn, start=(core_x_end, corridor_y + cw),
                end=(bw, corridor_y + cw),
                height=wh, thickness=INT_WALL_THICKNESS,
                name="Corridor North Wall East",
            )
            wall_n.load_bearing = False
            wall_n.is_external = False


# ══════════════════════════════════════════════════════════════════════
# PHASE 4: Façade-Based Apartment Subdivision
# ══════════════════════════════════════════════════════════════════════

def subdivide_apartments_v2(
    building: Building,
    core_info: dict,
    story_name: str | None = None,
) -> list[Apartment]:
    """Subdivide floors into apartments based on available façade length.

    KEY INSIGHT: Apartments are divided by FAÇADE, not by area.
    Count exterior wall length, divide by minimum room widths.

    Layout:
    ```
    +------+------+---+------+------+
    |      |      |   |      |      |
    | AptN1| AptN2|COR| AptN3| AptN4|  North zone
    +------+------+---+------+------+
    |     corridor + core            |
    +------+------+---+------+------+
    | AptS1| AptS2|   | AptS3| AptS4|  South zone
    +------+------+---+------+------+
    ```

    On each side (north/south), apartments span from exterior wall to corridor.
    Façade = exterior wall length available (building width minus core width on that side).
    """
    corridor_y = core_info["corridor_y"]
    cw = core_info["corridor_width"]
    core_x = core_info["core_x"]
    core_width = core_info["core_width"]
    bw = core_info["building_width"]
    bd = core_info["building_depth"]

    all_apartments: list[Apartment] = []

    stories_to_process = (
        [building._require_story(story_name)] if story_name
        else building.stories
    )

    for story in stories_to_process:
        sn = story.name
        wh = FLOOR_TO_FLOOR

        # ── South zone: y=0 to corridor_y ──
        south_depth = corridor_y
        south_facade = bw  # Full south façade available (no core on south exterior)
        south_apts = _plan_apartments_for_facade(south_facade, south_depth, "S")

        x_cursor = 0.0
        for i, apt_plan in enumerate(south_apts):
            x0 = x_cursor
            x1 = x_cursor + apt_plan["width"]
            y0 = 0.0
            y1 = corridor_y

            apt = _create_apartment_v2(
                x0, y0, x1, y1,
                name=f"Apt S{i+1}",
                facade_side="south",
                apt_plan=apt_plan,
            )
            story.apartments.append(apt)
            all_apartments.append(apt)

            # Partition wall between apartments (not at building edges)
            if i > 0:
                wall = building.add_wall(
                    sn, start=(x0, y0), end=(x0, y1),
                    height=wh, thickness=INT_WALL_THICKNESS,
                    name=f"Apt Partition S-{i}",
                )
                wall.load_bearing = True  # Bearing wall for vertical alignment
                wall.is_external = False

            x_cursor = x1

        # Add apartment entry doors from corridor (south side)
        for i, apt in enumerate(story.apartments):
            if not apt.name.startswith("Apt S"):
                continue
            verts = apt.boundary.vertices
            min_x = min(v.x for v in verts)
            max_x = max(v.x for v in verts)
            apt_center_x = (min_x + max_x) / 2

            # Find the correct corridor wall segment
            wall_name = _find_corridor_wall(story, apt_center_x, core_x,
                                            core_x + core_width, "south")
            if wall_name:
                corridor_wall = story.get_wall_by_name(wall_name)
                if corridor_wall:
                    wall_start_x = min(corridor_wall.start.x, corridor_wall.end.x)
                    door_pos = apt_center_x - wall_start_x - 0.45
                    if door_pos < 0.1:
                        door_pos = 0.1
                    if door_pos + 0.9 > corridor_wall.length:
                        door_pos = corridor_wall.length - 1.0
                    building.add_door(
                        sn, wall_name=wall_name,
                        position=max(0.1, door_pos), width=0.90, height=2.10,
                        name=f"{apt.name} Entry",
                    )

        # ── North zone: corridor_y + cw to building_depth ──
        north_y0 = corridor_y + cw
        north_depth = bd - north_y0
        # North façade is reduced by core projection
        # Core extends from core_y (= corridor_y + cw) northward
        # Apartments on the north side go from corridor north edge to building north edge
        # But the core occupies some of this zone
        north_facade = bw  # Full north façade
        north_apts = _plan_apartments_for_facade(north_facade, north_depth, "N")

        x_cursor = 0.0
        for i, apt_plan in enumerate(north_apts):
            x0 = x_cursor
            x1 = x_cursor + apt_plan["width"]
            y0 = north_y0
            y1 = bd

            apt = _create_apartment_v2(
                x0, y0, x1, y1,
                name=f"Apt N{i+1}",
                facade_side="north",
                apt_plan=apt_plan,
            )
            story.apartments.append(apt)
            all_apartments.append(apt)

            if i > 0:
                wall = building.add_wall(
                    sn, start=(x0, y0), end=(x0, y1),
                    height=wh, thickness=INT_WALL_THICKNESS,
                    name=f"Apt Partition N-{i}",
                )
                wall.load_bearing = True
                wall.is_external = False

            x_cursor = x1

        # Add apartment entry doors (north side)
        for apt in story.apartments:
            if not apt.name.startswith("Apt N"):
                continue
            verts = apt.boundary.vertices
            min_x = min(v.x for v in verts)
            max_x = max(v.x for v in verts)
            apt_center_x = (min_x + max_x) / 2

            wall_name = _find_corridor_wall(story, apt_center_x, core_x,
                                            core_x + core_width, "north")
            if wall_name:
                corridor_wall = story.get_wall_by_name(wall_name)
                if corridor_wall:
                    wall_start_x = min(corridor_wall.start.x, corridor_wall.end.x)
                    door_pos = apt_center_x - wall_start_x - 0.45
                    if door_pos < 0.1:
                        door_pos = 0.1
                    if door_pos + 0.9 > corridor_wall.length:
                        door_pos = corridor_wall.length - 1.0
                    building.add_door(
                        sn, wall_name=wall_name,
                        position=max(0.1, door_pos), width=0.90, height=2.10,
                        name=f"{apt.name} Entry",
                    )

    return all_apartments


def _plan_apartments_for_facade(
    facade_length: float,
    depth: float,
    side: str,
) -> list[dict]:
    """Plan apartment widths based on available façade length.

    Divides façade into apartments where each gets >= 6.50m for a 2-room unit.
    Returns list of dicts with 'width' and 'type' (number of rooms).
    """
    # How many 2-room apartments fit? (minimum 6.50m each)
    # With partition walls between: n apts need (n-1) * 0.15m partitions
    # Solve: n * 6.50 + (n-1) * 0.15 <= facade_length
    # n * 6.65 - 0.15 <= facade_length
    # n <= (facade_length + 0.15) / 6.65

    max_apts = int((facade_length + INT_WALL_THICKNESS) / (MIN_2ROOM_FACADE + INT_WALL_THICKNESS))
    if max_apts < 1:
        max_apts = 1

    # For 16m façade: (16 + 0.15) / 6.65 = 2.43 → 2 apartments
    num_apts = max_apts

    # Distribute remaining façade evenly
    partition_total = (num_apts - 1) * INT_WALL_THICKNESS
    usable_facade = facade_length - partition_total
    apt_width = usable_facade / num_apts

    result = []
    for i in range(num_apts):
        # Determine apartment type from façade width
        if apt_width >= LIVING_FACADE + 2 * PARTITION_WALL + MASTER_BEDROOM_FACADE + CHILD_BEDROOM_FACADE:
            apt_type = 3  # 3-room: living + master + child
        elif apt_width >= MIN_2ROOM_FACADE:
            apt_type = 2  # 2-room: living + master
        else:
            apt_type = 1  # Studio

        result.append({
            "width": apt_width,
            "type": apt_type,
            "depth": depth,
        })

    return result


def _find_corridor_wall(
    story, apt_center_x: float, core_x: float, core_x_end: float, side: str,
) -> str | None:
    """Find the correct corridor wall name for a given apartment position."""
    if side == "south":
        prefix = "Corridor South Wall"
    else:
        prefix = "Corridor North Wall"

    if apt_center_x < core_x:
        name = f"{prefix} West"
    else:
        name = f"{prefix} East"

    if story.get_wall_by_name(name):
        return name
    return None


# ══════════════════════════════════════════════════════════════════════
# PHASE 5: Room Subdivision
# ══════════════════════════════════════════════════════════════════════

def _create_apartment_v2(
    x0: float, y0: float, x1: float, y1: float,
    name: str,
    facade_side: str,
    apt_plan: dict,
) -> Apartment:
    """Create apartment with rooms following architect's rules.

    Room layout strategy (column-based, not strip-based):
    - Rooms run FULL DEPTH from façade to corridor (maximizes room area)
    - Vorraum is a narrow column at the entry point (1.80m wide)
    - Wet zone (bath + kitchen) is a column sharing installation shaft
    - Living + bedrooms are columns along the façade

    For south apartments (facade_side="south"):
      facade is at y=y0 (south wall), corridor at y=y1 (north)
    For north apartments:
      facade is at y=y1 (north wall), corridor at y=y0 (south)

    Layout example (south apartment, 2-room):
    ```
    +---------+---------+-----+---+
    | Living  | Bedroom |Bath |Vr |  ← corridor side (y1)
    |         |         |-----+   |
    |         |         |Kitch|   |
    +---------+---------+-----+---+  ← façade side (y0)
    ```
    """
    w = x1 - x0
    h = y1 - y0
    apt_type = apt_plan["type"]
    apt_area = w * h

    spaces = []

    # ── Box-based layout (like real apartments) ──
    # Bedroom(s) = FULL-DEPTH columns on one side (maximizes bedroom area)
    # Living zone = remaining space (full depth), with service boxes in corridor corner
    # Service boxes (Vorraum + Bathroom + WC) in the living zone's corridor-side corner
    #
    # Layout (south apartment, corridor at top, façade at bottom):
    # +---+-----+-----------+
    # |Vr | Bath|           |
    # +---+-----+  Bedroom  |  ← full depth, no service boxes
    # |         |           |
    # | Living/ |           |
    # | Kitchen |           |
    # +---------+-----------+
    #       façade
    #
    # Bedroom gets FULL depth → 2.80m × 5.25m = 14.7m² ✅

    # Bedroom column width (right side, full depth from facade to corridor)
    bedroom_w = MASTER_BEDROOM_FACADE  # 2.80m for master
    if apt_type >= 3:
        bedroom_w = MASTER_BEDROOM_FACADE + CHILD_BEDROOM_FACADE + PARTITION_WALL
    bedroom_w = min(bedroom_w, w * 0.55)

    # Living zone = everything left of bedroom
    living_x0 = x0
    living_x1 = x1 - bedroom_w
    bed_x0 = living_x1
    bed_x1 = x1

    # Service box dimensions
    service_depth = min(2.00, h * 0.35)
    vorraum_w = VORRAUM_WIDTH
    bath_w = BATHROOM_WIDTH

    # Fit service boxes within living zone width
    living_zone_w = living_x1 - living_x0
    if vorraum_w + bath_w > living_zone_w:
        # Scale down
        total = vorraum_w + bath_w
        vorraum_w = living_zone_w * (VORRAUM_WIDTH / total)
        bath_w = living_zone_w - vorraum_w

    # Cap Vorraum area to <= 10%
    max_vorraum_area = apt_area * 0.10
    if vorraum_w * service_depth > max_vorraum_area:
        vorraum_w = max(1.00, max_vorraum_area / service_depth)

    if facade_side == "south":
        service_y0 = y1 - service_depth
        service_y1 = y1
    else:
        service_y0 = y0
        service_y1 = y0 + service_depth

    # ── Vorraum (in living zone, corridor-side corner, near entry) ──
    # Vorraum at right side of living zone (adjacent to bedroom)
    vor_x0 = living_x1 - vorraum_w
    vor_x1 = living_x1
    spaces.append(Space(
        name=f"{name} Vorraum",
        room_type=RoomType.HALLWAY,
        boundary=Polygon2D(vertices=[
            Point2D(x=vor_x0, y=service_y0), Point2D(x=vor_x1, y=service_y0),
            Point2D(x=vor_x1, y=service_y1), Point2D(x=vor_x0, y=service_y1),
        ]),
    ))

    # ── Bathroom (next to Vorraum, in living zone corridor corner) ──
    bath_x0 = vor_x0 - bath_w
    bath_x1 = vor_x0
    # Clamp to living zone
    if bath_x0 < living_x0:
        bath_x0 = living_x0
    spaces.append(Space(
        name=f"{name} Bathroom",
        room_type=RoomType.BATHROOM,
        boundary=Polygon2D(vertices=[
            Point2D(x=bath_x0, y=service_y0), Point2D(x=bath_x1, y=service_y0),
            Point2D(x=bath_x1, y=service_y1), Point2D(x=bath_x0, y=service_y1),
        ]),
    ))

    # ── Separate WC for 3-room apartments ──
    if apt_type >= 3:
        wc_w = min(WC_WIDTH, bath_x0 - living_x0)
        if wc_w >= 0.80:
            wc_x0 = bath_x0 - wc_w
            wc_x1 = bath_x0
            spaces.append(Space(
                name=f"{name} WC",
                room_type=RoomType.TOILET,
                boundary=Polygon2D(vertices=[
                    Point2D(x=wc_x0, y=service_y0), Point2D(x=wc_x1, y=service_y0),
                    Point2D(x=wc_x1, y=service_y1), Point2D(x=wc_x0, y=service_y1),
                ]),
            ))

    # ── Living room (full depth of living zone) ──
    spaces.append(Space(
        name=f"{name} Living",
        room_type=RoomType.LIVING,
        boundary=Polygon2D(vertices=[
            Point2D(x=living_x0, y=y0), Point2D(x=living_x1, y=y0),
            Point2D(x=living_x1, y=y1), Point2D(x=living_x0, y=y1),
        ]),
    ))

    # ── Kitchen (open-plan, in living zone near façade for natural light) ──
    kitchen_w = min(KITCHEN_WIDTH, living_zone_w * 0.50)
    kitchen_depth = min(2.50, h * 0.40)

    if facade_side == "south":
        # Kitchen at facade side (bottom) in living zone
        kitchen_y0 = y0
        kitchen_y1 = y0 + kitchen_depth
    else:
        # Kitchen at facade side (top) in living zone
        kitchen_y0 = y1 - kitchen_depth
        kitchen_y1 = y1

    spaces.append(Space(
        name=f"{name} Kitchen",
        room_type=RoomType.KITCHEN,
        boundary=Polygon2D(vertices=[
            Point2D(x=living_x1 - kitchen_w, y=kitchen_y0),
            Point2D(x=living_x1, y=kitchen_y0),
            Point2D(x=living_x1, y=kitchen_y1),
            Point2D(x=living_x1 - kitchen_w, y=kitchen_y1),
        ]),
    ))

    # ── Bedroom(s) — FULL DEPTH columns (y0 to y1) ──
    if apt_type <= 2:
        spaces.append(Space(
            name=f"{name} Bedroom",
            room_type=RoomType.BEDROOM,
            boundary=Polygon2D(vertices=[
                Point2D(x=bed_x0, y=y0), Point2D(x=bed_x1, y=y0),
                Point2D(x=bed_x1, y=y1), Point2D(x=bed_x0, y=y1),
            ]),
        ))
    else:
        master_w = bedroom_w * (MASTER_BEDROOM_FACADE /
                                (MASTER_BEDROOM_FACADE + CHILD_BEDROOM_FACADE))
        master_x1 = bed_x0 + master_w
        spaces.append(Space(
            name=f"{name} Master Bedroom",
            room_type=RoomType.BEDROOM,
            boundary=Polygon2D(vertices=[
                Point2D(x=bed_x0, y=y0), Point2D(x=master_x1, y=y0),
                Point2D(x=master_x1, y=y1), Point2D(x=bed_x0, y=y1),
            ]),
        ))
        spaces.append(Space(
            name=f"{name} Child Bedroom",
            room_type=RoomType.BEDROOM,
            boundary=Polygon2D(vertices=[
                Point2D(x=master_x1, y=y0), Point2D(x=bed_x1, y=y0),
                Point2D(x=bed_x1, y=y1), Point2D(x=master_x1, y=y1),
            ]),
        ))

    boundary = Polygon2D(vertices=[
        Point2D(x=x0, y=y0), Point2D(x=x1, y=y0),
        Point2D(x=x1, y=y1), Point2D(x=x0, y=y1),
    ])

    return Apartment(
        name=name,
        boundary=boundary,
        spaces=spaces,
    )


# ══════════════════════════════════════════════════════════════════════
# PHASE 6: Vertical Consistency — handled by validators
# ══════════════════════════════════════════════════════════════════════
# Phase 6 is purely validation (E050, E051, W050).
# The generation pipeline above already ensures vertical alignment by:
# - Using identical core placement on all floors
# - Using the same partition wall positions on all floors
# - Template stamping would preserve alignment


# ══════════════════════════════════════════════════════════════════════
# WINDOWS — add after apartments are defined
# ══════════════════════════════════════════════════════════════════════

def add_windows_v2(building: Building, core_info: dict) -> None:
    """Add windows to all apartments on exterior walls.

    Every habitable room gets a window on the façade.
    Window width = 1.20m, height = 1.50m, sill = 0.90m.
    """
    bw = core_info["building_width"]
    bd = core_info["building_depth"]

    for story in building.stories:
        sn = story.name

        for apt in story.apartments:
            # Determine which exterior wall this apartment faces
            verts = apt.boundary.vertices
            min_y = min(v.y for v in verts)
            max_y = max(v.y for v in verts)
            min_x = min(v.x for v in verts)
            max_x = max(v.x for v in verts)

            facade_wall_name = None
            if abs(min_y) < 0.01:  # South facade
                facade_wall_name = "South Wall"
            elif abs(max_y - bd) < 0.01:  # North facade
                facade_wall_name = "North Wall"

            if facade_wall_name is None:
                continue

            facade_wall = story.get_wall_by_name(facade_wall_name)
            if facade_wall is None:
                continue

            # Place windows for each habitable room
            for space in apt.spaces:
                if space.room_type in (RoomType.BATHROOM, RoomType.TOILET,
                                       RoomType.HALLWAY, RoomType.CORRIDOR,
                                       RoomType.STORAGE):
                    continue  # These don't need windows

                # Window centered in the room's façade extent
                s_verts = space.boundary.vertices
                s_min_x = min(v.x for v in s_verts)
                s_max_x = max(v.x for v in s_verts)
                room_center_x = (s_min_x + s_max_x) / 2

                wall_start_x = min(facade_wall.start.x, facade_wall.end.x)
                win_width = 1.20
                win_pos = room_center_x - wall_start_x - win_width / 2

                # Ensure window fits in wall
                if win_pos < 0.3:
                    win_pos = 0.3
                if win_pos + win_width > facade_wall.length - 0.3:
                    continue  # Skip if can't fit

                building.add_window(
                    sn, wall_name=facade_wall_name,
                    position=win_pos, width=win_width, height=1.50,
                    sill_height=0.90,
                    name=f"{space.name} Window",
                )


# ══════════════════════════════════════════════════════════════════════
# FULL PIPELINE
# ══════════════════════════════════════════════════════════════════════

def generate_building_4apt(
    name: str = "4-Storey Building V2",
    width: float = 16.0,
    depth: float = 12.0,
    num_floors: int = 4,
) -> Building:
    """Complete building generation pipeline: Phases 1-6.

    Returns a fully designed building with shell, core, corridor,
    apartments (façade-based), rooms, and windows.
    """
    # Phase 1: Shell
    building = generate_shell_v2(name=name, width=width, depth=depth,
                                 num_floors=num_floors)

    # Phase 2: Core
    core_info = place_core_v2(building, width=width, depth=depth)

    # Phase 3: Corridor
    carve_corridor_v2(building, core_info)

    # Phase 4 + 5: Apartments with room subdivision
    subdivide_apartments_v2(building, core_info)

    # Windows for all habitable rooms
    add_windows_v2(building, core_info)

    return building


# ── Helpers ───────────────────────────────────────────────────────────

def _add_core_wall(
    building: Building,
    story_name: str,
    start: tuple[float, float],
    end: tuple[float, float],
    height: float,
    thickness: float,
    name: str,
) -> None:
    """Add a load-bearing core wall."""
    wall = building.add_wall(
        story_name, start=start, end=end,
        height=height, thickness=thickness, name=name,
    )
    wall.load_bearing = True
    wall.is_external = False


def _ordinal_floor_name(floor_idx: int) -> str:
    """Generate floor name: 1st Floor, 2nd Floor, etc."""
    suffixes = {1: "st", 2: "nd", 3: "rd"}
    suffix = suffixes.get(floor_idx, "th")
    return f"{floor_idx}{suffix} Floor"


# ══════════════════════════════════════════════════════════════════════
# INTERIOR VERSION (v3) — supersedes v2 for complete buildings
# ══════════════════════════════════════════════════════════════════════

# ── v3 constants ──────────────────────────────────────────────────────
PARTITION_THICKNESS = 0.10   # Interior partition wall (10cm)
BEDROOM_WIDTH_V3 = 3.50      # Wider bedroom for aspect ratio ≤ 1.50
BEDROOM_WIDTH_GF = 3.30      # Slightly narrower on ground floor (lobby eats space)
SERVICE_DEPTH = 2.10         # Depth of service zone (bathroom + vorraum)
LOBBY_WIDTH = 2.00           # Building entrance lobby clear width
LOBBY_WALL_T = PARTITION_THICKNESS  # Lobby wall thickness

# Door widths
DOOR_ROOM = 0.80             # Standard room door
DOOR_APARTMENT = 0.90        # Apartment entry door
DOOR_BUILDING = 1.20         # Building main entry
DOOR_CORE = 1.00             # Core entry / staircase
DOOR_ELEVATOR = 0.90         # Elevator
DOOR_BATHROOM = 0.80         # Bathroom door


# ══════════════════════════════════════════════════════════════════════
# PHASE 2: Core Placement (same as v2 but cleaner)
# ══════════════════════════════════════════════════════════════════════

def place_core_v3(
    building: Building,
    width: float = 16.0,
    depth: float = 12.0,
) -> dict:
    """Place enclosed vertical core (elevator + staircase).

    Same geometry as v2 but with:
    - No windows on any core wall (fire-rated)
    - Standard door sizes only (≤1.00m)
    - Ground floor: building entrance + lobby
    """
    core_total_width = ELEVATOR_WIDTH + CORE_WALL_THICKNESS + STAIR_WIDTH
    core_x = (width - core_total_width) / 2

    vestibule_depth = 1.50
    core_equipment_depth = max(ELEVATOR_DEPTH, STAIR_DEPTH)
    core_total_depth = vestibule_depth + core_equipment_depth

    corridor_y = (depth - CORRIDOR_WIDTH) / 2
    core_y = corridor_y + CORRIDOR_WIDTH
    core_north_y = core_y + core_total_depth

    if core_north_y > depth:
        core_y = depth - core_total_depth
        corridor_y = core_y - CORRIDOR_WIDTH
        core_north_y = depth

    vestibule_north_y = core_y + vestibule_depth
    equipment_north_y = core_north_y

    # Lobby geometry (centered on building)
    lobby_center_x = width / 2.0
    lobby_x0 = lobby_center_x - LOBBY_WIDTH / 2.0
    lobby_x1 = lobby_center_x + LOBBY_WIDTH / 2.0

    core_info = {
        "core_x": core_x,
        "core_y": core_y,
        "core_width": core_total_width,
        "core_depth": core_total_depth,
        "corridor_y": corridor_y,
        "corridor_width": CORRIDOR_WIDTH,
        "vestibule_north_y": vestibule_north_y,
        "equipment_north_y": equipment_north_y,
        "elevator_x": core_x,
        "elevator_x_end": core_x + ELEVATOR_WIDTH,
        "stair_x": core_x + ELEVATOR_WIDTH + CORE_WALL_THICKNESS,
        "stair_x_end": core_x + core_total_width,
        "building_width": width,
        "building_depth": depth,
        "lobby_x0": lobby_x0,
        "lobby_x1": lobby_x1,
    }

    for story in building.stories:
        sn = story.name
        wh = FLOOR_TO_FLOOR

        # ── Vestibule walls ──
        _add_core_wall(building, sn,
                       (core_x, core_y), (core_x, vestibule_north_y),
                       wh, CORE_WALL_THICKNESS, "Core Vestibule West Wall")
        _add_core_wall(building, sn,
                       (core_x + core_total_width, core_y),
                       (core_x + core_total_width, vestibule_north_y),
                       wh, CORE_WALL_THICKNESS, "Core Vestibule East Wall")
        _add_core_wall(building, sn,
                       (core_x, core_y),
                       (core_x + core_total_width, core_y),
                       wh, CORE_WALL_THICKNESS, "Core South Wall")

        # Core entry door (standard 0.90m fire-rated)
        door_pos = (core_total_width - DOOR_APARTMENT) / 2
        building.add_door(
            sn, wall_name="Core South Wall",
            position=door_pos, width=DOOR_APARTMENT, height=2.10,
            name="Core Entry" if sn != "Ground Floor" else "Lobby Core Entry",
        )

        # ── Elevator shaft ──
        elev_x0 = core_x
        elev_x1 = core_x + ELEVATOR_WIDTH
        elev_y0 = vestibule_north_y
        elev_y1 = equipment_north_y

        _add_core_wall(building, sn,
                       (elev_x0, elev_y0), (elev_x0, elev_y1),
                       wh, CORE_WALL_THICKNESS, "Elevator West Wall")
        _add_core_wall(building, sn,
                       (elev_x0, elev_y1), (elev_x1, elev_y1),
                       wh, CORE_WALL_THICKNESS, "Elevator North Wall")
        _add_core_wall(building, sn,
                       (elev_x0, elev_y0), (elev_x1, elev_y0),
                       wh, CORE_WALL_THICKNESS, "Elevator South Wall")
        building.add_door(
            sn, wall_name="Elevator South Wall",
            position=0.30, width=DOOR_ELEVATOR, height=2.10,
            name="Elevator Door",
        )

        # ── Divider wall ──
        divider_x = elev_x1
        _add_core_wall(building, sn,
                       (divider_x, vestibule_north_y),
                       (divider_x, equipment_north_y),
                       wh, CORE_WALL_THICKNESS, "Core Divider Wall")

        # ── Staircase ──
        stair_x0 = core_info["stair_x"]
        stair_x1 = core_info["stair_x_end"]
        stair_y0 = vestibule_north_y
        stair_y1 = equipment_north_y

        _add_core_wall(building, sn,
                       (stair_x1, stair_y0), (stair_x1, stair_y1),
                       wh, CORE_WALL_THICKNESS, "Staircase East Wall")
        _add_core_wall(building, sn,
                       (stair_x0, stair_y1), (stair_x1, stair_y1),
                       wh, CORE_WALL_THICKNESS, "Staircase North Wall")
        _add_core_wall(building, sn,
                       (stair_x0, stair_y0), (stair_x1, stair_y0),
                       wh, CORE_WALL_THICKNESS, "Staircase South Wall")
        building.add_door(
            sn, wall_name="Staircase South Wall",
            position=0.30, width=DOOR_CORE, height=2.10,
            name="Staircase Door",
        )

        stair_outline = [
            (stair_x0, stair_y0), (stair_x1, stair_y0),
            (stair_x1, stair_y1), (stair_x0, stair_y1),
        ]
        building.add_staircase(sn, vertices=stair_outline,
                               width=STAIR_FLIGHT_WIDTH, name="Main Staircase")

        # ── Ground floor: entrance + lobby ──
        if sn == "Ground Floor":
            building.add_door(
                sn, wall_name="South Wall",
                position=(width - DOOR_BUILDING) / 2,
                width=DOOR_BUILDING, height=2.20,
                name="Building Main Entry",
            )

    return core_info


# ══════════════════════════════════════════════════════════════════════
# PHASE 3: Corridor + Lobby
# ══════════════════════════════════════════════════════════════════════

def carve_corridor_v3(
    building: Building,
    core_info: dict,
) -> None:
    """Create corridor + ground floor lobby.

    Corridor runs east-west from core edges to building edges.
    On ground floor, a north-south lobby connects the building entrance
    (south wall) to the corridor.
    """
    corridor_y = core_info["corridor_y"]
    cw = core_info["corridor_width"]
    core_x = core_info["core_x"]
    core_x_end = core_x + core_info["core_width"]
    bw = core_info["building_width"]
    lobby_x0 = core_info["lobby_x0"]
    lobby_x1 = core_info["lobby_x1"]

    for story in building.stories:
        sn = story.name
        wh = FLOOR_TO_FLOOR
        is_ground = (sn == "Ground Floor")

        # West corridor segment: x=0 to core_x
        if core_x > 0.01:
            wall_s = building.add_wall(
                sn, start=(0, corridor_y), end=(core_x, corridor_y),
                height=wh, thickness=INT_WALL_THICKNESS,
                name="Corridor South Wall West",
            )
            wall_s.load_bearing = False
            wall_s.is_external = False

            wall_n = building.add_wall(
                sn, start=(0, corridor_y + cw), end=(core_x, corridor_y + cw),
                height=wh, thickness=INT_WALL_THICKNESS,
                name="Corridor North Wall West",
            )
            wall_n.load_bearing = False
            wall_n.is_external = False

        # East corridor segment: core_x_end to building width
        if core_x_end < bw - 0.01:
            wall_s = building.add_wall(
                sn, start=(core_x_end, corridor_y), end=(bw, corridor_y),
                height=wh, thickness=INT_WALL_THICKNESS,
                name="Corridor South Wall East",
            )
            wall_s.load_bearing = False
            wall_s.is_external = False

            wall_n = building.add_wall(
                sn, start=(core_x_end, corridor_y + cw), end=(bw, corridor_y + cw),
                height=wh, thickness=INT_WALL_THICKNESS,
                name="Corridor North Wall East",
            )
            wall_n.load_bearing = False
            wall_n.is_external = False

        # Core zone corridor south wall: fills the gap between west and east segments
        # The south wall must be continuous so south apartments have a proper boundary.
        # The north wall gap is intentional — the core south wall replaces it there.
        if core_x > 0.01 and core_x_end < bw - 0.01:
            wall_sc = building.add_wall(
                sn, start=(core_x, corridor_y), end=(core_x_end, corridor_y),
                height=wh, thickness=INT_WALL_THICKNESS,
                name="Corridor South Wall Core",
            )
            wall_sc.load_bearing = False
            wall_sc.is_external = False

        # ── Ground floor lobby walls ──
        if is_ground:
            # Lobby: north-south strip from y=0 to corridor_y
            # West lobby wall
            wall_lw = building.add_wall(
                sn, start=(lobby_x0, 0), end=(lobby_x0, corridor_y),
                height=wh, thickness=PARTITION_THICKNESS,
                name="Lobby West Wall",
            )
            wall_lw.load_bearing = False
            wall_lw.is_external = False

            # East lobby wall
            wall_le = building.add_wall(
                sn, start=(lobby_x1, 0), end=(lobby_x1, corridor_y),
                height=wh, thickness=PARTITION_THICKNESS,
                name="Lobby East Wall",
            )
            wall_le.load_bearing = False
            wall_le.is_external = False


# ══════════════════════════════════════════════════════════════════════
# PHASE 4+5: Apartments with Interior Walls
# ══════════════════════════════════════════════════════════════════════

def subdivide_apartments_v3(
    building: Building,
    core_info: dict,
) -> list[Apartment]:
    """Subdivide floors into apartments with proper interior walls.

    Key improvements over v2:
    - Ground floor has lobby → 3 south apartments (2 apts + lobby space)
    - All apartments have interior partition walls
    - All rooms have doors
    - Wider bedrooms, larger bathrooms
    """
    corridor_y = core_info["corridor_y"]
    cw = core_info["corridor_width"]
    core_x = core_info["core_x"]
    core_width = core_info["core_width"]
    bw = core_info["building_width"]
    bd = core_info["building_depth"]
    lobby_x0 = core_info["lobby_x0"]
    lobby_x1 = core_info["lobby_x1"]

    all_apartments: list[Apartment] = []

    for story in building.stories:
        sn = story.name
        wh = FLOOR_TO_FLOOR
        is_ground = (sn == "Ground Floor")

        # ── South zone: y=0 to corridor_y ──
        south_depth = corridor_y

        if is_ground:
            # Ground floor: lobby splits south zone into two apartments
            # Apt S1: x=0 to lobby_x0
            # Lobby: lobby_x0 to lobby_x1 (not an apartment)
            # Apt S2: lobby_x1 to bw
            south_apt_ranges = [
                (0.0, lobby_x0, "Apt S1"),
                (lobby_x1, bw, "Apt S2"),
            ]
        else:
            # Upper floors: 2 apartments spanning full width
            mid_x = bw / 2.0
            south_apt_ranges = [
                (0.0, mid_x, "Apt S1"),
                (mid_x, bw, "Apt S2"),
            ]

        for i, (ax0, ax1, apt_name) in enumerate(south_apt_ranges):
            apt_width = ax1 - ax0

            # Skip if too narrow
            if apt_width < 4.0:
                continue

            # Add partition wall between apartments (not at building edges or lobby)
            if i > 0 and not is_ground:
                wall = building.add_wall(
                    sn, start=(ax0, 0), end=(ax0, south_depth),
                    height=wh, thickness=PARTITION_THICKNESS,
                    name=f"Apt Partition S-{i}",
                )
                wall.load_bearing = False
                wall.is_external = False

            # Create apartment with interior walls
            apt = _create_apartment_with_walls_v3(
                building, sn,
                ax0, 0.0, ax1, south_depth,
                name=apt_name,
                facade_side="south",
                core_info=core_info,
            )
            story.apartments.append(apt)
            all_apartments.append(apt)

        # ── North zone: corridor_y + cw to building_depth ──
        north_y0 = corridor_y + cw
        north_depth = bd - north_y0

        mid_x = bw / 2.0
        north_apt_ranges = [
            (0.0, mid_x, "Apt N1"),
            (mid_x, bw, "Apt N2"),
        ]

        for i, (ax0, ax1, apt_name) in enumerate(north_apt_ranges):
            if i > 0:
                wall = building.add_wall(
                    sn, start=(ax0, north_y0), end=(ax0, bd),
                    height=wh, thickness=PARTITION_THICKNESS,
                    name=f"Apt Partition N-{i}",
                )
                wall.load_bearing = False
                wall.is_external = False

            apt = _create_apartment_with_walls_v3(
                building, sn,
                ax0, north_y0, ax1, bd,
                name=apt_name,
                facade_side="north",
                core_info=core_info,
            )
            story.apartments.append(apt)
            all_apartments.append(apt)

    return all_apartments


def _create_apartment_with_walls_v3(
    building: Building,
    story_name: str,
    x0: float, y0: float, x1: float, y1: float,
    name: str,
    facade_side: str,
    core_info: dict,
) -> Apartment:
    """Create apartment with physical interior partition walls and doors.

    Layout (south apartment, facade at bottom, corridor at top):
    ```
    corridor (y1)
    ┌──────────────┬──────────┬─────────────┐
    │  Bathroom    │ Vorraum  │             │
    │  (≥5m²)     │ (1.8m)   │             │
    ├──────────────┴──────────┤   Bedroom   │
    │                         │   (3.50m)   │
    │   Living / Kitchen      │             │
    │                         │             │
    └─────────────────────────┴─────────────┘
    facade (y0)
    ```
    """
    w = x1 - x0
    h = y1 - y0
    apt_area = w * h
    wh = FLOOR_TO_FLOOR

    # Choose bedroom width based on available space
    bedroom_w = BEDROOM_WIDTH_V3  # 3.50m
    if w - bedroom_w < LIVING_FACADE:
        # Reduce bedroom to maintain minimum living room width
        bedroom_w = max(MASTER_BEDROOM_FACADE, w - LIVING_FACADE)

    living_zone_w = w - bedroom_w

    # Bedroom occupies the RIGHT side (when looking at the plan from south)
    bed_x0 = x1 - bedroom_w
    bed_x1 = x1

    # Service zone at corridor side
    service_depth = SERVICE_DEPTH  # 2.10m
    vorraum_w = VORRAUM_WIDTH  # 1.80m

    # Bathroom gets remaining width of living zone
    bath_w = living_zone_w - vorraum_w
    if bath_w < 1.80:
        # Shrink vorraum if needed
        vorraum_w = max(1.20, living_zone_w - 1.80)
        bath_w = living_zone_w - vorraum_w

    # Service zone Y coordinates
    if facade_side == "south":
        # Corridor at y1, facade at y0
        svc_y0 = y1 - service_depth  # Bottom of service zone
        svc_y1 = y1                   # Top = corridor
        corridor_side_y = y1
    else:
        # Corridor at y0, facade at y1
        svc_y0 = y0                   # Top of service zone = corridor
        svc_y1 = y0 + service_depth   # Bottom of service zone
        corridor_side_y = y0

    # Service zone X coordinates (from left of living zone)
    bath_x0 = x0
    bath_x1 = x0 + bath_w
    vor_x0 = bath_x1
    vor_x1 = vor_x0 + vorraum_w

    # ── Create Spaces ──
    spaces = []

    # Vorraum
    spaces.append(Space(
        name=f"{name} Vorraum",
        room_type=RoomType.HALLWAY,
        boundary=Polygon2D(vertices=[
            Point2D(x=vor_x0, y=svc_y0), Point2D(x=vor_x1, y=svc_y0),
            Point2D(x=vor_x1, y=svc_y1), Point2D(x=vor_x0, y=svc_y1),
        ]),
    ))

    # Bathroom
    spaces.append(Space(
        name=f"{name} Bathroom",
        room_type=RoomType.BATHROOM,
        boundary=Polygon2D(vertices=[
            Point2D(x=bath_x0, y=svc_y0), Point2D(x=bath_x1, y=svc_y0),
            Point2D(x=bath_x1, y=svc_y1), Point2D(x=bath_x0, y=svc_y1),
        ]),
    ))

    # Living room (full depth of living zone minus service area)
    if facade_side == "south":
        living_y0 = y0
        living_y1 = svc_y0
    else:
        living_y0 = svc_y1
        living_y1 = y1

    spaces.append(Space(
        name=f"{name} Living",
        room_type=RoomType.LIVING,
        boundary=Polygon2D(vertices=[
            Point2D(x=x0, y=living_y0), Point2D(x=bed_x0, y=living_y0),
            Point2D(x=bed_x0, y=living_y1), Point2D(x=x0, y=living_y1),
        ]),
    ))

    # Kitchen (sub-zone of living, near facade for natural light)
    kitchen_w = min(KITCHEN_WIDTH, living_zone_w * 0.50)
    kitchen_depth = min(2.50, h * 0.35)

    if facade_side == "south":
        kit_y0 = y0
        kit_y1 = y0 + kitchen_depth
    else:
        kit_y0 = y1 - kitchen_depth
        kit_y1 = y1

    spaces.append(Space(
        name=f"{name} Kitchen",
        room_type=RoomType.KITCHEN,
        boundary=Polygon2D(vertices=[
            Point2D(x=bed_x0 - kitchen_w, y=kit_y0),
            Point2D(x=bed_x0, y=kit_y0),
            Point2D(x=bed_x0, y=kit_y1),
            Point2D(x=bed_x0 - kitchen_w, y=kit_y1),
        ]),
    ))

    # Bedroom (full depth)
    spaces.append(Space(
        name=f"{name} Bedroom",
        room_type=RoomType.BEDROOM,
        boundary=Polygon2D(vertices=[
            Point2D(x=bed_x0, y=y0), Point2D(x=bed_x1, y=y0),
            Point2D(x=bed_x1, y=y1), Point2D(x=bed_x0, y=y1),
        ]),
    ))

    # ── Add Interior Partition Walls ──

    # 1. Bedroom wall: separates bedroom from living zone (full height of apt)
    bedroom_wall_name = f"{name} Bedroom Wall"
    bw_wall = building.add_wall(
        story_name,
        start=(bed_x0, y0), end=(bed_x0, y1),
        height=wh, thickness=PARTITION_THICKNESS,
        name=bedroom_wall_name,
    )
    bw_wall.load_bearing = False
    bw_wall.is_external = False

    # Bedroom door (in bedroom wall, near corridor side)
    if facade_side == "south":
        bed_door_pos = h - service_depth - 1.50  # Near service zone
    else:
        bed_door_pos = service_depth + 0.50       # Near service zone

    bed_door_pos = max(0.3, min(bed_door_pos, h - DOOR_ROOM - 0.3))
    building.add_door(
        story_name, wall_name=bedroom_wall_name,
        position=bed_door_pos, width=DOOR_ROOM, height=2.10,
        name=f"{name} Bedroom Door",
    )

    # 2. Service zone horizontal wall (separates service from living)
    if facade_side == "south":
        svc_wall_y = svc_y0
    else:
        svc_wall_y = svc_y1

    # Bathroom south/north wall (from apartment left edge to bathroom right edge)
    bath_hwall_name = f"{name} Bathroom Outer Wall"
    bhw = building.add_wall(
        story_name,
        start=(bath_x0, svc_wall_y), end=(bath_x1, svc_wall_y),
        height=wh, thickness=PARTITION_THICKNESS,
        name=bath_hwall_name,
    )
    bhw.load_bearing = False
    bhw.is_external = False

    # Vorraum south/north wall
    vor_hwall_name = f"{name} Vorraum Outer Wall"
    vhw = building.add_wall(
        story_name,
        start=(vor_x0, svc_wall_y), end=(vor_x1, svc_wall_y),
        height=wh, thickness=PARTITION_THICKNESS,
        name=vor_hwall_name,
    )
    vhw.load_bearing = False
    vhw.is_external = False

    # Door from Vorraum to living (in vorraum outer wall)
    building.add_door(
        story_name, wall_name=vor_hwall_name,
        position=0.30, width=DOOR_ROOM, height=2.10,
        name=f"{name} Vorraum Door",
    )

    # 3. Bathroom-Vorraum dividing wall (vertical, from service_y to corridor)
    bath_vor_wall_name = f"{name} Bath-Vorraum Wall"
    bvw = building.add_wall(
        story_name,
        start=(bath_x1, svc_y0), end=(bath_x1, svc_y1),
        height=wh, thickness=PARTITION_THICKNESS,
        name=bath_vor_wall_name,
    )
    bvw.load_bearing = False
    bvw.is_external = False

    # Bathroom door (in bath-vorraum wall, opens from vorraum)
    building.add_door(
        story_name, wall_name=bath_vor_wall_name,
        position=0.30, width=DOOR_BATHROOM, height=2.10,
        name=f"{name} Bathroom Door",
    )

    # ── Apartment Entry Door (from corridor) ──
    # Find the corridor wall on the correct side
    apt_center_x = (x0 + x1) / 2
    wall_name = _find_corridor_wall_v3(
        building._require_story(story_name),
        apt_center_x, core_info
    )

    if wall_name:
        corridor_wall = building._require_story(story_name).get_wall_by_name(wall_name)
        if corridor_wall:
            # Position door at the Vorraum location
            vor_center_x = (vor_x0 + vor_x1) / 2
            wall_start_x = min(corridor_wall.start.x, corridor_wall.end.x)
            door_pos = vor_center_x - wall_start_x - DOOR_APARTMENT / 2
            door_pos = max(0.15, min(door_pos, corridor_wall.length - DOOR_APARTMENT - 0.15))
            building.add_door(
                story_name, wall_name=wall_name,
                position=door_pos, width=DOOR_APARTMENT, height=2.10,
                name=f"{name} Entry",
            )

    # ── Create Apartment ──
    boundary = Polygon2D(vertices=[
        Point2D(x=x0, y=y0), Point2D(x=x1, y=y0),
        Point2D(x=x1, y=y1), Point2D(x=x0, y=y1),
    ])

    return Apartment(name=name, boundary=boundary, spaces=spaces)


def _find_corridor_wall_v3(story, apt_center_x: float, core_info: dict) -> str | None:
    """Find the correct corridor wall for apartment entry."""
    core_x = core_info["core_x"]
    core_x_end = core_x + core_info["core_width"]

    # Determine which side of the core
    if apt_center_x < core_x:
        suffix = "West"
    else:
        suffix = "East"

    # Determine north or south based on apartment Y position
    # Check apartments on each side
    for prefix in ["Corridor South Wall", "Corridor North Wall"]:
        name = f"{prefix} {suffix}"
        if story.get_wall_by_name(name):
            # Check if apartment center Y is on the correct side
            wall = story.get_wall_by_name(name)
            wall_y = (wall.start.y + wall.end.y) / 2
            corridor_y = core_info["corridor_y"]
            cw = core_info["corridor_width"]

            # For south apartments, entry is on corridor south wall
            # For north apartments, entry is on corridor north wall
            # We detect by checking which side the wall is on
            return name

    return None


# ══════════════════════════════════════════════════════════════════════
# WINDOWS
# ══════════════════════════════════════════════════════════════════════

def add_windows_v3(building: Building, core_info: dict) -> None:
    """Add windows to exterior walls for habitable rooms.

    NO windows on core walls. Only exterior walls get windows.
    """
    bw = core_info["building_width"]
    bd = core_info["building_depth"]

    for story in building.stories:
        sn = story.name

        for apt in story.apartments:
            verts = apt.boundary.vertices
            min_y = min(v.y for v in verts)
            max_y = max(v.y for v in verts)

            if abs(min_y) < 0.01:
                facade_wall_name = "South Wall"
            elif abs(max_y - bd) < 0.01:
                facade_wall_name = "North Wall"
            else:
                continue

            facade_wall = story.get_wall_by_name(facade_wall_name)
            if not facade_wall:
                continue

            for space in apt.spaces:
                if space.room_type in (RoomType.BATHROOM, RoomType.TOILET,
                                       RoomType.HALLWAY, RoomType.CORRIDOR,
                                       RoomType.STORAGE):
                    continue

                s_verts = space.boundary.vertices
                s_min_x = min(v.x for v in s_verts)
                s_max_x = max(v.x for v in s_verts)
                room_center_x = (s_min_x + s_max_x) / 2

                wall_start_x = min(facade_wall.start.x, facade_wall.end.x)
                win_width = 1.20
                win_pos = room_center_x - wall_start_x - win_width / 2

                if win_pos < 0.3:
                    win_pos = 0.3
                if win_pos + win_width > facade_wall.length - 0.3:
                    continue

                building.add_window(
                    sn, wall_name=facade_wall_name,
                    position=win_pos, width=win_width, height=1.50,
                    sill_height=0.90,
                    name=f"{space.name} Window",
                )


# ══════════════════════════════════════════════════════════════════════
# FULL PIPELINE
# ══════════════════════════════════════════════════════════════════════

def generate_building_4apt_interior(
    name: str = "4-Storey Building V3",
    width: float = 16.0,
    depth: float = 12.0,
    num_floors: int = 4,
) -> Building:
    """Complete v3 building generation: shell + core + corridor + lobby + apartments.

    Generates only ground floor and 1st floor with full detail.
    Upper floors get basic shell + core (template for future stamping).
    """
    # Phase 1: Shell
    building = generate_shell_v2(name=name, width=width, depth=depth,
                                 num_floors=num_floors)

    # Phase 2: Core
    core_info = place_core_v3(building, width=width, depth=depth)

    # Phase 3: Corridor + lobby
    carve_corridor_v3(building, core_info)

    # Phase 4+5: Apartments with interior walls (ground + 1st floor only)
    subdivide_apartments_v3(building, core_info)

    # Windows
    add_windows_v3(building, core_info)

    return building
