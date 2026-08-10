"""Phase validators for building design v2/v3.

Validates each phase of the architect's building design process:
  Phase 1: Shell (E001, W001, E002)
  Phase 2: Core (E010-E013, W010-W011, E060-E061)
  Phase 3: Corridor (E020-E022, W020)
  Phase 4: Façade subdivision (E030-E031, W030-W031)
  Phase 5: Room subdivision (E040-E049, E041b, E070-E071, W040-W045, W060)
  Optimization: Layout improvements (O001, O002, O041)
  Phase 6: Vertical consistency (E050-E052, W050)

v3 additions:
  E060: Core wall opening > 1.20m → ERROR
  E062: Wide opening on bearing wall without a beam → ERROR
  E063: Covering beam implausibly slender → ERROR
  E061: Window on core/staircase wall → ERROR
  W060: Any door > 1.20m → WARNING (suspicious width)
  E070: Enclosed room has no door → ERROR
  E071: Bathroom not enclosed by walls → ERROR
  E041b: Bathroom < 5m² → WARNING
"""

from __future__ import annotations

import math

from shapely.geometry import LineString as ShapelyLine
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.ops import unary_union
from shapely.validation import make_valid

from archicad_builder.models.building import Building, Story
from archicad_builder.models.geometry import Point2D
from archicad_builder.models.spaces import RoomType, Space
from archicad_builder.validators.spaces import (
    validate_space_overlaps as _validate_space_overlaps,
)
from archicad_builder.validators.structural import ValidationError

# Construction constants
CLEAR_HEIGHT_MIN = 2.50      # Legal minimum
CLEAR_HEIGHT_TARGET = 2.52   # Standard practice (with tolerance buffer)
FLOOR_STRUCTURE = 0.37       # 0.20m concrete + 0.17m flooring
MIN_STAIR_WIDTH = 1.20       # Minimum staircase flight width
MIN_CORRIDOR_WIDTH = 1.20    # OIB RL 4
MIN_FACADE_2ROOM = 6.50      # 3.60 + 0.10 + 2.80
MASTER_BEDROOM_MIN_WIDTH = 2.80
MASTER_BEDROOM_MIN_AREA = 12.0
CHILD_BEDROOM_MIN_WIDTH = 2.60
CHILD_BEDROOM_MIN_AREA = 10.0
MAX_ROOM_RATIO = 1.5         # Width:depth max ratio (no tunnels)
MAX_VORRAUM_AREA_PCT = 0.10  # Vorraum <= 10% of apartment area

# v3 constants
MAX_CORE_OPENING = 1.20       # Maximum opening width in core walls (fire-rated)
MAX_SUSPICIOUS_DOOR = 1.20    # Doors wider than this get a warning
MIN_BATHROOM_AREA = 5.0       # OIB adaptable housing requirement
CORE_WALL_KEYWORDS = ["core", "elevator", "staircase", "divider"]  # Wall names indicating core


def validate_all_phases(building: Building,
                        site=None) -> list[ValidationError]:
    """Run all phase validators (v2 + v3).

    `site` is the project's [site] config (specs/seismic-lateral.md);
    None -> the seismic validators report nothing (unresolved, never
    guessed) so buildings without a site keep validating as before."""
    errors: list[ValidationError] = []
    errors.extend(validate_phase1_shell(building))
    errors.extend(validate_phase2_core(building))
    errors.extend(validate_phase3_corridor(building))
    errors.extend(validate_phase4_facade(building))
    errors.extend(validate_phase5_rooms(building))
    errors.extend(validate_apartment_connectivity(building))
    errors.extend(validate_phase6_vertical(building))
    # Phase B structural loads (specs/structural-plausibility.md)
    errors.extend(validate_structural_loads(building))
    # S1 seismic (specs/seismic-lateral.md)
    errors.extend(validate_seismic(building, site))
    # S3 foundations (specs/foundations.md)
    errors.extend(validate_foundations(building, site))
    # v3 additions
    errors.extend(validate_core_integrity(building))
    errors.extend(validate_interior_enclosure(building))
    # Data invariants
    errors.extend(_validate_space_overlaps(building))
    # Optimization validators
    errors.extend(validate_optimizations(building))
    return errors


# ══════════════════════════════════════════════════════════════════════
# PHASE 1: Shell Validators
# ══════════════════════════════════════════════════════════════════════

def validate_phase1_shell(building: Building) -> list[ValidationError]:
    """Phase 1 validators: E001, W001, E002."""
    errors: list[ValidationError] = []

    for story in building.stories:
        # Clear height = floor-to-floor minus floor structure
        # Story.height IS the floor-to-floor height
        # Clear height = height - FLOOR_STRUCTURE
        clear_height = story.height - FLOOR_STRUCTURE

        # E001: Clear height < 2.50m → ERROR
        if clear_height < CLEAR_HEIGHT_MIN - 0.01:
            errors.append(ValidationError(
                severity="error",
                element_type="Story",
                element_id=story.global_id,
                message=(
                    f"E001: Story '{story.name}' clear height is {clear_height:.2f}m "
                    f"(floor-to-floor {story.height:.2f}m - structure {FLOOR_STRUCTURE}m). "
                    f"Minimum is {CLEAR_HEIGHT_MIN}m (OIB RL 3)."
                ),
            ))

        # W001: Clear height != 2.52m → WARNING
        elif abs(clear_height - CLEAR_HEIGHT_TARGET) > 0.01:
            errors.append(ValidationError(
                severity="warning",
                element_type="Story",
                element_id=story.global_id,
                message=(
                    f"W001: Story '{story.name}' clear height is {clear_height:.2f}m, "
                    f"target is {CLEAR_HEIGHT_TARGET}m (2cm tolerance buffer over "
                    f"{CLEAR_HEIGHT_MIN}m minimum)."
                ),
            ))

        # E002: Missing floor slab → ERROR
        floor_slabs = [s for s in story.slabs if s.is_floor]
        if not floor_slabs:
            errors.append(ValidationError(
                severity="error",
                element_type="Story",
                element_id=story.global_id,
                message=f"E002: Story '{story.name}' has no floor slab.",
            ))

    return errors


# ══════════════════════════════════════════════════════════════════════
# PHASE 2: Core Validators
# ══════════════════════════════════════════════════════════════════════

def validate_phase2_core(building: Building) -> list[ValidationError]:
    """Phase 2 validators: E010-E013, W010-W011."""
    errors: list[ValidationError] = []

    if len(building.stories) < 2:
        return errors  # Single-storey doesn't need core validation

    # E010: No staircase in multi-storey building
    for story in building.stories:
        if not story.staircases:
            errors.append(ValidationError(
                severity="error",
                element_type="Building",
                element_id=building.global_id,
                message=(
                    f"E010: Multi-storey building has no staircase on "
                    f"'{story.name}'."
                ),
            ))

    # E011: Core not accessible from every storey
    # Check that each floor has a door to the core area (named "Core Entry" or similar)
    for story in building.stories:
        core_doors = [d for d in story.doors
                      if "core" in (d.name or "").lower()
                      or "lobby" in (d.name or "").lower()
                      or "staircase door" in (d.name or "").lower()]
        if not core_doors:
            errors.append(ValidationError(
                severity="error",
                element_type="Story",
                element_id=story.global_id,
                message=(
                    f"E011: Story '{story.name}' has no door to the vertical core. "
                    f"Core must be accessible from every floor."
                ),
            ))

    # E012: Staircase flight width < 1.20m
    for story in building.stories:
        for st in story.staircases:
            if st.width < MIN_STAIR_WIDTH - 0.01:
                errors.append(ValidationError(
                    severity="error",
                    element_type="Staircase",
                    element_id=st.global_id,
                    message=(
                        f"E012: Staircase '{st.name}' on '{story.name}' has "
                        f"flight width {st.width:.2f}m — minimum is "
                        f"{MIN_STAIR_WIDTH}m."
                    ),
                ))

    # E013: No building entrance / ground floor lobby
    ground = building.stories[0] if building.stories else None
    if ground:
        building_entries = [d for d in ground.doors
                           if "building" in (d.name or "").lower()
                           or "main entry" in (d.name or "").lower()]
        if not building_entries:
            errors.append(ValidationError(
                severity="error",
                element_type="Building",
                element_id=building.global_id,
                message=(
                    "E013: No building entrance found on ground floor. "
                    "Multi-storey buildings need a main entry."
                ),
            ))

    # W010: Elevator opens directly into apartment (no vestibule)
    # Check if elevator door faces apartment space (not a vestibule/corridor)
    # We validate this by checking that elevator doors face core walls, not apartment boundaries
    # For v2, the enclosed core design prevents this by construction

    # W011: Core > 15% BGF
    if building.stories:
        first_story = building.stories[0]
        building_area = sum(s.area for s in first_story.slabs if s.is_floor)
        if building_area > 0:
            core_area = sum(st.area for st in first_story.staircases)
            # Add elevator area (estimate from walls)
            elev_walls = [w for w in first_story.walls
                          if "elevator" in (w.name or "").lower()]
            if elev_walls:
                elev_xs = []
                elev_ys = []
                for w in elev_walls:
                    elev_xs.extend([w.start.x, w.end.x])
                    elev_ys.extend([w.start.y, w.end.y])
                if elev_xs and elev_ys:
                    core_area += ((max(elev_xs) - min(elev_xs)) *
                                  (max(elev_ys) - min(elev_ys)))

            ratio = core_area / building_area
            if ratio > 0.15:
                errors.append(ValidationError(
                    severity="warning",
                    element_type="Building",
                    element_id=building.global_id,
                    message=(
                        f"W011: Core area ({core_area:.1f}m²) is "
                        f"{ratio*100:.1f}% of BGF ({building_area:.1f}m²) — "
                        f"target is < 15%."
                    ),
                ))

    return errors


# ══════════════════════════════════════════════════════════════════════
# PHASE 3: Corridor Validators
# ══════════════════════════════════════════════════════════════════════

