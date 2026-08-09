"""IFC export via ifcopenshell.

Converts Pydantic building models to IFC 2x3 format for ArchiCAD import.
Focuses on correct geometry and proper IFC hierarchy.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid

from archicad_builder.models.building import Building, Story
from archicad_builder.models.elements import (
    Door,
    Roof,
    Slab,
    Staircase,
    VirtualElement,
    Wall,
    Window,
)
from archicad_builder.models.ifc_id import derived_ifc_id
from archicad_builder.models.spaces import Space
from archicad_builder.queries.connectivity import _point_in_polygon

# Header timestamp when SOURCE_DATE_EPOCH is unset. Frozen so an unchanged
# building exports an unchanged file (specs/ifc-identity.md) — the wall
# clock in here was 100% of the reason two exports never matched.
PINNED_TIME = "2026-01-01T00:00:00"


def _wall_direction(wall: Wall) -> tuple[float, float]:
    """Unit direction vector of a wall."""
    dx = wall.end.x - wall.start.x
    dy = wall.end.y - wall.start.y
    length = wall.length
    return (dx / length, dy / length)


def _wall_normal(wall: Wall) -> tuple[float, float]:
    """Left-hand normal of wall direction (for thickness offset)."""
    dx, dy = _wall_direction(wall)
    return (-dy, dx)


# Window infill depth (specs/window-glazing-placement.md). The wall opening
# still cuts the full thickness; only the glazing pane is thin.
WINDOW_PANE_DEPTH = 0.06


def _exterior_at_local_y_zero(wall: Wall, story: Story) -> bool:
    """True if the wall face at window-local y=0 (the −normal face) is the
    exterior one.

    Primary test: probe a point just beyond each face against the story's
    floor slabs — the face NOT over a floor is exterior. A bbox-centroid
    heuristic alone flips sides on concave (L/U) footprints, where the bbox
    center can fall outside the building (Gemini review 2026-08-06).
    Fallback (no floor slabs, or both/neither face over one — e.g. a wall
    between a room and a deck slab): the face pointing away from the center
    of the story's wall-endpoint bounding box.
    """
    nx, ny = _wall_normal(wall)
    mx = (wall.start.x + wall.end.x) / 2
    my = (wall.start.y + wall.end.y) / 2

    floors = [
        [(v.x, v.y) for v in s.outline.vertices]
        for s in story.slabs
        if s.is_floor
    ]
    if floors:
        off = wall.thickness / 2 + 0.05

        def over_floor(px: float, py: float) -> bool:
            return any(_point_in_polygon(px, py, verts) for verts in floors)

        neg_side = over_floor(mx - nx * off, my - ny * off)
        pos_side = over_floor(mx + nx * off, my + ny * off)
        if neg_side != pos_side:
            return not neg_side

    xs = [p for w in story.walls for p in (w.start.x, w.end.x)]
    ys = [p for w in story.walls for p in (w.start.y, w.end.y)]
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    return (mx - cx) * -nx + (my - cy) * -ny >= 0


def _corner_extensions(wall: Wall, story: Story) -> tuple[float, float]:
    """Lengthwise extensions (at start, at end) closing L-corner gaps
    (specs/wall-corner-joins.md).

    A wall end that coincides with a NON-parallel wall's endpoint extends
    by the largest such partner's half-thickness; both corner walls extend
    and overlap in the corner cube. Parallel partners (collinear splits)
    never extend — they butt flush, and overlapping them would z-fight
    coplanar faces.
    """
    tol = 1e-6
    dx, dy = _wall_direction(wall)

    def extension_at(px: float, py: float) -> float:
        ext = 0.0
        for other in story.walls:
            if other is wall:
                continue
            odx, ody = _wall_direction(other)
            if abs(dx * ody - dy * odx) < 1e-9:  # parallel
                continue
            for p in (other.start, other.end):
                if abs(p.x - px) < tol and abs(p.y - py) < tol:
                    ext = max(ext, other.thickness / 2)
        return ext

    return (
        extension_at(wall.start.x, wall.start.y),
        extension_at(wall.end.x, wall.end.y),
    )


def _corner_glazing(
    window: Window | Door, wall: Wall, story: Story
) -> tuple[float, float, list[Wall]]:
    """(lead_ext, trail_ext, partner_walls) for corner glazing
    (specs/wall-corner-joins.md).

    A window flush with a wall end that has a corner join extends through
    the joint — pane and opening grow by the corner extension, and the
    opening must ALSO void each partner wall, whose own solid (with its
    corner extension) crosses the glazing zone. Without that second void
    the joint stays filled and the "corner window" hits a hidden post.
    """
    tol = 1e-6
    ext_start, ext_end = _corner_extensions(wall, story)
    lead = ext_start if window.position <= tol else 0.0
    trail = (
        ext_end
        if abs(wall.length - (window.position + window.width)) <= tol
        else 0.0
    )
    partners: list[Wall] = []
    if lead or trail:
        dx, dy = _wall_direction(wall)
        for other in story.walls:
            if other is wall:
                continue
            odx, ody = _wall_direction(other)
            if abs(dx * ody - dy * odx) < 1e-9:  # parallel — no corner
                continue
            for p in (other.start, other.end):
                at_start = abs(p.x - wall.start.x) < tol and abs(p.y - wall.start.y) < tol
                at_end = abs(p.x - wall.end.x) < tol and abs(p.y - wall.end.y) < tol
                if (lead and at_start) or (trail and at_end):
                    partners.append(other)
                    break
    return lead, trail, partners


def _pane_extensions(
    window: Window | Door, wall: Wall, story: Story
) -> tuple[float, float]:
    """Pane lengthwise extensions (at start, at end) for corner glazing —
    for windows AND glass doors (pane_side set).

    Glass meeting a SOLID partner wall end runs through the joint to its
    face (the full corner extension). Two flush panes sharing one corner
    must TOUCH, not cross (owner feedback #002 — crossing boxes read as
    glass-through-glass): the pane on the lexicographically smaller wall
    GlobalId passes (covers the corner, ext = pane depth − partner t/2),
    the other butts against its face (ext = −partner t/2). Partner panes
    include flush glass doors (Gemini review 2026-08-06). Exact for the
    inner-flush pane pair; mixed inner/outer corners would need per-side
    planes (no case yet).
    """
    tol = 1e-6
    lead, trail, _ = _corner_glazing(window, wall, story)
    dx, dy = _wall_direction(wall)
    my_side = window.pane_side or "outer"

    def z_span(el) -> tuple[float, float]:
        lo = getattr(el, "sill_height", 0.0)
        return lo, lo + el.height

    def z_overlaps(a, b) -> bool:
        a0, a1 = z_span(a)
        b0, b1 = z_span(b)
        return a0 < b1 - tol and b0 < a1 - tol

    def partner_flush(el, other: Wall, px: float, py: float) -> bool:
        if abs(other.start.x - px) < tol and abs(other.start.y - py) < tol:
            return el.position <= tol
        if abs(other.end.x - px) < tol and abs(other.end.y - py) < tol:
            return abs(other.length - (el.position + el.width)) <= tol
        return False

    def adjust(ext: float, px: float, py: float) -> float:
        if not ext:
            return 0.0
        panes = list(story.windows) + [
            d for d in story.doors if d.pane_side is not None
        ]
        # All flush partner panes at this corner that share a height band —
        # vertically disjoint panes never meet (Codex review 2026-08-06).
        candidates = []
        for other in story.walls:
            if other is wall:
                continue
            odx, ody = _wall_direction(other)
            if abs(dx * ody - dy * odx) < 1e-9:  # parallel — no corner
                continue
            if not any(
                abs(p.x - px) < tol and abs(p.y - py) < tol
                for p in (other.start, other.end)
            ):
                continue
            for el in panes:
                if (el is not window
                        and el.wall_id == other.global_id
                        and partner_flush(el, other, px, py)
                        and z_overlaps(window, el)):
                    candidates.append((other, el))
        if not candidates:
            return ext
        # Deterministic regardless of story.walls order (Codex).
        other, el = min(candidates, key=lambda pair: pair[0].global_id)
        other_side = el.pane_side or "outer"
        if my_side == "inner" and other_side == "inner":
            if wall.global_id < other.global_id:
                return WINDOW_PANE_DEPTH - other.thickness / 2
            return -other.thickness / 2
        # Outer or mixed pairs keep the full extension: the pass/butt
        # formulas are exact only for the inner-flush pair (the villa
        # case); other combinations overlap inside the corner cube, which
        # transparent glass hides. Exact joins for those need per-side
        # plane math — specs/wall-corner-joins.md § Limits.
        return ext

    return (
        adjust(lead, wall.start.x, wall.start.y),
        adjust(trail, wall.end.x, wall.end.y),
    )


def _pane_center_y(
    pane_side: str, wall: Wall, story: Story, element_label: str
) -> float:
    """Profile-center Y for a thin pane flush with the requested wall face
    (local y spans the wall depth [0, thickness]; y=0 is the −normal face).

    Fails loud (pydantic validates construction/loading, not later
    assignment) — a typo here would otherwise silently render as "inner".
    """
    if pane_side not in ("outer", "inner"):
        raise ValueError(
            f"{element_label}: invalid pane_side {pane_side!r} "
            f"(expected 'outer' or 'inner')"
        )
    if wall.thickness < WINDOW_PANE_DEPTH:
        raise ValueError(
            f"{element_label}: host wall '{wall.name}' is {wall.thickness}m "
            f"thick — thinner than the {WINDOW_PANE_DEPTH}m glazing pane"
        )
    outer_at_zero = _exterior_at_local_y_zero(wall, story)
    flush_at_zero = (pane_side == "outer") == outer_at_zero
    return (
        WINDOW_PANE_DEPTH / 2
        if flush_at_zero
        else wall.thickness - WINDOW_PANE_DEPTH / 2
    )


class IFCExporter:
    """Export a Building model to IFC file."""

    def __init__(self, building: Building):
        self.building = building
        self.file = ifcopenshell.file(schema="IFC2X3")
        self._setup_header()
        self._context: ifcopenshell.entity_instance | None = None
        self._body_context: ifcopenshell.entity_instance | None = None

    def _setup_header(self) -> None:
        """Pin the IFC file header so exports are deterministic.

        NB: `wrapped_data.header().file_name_py()` returns a DETACHED copy —
        the old code wrote to it and the file shipped blanks plus a wall
        clock (found in pre-code review 2026-08-09). Write through
        `self.file.header.file_name`, which is live."""
        epoch = os.environ.get("SOURCE_DATE_EPOCH")
        try:
            stamp = (datetime.fromtimestamp(int(epoch), UTC)
                     .strftime("%Y-%m-%dT%H:%M:%S") if epoch else PINNED_TIME)
        except ValueError as exc:
            raise ValueError(
                f"SOURCE_DATE_EPOCH must be an integer epoch, got {epoch!r}"
            ) from exc
        file_name = self.file.header.file_name
        file_name.name = f"{self.building.name}.ifc"
        file_name.time_stamp = stamp
        file_name.author = ("ArchiCAD Builder",)
        file_name.organization = ("",)

    def export(self, output_path: str | Path) -> Path:
        """Export the building to an IFC file. Returns the output path."""
        output_path = Path(output_path)

        # Create geometric contexts
        self._create_contexts()

        # IFC hierarchy: Project → Site → Building → Stories
        ifc_project = self._create_project()
        ifc_site = self._create_site(ifc_project)
        ifc_building = self._create_building(ifc_site)

        for story in self.building.stories:
            self._export_story(story, ifc_building)

        # ArchiCAD silently DROPS entities with colliding GlobalIds — a bad
        # derived-id seed would lose geometry with no error anywhere. Fail
        # loudly instead (specs/ifc-identity.md).
        ids: dict[str, list[str]] = {}
        for entity in self.file.by_type("IfcRoot"):
            ids.setdefault(entity.GlobalId, []).append(
                f"{entity.is_a()} {entity.Name!r}")
        collisions = {gid: who for gid, who in ids.items() if len(who) > 1}
        if collisions:
            detail = "; ".join(
                f"{gid}: {' + '.join(who)}" for gid, who in collisions.items())
            raise ValueError(f"duplicate GlobalIds in export — {detail}")

        self.file.write(str(output_path))
        return output_path

    def _create_contexts(self) -> None:
        """Create geometric representation contexts."""
        # 3D context
        self._context = self.file.createIfcGeometricRepresentationContext(
            ContextIdentifier="3D",
            ContextType="Model",
            CoordinateSpaceDimension=3,
            Precision=1e-5,
            WorldCoordinateSystem=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            TrueNorth=self.file.createIfcDirection((0.0, 1.0)),
        )

        # Body sub-context for geometry
        self._body_context = self.file.createIfcGeometricRepresentationSubContext(
            ContextIdentifier="Body",
            ContextType="Model",
            ParentContext=self._context,
            TargetView="MODEL_VIEW",
        )

    def _create_project(self) -> ifcopenshell.entity_instance:
        """Create IfcProject with units."""
        # Length unit: meters
        length_unit = self.file.createIfcSIUnit(
            UnitType="LENGTHUNIT",
            Name="METRE",
        )
        area_unit = self.file.createIfcSIUnit(
            UnitType="AREAUNIT",
            Name="SQUARE_METRE",
        )
        volume_unit = self.file.createIfcSIUnit(
            UnitType="VOLUMEUNIT",
            Name="CUBIC_METRE",
        )
        # Angle unit: radians
        angle_unit = self.file.createIfcSIUnit(
            UnitType="PLANEANGLEUNIT",
            Name="RADIAN",
        )
        unit_assignment = self.file.createIfcUnitAssignment(
            Units=[length_unit, area_unit, volume_unit, angle_unit],
        )

        project = self.file.createIfcProject(
            GlobalId=self.building.global_id,
            Name=self.building.name,
            UnitsInContext=unit_assignment,
            RepresentationContexts=[self._context],
        )
        return project

    def _create_site(
        self, project: ifcopenshell.entity_instance
    ) -> ifcopenshell.entity_instance:
        """Create IfcSite and attach to project."""
        site = self.file.createIfcSite(
            GlobalId=derived_ifc_id("site", self.building.global_id),
            Name="Default Site",
            CompositionType="ELEMENT",
        )
        self.file.createIfcRelAggregates(
            GlobalId=derived_ifc_id("rel-aggregates", project.GlobalId,
                                    site.GlobalId),
            RelatingObject=project,
            RelatedObjects=[site],
        )
        return site

    def _create_building(
        self, site: ifcopenshell.entity_instance
    ) -> ifcopenshell.entity_instance:
        """Create IfcBuilding and attach to site."""
        # the model's global_id names the IfcProject; the IfcBuilding node
        # gets a derived id of its own
        ifc_building = self.file.createIfcBuilding(
            GlobalId=derived_ifc_id("building", self.building.global_id),
            Name=self.building.name,
            CompositionType="ELEMENT",
        )
        self.file.createIfcRelAggregates(
            GlobalId=derived_ifc_id("rel-aggregates", site.GlobalId,
                                    ifc_building.GlobalId),
            RelatingObject=site,
            RelatedObjects=[ifc_building],
        )
        return ifc_building

    def _export_story(
        self,
        story: Story,
        ifc_building: ifcopenshell.entity_instance,
    ) -> None:
        """Export a single story with all its elements."""
        ifc_storey = self.file.createIfcBuildingStorey(
            GlobalId=story.global_id,
            Name=story.name,
            CompositionType="ELEMENT",
            Elevation=story.elevation,
        )
        self.file.createIfcRelAggregates(
            GlobalId=derived_ifc_id("rel-aggregates", ifc_building.GlobalId,
                                    story.global_id),
            RelatingObject=ifc_building,
            RelatedObjects=[ifc_storey],
        )

        products: list[ifcopenshell.entity_instance] = []

        # Export walls
        wall_map: dict[str, ifcopenshell.entity_instance] = {}
        for wall in story.walls:
            ifc_wall = self._create_wall(wall, story)
            wall_map[wall.global_id] = ifc_wall
            products.append(ifc_wall)

        # Export virtual elements (IfcVirtualElement — room boundaries)
        for ve in story.virtual_elements:
            ifc_ve = self._create_virtual_element(ve, story.elevation)
            products.append(ifc_ve)

        # Export slabs
        for slab in story.slabs:
            ifc_slab = self._create_slab(slab, story.elevation)
            products.append(ifc_slab)

        # Export staircases
        for staircase in story.staircases:
            ifc_stair = self._create_staircase(staircase, story.elevation)
            products.append(ifc_stair)

        # Export beams (ring beams / lintels)
        for beam in story.beams:
            products.append(self._create_beam(beam, story.elevation))

        # Export roofs
        for roof in story.roofs:
            ifc_roof = self._create_roof(roof, story.elevation + story.height)
            products.append(ifc_roof)

        # Export doors (with wall openings)
        # Note: IfcOpeningElements are NOT added to spatial containment —
        # they're linked to their host wall via IfcRelVoidsElement only.
        for door in story.doors:
            wall = story.get_wall(door.wall_id)
            if wall:
                ifc_door = self._create_door(door, wall, story)
                ifc_wall_host = wall_map.get(door.wall_id)
                if ifc_wall_host:
                    opening = self._create_opening(
                        door, wall, story, is_door=True,
                        guid=derived_ifc_id("opening", wall.global_id,
                                            door.global_id))
                    self.file.createIfcRelVoidsElement(
                        GlobalId=derived_ifc_id("rel-voids", wall.global_id,
                                                opening.GlobalId),
                        RelatingBuildingElement=ifc_wall_host,
                        RelatedOpeningElement=opening,
                    )
                    self.file.createIfcRelFillsElement(
                        GlobalId=derived_ifc_id("rel-fills", opening.GlobalId,
                                                door.global_id),
                        RelatingOpeningElement=opening,
                        RelatedBuildingElement=ifc_door,
                    )
                    # Glass doors get corner glazing like windows: cut the
                    # partner wall crossing the joint (one void per opening).
                    if door.pane_side is not None:
                        _, _, partners = _corner_glazing(door, wall, story)
                        # index per PARTNER, not list position: a new joint
                        # must not shift existing twins' ids (CodeRabbit)
                        twin_count: dict[str, int] = {}
                        for partner in partners:
                            i = twin_count.get(partner.global_id, 0)
                            twin_count[partner.global_id] = i + 1
                            ifc_partner = wall_map.get(partner.global_id)
                            if ifc_partner is None:
                                raise ValueError(
                                    f"corner-glazing partner wall "
                                    f"'{partner.name}' of door "
                                    f"'{door.name}' was not exported"
                                )
                            twin = self._create_opening(
                                door, wall, story, is_door=True,
                                name="Corner Glazing Opening",
                                guid=derived_ifc_id(
                                    "opening", partner.global_id,
                                    door.global_id, index=i),
                            )
                            self.file.createIfcRelVoidsElement(
                                GlobalId=derived_ifc_id(
                                    "rel-voids", partner.global_id,
                                    twin.GlobalId),
                                RelatingBuildingElement=ifc_partner,
                                RelatedOpeningElement=twin,
                            )
                products.append(ifc_door)
                products.extend(self._create_door_handles(door, wall, story))

        # Export windows (with wall openings)
        for window in story.windows:
            wall = story.get_wall(window.wall_id)
            if wall:
                ifc_window = self._create_window(window, wall, story)
                ifc_wall_host = wall_map.get(window.wall_id)
                if ifc_wall_host:
                    opening = self._create_opening_for_window(
                        window, wall, story,
                        guid=derived_ifc_id("opening", wall.global_id,
                                            window.global_id),
                    )
                    self.file.createIfcRelVoidsElement(
                        GlobalId=derived_ifc_id("rel-voids", wall.global_id,
                                                opening.GlobalId),
                        RelatingBuildingElement=ifc_wall_host,
                        RelatedOpeningElement=opening,
                    )
                    self.file.createIfcRelFillsElement(
                        GlobalId=derived_ifc_id("rel-fills", opening.GlobalId,
                                                window.global_id),
                        RelatingOpeningElement=opening,
                        RelatedBuildingElement=ifc_window,
                    )
                    # Corner glazing: the partner wall's solid crosses the
                    # joint — cut it too, or the glass hits a hidden post.
                    # (IFC allows one void per opening, hence a twin.)
                    _, _, partners = _corner_glazing(window, wall, story)
                    # index per PARTNER, not list position (CodeRabbit) —
                    # see the door twin loop above
                    twin_count = {}
                    for partner in partners:
                        i = twin_count.get(partner.global_id, 0)
                        twin_count[partner.global_id] = i + 1
                        ifc_partner = wall_map.get(partner.global_id)
                        if ifc_partner is None:
                            raise ValueError(
                                f"corner-glazing partner wall '{partner.name}' "
                                f"of window '{window.name}' was not exported"
                            )
                        twin = self._create_opening_for_window(
                            window, wall, story, name="Corner Glazing Opening",
                            guid=derived_ifc_id("opening", partner.global_id,
                                                window.global_id, index=i),
                        )
                        self.file.createIfcRelVoidsElement(
                            GlobalId=derived_ifc_id(
                                "rel-voids", partner.global_id,
                                twin.GlobalId),
                            RelatingBuildingElement=ifc_partner,
                            RelatedOpeningElement=twin,
                        )
                products.append(ifc_window)

        # Contain all products in the storey
        if products:
            self.file.createIfcRelContainedInSpatialStructure(
                GlobalId=derived_ifc_id("rel-contained", story.global_id),
                RelatingStructure=ifc_storey,
                RelatedElements=products,
            )

        # Export spaces (IfcSpace) — these aggregate under the storey
        all_spaces = list(story.spaces)
        for apt in story.apartments:
            all_spaces.extend(apt.spaces)
        if all_spaces:
            ifc_spaces = []
            for space in all_spaces:
                ifc_space = self._create_space(space, story.elevation)
                ifc_spaces.append(ifc_space)
            self.file.createIfcRelAggregates(
                GlobalId=derived_ifc_id("rel-aggregates-spaces",
                                        story.global_id),
                RelatingObject=ifc_storey,
                RelatedObjects=ifc_spaces,
            )

    def _create_wall(
        self, wall: Wall, story: Story
    ) -> ifcopenshell.entity_instance:
        """Create an IfcWallStandardCase with extruded geometry.

        The solid extends past coincident non-parallel wall ends to close
        L-corner gaps (specs/wall-corner-joins.md); the model stays
        centerline-based and openings are placed from wall.start."""
        dx, dy = _wall_direction(wall)
        nx, ny = _wall_normal(wall)
        ext_start, ext_end = _corner_extensions(wall, story)

        # Wall placement at start point (pulled back by any corner
        # extension), offset by half thickness along normal
        ox = wall.start.x - dx * ext_start - nx * wall.thickness / 2
        oy = wall.start.y - dy * ext_start - ny * wall.thickness / 2

        placement = self._create_local_placement(
            origin=(ox, oy, story.elevation),
            z_dir=(0.0, 0.0, 1.0),
            x_dir=(dx, dy, 0.0),
        )

        # Profile: rectangle (length x thickness)
        solid_length = wall.length + ext_start + ext_end
        profile = self.file.createIfcRectangleProfileDef(
            ProfileType="AREA",
            XDim=solid_length,
            YDim=wall.thickness,
            Position=self.file.createIfcAxis2Placement2D(
                Location=self.file.createIfcCartesianPoint(
                    (solid_length / 2, wall.thickness / 2)
                ),
            ),
        )

        # Extrude upward
        solid = self.file.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=self.file.createIfcDirection((0.0, 0.0, 1.0)),
            Depth=wall.height,
        )

        shape = self.file.createIfcShapeRepresentation(
            ContextOfItems=self._body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

        product_shape = self.file.createIfcProductDefinitionShape(
            Representations=[shape],
        )

        ifc_wall = self.file.createIfcWallStandardCase(
            GlobalId=wall.global_id,
            Name=wall.name or "Wall",
            Description=wall.description or None,
            ObjectPlacement=placement,
            Representation=product_shape,
        )

        # Pset_WallCommon — IFC standard property set
        props = [
            self.file.createIfcPropertySingleValue(
                Name="LoadBearing",
                NominalValue=self.file.create_entity("IfcBoolean", wall.load_bearing),
            ),
            self.file.createIfcPropertySingleValue(
                Name="IsExternal",
                NominalValue=self.file.create_entity("IfcBoolean", wall.is_external),
            ),
        ]
        pset = self.file.createIfcPropertySet(
            GlobalId=derived_ifc_id("pset", wall.global_id,
                                    "Pset_WallCommon"),
            Name="Pset_WallCommon",
            HasProperties=props,
        )
        self.file.createIfcRelDefinesByProperties(
            GlobalId=derived_ifc_id("rel-defines", wall.global_id,
                                    "Pset_WallCommon"),
            RelatedObjects=[ifc_wall],
            RelatingPropertyDefinition=pset,
        )

        return ifc_wall

    def _create_virtual_element(
        self, ve: VirtualElement, elevation: float
    ) -> ifcopenshell.entity_instance:
        """Create an IfcVirtualElement — a zero-thickness boundary line."""

        dx = ve.end.x - ve.start.x
        dy = ve.end.y - ve.start.y
        length = ve.length

        placement = self._create_local_placement(
            origin=(ve.start.x, ve.start.y, elevation),
            z_dir=(0.0, 0.0, 1.0),
            x_dir=(dx / length, dy / length, 0.0),
        )

        ifc_ve = self.file.createIfcVirtualElement(
            GlobalId=ve.global_id,
            Name=ve.name or "VirtualElement",
            Description=ve.description or None,
            ObjectPlacement=placement,
        )
        return ifc_ve

    def _create_slab(
        self, slab: Slab, elevation: float
    ) -> ifcopenshell.entity_instance:
        """Create an IfcSlab with extruded polygon geometry."""
        vertices = slab.outline.vertices

        # Create polyline profile from polygon vertices
        ifc_points = [
            self.file.createIfcCartesianPoint((v.x, v.y)) for v in vertices
        ]
        # Close the loop
        ifc_points.append(ifc_points[0])

        polyline = self.file.createIfcPolyline(Points=ifc_points)
        profile = self.file.createIfcArbitraryClosedProfileDef(
            ProfileType="AREA",
            OuterCurve=polyline,
        )

        # Storey elevation is the finished floor level: floor slabs hang
        # BELOW the datum so walls/doors sit ON them, not inside them
        # (specs/storey-datum.md, villa feedback #013). Ceilings share the
        # placement — legacy/unspecified, no project exports ceilings yet.
        z = elevation - slab.thickness

        placement = self._create_local_placement(
            origin=(0.0, 0.0, z),
        )

        solid = self.file.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=self.file.createIfcDirection((0.0, 0.0, 1.0)),
            Depth=slab.thickness,
        )

        shape = self.file.createIfcShapeRepresentation(
            ContextOfItems=self._body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

        product_shape = self.file.createIfcProductDefinitionShape(
            Representations=[shape],
        )

        ifc_slab = self.file.createIfcSlab(
            GlobalId=slab.global_id,
            Name=slab.name or "Slab",
            ObjectPlacement=placement,
            Representation=product_shape,
            PredefinedType=slab.slab_type.value,
        )
        return ifc_slab

    def _create_beam(
        self, beam, elevation: float
    ) -> ifcopenshell.entity_instance:
        """IfcBeam: rectangle footprint along the centerline extruded up by
        depth from (elevation + z_top − depth). Upstands over full-height
        openings rise into the roof zone (specs/structural-plausibility.md)."""
        import math as _math

        dx = beam.end.x - beam.start.x
        dy = beam.end.y - beam.start.y
        length = _math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        nx, ny = -uy * beam.width / 2, ux * beam.width / 2
        corners = [
            (beam.start.x + nx, beam.start.y + ny),
            (beam.end.x + nx, beam.end.y + ny),
            (beam.end.x - nx, beam.end.y - ny),
            (beam.start.x - nx, beam.start.y - ny),
        ]
        ifc_points = [self.file.createIfcCartesianPoint(c) for c in corners]
        ifc_points.append(ifc_points[0])
        profile = self.file.createIfcArbitraryClosedProfileDef(
            ProfileType="AREA",
            OuterCurve=self.file.createIfcPolyline(Points=ifc_points),
        )
        placement = self._create_local_placement(
            origin=(0.0, 0.0, elevation + beam.z_top - beam.depth),
        )
        solid = self.file.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=self.file.createIfcDirection((0.0, 0.0, 1.0)),
            Depth=beam.depth,
        )
        shape = self.file.createIfcShapeRepresentation(
            ContextOfItems=self._body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )
        return self.file.createIfcBeam(
            GlobalId=beam.global_id,
            Name=beam.name or "Beam",
            ObjectPlacement=placement,
            Representation=self.file.createIfcProductDefinitionShape(
                Representations=[shape],
            ),
        )

    def _create_roof(
        self, roof: Roof, elevation: float
    ) -> ifcopenshell.entity_instance:
        """Create an IfcSlab with ROOF type (flat roof as slab)."""
        vertices = roof.outline.vertices
        ifc_points = [
            self.file.createIfcCartesianPoint((v.x, v.y)) for v in vertices
        ]
        ifc_points.append(ifc_points[0])

        polyline = self.file.createIfcPolyline(Points=ifc_points)
        profile = self.file.createIfcArbitraryClosedProfileDef(
            ProfileType="AREA",
            OuterCurve=polyline,
        )

        placement = self._create_local_placement(
            origin=(0.0, 0.0, elevation),
        )

        solid = self.file.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=self.file.createIfcDirection((0.0, 0.0, 1.0)),
            Depth=roof.thickness,
        )

        shape = self.file.createIfcShapeRepresentation(
            ContextOfItems=self._body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

        product_shape = self.file.createIfcProductDefinitionShape(
            Representations=[shape],
        )

        ifc_roof = self.file.createIfcSlab(
            GlobalId=roof.global_id,
            Name=roof.name or "Roof",
            ObjectPlacement=placement,
            Representation=product_shape,
            PredefinedType="ROOF",
        )
        return ifc_roof

    def _create_staircase(
        self, staircase: Staircase, elevation: float
    ) -> ifcopenshell.entity_instance:
        """Create an IfcStair with extruded polygon geometry.

        In IFC 2x3, IfcStair uses ShapeType attribute for the staircase type.
        The geometry is a simple extrusion of the footprint outline — detailed
        flights/landings can be added later as IfcStairFlight components.
        """
        vertices = staircase.outline.vertices

        ifc_points = [
            self.file.createIfcCartesianPoint((v.x, v.y)) for v in vertices
        ]
        ifc_points.append(ifc_points[0])

        polyline = self.file.createIfcPolyline(Points=ifc_points)
        profile = self.file.createIfcArbitraryClosedProfileDef(
            ProfileType="AREA",
            OuterCurve=polyline,
        )

        placement = self._create_local_placement(
            origin=(0.0, 0.0, elevation),
        )

        # Extrude to a reasonable height (story height approximation)
        # Using width as a proxy for stair height per flight
        stair_height = staircase.riser_height * 17  # ~17 risers per flight typical

        solid = self.file.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=self.file.createIfcDirection((0.0, 0.0, 1.0)),
            Depth=stair_height,
        )

        shape = self.file.createIfcShapeRepresentation(
            ContextOfItems=self._body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

        product_shape = self.file.createIfcProductDefinitionShape(
            Representations=[shape],
        )

        ifc_stair = self.file.createIfcStair(
            GlobalId=staircase.global_id,
            Name=staircase.name or "Staircase",
            ObjectPlacement=placement,
            Representation=product_shape,
            ShapeType=staircase.stair_type.value,
        )
        return ifc_stair

    def _create_space(
        self, space: Space, elevation: float
    ) -> ifcopenshell.entity_instance:
        """Create an IfcSpace with extruded polygon geometry.

        IfcSpace represents a bounded area within the building — rooms,
        corridors, etc. In IFC 2x3, uses CompositionType and InternalOrExternal.
        """
        vertices = space.boundary.vertices

        ifc_points = [
            self.file.createIfcCartesianPoint((v.x, v.y)) for v in vertices
        ]
        ifc_points.append(ifc_points[0])

        polyline = self.file.createIfcPolyline(Points=ifc_points)
        profile = self.file.createIfcArbitraryClosedProfileDef(
            ProfileType="AREA",
            OuterCurve=polyline,
        )

        placement = self._create_local_placement(
            origin=(0.0, 0.0, elevation),
        )

        # Extrude to standard room height (2.7m typical)
        room_height = 2.7

        solid = self.file.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=self.file.createIfcDirection((0.0, 0.0, 1.0)),
            Depth=room_height,
        )

        shape = self.file.createIfcShapeRepresentation(
            ContextOfItems=self._body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

        product_shape = self.file.createIfcProductDefinitionShape(
            Representations=[shape],
        )

        ifc_space = self.file.createIfcSpace(
            GlobalId=space.global_id,
            Name=space.name or "Space",
            Description=space.description or None,
            ObjectPlacement=placement,
            Representation=product_shape,
            CompositionType="ELEMENT",
            InteriorOrExteriorSpace="INTERNAL",
        )

        # Add room type as property
        if space.room_type.value != "notdefined":
            props = [
                self.file.createIfcPropertySingleValue(
                    Name="RoomType",
                    NominalValue=self.file.create_entity(
                        "IfcLabel", space.room_type.value
                    ),
                ),
            ]
            pset = self.file.createIfcPropertySet(
                GlobalId=derived_ifc_id("pset", space.global_id,
                                        "Pset_SpaceCommon"),
                Name="Pset_SpaceCommon",
                HasProperties=props,
            )
            self.file.createIfcRelDefinesByProperties(
                GlobalId=derived_ifc_id("rel-defines", space.global_id,
                                        "Pset_SpaceCommon"),
                RelatedObjects=[ifc_space],
                RelatingPropertyDefinition=pset,
            )

        return ifc_space

    def _create_door(
        self, door: Door, wall: Wall, story: Story
    ) -> ifcopenshell.entity_instance:
        """Create an IfcDoor with geometry placed in the host wall.

        Default: a full-thickness leaf. Glass doors opt into the thin-pane
        treatment via pane_side (specs/window-glazing-placement.md)."""
        dx, dy = _wall_direction(wall)
        nx, ny = _wall_normal(wall)

        # Door origin: wall start + offset along wall direction (pulled back
        # through a corner joint when a glass leaf is flush there); pass/butt
        # against partner panes like windows (Gemini review 2026-08-06)
        lead = trail = 0.0
        if door.pane_side is not None:
            lead, trail = _pane_extensions(door, wall, story)
        leaf_width = door.width + lead + trail
        if leaf_width <= 0:
            raise ValueError(
                f"Door '{door.name}': corner setbacks consumed the leaf "
                f"(width {leaf_width:.3f}m)"
            )

        ox = wall.start.x + dx * (door.position - lead) - nx * wall.thickness / 2
        oy = wall.start.y + dy * (door.position - lead) - ny * wall.thickness / 2

        placement = self._create_local_placement(
            origin=(ox, oy, story.elevation),
            z_dir=(0.0, 0.0, 1.0),
            x_dir=(dx, dy, 0.0),
        )

        if door.pane_side is None:
            leaf_depth = wall.thickness
            leaf_center_y = wall.thickness / 2
        else:
            leaf_depth = WINDOW_PANE_DEPTH
            leaf_center_y = _pane_center_y(
                door.pane_side, wall, story, f"Door '{door.name}'"
            )

        profile = self.file.createIfcRectangleProfileDef(
            ProfileType="AREA",
            XDim=leaf_width,
            YDim=leaf_depth,
            Position=self.file.createIfcAxis2Placement2D(
                Location=self.file.createIfcCartesianPoint(
                    (leaf_width / 2, leaf_center_y)
                ),
            ),
        )

        solid = self.file.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=self.file.createIfcDirection((0.0, 0.0, 1.0)),
            Depth=door.height,
        )

        shape = self.file.createIfcShapeRepresentation(
            ContextOfItems=self._body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

        product_shape = self.file.createIfcProductDefinitionShape(
            Representations=[shape],
        )

        ifc_door = self.file.createIfcDoor(
            GlobalId=door.global_id,
            Name=door.name or "Door",
            ObjectPlacement=placement,
            Representation=product_shape,
            OverallHeight=door.height,
            OverallWidth=door.width,
        )
        return ifc_door

    def _create_window(
        self, window: Window, wall: Wall, story: Story
    ) -> ifcopenshell.entity_instance:
        """Create an IfcWindow as a thin pane flush with one wall face
        (specs/window-glazing-placement.md)."""
        dx, dy = _wall_direction(wall)
        nx, ny = _wall_normal(wall)

        # Corner glazing: a pane flush with a joined wall end runs through
        # the corner so the two glass planes meet (pass/butt when the
        # partner has its own flush pane — see _pane_extensions).
        lead, trail = _pane_extensions(window, wall, story)
        pane_width = window.width + lead + trail
        if pane_width <= 0:
            raise ValueError(
                f"Window '{window.name}': corner setbacks consumed the pane "
                f"(width {pane_width:.3f}m) — window too narrow for its "
                f"corner joins"
            )

        # Window origin: wall start + offset (pulled back through the
        # corner joint when flush there), elevated by sill height
        ox = wall.start.x + dx * (window.position - lead) - nx * wall.thickness / 2
        oy = wall.start.y + dy * (window.position - lead) - ny * wall.thickness / 2

        placement = self._create_local_placement(
            origin=(ox, oy, story.elevation + window.sill_height),
            z_dir=(0.0, 0.0, 1.0),
            x_dir=(dx, dy, 0.0),
        )

        pane_center_y = _pane_center_y(
            window.pane_side, wall, story, f"Window '{window.name}'"
        )

        profile = self.file.createIfcRectangleProfileDef(
            ProfileType="AREA",
            XDim=pane_width,
            YDim=WINDOW_PANE_DEPTH,
            Position=self.file.createIfcAxis2Placement2D(
                Location=self.file.createIfcCartesianPoint(
                    (pane_width / 2, pane_center_y)
                ),
            ),
        )

        solid = self.file.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=self.file.createIfcDirection((0.0, 0.0, 1.0)),
            Depth=window.height,
        )

        shape = self.file.createIfcShapeRepresentation(
            ContextOfItems=self._body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

        product_shape = self.file.createIfcProductDefinitionShape(
            Representations=[shape],
        )

        ifc_window = self.file.createIfcWindow(
            GlobalId=window.global_id,
            Name=window.name or "Window",
            ObjectPlacement=placement,
            Representation=product_shape,
            OverallHeight=window.height,
            OverallWidth=window.width,
        )
        return ifc_window

    def _create_door_handles(
        self, door: Door, wall: Wall, story: Story
    ) -> list[ifcopenshell.entity_instance]:
        """Handles as IfcDiscreteAccessory products — a door must read as a
        door in every output (owner 2026-08-06), so this is geometry, not
        per-project render decor.

        Swing doors: lever pair at the latch edge (LEFT hinges at the door
        start, matching the plan swing arcs); DOUBLE: levers at the meeting
        stiles; SLIDING and glass (pane) doors: vertical pull bars;
        NOTDEFINED: none (unknown mechanism, e.g. a sectional garage door).
        One handle per leaf face."""
        op = door.operation_type.value
        if op == "NOTDEFINED":
            return []
        pull_bar = op.startswith("SLIDING") or door.pane_side is not None
        if op == "DOUBLE_DOOR_SINGLE_SWING":
            offsets = [door.width / 2 - 0.06, door.width / 2 + 0.06]
        elif pull_bar:
            offsets = [door.width - 0.12]
        elif op == "SINGLE_SWING_RIGHT":
            offsets = [0.08]
        else:  # SINGLE_SWING_LEFT
            offsets = [door.width - 0.08]

        if door.pane_side is not None:
            leaf_center_y = _pane_center_y(
                door.pane_side, wall, story, f"Door '{door.name}'"
            )
            leaf_half = WINDOW_PANE_DEPTH / 2
        else:
            leaf_center_y = wall.thickness / 2
            leaf_half = wall.thickness / 2

        if pull_bar:
            profile_x, profile_y, depth, z0 = 0.03, 0.03, 0.35, 0.9
        else:
            profile_x, profile_y, depth, z0 = 0.14, 0.03, 0.03, 1.035

        dx, dy = _wall_direction(wall)
        nx, ny = _wall_normal(wall)
        handles = []
        for off in offsets:
            for side in (-1.0, 1.0):
                # offset across the wall, measured from the −normal face
                y_c = leaf_center_y + side * (leaf_half + 0.035)
                hx = (wall.start.x + dx * (door.position + off)
                      + nx * (y_c - wall.thickness / 2))
                hy = (wall.start.y + dy * (door.position + off)
                      + ny * (y_c - wall.thickness / 2))
                placement = self._create_local_placement(
                    origin=(hx, hy, story.elevation + z0),
                    z_dir=(0.0, 0.0, 1.0),
                    x_dir=(dx, dy, 0.0),
                )
                profile = self.file.createIfcRectangleProfileDef(
                    ProfileType="AREA",
                    XDim=profile_x,
                    YDim=profile_y,
                    Position=self.file.createIfcAxis2Placement2D(
                        Location=self.file.createIfcCartesianPoint((0.0, 0.0)),
                    ),
                )
                solid = self.file.createIfcExtrudedAreaSolid(
                    SweptArea=profile,
                    Position=self.file.createIfcAxis2Placement3D(
                        Location=self.file.createIfcCartesianPoint(
                            (0.0, 0.0, 0.0)
                        ),
                    ),
                    ExtrudedDirection=self.file.createIfcDirection(
                        (0.0, 0.0, 1.0)
                    ),
                    Depth=depth,
                )
                shape = self.file.createIfcShapeRepresentation(
                    ContextOfItems=self._body_context,
                    RepresentationIdentifier="Body",
                    RepresentationType="SweptSolid",
                    Items=[solid],
                )
                handles.append(self.file.createIfcDiscreteAccessory(
                    GlobalId=derived_ifc_id("handle", door.global_id,
                                            index=len(handles)),
                    Name=f"{door.name or 'Door'} Handle {len(handles)}",
                    ObjectPlacement=placement,
                    Representation=self.file.createIfcProductDefinitionShape(
                        Representations=[shape],
                    ),
                ))
        return handles

    def _create_opening(
        self,
        door: Door,
        wall: Wall,
        story: Story,
        is_door: bool = True,
        name: str | None = None,
        *,
        guid: str,
    ) -> ifcopenshell.entity_instance:
        """Create an IfcOpeningElement for a door in a wall.

        The GlobalId comes from the caller — identity depends on which wall
        is being voided (main vs corner-glazing twin), which only the caller
        knows (specs/ifc-identity.md).

        Glass doors (pane_side set) flush with a joined wall end get the
        corner-glazing extension, like windows."""
        dx, dy = _wall_direction(wall)
        nx, ny = _wall_normal(wall)

        lead = trail = 0.0
        if door.pane_side is not None:
            lead, trail, _ = _corner_glazing(door, wall, story)
            if lead:
                lead += 0.01
            if trail:
                trail += 0.01
        cut_width = door.width + lead + trail

        ox = wall.start.x + dx * (door.position - lead) - nx * wall.thickness / 2
        oy = wall.start.y + dy * (door.position - lead) - ny * wall.thickness / 2

        placement = self._create_local_placement(
            origin=(ox, oy, story.elevation),
            z_dir=(0.0, 0.0, 1.0),
            x_dir=(dx, dy, 0.0),
        )

        # Opening is slightly larger than the door for clean boolean
        profile = self.file.createIfcRectangleProfileDef(
            ProfileType="AREA",
            XDim=cut_width,
            YDim=wall.thickness + 0.01,  # slightly thicker for clean cut
            Position=self.file.createIfcAxis2Placement2D(
                Location=self.file.createIfcCartesianPoint(
                    (cut_width / 2, (wall.thickness + 0.01) / 2)
                ),
            ),
        )

        solid = self.file.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=self.file.createIfcDirection((0.0, 0.0, 1.0)),
            Depth=door.height,
        )

        shape = self.file.createIfcShapeRepresentation(
            ContextOfItems=self._body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

        product_shape = self.file.createIfcProductDefinitionShape(
            Representations=[shape],
        )

        opening = self.file.createIfcOpeningElement(
            GlobalId=guid,
            Name=name or ("Door Opening" if is_door else "Window Opening"),
            ObjectPlacement=placement,
            Representation=product_shape,
        )
        return opening

    def _create_opening_for_window(
        self,
        window: Window,
        wall: Wall,
        story: Story,
        name: str = "Window Opening",
        *,
        guid: str,
    ) -> ifcopenshell.entity_instance:
        """Create an IfcOpeningElement for a window in a wall.

        Flush corner-glazed windows get an opening extended through the
        corner joint (+0.01 clean-cut margin); the caller voids the corner
        partner wall with a second one of these."""
        dx, dy = _wall_direction(wall)
        nx, ny = _wall_normal(wall)

        lead, trail, _ = _corner_glazing(window, wall, story)
        if lead:
            lead += 0.01
        if trail:
            trail += 0.01
        cut_width = window.width + lead + trail

        ox = wall.start.x + dx * (window.position - lead) - nx * wall.thickness / 2
        oy = wall.start.y + dy * (window.position - lead) - ny * wall.thickness / 2

        placement = self._create_local_placement(
            origin=(ox, oy, story.elevation + window.sill_height),
            z_dir=(0.0, 0.0, 1.0),
            x_dir=(dx, dy, 0.0),
        )

        profile = self.file.createIfcRectangleProfileDef(
            ProfileType="AREA",
            XDim=cut_width,
            YDim=wall.thickness + 0.01,
            Position=self.file.createIfcAxis2Placement2D(
                Location=self.file.createIfcCartesianPoint(
                    (cut_width / 2, (wall.thickness + 0.01) / 2)
                ),
            ),
        )

        solid = self.file.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=self.file.createIfcDirection((0.0, 0.0, 1.0)),
            Depth=window.height,
        )

        shape = self.file.createIfcShapeRepresentation(
            ContextOfItems=self._body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

        product_shape = self.file.createIfcProductDefinitionShape(
            Representations=[shape],
        )

        opening = self.file.createIfcOpeningElement(
            GlobalId=guid,
            Name=name,
            ObjectPlacement=placement,
            Representation=product_shape,
        )
        return opening

    def _create_local_placement(
        self,
        origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
        z_dir: tuple[float, float, float] = (0.0, 0.0, 1.0),
        x_dir: tuple[float, float, float] = (1.0, 0.0, 0.0),
    ) -> ifcopenshell.entity_instance:
        """Create an IfcLocalPlacement."""
        axis2 = self.file.createIfcAxis2Placement3D(
            Location=self.file.createIfcCartesianPoint(origin),
            Axis=self.file.createIfcDirection(z_dir),
            RefDirection=self.file.createIfcDirection(x_dir),
        )
        return self.file.createIfcLocalPlacement(
            RelativePlacement=axis2,
        )