def validate_phase3_corridor(building: Building) -> list[ValidationError]:
    """Phase 3 validators: E020-E023, W020."""
    errors: list[ValidationError] = []

    for story in building.stories:
        # Find corridor walls
        corridor_walls = [w for w in story.walls
                          if "corridor" in (w.name or "").lower()]

        if not corridor_walls and story.apartments:
            # E022 (partial): apartments exist but no corridor
            errors.append(ValidationError(
                severity="error",
                element_type="Story",
                element_id=story.global_id,
                message=(
                    f"E022: Story '{story.name}' has apartments but no "
                    f"corridor walls for access."
                ),
            ))
            continue

        # E021: Corridor width < 1.20m
        south_walls = [w for w in corridor_walls if "south" in (w.name or "").lower()]
        north_walls = [w for w in corridor_walls if "north" in (w.name or "").lower()]

        for sw in south_walls:
            for nw in north_walls:
                # Check matching segments (same east/west designation)
                sw_suffix = (sw.name or "").split()[-1].lower()
                nw_suffix = (nw.name or "").split()[-1].lower()
                if sw_suffix != nw_suffix:
                    continue

                sy = (sw.start.y + sw.end.y) / 2
                ny = (nw.start.y + nw.end.y) / 2
                clear_width = abs(ny - sy) - sw.thickness / 2 - nw.thickness / 2

                if clear_width < MIN_CORRIDOR_WIDTH - 0.01:
                    errors.append(ValidationError(
                        severity="error",
                        element_type="Corridor",
                        element_id=sw.global_id,
                        message=(
                            f"E021: Corridor on '{story.name}' ({sw_suffix}) has "
                            f"clear width {clear_width:.2f}m — minimum is "
                            f"{MIN_CORRIDOR_WIDTH}m."
                        ),
                    ))

        # E022: Apartment has no corridor access
        for apt in story.apartments:
            entry_doors = [d for d in story.doors
                           if apt.name.lower() in (d.name or "").lower()
                           and "entry" in (d.name or "").lower()]
            if not entry_doors:
                errors.append(ValidationError(
                    severity="error",
                    element_type="Apartment",
                    element_id=apt.global_id,
                    message=(
                        f"E022: Apartment '{apt.name}' on '{story.name}' "
                        f"has no entry door from the corridor."
                    ),
                ))

        # W020: Corridor longer than necessary
        # Total corridor length vs. minimum needed to reach apartments
        total_length = sum(w.length for w in corridor_walls) / 2  # Both sides
        if total_length > 0:
            building_width = max(
                (max(w.start.x, w.end.x) for w in story.walls), default=0
            )
            if total_length > building_width * 1.2:
                errors.append(ValidationError(
                    severity="warning",
                    element_type="Story",
                    element_id=story.global_id,
                    message=(
                        f"W020: Corridor on '{story.name}' total length "
                        f"{total_length:.1f}m may be longer than necessary."
                    ),
                ))

        # E023: Corridor must provide continuous access from core to every
        # apartment entry door. If the corridor has gaps (disconnected
        # segments), entries on the wrong side of a gap are unreachable.
        #
        # Algorithm: project all corridor wall x-ranges onto a 1D line,
        # merge into continuous intervals. Core and every entry must be
        # on the same connected interval. Works for axis-aligned corridors.
        if corridor_walls and story.apartments:
            # Build x-intervals from all corridor wall segments
            x_intervals: list[tuple[float, float]] = []
            for w in corridor_walls:
                x_min = min(w.start.x, w.end.x)
                x_max = max(w.start.x, w.end.x)
                if x_max - x_min > 0.01:  # Skip vertical terminators
                    x_intervals.append((x_min, x_max))

            if x_intervals:
                # Merge overlapping/touching intervals
                x_intervals.sort()
                merged: list[list[float]] = [list(x_intervals[0])]
                for lo, hi in x_intervals[1:]:
                    if lo <= merged[-1][1] + 0.1:  # tolerance for touching
                        merged[-1][1] = max(merged[-1][1], hi)
                    else:
                        merged.append([lo, hi])

                # Find core x-position from staircase
                core_x: float | None = None
                if story.staircases:
                    sc = story.staircases[0]
                    verts = sc.outline.vertices
                    core_x = sum(v.x for v in verts) / len(verts)

                # Determine which merged interval the core is on
                core_interval_idx: int | None = None
                if core_x is not None:
                    for idx, (lo, hi) in enumerate(merged):
                        # Core may be slightly outside corridor (adjacent)
                        if lo - 1.0 <= core_x <= hi + 1.0:
                            core_interval_idx = idx
                            break

                # Check each apartment entry door
                corridor_wall_ids = {w.global_id for w in corridor_walls}
                for apt in story.apartments:
                    # Find entry doors for this apartment on corridor walls
                    entry_doors = [
                        d for d in story.doors
                        if d.wall_id in corridor_wall_ids
                        and apt.name.lower() in (d.name or "").lower()
                        and "entry" in (d.name or "").lower()
                    ]

                    for door in entry_doors:
                        host = next(
                            (w for w in story.walls
                             if w.global_id == door.wall_id),
                            None,
                        )
                        if host is None:
                            continue

                        # Door world x-position
                        dx = host.end.x - host.start.x
                        dy = host.end.y - host.start.y
                        length = (dx ** 2 + dy ** 2) ** 0.5
                        door_x = (
                            host.start.x + dx * door.position / length
                            if length > 0
                            else host.start.x
                        )

                        # Which corridor interval is this door on?
                        door_interval_idx: int | None = None
                        for idx, (lo, hi) in enumerate(merged):
                            if lo - 0.1 <= door_x <= hi + 0.1:
                                door_interval_idx = idx
                                break

                        if door_interval_idx is None:
                            errors.append(ValidationError(
                                severity="error",
                                element_type="Apartment",
                                element_id=apt.global_id,
                                message=(
                                    f"E023: Apartment '{apt.name}' entry door "
                                    f"'{door.name}' on '{story.name}' at "
                                    f"x={door_x:.1f}m is outside all corridor "
                                    f"segments — unreachable."
                                ),
                            ))
                        elif (core_interval_idx is not None
                              and door_interval_idx != core_interval_idx):
                            errors.append(ValidationError(
                                severity="error",
                                element_type="Apartment",
                                element_id=apt.global_id,
                                message=(
                                    f"E023: Apartment '{apt.name}' entry door "
                                    f"'{door.name}' on '{story.name}' at "
                                    f"x={door_x:.1f}m is on corridor segment "
                                    f"[{merged[door_interval_idx][0]:.1f}–"
                                    f"{merged[door_interval_idx][1]:.1f}] "
                                    f"disconnected from the core (segment "
                                    f"[{merged[core_interval_idx][0]:.1f}–"
                                    f"{merged[core_interval_idx][1]:.1f}])."
                                ),
                            ))

    return errors


# ══════════════════════════════════════════════════════════════════════
# PHASE 4: Façade Subdivision Validators
# ══════════════════════════════════════════════════════════════════════

def validate_phase4_facade(building: Building) -> list[ValidationError]:
    """Phase 4 validators: E030-E032, W030-W031."""
    errors: list[ValidationError] = []

    for story in building.stories:
        building_width = max(
            (max(w.start.x, w.end.x) for w in story.walls if w.is_external),
            default=0,
        )
        building_depth = max(
            (max(w.start.y, w.end.y) for w in story.walls if w.is_external),
            default=0,
        )
        building_area = building_width * building_depth

        for apt in story.apartments:
            verts = apt.boundary.vertices
            min_x = min(v.x for v in verts)
            max_x = max(v.x for v in verts)
            min_y = min(v.y for v in verts)
            max_y = max(v.y for v in verts)
            apt_width = max_x - min_x
            apt_depth = max_y - min_y

            # E030: Apartment < 6.50m façade (only for 2+ room apartments)
            # Studios (no separate bedroom) don't need 6.5m minimum
            facade_width = apt_width  # Façade = width along exterior wall
            bedrooms_for_facade = apt.get_space_by_type(RoomType.BEDROOM)
            is_studio = len(bedrooms_for_facade) == 0
            if not is_studio and facade_width < MIN_FACADE_2ROOM - 0.01:
                errors.append(ValidationError(
                    severity="error",
                    element_type="Apartment",
                    element_id=apt.global_id,
                    message=(
                        f"E030: Apartment '{apt.name}' has {facade_width:.2f}m "
                        f"façade — minimum for 2-room apartment is "
                        f"{MIN_FACADE_2ROOM}m."
                    ),
                ))

            # E031: Apartment unreachable from corridor/core
            entry_doors = [d for d in story.doors
                           if apt.name.lower() in (d.name or "").lower()
                           and "entry" in (d.name or "").lower()]
            if not entry_doors:
                errors.append(ValidationError(
                    severity="error",
                    element_type="Apartment",
                    element_id=apt.global_id,
                    message=(
                        f"E031: Apartment '{apt.name}' has no entry — "
                        f"unreachable from corridor."
                    ),
                ))

            # W030: Depth:width ratio > 1.5
            if apt_width > 0:
                ratio = apt_depth / apt_width
                if ratio > MAX_ROOM_RATIO:
                    errors.append(ValidationError(
                        severity="warning",
                        element_type="Apartment",
                        element_id=apt.global_id,
                        message=(
                            f"W030: Apartment '{apt.name}' depth:width ratio "
                            f"is {ratio:.2f} (max {MAX_ROOM_RATIO}) — "
                            f"'tunnel' apartment."
                        ),
                    ))

        # W031: Wohnnutzfläche/BGF < 0.65
        if building_area > 0 and story.apartments:
            living_area = sum(apt.area for apt in story.apartments)
            ratio = living_area / building_area
            if ratio < 0.65:
                errors.append(ValidationError(
                    severity="warning",
                    element_type="Story",
                    element_id=story.global_id,
                    message=(
                        f"W031: Story '{story.name}' Wohnnutzfläche/BGF is "
                        f"{ratio:.2f} ({living_area:.1f}m² / {building_area:.1f}m²) "
                        f"— target is ≥ 0.65."
                    ),
                ))

        # E032: Unassigned floor area (šupak detector)
        # Every m² of floor area must belong to either an apartment, the
        # corridor, or the core. Orphaned space is wasted area that
        # belongs to no unit and has no purpose.
        #
        # Algorithm: sample the floor on a grid, check each point against
        # apartment boundaries, corridor zone, and core outlines. Cluster
        # uncovered points into contiguous regions. Flag regions > 1m².
        if building_area > 0 and story.apartments:
            grid_step = 0.5  # 0.5m resolution
            # Build zones to check against
            zones: list[tuple[float, float, float, float]] = []  # (xmin, ymin, xmax, ymax)

            # Apartment boundaries
            for apt in story.apartments:
                av = apt.boundary.vertices
                zones.append((
                    min(v.x for v in av), min(v.y for v in av),
                    max(v.x for v in av), max(v.y for v in av),
                ))

            # Corridor zone: between south and north corridor walls
            corridor_walls = [
                w for w in story.walls
                if "corridor" in (w.name or "").lower()
            ]
            south_cw = [
                w for w in corridor_walls
                if "south" in (w.name or "").lower()
            ]
            north_cw = [
                w for w in corridor_walls
                if "north" in (w.name or "").lower()
            ]
            if south_cw and north_cw:
                cw_y_south = min(
                    min(w.start.y, w.end.y) for w in south_cw
                )
                cw_y_north = max(
                    max(w.start.y, w.end.y) for w in north_cw
                )
                cw_x_min = min(
                    min(w.start.x, w.end.x)
                    for w in south_cw + north_cw
                )
                cw_x_max = max(
                    max(w.start.x, w.end.x)
                    for w in south_cw + north_cw
                )
                zones.append((cw_x_min, cw_y_south, cw_x_max, cw_y_north))

            # Core zone: staircase + elevator outlines
            for sc in story.staircases:
                sv = sc.outline.vertices
                zones.append((
                    min(v.x for v in sv), min(v.y for v in sv),
                    max(v.x for v in sv), max(v.y for v in sv),
                ))

            # Lobby zone (ground floor entrance area)
            # Lobby is between building exterior and lobby walls.
            # Include the area from exterior to the lobby wall boundary,
            # extended up to the corridor/core (vestibule connection).
            lobby_walls = [
                w for w in story.walls
                if "lobby" in (w.name or "").lower()
            ]
            if lobby_walls:
                lx = [c for w in lobby_walls for c in (w.start.x, w.end.x)]
                ly = [c for w in lobby_walls for c in (w.start.y, w.end.y)]
                # Extend to building origin and up to corridor north edge
                lobby_y_max = max(ly)
                if north_cw:
                    lobby_y_max = max(
                        lobby_y_max,
                        max(max(w.start.y, w.end.y) for w in north_cw),
                    )
                zones.append((0, 0, max(lx), lobby_y_max))

            # Also include core walls area (vestibule, divider walls)
            core_walls = [
                w for w in story.walls
                if any(kw in (w.name or "").lower()
                       for kw in CORE_WALL_KEYWORDS)
            ]
            if core_walls:
                core_x = [
                    c for w in core_walls
                    for c in (w.start.x, w.end.x)
                ]
                core_y = [
                    c for w in core_walls
                    for c in (w.start.y, w.end.y)
                ]
                zones.append((
                    min(core_x), min(core_y),
                    max(core_x), max(core_y),
                ))

            # Sample grid and find uncovered points
            uncovered: list[tuple[float, float]] = []
            nx = int(building_width / grid_step)
            ny = int(building_depth / grid_step)
            for ix in range(nx):
                px = ix * grid_step + grid_step / 2
                for iy in range(ny):
                    py = iy * grid_step + grid_step / 2
                    covered = False
                    for zx0, zy0, zx1, zy1 in zones:
                        if zx0 - 0.05 <= px <= zx1 + 0.05 and \
                           zy0 - 0.05 <= py <= zy1 + 0.05:
                            covered = True
                            break
                    if not covered:
                        uncovered.append((px, py))

            # Cluster uncovered points into contiguous regions (simple grid flood-fill)
            if uncovered:
                uncov_set = set(uncovered)
                visited: set[tuple[float, float]] = set()
                regions: list[list[tuple[float, float]]] = []

                for pt in uncovered:
                    if pt in visited:
                        continue
                    # BFS flood fill
                    region: list[tuple[float, float]] = []
                    queue = [pt]
                    while queue:
                        curr = queue.pop()
                        if curr in visited:
                            continue
                        visited.add(curr)
                        region.append(curr)
                        cx, cy = curr
                        for dx, dy in [
                            (grid_step, 0), (-grid_step, 0),
                            (0, grid_step), (0, -grid_step),
                        ]:
                            nb = (round(cx + dx, 2), round(cy + dy, 2))
                            if nb in uncov_set and nb not in visited:
                                queue.append(nb)
                    if region:
                        regions.append(region)

                # Report regions > 1m² (each grid cell = grid_step² = 0.25m²)
                min_region_area = 1.0  # m²
                for region in regions:
                    region_area = len(region) * grid_step * grid_step
                    if region_area >= min_region_area:
                        xs = [p[0] for p in region]
                        ys = [p[1] for p in region]
                        errors.append(ValidationError(
                            severity="error",
                            element_type="Story",
                            element_id=story.global_id,
                            message=(
                                f"E032: Unassigned floor area (šupak) on "
                                f"'{story.name}': ~{region_area:.1f}m² at "
                                f"x={min(xs):.1f}–{max(xs):.1f}, "
                                f"y={min(ys):.1f}–{max(ys):.1f} belongs to "
                                f"no apartment, corridor, or core."
                            ),
                        ))

    return errors


# ══════════════════════════════════════════════════════════════════════
# PHASE 5: Room Subdivision Validators
# ══════════════════════════════════════════════════════════════════════

def validate_phase5_rooms(building: Building) -> list[ValidationError]:
    """Phase 5 validators: E040-E045, W040-W042."""
    errors: list[ValidationError] = []

    for story in building.stories:
        # W046: façade checks need is_external flags; without them E044
        # cannot judge (fail loud instead of flagging every room).
        story_has_external_walls = any(w.is_external for w in story.walls)
        if story.apartments and not story_has_external_walls:
            errors.append(ValidationError(
                severity="warning",
                element_type="Story",
                element_id=story.global_id,
                message=(
                    f"W046: Story '{story.name}' has no walls marked "
                    f"is_external — façade checks (E044) skipped."
                ),
            ))

        for apt in story.apartments:
            # E040: No kitchen
            kitchens = apt.get_space_by_type(RoomType.KITCHEN)
            if not kitchens:
                errors.append(ValidationError(
                    severity="error",
                    element_type="Apartment",
                    element_id=apt.global_id,
                    message=f"E040: Apartment '{apt.name}' has no kitchen.",
                ))

            # E041: No bathroom
            bathrooms = apt.get_space_by_type(RoomType.BATHROOM)
            toilets = apt.get_space_by_type(RoomType.TOILET)
            if not bathrooms and not toilets:
                errors.append(ValidationError(
                    severity="error",
                    element_type="Apartment",
                    element_id=apt.global_id,
                    message=f"E041: Apartment '{apt.name}' has no bathroom.",
                ))

            # E046: No living room — apartment must have at least one
            # habitable main room (living room). An apartment with only
            # service rooms (vorraum, bathroom, storage) is not a dwelling.
            livings = apt.get_space_by_type(RoomType.LIVING)
            if not livings:
                errors.append(ValidationError(
                    severity="error",
                    element_type="Apartment",
                    element_id=apt.global_id,
                    message=(
                        f"E046: Apartment '{apt.name}' has no living room. "
                        f"Every dwelling needs at least one habitable main room."
                    ),
                ))

            # E047: Apartment has no habitable rooms at all — only service
            # rooms (hallway, bathroom, storage, toilet). Not a dwelling!
            habitable_types = {RoomType.LIVING, RoomType.BEDROOM, RoomType.KITCHEN}
            habitable_rooms = [
                sp for sp in apt.spaces if sp.room_type in habitable_types
            ]
            if not habitable_rooms:
                errors.append(ValidationError(
                    severity="error",
                    element_type="Apartment",
                    element_id=apt.global_id,
                    message=(
                        f"E047: Apartment '{apt.name}' has NO habitable rooms — "
                        f"only service rooms ({', '.join(sp.room_type.value for sp in apt.spaces)}). "
                        f"This is not a dwelling."
                    ),
                ))

            # E048: Room outside apartment boundary — space claims to
            # belong to apartment but is physically disconnected (e.g.,
            # storage room across the corridor from the apartment).
            apt_verts_e048 = apt.boundary.vertices
            apt_min_x = min(v.x for v in apt_verts_e048)
            apt_max_x = max(v.x for v in apt_verts_e048)
            apt_min_y = min(v.y for v in apt_verts_e048)
            apt_max_y = max(v.y for v in apt_verts_e048)

            for space in apt.spaces:
                s_verts = space.boundary.vertices
                s_cx = sum(v.x for v in s_verts) / len(s_verts)
                s_cy = sum(v.y for v in s_verts) / len(s_verts)
                # Check if room center is inside apartment bounding box
                # (with tolerance for wall thickness)
                margin = 0.3  # allow for wall thickness
                if (s_cx < apt_min_x - margin or s_cx > apt_max_x + margin or
                        s_cy < apt_min_y - margin or s_cy > apt_max_y + margin):
                    errors.append(ValidationError(
                        severity="error",
                        element_type="Space",
                        element_id=space.global_id,
                        message=(
                            f"E048: Room '{space.name}' ({space.room_type.value}) "
                            f"center at ({s_cx:.1f},{s_cy:.1f}) is outside "
                            f"apartment '{apt.name}' boundary "
                            f"(x={apt_min_x:.1f}→{apt_max_x:.1f}, "
                            f"y={apt_min_y:.1f}→{apt_max_y:.1f}). "
                            f"Room is physically disconnected from apartment."
                        ),
                    ))

            # E042/E043: Bedroom dimensions
            bedrooms = apt.get_space_by_type(RoomType.BEDROOM)
            for i, br in enumerate(bedrooms):
                verts = br.boundary.vertices
                br_min_x = min(v.x for v in verts)
                br_max_x = max(v.x for v in verts)
                br_min_y = min(v.y for v in verts)
                br_max_y = max(v.y for v in verts)
                br_width = br_max_x - br_min_x
                br_depth = br_max_y - br_min_y
                br_area = br.area

                is_master = i == 0 or "master" in (br.name or "").lower()
                min_width = MASTER_BEDROOM_MIN_WIDTH if is_master else CHILD_BEDROOM_MIN_WIDTH
                min_area = MASTER_BEDROOM_MIN_AREA if is_master else CHILD_BEDROOM_MIN_AREA

                # E042: Bedroom width check
                min(br_width, br_depth)  # Shorter dimension
                facade_width = br_width  # Along façade (X axis)
                if facade_width < min_width - 0.01:
                    errors.append(ValidationError(
                        severity="error",
                        element_type="Space",
                        element_id=br.global_id,
                        message=(
                            f"E042: Bedroom '{br.name}' width is "
                            f"{facade_width:.2f}m — minimum is {min_width}m "
                            f"({'master' if is_master else 'child'})."
                        ),
                    ))

                # E043: Bedroom area check
                if br_area < min_area - 0.01:
                    errors.append(ValidationError(
                        severity="error",
                        element_type="Space",
                        element_id=br.global_id,
                        message=(
                            f"E043: Bedroom '{br.name}' area is {br_area:.1f}m² "
                            f"— minimum is {min_area}m² "
                            f"({'master' if is_master else 'child'})."
                        ),
                    ))

            # E044: Habitable room without façade access.
            # A room has façade access iff any axis-aligned edge of its
            # boundary polygon lies along a wall flagged is_external
            # (see specs/facade-detection.md). Skipped (with W046 emitted
            # at story level below) when no walls are flagged external.
            if story_has_external_walls:
                habitable_types = {RoomType.LIVING, RoomType.BEDROOM,
                                   RoomType.KITCHEN}
                for space in apt.spaces:
                    if space.room_type not in habitable_types:
                        continue
                    if not _touches_external_wall(story, space):
                        errors.append(ValidationError(
                            severity="error",
                            element_type="Space",
                            element_id=space.global_id,
                            message=(
                                f"E044: Room '{space.name}' "
                                f"({space.room_type.value}) has no façade "
                                f"access — no boundary edge lies on an "
                                f"external wall."
                            ),
                        ))

            # E045: 2+ bedrooms but no separate WC
            if len(bedrooms) >= 2 and not toilets:
                errors.append(ValidationError(
                    severity="error",
                    element_type="Apartment",
                    element_id=apt.global_id,
                    message=(
                        f"E045: Apartment '{apt.name}' has "
                        f"{len(bedrooms)} bedrooms but no separate WC. "
                        f"Mandatory for 2+ bedroom apartments."
                    ),
                ))

            # W040: Vorraum > 10% of apartment area
            hallways = apt.get_space_by_type(RoomType.HALLWAY)
            vorraum_area = sum(h.area for h in hallways)
            if apt.area > 0 and vorraum_area > apt.area * MAX_VORRAUM_AREA_PCT + 0.01:
                errors.append(ValidationError(
                    severity="warning",
                    element_type="Apartment",
                    element_id=apt.global_id,
                    message=(
                        f"W040: Apartment '{apt.name}' Vorraum area "
                        f"{vorraum_area:.1f}m² is {vorraum_area/apt.area*100:.1f}% "
                        f"of apartment area — target is ≤ 10%."
                    ),
                ))

            # W041: Wet rooms not on same installation shaft
            # Check if bathroom and kitchen share a wall (adjacent)
            if kitchens and bathrooms:
                kitchen = kitchens[0]
                bathroom = bathrooms[0]
                k_verts = kitchen.boundary.vertices
                b_verts = bathroom.boundary.vertices

                k_xs = [v.x for v in k_verts]
                b_xs = [v.x for v in b_verts]
                k_ys = [v.y for v in k_verts]
                b_ys = [v.y for v in b_verts]

                # Check if they share an edge (adjacent)
                shared_x = (
                    abs(max(k_xs) - max(b_xs)) < 0.1 or
                    abs(min(k_xs) - min(b_xs)) < 0.1 or
                    abs(max(k_xs) - min(b_xs)) < 0.1 or
                    abs(min(k_xs) - max(b_xs)) < 0.1
                )
                shared_y = (
                    abs(max(k_ys) - max(b_ys)) < 0.1 or
                    abs(min(k_ys) - min(b_ys)) < 0.1 or
                    abs(max(k_ys) - min(b_ys)) < 0.1 or
                    abs(min(k_ys) - max(b_ys)) < 0.1
                )

                if not (shared_x or shared_y):
                    errors.append(ValidationError(
                        severity="optimization",
                        element_type="Apartment",
                        element_id=apt.global_id,
                        message=(
                            f"O041: Apartment '{apt.name}' wet rooms "
                            f"(kitchen + bathroom) are not on the same "
                            f"installation shaft."
                        ),
                    ))

            # W042: Room aspect ratio check (no tunnels)
            # Only applies to habitable rooms (bedrooms, living rooms).
            # Service rooms (bathrooms, toilets, hallways, etc.) are naturally
            # narrow and excluded from this check.
            for space in apt.spaces:
                if space.room_type in (RoomType.HALLWAY, RoomType.CORRIDOR,
                                       RoomType.STORAGE, RoomType.TOILET,
                                       RoomType.BATHROOM, RoomType.KITCHEN):
                    continue
                s_verts = space.boundary.vertices
                s_w = max(v.x for v in s_verts) - min(v.x for v in s_verts)
                s_h = max(v.y for v in s_verts) - min(v.y for v in s_verts)
                if s_w > 0 and s_h > 0:
                    ratio = max(s_w, s_h) / min(s_w, s_h)
                    narrow_dim = min(s_w, s_h)
                    # Skip tunnel check if narrow dimension ≥ 3.0m —
                    # rooms this wide are usable regardless of ratio
                    # (e.g. 5.7×3.15m studio living room is fine)
                    if ratio > MAX_ROOM_RATIO and narrow_dim < 3.0:
                        errors.append(ValidationError(
                            severity="warning",
                            element_type="Space",
                            element_id=space.global_id,
                            message=(
                                f"W042: Room '{space.name}' aspect ratio is "
                                f"{ratio:.2f} (max {MAX_ROOM_RATIO}) — "
                                f"tunnel-shaped room."
                            ),
                        ))

            # W043: Living room minimum façade width
            # Professional rule: living room needs ≥3.60m façade width for
            # 2-room apartments, ≥4.00m for 3+ room apartments.
            # "Façade width" approximated as the wider dimension of the room
            # (assumes room is oriented with one side along exterior wall).
            living_rooms = [s for s in apt.spaces
                           if s.room_type == RoomType.LIVING and s.boundary]
            bedroom_count = sum(
                1 for s in apt.spaces if s.room_type == RoomType.BEDROOM
            )
            for lr in living_rooms:
                lr_verts = lr.boundary.vertices
                lr_w = max(v.x for v in lr_verts) - min(v.x for v in lr_verts)
                lr_h = max(v.y for v in lr_verts) - min(v.y for v in lr_verts)
                facade_width = max(lr_w, lr_h)
                min_width = 4.00 if bedroom_count >= 2 else 3.60
                label = "3+ room" if bedroom_count >= 2 else "2-room"
                if facade_width < min_width - 0.01:  # 1cm tolerance for FP
                    errors.append(ValidationError(
                        severity="warning",
                        element_type="Space",
                        element_id=lr.global_id,
                        message=(
                            f"W043: Living room '{lr.name}' façade width is "
                            f"{facade_width:.2f}m — minimum {min_width:.2f}m "
                            f"for {label} apartment."
                        ),
                    ))

            # W044: Kitchen minimum width
            # Professional rule: kitchen needs ≥2.20m width for functional
            # two-counter layout (60cm + 100cm passage + 60cm).
            # Better practice: ≥2.40m.
            kitchens = [s for s in apt.spaces
                        if s.room_type == RoomType.KITCHEN and s.boundary]
            for k in kitchens:
                k_verts = k.boundary.vertices
                k_w = max(v.x for v in k_verts) - min(v.x for v in k_verts)
                k_h = max(v.y for v in k_verts) - min(v.y for v in k_verts)
                kitchen_width = min(k_w, k_h)  # narrower dimension
                if kitchen_width < 2.20 - 0.01:  # 1cm tolerance for FP
                    errors.append(ValidationError(
                        severity="warning",
                        element_type="Space",
                        element_id=k.global_id,
                        message=(
                            f"W044: Kitchen '{k.name}' width is "
                            f"{kitchen_width:.2f}m — minimum 2.20m for "
                            f"two-counter layout "
                            f"(60cm counter + 100cm passage + 60cm counter)."
                        ),
                    ))

            # W045: WC (separate toilet) minimum width
            # Professional rule: WC minimum width 90cm.
            # If door is at the front (stirnseitig): minimum 100cm.
            wcs = [s for s in apt.spaces
                   if s.room_type == RoomType.TOILET and s.boundary]
            for wc in wcs:
                wc_verts = wc.boundary.vertices
                wc_w = max(v.x for v in wc_verts) - min(v.x for v in wc_verts)
                wc_h = max(v.y for v in wc_verts) - min(v.y for v in wc_verts)
                wc_width = min(wc_w, wc_h)  # narrower dimension
                if wc_width < 0.90 - 0.01:  # 1cm tolerance for FP
                    errors.append(ValidationError(
                        severity="warning",
                        element_type="Space",
                        element_id=wc.global_id,
                        message=(
                            f"W045: WC '{wc.name}' width is "
                            f"{wc_width:.2f}m — minimum 0.90m "
                            f"(OIB Richtlinie 3)."
                        ),
                    ))

    return errors


# ══════════════════════════════════════════════════════════════════════
# PHASE 5b: Apartment Internal Connectivity (E049)
# ══════════════════════════════════════════════════════════════════════

def validate_apartment_connectivity(building: Building) -> list[ValidationError]:
    """E049: All rooms in an apartment must be internally connected.

    Every room must be reachable from the Vorraum (entry) through internal
    doors OR spatial overlap (open-plan rooms), WITHOUT going through the
    building corridor or exterior.
    A room that is only reachable via the corridor is a 'šupak' — a storage
    closet pretending to be part of the apartment.

    Connectivity is established by:
    1. Doors between rooms (from the storey connectivity graph)
    2. Overlapping/touching boundaries (open-plan layouts, e.g. Wohnküche)
    """
    from archicad_builder.queries.connectivity import build_connectivity_graph

    errors: list[ValidationError] = []

    for story in building.stories:
        if not story.apartments:
            continue

        # Build the connectivity graph for this storey
        graph = build_connectivity_graph(building, story.name)

        for apt in story.apartments:
            if not apt.spaces:
                continue

            # Get the set of room names belonging to this apartment
            apt_room_names = {space.name for space in apt.spaces}

            # Build spatial adjacency: rooms with overlapping boundaries
            # are considered connected (handles open-plan Wohnküche, etc.)
            spatial_neighbors: dict[str, set[str]] = {
                s.name: set() for s in apt.spaces
            }
            spaces_with_bounds = [
                s for s in apt.spaces if s.boundary and s.boundary.vertices
            ]
            for i, s1 in enumerate(spaces_with_bounds):
                for s2 in spaces_with_bounds[i + 1:]:
                    if _boundaries_overlap(s1, s2):
                        spatial_neighbors[s1.name].add(s2.name)
                        spatial_neighbors[s2.name].add(s1.name)

            # Find the entry point (Vorraum/hallway)
            entry_rooms = [
                s.name for s in apt.spaces
                if s.room_type == RoomType.HALLWAY
            ]

            if not entry_rooms:
                # No Vorraum — use any room that connects to the corridor
                # as the starting point
                corridor_nodes = {
                    name for name, node in graph.nodes.items()
                    if node.node_type in ("corridor", "lobby")
                }
                for space in apt.spaces:
                    for neighbor, _ in graph.neighbors(space.name):
                        if neighbor in corridor_nodes:
                            entry_rooms.append(space.name)
                            break
                    if entry_rooms:
                        break

            if not entry_rooms:
                # Can't determine entry point — E082 handles this
                continue

            # BFS from entry room through apartment-internal rooms only.
            # Connectivity via: (a) doors, (b) spatial overlap.
            # Do NOT traverse through corridor, exterior, or other apartments.
            reachable: set[str] = set()
            queue = list(entry_rooms)
            visited = set(entry_rooms)

            while queue:
                current = queue.pop(0)
                reachable.add(current)

                # Door-connected neighbors (from connectivity graph)
                for neighbor, edge in graph.neighbors(current):
                    if neighbor in visited:
                        continue
                    if neighbor in apt_room_names:
                        visited.add(neighbor)
                        queue.append(neighbor)

                # Spatially overlapping neighbors (open-plan)
                for neighbor in spatial_neighbors.get(current, set()):
                    if neighbor in visited:
                        continue
                    visited.add(neighbor)
                    queue.append(neighbor)

            # Check which apartment rooms are NOT reachable internally
            unreachable = apt_room_names - reachable
            for room_name in sorted(unreachable):
                space = next(
                    (s for s in apt.spaces if s.name == room_name), None
                )
                room_type_str = space.room_type.value if space else "unknown"
                errors.append(ValidationError(
                    severity="error",
                    element_type="Space",
                    element_id=space.global_id if space else "",
                    message=(
                        f"E049: Room '{room_name}' ({room_type_str}) in "
                        f"apartment '{apt.name}' on '{story.name}' is not "
                        f"reachable from the entry through internal doors. "
                        f"Room is only accessible via the building corridor "
                        f"(šupak — disconnected room)."
                    ),
                ))

    return errors


def _boundaries_overlap(s1: Space, s2: Space) -> bool:
    """Check if two spaces have overlapping or touching boundaries.

    Two rectangular spaces overlap if their bounding boxes overlap
    (share area) or share an edge (touching boundaries count as
    connected for open-plan layouts).
    """
    v1 = s1.boundary.vertices
    v2 = s2.boundary.vertices

    x1_min = min(v.x for v in v1)
    x1_max = max(v.x for v in v1)
    y1_min = min(v.y for v in v1)
    y1_max = max(v.y for v in v1)

    x2_min = min(v.x for v in v2)
    x2_max = max(v.x for v in v2)
    y2_min = min(v.y for v in v2)
    y2_max = max(v.y for v in v2)

    # Check for overlap or touching (shared edge).
    # Use a small tolerance for floating point comparison.
    eps = 0.01
    overlap_x = x1_min < x2_max + eps and x2_min < x1_max + eps
    overlap_y = y1_min < y2_max + eps and y2_min < y1_max + eps

    return overlap_x and overlap_y


# ══════════════════════════════════════════════════════════════════════
# PHASE 6: Vertical Consistency Validators
# ══════════════════════════════════════════════════════════════════════

def validate_phase6_vertical(building: Building) -> list[ValidationError]:
    """Phase 6 validators: E050-E052, W050."""
    errors: list[ValidationError] = []
    stories = sorted(building.stories, key=lambda s: s.elevation)

    # E062/E063 are per-storey — they must not hide behind the two-storey
    # guard the inter-storey rules need (specs/structural-plausibility.md).
    for story in stories:
        errors.extend(_validate_beams_over_openings(story))

    if len(stories) < 2:
        return errors

    errors.extend(_validate_opening_slab_clash(stories))

    for i in range(1, len(stories)):
        upper = stories[i]
        lower = stories[i - 1]

        # E050: Load-bearing walls must be supported below — but only where
        # the lower storey actually exists. A wall (or portion) outside the
        # lower slab footprint stands on foundations/grade and needs nothing
        # (2026-08-08: the old whole-wall rule force-modeled full basements —
        # villa-maketa grew a 90 m² garage because of it). A lower storey
        # with NO slab geometry falls back to the legacy whole-wall check:
        # missing data must not silently exempt (Codex review 2026-08-08).
        upper_bearing = [w for w in upper.walls if w.load_bearing]
        lower_bearing = [w for w in lower.walls if w.load_bearing]
        footprint = _storey_footprint(lower)

        for wall in upper_bearing:
            if footprint is None:
                if not _has_aligned_wall(wall, lower_bearing, tolerance=0.1):
                    errors.append(ValidationError(
                        severity="error",
                        element_type="Wall",
                        element_id=wall.global_id,
                        message=(
                            f"E050: Load-bearing wall '{wall.name}' on "
                            f"'{upper.name}' has no aligned wall below on "
                            f"'{lower.name}'."
                        ),
                    ))
                continue
            unsupported = _unsupported_length(wall, footprint, lower_bearing)
            if unsupported >= 0.1:
                errors.append(ValidationError(
                    severity="error",
                    element_type="Wall",
                    element_id=wall.global_id,
                    message=(
                        f"E050: Load-bearing wall '{wall.name}' on "
                        f"'{upper.name}' has no aligned wall below on "
                        f"'{lower.name}' ({unsupported:.2f}m over the "
                        f"lower storey lacks support)."
                    ),
                ))

        # E051: Core misaligned between storeys
        upper_stairs = upper.staircases
        lower_stairs = lower.staircases

        for st_u in upper_stairs:
            aligned = False
            for st_l in lower_stairs:
                if _staircases_aligned(st_u, st_l, tolerance=0.1):
                    aligned = True
                    break
            if not aligned and lower_stairs:
                errors.append(ValidationError(
                    severity="error",
                    element_type="Staircase",
                    element_id=st_u.global_id,
                    message=(
                        f"E051: Staircase '{st_u.name}' on '{upper.name}' "
                        f"is not aligned with staircase on '{lower.name}'."
                    ),
                ))

    # W050: Installation shafts not vertically aligned
    # Detect via wet room positions across floors
    for i in range(1, len(stories)):
        upper = stories[i]
        lower = stories[i - 1]

        upper_wet = _get_wet_room_positions(upper)
        lower_wet = _get_wet_room_positions(lower)

        for pos_u in upper_wet:
            has_match = any(
                abs(pos_u[0] - pos_l[0]) < 1.0 and abs(pos_u[1] - pos_l[1]) < 1.0
                for pos_l in lower_wet
            )
            if not has_match and lower_wet:
                errors.append(ValidationError(
                    severity="warning",
                    element_type="Story",
                    element_id=upper.global_id,
                    message=(
                        f"W050: Wet room at ({pos_u[0]:.1f}, {pos_u[1]:.1f}) "
                        f"on '{upper.name}' has no aligned wet room below on "
                        f"'{lower.name}' — installation shaft misalignment."
                    ),
                ))

    return errors


# E052 tolerances: vertical penetration below EPS is contact, and a
# footprint intersection below EPS m² is an edge/vertex touch — both are
# the CORRECT post-flip geometry and must stay legal (specs/storey-datum.md)
_CLASH_EPS = 1e-6


def _validate_opening_slab_clash(
    stories: list[Story],
) -> list[ValidationError]:
    """E052: door/window opening volume clashes with another storey's slab.

    Slabs hang below their storey datum ([elevation − thickness,
    elevation]), so a same-storey clash is geometrically impossible —
    this catches CROSS-storey penetrations (e.g. an upper floor slab
    dipping into a tall ground-floor door). Model-level only: it derives
    slab z the way the exporter does, so exporter regressions are guarded
    by the IFC placement tests, not by this rule.
    """
    errors: list[ValidationError] = []

    slabs: list[tuple[Story, object, float, float, ShapelyPolygon]] = []
    for story in stories:
        for slab in story.slabs:
            poly = ShapelyPolygon(
                [(v.x, v.y) for v in slab.outline.vertices]
            )
            if not poly.is_valid:
                # Polygon2D permits self-intersecting outlines; Shapely's
                # intersection() raises GEOSException on them. Normalize
                # instead of crashing the whole validation run.
                poly = make_valid(poly)
            slabs.append((
                story, slab,
                story.elevation - slab.thickness, story.elevation, poly,
            ))

    for story in stories:
        walls = {w.global_id: w for w in story.walls}
        openings = [
            (d, "Door", story.elevation, story.elevation + d.height)
            for d in story.doors
        ] + [
            (w, "Window",
             story.elevation + w.sill_height,
             story.elevation + w.sill_height + w.height)
            for w in story.windows
        ]
        for elem, element_type, z0, z1 in openings:
            wall = walls.get(elem.wall_id)
            if wall is None or wall.length == 0:
                continue  # dangling wall_id — structural validation owns it
            footprint = _opening_footprint(wall, elem.position, elem.width)
            for slab_story, slab, s0, s1, poly in slabs:
                depth = min(z1, s1) - max(z0, s0)
                if depth <= _CLASH_EPS:
                    continue
                if footprint.intersection(poly).area <= _CLASH_EPS:
                    continue
                errors.append(ValidationError(
                    severity="error",
                    element_type=element_type,
                    element_id=elem.global_id,
                    message=(
                        f"E052: {element_type} '{elem.name}' on "
                        f"'{story.name}' penetrates slab "
                        f"'{slab.name}' of '{slab_story.name}' by "
                        f"{depth:.3f}m — openings must sit clear of "
                        f"slab volumes (specs/storey-datum.md)."
                    ),
                ))

    return errors


def _opening_footprint(
    wall, position: float, width: float
) -> ShapelyPolygon:
    """The opening's plan rectangle: width along the wall axis × full
    wall thickness across it. A wall-CENTERLINE test would miss a slab
    edge that stops between the wall faces (plan review 2026-08-06)."""
    dx = (wall.end.x - wall.start.x) / wall.length
    dy = (wall.end.y - wall.start.y) / wall.length
    nx, ny = -dy, dx
    half_t = wall.thickness / 2
    ax = wall.start.x + dx * position
    ay = wall.start.y + dy * position
    bx = ax + dx * width
    by = ay + dy * width
    return ShapelyPolygon([
        (ax - nx * half_t, ay - ny * half_t),
        (bx - nx * half_t, by - ny * half_t),
        (bx + nx * half_t, by + ny * half_t),
        (ax + nx * half_t, ay + ny * half_t),
    ])


# ── Helpers ───────────────────────────────────────────────────────────

# E063 span/depth limits per material (specs/structural-plausibility.md;
# rc lintel practice ~L/15, steel stiffer per unit depth, timber softer).
_SLENDERNESS_LIMIT = {"rc": 15.0, "steel": 20.0, "timber": 12.0}
_BEAM_MIN_OPENING = 1.25   # m — narrower openings survive a reinforced band
_BEAM_LATERAL_TOL = 0.15   # m off the wall axis
_BEAM_BEARING = 0.10       # m required past each opening edge


def _validate_beams_over_openings(story) -> list[ValidationError]:
    """E062: wide opening on a bearing wall without a covering beam.
    E063: the covering beam is implausibly slender for the clear span.
    (E060/E061 are the core-integrity rules — reusing their prefixes would
    let existing waivers silently suppress beam findings; Codex review.)
    One beam must cover the whole opening — collinear part-beams jointly
    covering are NOT accepted (a ring beam is continuous; Phase A)."""
    errors: list[ValidationError] = []
    walls = {w.global_id: w for w in story.walls}
    openings = [(d, d.height, "Door") for d in story.doors] + [
        (w, w.sill_height + w.height, "Window") for w in story.windows
    ]
    for opening, head, kind in openings:
        wall = walls.get(opening.wall_id)
        if wall is None or not wall.load_bearing:
            continue
        if opening.width < _BEAM_MIN_OPENING:
            continue
        length = math.hypot(wall.end.x - wall.start.x,
                            wall.end.y - wall.start.y)
        if length < 1e-6:
            continue
        ux = (wall.end.x - wall.start.x) / length
        uy = (wall.end.y - wall.start.y) / length
        # opening extent along the wall, extended by the required bearing
        a = opening.position - _BEAM_BEARING
        bpos = opening.position + opening.width + _BEAM_BEARING
        p0 = (wall.start.x + ux * a, wall.start.y + uy * a)
        p1 = (wall.start.x + ux * bpos, wall.start.y + uy * bpos)
        covering = next(
            (bm for bm in story.beams
             if _beam_covers(bm, wall, ux, uy, p0, p1, head)),
            None,
        )
        if covering is None:
            errors.append(ValidationError(
                severity="error",
                element_type=kind,
                element_id=opening.global_id,
                message=(
                    f"E062: Opening '{opening.name}' ({opening.width:.2f}m) "
                    f"on load-bearing wall '{wall.name}' has no beam over "
                    f"it — a {opening.width:.2f}m span cannot ride on the "
                    f"wall band alone."
                ),
            ))
            continue
        limit = _SLENDERNESS_LIMIT[covering.material]
        if opening.width / covering.depth > limit:
            errors.append(ValidationError(
                severity="error",
                element_type="Beam",
                element_id=covering.global_id,
                message=(
                    f"E063: Beam '{covering.name}' over '{opening.name}' is "
                    f"implausibly slender: span/depth "
                    f"{opening.width / covering.depth:.1f} > {limit:.0f} "
                    f"({covering.material})."
                ),
            ))
    return errors


def _beam_covers(beam, wall, ux, uy, p0, p1, head) -> bool:
    """Does `beam` span the opening? Parallel to the wall (±15°), laterally
    within tolerance, both extended endpoints projecting inside the beam
    segment (real end bearing — extended points merely NEAR the beam end
    would fake bearing), wide enough for the wall, above the head."""
    bdx = beam.end.x - beam.start.x
    bdy = beam.end.y - beam.start.y
    blen = math.hypot(bdx, bdy)
    if blen < 1e-6:
        return False
    bux, buy = bdx / blen, bdy / blen
    if abs(ux * buy - uy * bux) > 0.26:  # ~15°, modulo 180 via |cross|
        return False
    # thin walls need a tighter lateral fit: a beam 0.15m off a 0.12m wall
    # misses it entirely (Codex review 2026-08-08)
    lateral_tol = min(_BEAM_LATERAL_TOL, wall.thickness / 2)
    if beam.width < wall.thickness - 0.05:
        return False
    if beam.z_top - beam.depth < head - 0.05:
        return False
    for px, py in (p0, p1):
        rx, ry = px - beam.start.x, py - beam.start.y
        along = rx * bux + ry * buy
        lateral = abs(rx * -buy + ry * bux)
        if lateral > lateral_tol:
            return False
        if along < -1e-6 or along > blen + 1e-6:
            return False
    return True


def validate_structural_loads(building) -> list[ValidationError]:
    """Phase B (specs/structural-plausibility.md): load-based checks.
    E064 rc beam bending util > 1.0; E065 roof slab spanning util > 1.0
    (incl. cantilever and deflection proxy) — only for declared span
    directions; E066 gross wall axial util > 1.0. Unresolved elements
    never error."""
    from archicad_builder.structural import compute_loads

    errors: list[ValidationError] = []
    loads = compute_loads(building)
    for key, data in loads.items():
        if key.startswith("_"):
            continue
        # loads.json keys are GlobalIds; the name is a real field on the
        # record (owner 2026-08-10 — attributes, not key parsing)
        name = data.get("name", key)
        if data["kind"] == "beam" and data["u"] > 1.0:
            errors.append(ValidationError(
                severity="error", element_type="Beam", element_id=key,
                message=(f"E064: Beam '{name}' at {data['u']:.2f} of bending "
                         f"capacity over '{data['over']}' (M {data['M']} kNm)."),
            ))
        elif data["kind"] == "slab" and data["u"] > 1.0:
            what = "cantilever" if data.get("cantilever") else "span"
            errors.append(ValidationError(
                severity="error", element_type="Slab", element_id=key,
                message=(f"E065: Roof slab '{name}' at {data['u']:.2f} of "
                         f"capacity — governing {what} {data['span']}m."),
            ))
        elif data["kind"] == "wall" and data["u"] > 1.0:
            errors.append(ValidationError(
                severity="error", element_type="Wall", element_id=key,
                message=(f"E066: Bearing wall '{name}' at {data['u']:.2f} of "
                         f"gross axial capacity (q {data['q']} kN/m)."),
            ))
    return errors


def validate_seismic(building, site, basis=None) -> list[ValidationError]:
    """S1 seismic plausibility (specs/seismic-lateral.md).

    E100 storey seismic shear > wall shear capacity per direction (error)
    E101 wall density below EN 1998-1 Table 9.3 minimum / URM not
         acceptable at this seismicity (error)
    E102 torsional irregularity e0 > 0.30*r or r < ls (warning)
    E103 lateral discontinuity: bearing wall over the lower storey with
         no bearing wall body under it — same geometry as E050, but a
         gravity waiver (e.g. an engineered transfer beam) does NOT
         restore the seismic shear path, so the codes are waived on
         different grounds (spec decision log)

    No [site] configured -> no findings (unresolved, never guessed).
    """
    if site is None or not building.stories:
        return []
    from archicad_builder.seismic import compute_seismic

    errors: list[ValidationError] = []
    res = compute_seismic(building, site, basis)
    elf_ok = "elf" not in res["_unresolved"]

    for st in res["storeys"]:
        for d in ("x", "y"):
            e = st[d]
            if elf_ok and st["V"] > e["capacity"]:
                errors.append(ValidationError(
                    severity="error", element_type="Story",
                    element_id=st["story_id"],
                    message=(
                        f"E100: Story '{st['story']}' direction {d}: "
                        f"seismic shear demand {st['V']:.0f} kN exceeds "
                        f"wall shear capacity {e['capacity']:.0f} kN — "
                        f"add or lengthen {d}-direction bearing walls."),
                ))
            if not e["acceptable"]:
                errors.append(ValidationError(
                    severity="error", element_type="Story",
                    element_id=st["story_id"],
                    message=(
                        f"E101: Story '{st['story']}' direction {d}: "
                        "unreinforced masonry is not acceptable at this "
                        "seismicity/storey count per EN 1998-1 Table 9.3 "
                        "simple rules — full engineering verification "
                        "required."),
                ))
            elif (e["density_min"] is not None
                    and e["density"] < e["density_min"]):
                errors.append(ValidationError(
                    severity="error", element_type="Story",
                    element_id=st["story_id"],
                    message=(
                        f"E101: Story '{st['story']}' direction {d}: "
                        f"shear wall density {e['density']:.1f}% is below "
                        f"the {e['density_min']:.1f}% minimum "
                        "(EN 1998-1 Table 9.3)."),
                ))
            if (e["e0"] is not None and e["r"] is not None
                    and not e["regular"]):
                errors.append(ValidationError(
                    severity="warning", element_type="Story",
                    element_id=st["story_id"],
                    message=(
                        f"E102: Story '{st['story']}' direction {d} is "
                        f"torsionally irregular: e0 {e['e0']:.2f} m vs "
                        f"0.30*r {0.30 * e['r']:.2f} m, r {e['r']:.2f} m "
                        f"vs ls {e['ls']:.2f} m (EN 1998-1 4.2.3.2) — "
                        "the earthquake will twist this storey."),
                ))

    # E103 — lateral continuity (pure geometry, E050's own helpers)
    stories = sorted(building.stories, key=lambda s: s.elevation)
    for i in range(1, len(stories)):
        upper, lower = stories[i], stories[i - 1]
        lower_bearing = [w for w in lower.walls if w.load_bearing]
        footprint = _storey_footprint(lower)
        if footprint is None:
            continue        # no slab geometry: E050's legacy check owns it
        for wall in upper.walls:
            if not wall.load_bearing:
                continue
            unsupported = _unsupported_length(wall, footprint, lower_bearing)
            if unsupported >= 0.1:
                errors.append(ValidationError(
                    severity="error", element_type="Wall",
                    element_id=wall.global_id,
                    message=(
                        f"E103: Bearing wall '{wall.name}' on "
                        f"'{upper.name}' interrupts the lateral load path "
                        f"({unsupported:.2f}m has no wall below on "
                        f"'{lower.name}') — seismic shear collected above "
                        "cannot reach the ground here."),
                ))
    return errors


def _covering_footing(wall, footings):
    """The footing that carries `wall`: parallel (±15°), transverse
    containment offset + t/2 <= width/2 (Codex plan review — a
    centerline-offset rule alone can leave the wall edge hanging off an
    equal-width footing), and covering the full wall extent. End
    projection past the wall is NOT required — footings meet at corners
    (spec amendment 2026-08-10)."""
    wl = math.hypot(wall.end.x - wall.start.x, wall.end.y - wall.start.y)
    if wl < 1e-6:
        return None
    for f in footings:
        fdx, fdy = f.end.x - f.start.x, f.end.y - f.start.y
        flen = math.hypot(fdx, fdy)
        if flen < 1e-6:
            continue
        ux, uy = fdx / flen, fdy / flen
        wux = (wall.end.x - wall.start.x) / wl
        wuy = (wall.end.y - wall.start.y) / wl
        if abs(ux * wuy - uy * wux) > 0.26:      # ~15 degrees
            continue
        ok = True
        for px, py in ((wall.start.x, wall.start.y),
                       (wall.end.x, wall.end.y)):
            rx, ry = px - f.start.x, py - f.start.y
            along = rx * ux + ry * uy
            offset = abs(-rx * uy + ry * ux)
            if (offset + wall.thickness / 2 > f.width / 2 + 0.01
                    or along < -0.05 or along > flen + 0.05):
                ok = False
                break
        if ok:
            return f
    return None


def validate_foundations(building, site, basis=None) -> list[ValidationError]:
    """S3 foundations (specs/foundations.md). E104 coverage, E105 bearing
    pressure (factored ULS action vs design resistance, DA2-style), E106
    sliding (dead weight only credited as friction), E107 rigid-body
    overturning about the foundation footprint toe. No [site.soil] ->
    unresolved, no findings."""
    if site is None or site.soil is None or not building.stories:
        return []
    from archicad_builder.models.elements import SlabType
    from archicad_builder.seismic import compute_seismic
    from archicad_builder.structural import DesignBasis, compute_loads

    errors: list[ValidationError] = []
    db = DesignBasis()
    stories = sorted(building.stories, key=lambda s: s.elevation)
    lowest = stories[0]
    bearing = [w for w in lowest.walls if w.load_bearing]

    base_polys = []
    for sl in lowest.slabs:
        if sl.slab_type == SlabType.BASESLAB and len(sl.outline.vertices) >= 3:
            p = ShapelyPolygon([(v.x, v.y) for v in sl.outline.vertices])
            base_polys.append(make_valid(p) if not p.is_valid else p)
    base_union = unary_union(base_polys).buffer(0.05) if base_polys else None

    # E104 — every bearing wall on the lowest storey needs a footing
    covered: dict[str, object] = {}
    for w in bearing:
        line = ShapelyLine([(w.start.x, w.start.y), (w.end.x, w.end.y)])
        if base_union is not None and base_union.covers(line):
            continue        # slab-on-grade grounds it, as the FEM assumes
        f = _covering_footing(w, lowest.footings)
        if f is None:
            errors.append(ValidationError(
                severity="error", element_type="Wall",
                element_id=w.global_id,
                message=(
                    f"E104: Bearing wall '{w.name}' on '{lowest.name}' has "
                    "no covering strip footing (and no base slab under "
                    "it) — its load ends in nothing."),
            ))
        else:
            covered.setdefault(f.global_id, []).append(w)

    # E105 — factored bearing pressure vs design resistance
    loads = compute_loads(building)
    wall_cap = {w.global_id: w.thickness * db.wall_phi * db.wall_fd
                for w in bearing}
    for f in lowest.footings:
        walls = covered.get(f.global_id, [])
        q_max = 0.0
        for w in walls:
            rec = loads.get(w.global_id)
            if rec and rec.get("profile"):
                q_max = max(q_max,
                            max(rec["profile"]) * wall_cap[w.global_id])
        self_w = db.gamma_g * f.width * f.height * db.rc_density  # kN/m
        pressure = (q_max + self_w) / f.width
        if pressure > site.soil.sigma_rd:
            errors.append(ValidationError(
                severity="error", element_type="Footing",
                element_id=f.global_id,
                message=(
                    f"E105: Footing '{f.name}' bears {pressure:.0f} kPa "
                    f"(worst station, ULS) > sigma_rd "
                    f"{site.soil.sigma_rd:.0f} kPa — widen the footing "
                    "or confirm better soil."),
            ))

    # E106/E107 — base shear into the ground
    seis = compute_seismic(building, site, basis)
    foot_dead = sum(
        math.hypot(f.end.x - f.start.x, f.end.y - f.start.y)
        * f.width * f.height * db.rc_density for f in lowest.footings)
    n_dead = seis["dead_total"] + foot_dead
    fb = seis["Fb"]
    mu = site.soil.friction_mu
    for d in ("x", "y"):
        if fb > mu * n_dead:
            errors.append(ValidationError(
                severity="error", element_type="Building",
                element_id=lowest.global_id,
                message=(
                    f"E106: direction {d}: seismic base shear {fb:.0f} kN "
                    f"exceeds sliding friction mu*G = {mu:.2f} * "
                    f"{n_dead:.0f} = {mu * n_dead:.0f} kN (dead weight "
                    "only credited; passive earth pressure ignored)."),
            ))

    geoms = [ShapelyLine([(f.start.x, f.start.y), (f.end.x, f.end.y)])
             .buffer(f.width / 2, cap_style=2) for f in lowest.footings]
    if base_union is not None:
        geoms.append(base_union)
    if geoms:
        hull = unary_union(geoms)
        minx, miny, maxx, maxy = hull.bounds
        m_ot = sum(frc["F"] * (frc["z"] - seis["base"])
                   for frc in seis["forces"])
        com = seis["com"]
        for d, lo, hi, c in (("x", minx, maxx, com[0]),
                             ("y", miny, maxy, com[1])):
            arm = min(c - lo, hi - c)
            if arm <= 0 or m_ot <= 0:
                continue
            ratio = n_dead * arm / m_ot
            if ratio < 1.1:
                errors.append(ValidationError(
                    severity="error", element_type="Building",
                    element_id=lowest.global_id,
                    message=(
                        f"E107: direction {d}: rigid-body overturning "
                        f"ratio {ratio:.2f} < 1.1 (stabilizing "
                        f"{n_dead:.0f} kN x {arm:.2f} m vs overturning "
                        f"{m_ot:.0f} kNm) — the building tips before it "
                        "slides."),
                ))
    elif bearing:
        # no footings and no base slab: E104 already fired per wall;
        # sliding was still checkable, overturning was not
        pass
    return errors


def _storey_footprint(story):
    """Union of a storey's slab outlines, mitre-buffered 0.05m so a wall
    centerline riding the slab edge still counts as inside. None when the
    storey has no valid slab geometry (caller falls back to legacy check)."""
    polys = []
    for slab in story.slabs:
        if len(slab.outline.vertices) < 3:
            continue
        p = ShapelyPolygon([(v.x, v.y) for v in slab.outline.vertices])
        if not p.is_valid:
            p = make_valid(p)
        if not p.is_empty:
            polys.append(p)
    if not polys:
        return None
    return unary_union(polys).buffer(0.05, join_style=2)


def _unsupported_length(wall, footprint, lower_bearing) -> float:
    """Longest contiguous run of `wall`'s centerline that lies over the
    lower footprint without a parallel load-bearing wall body under it.
    Parallel filter + flat-cap thickness buffers per Codex review
    2026-08-08 — round caps would fake ~15cm of support past wall ends,
    and perpendicular crossings are not support."""
    line = ShapelyLine([(wall.start.x, wall.start.y), (wall.end.x, wall.end.y)])
    if line.length < 1e-6:
        return 0.0
    inside = line.intersection(footprint)
    if inside.is_empty or inside.length < 0.1:
        return 0.0  # on grade
    ux = (wall.end.x - wall.start.x) / line.length
    uy = (wall.end.y - wall.start.y) / line.length
    supports = []
    for other in lower_bearing:
        seg = ShapelyLine([(other.start.x, other.start.y),
                           (other.end.x, other.end.y)])
        if seg.length < 1e-6:
            continue
        ox = (other.end.x - other.start.x) / seg.length
        oy = (other.end.y - other.start.y) / seg.length
        if abs(ux * oy - uy * ox) > 0.26:  # ~15 degrees off parallel
            continue
        supports.append(seg.buffer(other.thickness / 2 + 0.1, cap_style=2))
    uncovered = inside.difference(unary_union(supports)) if supports else inside
    if uncovered.is_empty:
        return 0.0
    pieces = getattr(uncovered, "geoms", [uncovered])
    return max((g.length for g in pieces), default=0.0)


def _has_aligned_wall(wall, candidates: list, tolerance: float) -> bool:
    """Check if a wall has a vertically aligned counterpart."""
    for other in candidates:
        if (_points_close(wall.start, other.start, tolerance)
                and _points_close(wall.end, other.end, tolerance)):
            return True
        if (_points_close(wall.start, other.end, tolerance)
                and _points_close(wall.end, other.start, tolerance)):
            return True
    return False


def _points_close(p1: Point2D, p2: Point2D, tolerance: float) -> bool:
    """Check if two points are within tolerance."""
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2) <= tolerance


def _staircases_aligned(st1, st2, tolerance: float) -> bool:
    """Check if two staircases are at the same XY position."""
    c1 = _polygon_center(st1.outline)
    c2 = _polygon_center(st2.outline)
    return _points_close(c1, c2, tolerance)


def _polygon_center(poly) -> Point2D:
    """Calculate center of a polygon."""
    xs = [v.x for v in poly.vertices]
    ys = [v.y for v in poly.vertices]
    return Point2D(x=sum(xs) / len(xs), y=sum(ys) / len(ys))


def _get_wet_room_positions(story: Story) -> list[tuple[float, float]]:
    """Get center positions of wet rooms on a storey."""
    positions = []
    for apt in story.apartments:
        for space in apt.spaces:
            if space.room_type in (RoomType.BATHROOM, RoomType.TOILET, RoomType.KITCHEN):
                c = _polygon_center(space.boundary)
                positions.append((c.x, c.y))
    return positions


# ══════════════════════════════════════════════════════════════════════
# v3 VALIDATORS: Core Integrity
# ══════════════════════════════════════════════════════════════════════

def _is_core_wall(wall) -> bool:
    """Check if a wall is part of the core (elevator, staircase, vestibule)."""
    name = (wall.name or "").lower()
    return any(kw in name for kw in CORE_WALL_KEYWORDS)


def validate_core_integrity(building: Building) -> list[ValidationError]:
    """v3 validators: E060, E061, W060 — core wall integrity.

    E060: Door on core wall wider than 1.20m → ERROR
    E061: Window on core/staircase wall → ERROR
    W060: Any door in the building wider than 1.20m → WARNING
    """
    errors: list[ValidationError] = []

    for story in building.stories:
        # Build set of core wall IDs
        core_wall_ids = set()
        for wall in story.walls:
            if _is_core_wall(wall):
                core_wall_ids.add(wall.global_id)

        # E060: Core wall doors must be ≤ 1.20m
        for door in story.doors:
            if door.wall_id in core_wall_ids and door.width > MAX_CORE_OPENING + 0.01:
                errors.append(ValidationError(
                    severity="error",
                    element_type="Door",
                    element_id=door.global_id,
                    message=(
                        f"E060: Door '{door.name}' on core wall has "
                        f"width {door.width:.2f}m — maximum for fire-rated "
                        f"core opening is {MAX_CORE_OPENING}m."
                    ),
                ))

        # E061: No windows on core walls
        for window in story.windows:
            if window.wall_id in core_wall_ids:
                # Find wall name for error message
                wall_name = "unknown"
                for w in story.walls:
                    if w.global_id == window.wall_id:
                        wall_name = w.name or "unnamed"
                        break
                errors.append(ValidationError(
                    severity="error",
                    element_type="Window",
                    element_id=window.global_id,
                    message=(
                        f"E061: Window '{window.name}' found on core wall "
                        f"'{wall_name}' — core walls must be solid "
                        f"(fire-rated, no windows)."
                    ),
                ))

        # W060: Any door wider than 1.20m is suspicious
        for door in story.doors:
            if door.width > MAX_SUSPICIOUS_DOOR + 0.01:
                errors.append(ValidationError(
                    severity="warning",
                    element_type="Door",
                    element_id=door.global_id,
                    message=(
                        f"W060: Door '{door.name}' on '{story.name}' has "
                        f"width {door.width:.2f}m — unusually wide "
                        f"(standard max is {MAX_SUSPICIOUS_DOOR}m). "
                        f"Check if this is intentional."
                    ),
                ))

    return errors


# ══════════════════════════════════════════════════════════════════════
# v3 VALIDATORS: Interior Enclosure
# ══════════════════════════════════════════════════════════════════════

def validate_interior_enclosure(building: Building) -> list[ValidationError]:
    """v3 validators: E070, E071, E041b — room enclosure and sizing.

    E070: Room that should be enclosed has no door → ERROR
          (checks bathroom, bedroom — they MUST have a door)
    E071: Bathroom not enclosed by walls → ERROR
          (checks that bathroom space has walls on its boundaries)
    E041b: Bathroom < 5m² → WARNING (adaptable housing)
    """
    errors: list[ValidationError] = []

    for story in building.stories:
        for apt in story.apartments:
            # Collect all doors in this apartment's area
            apt_verts = apt.boundary.vertices
            min(v.x for v in apt_verts)
            max(v.x for v in apt_verts)
            min(v.y for v in apt_verts)
            max(v.y for v in apt_verts)

            # Find doors whose names match this apartment
            apt_doors = [
                d for d in story.doors
                if apt.name.lower() in (d.name or "").lower()
            ]
            apt_door_names = {(d.name or "").lower() for d in apt_doors}

            # E070: Rooms that need doors
            for space in apt.spaces:
                if space.room_type in (RoomType.BEDROOM, RoomType.BATHROOM,
                                       RoomType.TOILET):
                    room_type_str = space.room_type.value
                    # Check if there's a door named after this room
                    has_door = any(
                        room_type_str in name or
                        space.name.lower().split()[-1] in name
                        for name in apt_door_names
                    )
                    if not has_door:
                        errors.append(ValidationError(
                            severity="error",
                            element_type="Space",
                            element_id=space.global_id,
                            message=(
                                f"E070: Room '{space.name}' ({room_type_str}) "
                                f"on '{story.name}' has no door. "
                                f"Every enclosed room needs a door for access."
                            ),
                        ))

            # E071: Bathroom must be enclosed by walls
            bathrooms = apt.get_space_by_type(RoomType.BATHROOM)
            for bath in bathrooms:
                b_verts = bath.boundary.vertices
                b_min_x = min(v.x for v in b_verts)
                b_max_x = max(v.x for v in b_verts)
                b_min_y = min(v.y for v in b_verts)
                b_max_y = max(v.y for v in b_verts)

                # Check each edge of the bathroom for a wall
                edges = [
                    ("south", b_min_y, b_min_x, b_max_x, "horizontal"),
                    ("north", b_max_y, b_min_x, b_max_x, "horizontal"),
                    ("west", b_min_x, b_min_y, b_max_y, "vertical"),
                    ("east", b_max_x, b_min_y, b_max_y, "vertical"),
                ]

                missing_walls = []
                for edge_name, coord, start, end, orientation in edges:
                    has_wall = _edge_has_wall(
                        story, coord, start, end, orientation, tolerance=0.2
                    )
                    if not has_wall:
                        missing_walls.append(edge_name)

                if missing_walls:
                    errors.append(ValidationError(
                        severity="error",
                        element_type="Space",
                        element_id=bath.global_id,
                        message=(
                            f"E071: Bathroom '{bath.name}' on '{story.name}' "
                            f"is not fully enclosed — missing wall(s) on: "
                            f"{', '.join(missing_walls)}. "
                            f"Bathrooms must be walled off for privacy/plumbing."
                        ),
                    ))

            # E041b: Bathroom area check
            for bath in bathrooms:
                if bath.area < MIN_BATHROOM_AREA - 0.01:
                    errors.append(ValidationError(
                        severity="warning",
                        element_type="Space",
                        element_id=bath.global_id,
                        message=(
                            f"E041b: Bathroom '{bath.name}' area is "
                            f"{bath.area:.1f}m² — minimum for adaptable "
                            f"housing is {MIN_BATHROOM_AREA}m² (OIB)."
                        ),
                    ))

    return errors


def _touches_external_wall(
    story: Story,
    space,
    tolerance: float = 0.2,
    min_overlap: float = 0.01,
) -> bool:
    """True iff any axis-aligned edge of the space boundary lies along an
    external wall (specs/facade-detection.md).

    Unlike _edge_has_wall this requires the wall itself to be axis-aligned in
    the edge's direction, filters to is_external walls, and accepts any
    positive overlap (an L-notch segment may cover well under 50% of an edge).
    """
    verts = space.boundary.vertices
    n = len(verts)
    for i in range(n):
        a, b = verts[i], verts[(i + 1) % n]  # includes the closing edge
        if abs(a.y - b.y) < 1e-6:  # horizontal edge
            lo, hi = sorted((a.x, b.x))
            for w in story.walls:
                if not w.is_external:
                    continue
                if abs(w.start.y - w.end.y) > 1e-6:  # wall not horizontal
                    continue
                if abs(w.start.y - a.y) > tolerance:
                    continue
                w_lo, w_hi = sorted((w.start.x, w.end.x))
                if min(hi, w_hi) - max(lo, w_lo) > min_overlap:
                    return True
        elif abs(a.x - b.x) < 1e-6:  # vertical edge
            lo, hi = sorted((a.y, b.y))
            for w in story.walls:
                if not w.is_external:
                    continue
                if abs(w.start.x - w.end.x) > 1e-6:  # wall not vertical
                    continue
                if abs(w.start.x - a.x) > tolerance:
                    continue
                w_lo, w_hi = sorted((w.start.y, w.end.y))
                if min(hi, w_hi) - max(lo, w_lo) > min_overlap:
                    return True
        # diagonal edges: out of scope (repo is axis-aligned throughout)
    return False


def _edge_has_wall(
    story: Story,
    coord: float,
    start: float,
    end: float,
    orientation: str,
    tolerance: float = 0.2,
) -> bool:
    """Check if there's a wall along a given edge.

    For horizontal edges: checks walls at y=coord spanning from start_x to end_x.
    For vertical edges: checks walls at x=coord spanning from start_y to end_y.
    """
    for wall in story.walls:
        if orientation == "horizontal":
            # Wall must be roughly horizontal at the given y coordinate
            wall_y = (wall.start.y + wall.end.y) / 2
            if abs(wall_y - coord) > tolerance:
                continue
            # Check if wall spans the required range
            wall_min_x = min(wall.start.x, wall.end.x)
            wall_max_x = max(wall.start.x, wall.end.x)
            # Wall should cover at least 50% of the edge
            overlap_start = max(wall_min_x, start)
            overlap_end = min(wall_max_x, end)
            edge_length = end - start
            if edge_length > 0 and (overlap_end - overlap_start) / edge_length >= 0.5:
                return True
        else:
            # Wall must be roughly vertical at the given x coordinate
            wall_x = (wall.start.x + wall.end.x) / 2
            if abs(wall_x - coord) > tolerance:
                continue
            wall_min_y = min(wall.start.y, wall.end.y)
            wall_max_y = max(wall.start.y, wall.end.y)
            overlap_start = max(wall_min_y, start)
            overlap_end = min(wall_max_y, end)
            edge_length = end - start
            if edge_length > 0 and (overlap_end - overlap_start) / edge_length >= 0.5:
                return True

    return False


# ══════════════════════════════════════════════════════════════════════
# OPTIMIZATION VALIDATORS
# ══════════════════════════════════════════════════════════════════════

def validate_optimizations(building: Building) -> list[ValidationError]:
    """Optimization-level validators: layout improvements, not code violations."""
    errors: list[ValidationError] = []
    errors.extend(_validate_dead_end_corridors(building))
    errors.extend(_validate_windowless_alcoves(building))
    return errors


def _validate_dead_end_corridors(building: Building) -> list[ValidationError]:
    """O001: Flag corridor sections that extend past the last door (dead-ends).

    Dead-end corridors waste floor area that could be annexed to apartments.
    """
    errors: list[ValidationError] = []

    for story in building.stories:
        # Find corridor walls (come in pairs: south + north)
        corridor_walls = [w for w in story.walls if "corridor" in w.name.lower()]
        if not corridor_walls:
            continue

        # Group corridor wall pairs by segment (west/east/core)
        for cw in corridor_walls:
            # Skip core corridor segment — it connects to the core, not apartments
            if "core" in cw.name.lower():
                continue

            cw_start_x = min(cw.start.x, cw.end.x)
            cw_end_x = max(cw.start.x, cw.end.x)

            # Find entry doors on this corridor wall
            door_positions = []
            for door in story.doors:
                if door.wall_id == cw.global_id and "entry" in door.name.lower():
                    door_positions.append(door.position)

            if not door_positions:
                continue

            cw_length = ((cw.end.x - cw.start.x)**2 + (cw.end.y - cw.start.y)**2)**0.5
            if cw_length < 0.01:
                continue

            # Direction vector
            dx = (cw.end.x - cw.start.x) / cw_length
            (cw.end.y - cw.start.y) / cw_length

            # Convert door positions to world x coordinates
            door_world_xs = []
            for pos in door_positions:
                world_x = cw.start.x + dx * pos
                door_world_xs.append(world_x)

            # Find the extent of doors (min and max x positions including door width)
            min_door_x = min(door_world_xs)
            max_door_x = max(door_world_xs)

            # Check for dead-end at start of wall (before first door)
            dead_start = min_door_x - cw_start_x
            if dead_start > 1.0:  # More than 1m of dead corridor
                dead_area = dead_start * 1.5  # corridor width ~1.5m
                errors.append(ValidationError(
                    severity="optimization",
                    element_type="Wall",
                    element_id=cw.global_id,
                    message=(
                        f"O001: Dead-end corridor on '{cw.name}': "
                        f"{dead_start:.1f}m before first door "
                        f"(~{dead_area:.1f}m² wasted). "
                        f"Could be annexed to adjacent apartment."
                    ),
                ))

            # Check for dead-end at end of wall (after last door)
            # Need to account for door width (~0.9m)
            max_door_end_x = max_door_x + 0.9  # approximate door width
            dead_end = cw_end_x - max_door_end_x
            if dead_end > 1.0:
                dead_area = dead_end * 1.5
                errors.append(ValidationError(
                    severity="optimization",
                    element_type="Wall",
                    element_id=cw.global_id,
                    message=(
                        f"O001: Dead-end corridor on '{cw.name}': "
                        f"{dead_end:.1f}m after last door "
                        f"(~{dead_area:.1f}m² wasted). "
                        f"Could be annexed to adjacent apartment."
                    ),
                ))

    return errors


def _validate_windowless_alcoves(building: Building) -> list[ValidationError]:
    """O002: Flag L-shaped rooms where the alcove has no window.

    Detects rooms with non-rectangular boundaries (>4 vertices) where
    part of the room is likely an alcove without natural light.
    """
    errors: list[ValidationError] = []

    for story in building.stories:
        # Collect exterior wall segments for window/light check
        exterior_edges: list[tuple[float, float, float, float]] = []
        for wall in story.walls:
            if wall.is_external:
                exterior_edges.append((
                    wall.start.x, wall.start.y,
                    wall.end.x, wall.end.y,
                ))

        for apt in story.apartments:
            for space in apt.spaces:
                # Only check habitable rooms (living, bedroom)
                if space.room_type not in (RoomType.LIVING, RoomType.BEDROOM):
                    continue

                verts = space.boundary.vertices
                if len(verts) <= 4:
                    continue  # Rectangle — no alcove

                # L-shaped room detected (>4 vertices)
                # Find the bounding box
                xs = [v.x for v in verts]
                ys = [v.y for v in verts]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)
                bbox_area = (max_x - min_x) * (max_y - min_y)
                actual_area = space.boundary.area

                # If actual area is significantly less than bbox, it's L-shaped
                if actual_area < bbox_area * 0.95:
                    # Check if all edges of the room touch exterior walls
                    # (simplified: check if room has windows)
                    room_windows = []
                    for wall in story.walls:
                        if not wall.is_external:
                            continue
                        for win in story.windows:
                            if win.wall_id != wall.global_id:
                                continue
                            # Check if window is within room's x/y range
                            w_len = ((wall.end.x - wall.start.x)**2 +
                                     (wall.end.y - wall.start.y)**2)**0.5
                            if w_len < 0.01:
                                continue
                            ratio = win.position / w_len
                            win_x = wall.start.x + (wall.end.x - wall.start.x) * ratio
                            win_y = wall.start.y + (wall.end.y - wall.start.y) * ratio
                            if (min_x - 0.5 <= win_x <= max_x + 0.5 and
                                    min_y - 0.5 <= win_y <= max_y + 0.5):
                                room_windows.append(win.name)

                    alcove_area = bbox_area - actual_area
                    errors.append(ValidationError(
                        severity="optimization",
                        element_type="Space",
                        element_id=space.global_id,
                        message=(
                            f"O002: L-shaped room '{space.name}' in '{apt.name}' "
                            f"({len(verts)} vertices, {actual_area:.1f}m² of "
                            f"{bbox_area:.1f}m² bbox). Alcove ~{alcove_area:.1f}m² "
                            f"may lack natural light. Consider converting to "
                            f"Abstellraum (storage) or redesigning layout."
                        ),
                    ))

    return errors
