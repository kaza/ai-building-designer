"""Tests for IFC export."""

import tempfile
from pathlib import Path

import ifcopenshell

from archicad_builder.export.ifc import IFCExporter
from archicad_builder.models import (
    Building,
    Door,
    Point2D,
    Polygon2D,
    Roof,
    RoofType,
    Slab,
    Story,
    Wall,
    Window,
)


def _simple_building() -> Building:
    """Create a minimal test building."""
    wall_s = Wall(
        name="South", start=Point2D(x=0, y=0), end=Point2D(x=6, y=0),
        height=3.0, thickness=0.25,
    )
    wall_e = Wall(
        name="East", start=Point2D(x=6, y=0), end=Point2D(x=6, y=4),
        height=3.0, thickness=0.25,
    )
    wall_n = Wall(
        name="North", start=Point2D(x=6, y=4), end=Point2D(x=0, y=4),
        height=3.0, thickness=0.25,
    )
    wall_w = Wall(
        name="West", start=Point2D(x=0, y=4), end=Point2D(x=0, y=0),
        height=3.0, thickness=0.25,
    )

    door = Door(
        name="Door", wall_id=wall_s.global_id, position=2.5, width=0.9, height=2.1,
    )
    window = Window(
        name="Window", wall_id=wall_e.global_id, position=1.2,
        width=1.2, height=1.5, sill_height=0.9,
    )
    floor = Slab(
        name="Floor",
        outline=Polygon2D(vertices=[
            Point2D(x=0, y=0), Point2D(x=6, y=0),
            Point2D(x=6, y=4), Point2D(x=0, y=4),
        ]),
        thickness=0.25,
    )
    roof = Roof(
        name="Roof",
        outline=Polygon2D(vertices=[
            Point2D(x=0, y=0), Point2D(x=6, y=0),
            Point2D(x=6, y=4), Point2D(x=0, y=4),
        ]),
        roof_type=RoofType.FLAT, pitch=0, thickness=0.3,
    )

    story = Story(
        name="Ground Floor", elevation=0.0, height=3.0,
        walls=[wall_s, wall_e, wall_n, wall_w],
        slabs=[floor], doors=[door], windows=[window], roofs=[roof],
    )
    return Building(name="Test House", stories=[story])


class TestIFCExport:
    def test_export_creates_file(self):
        """Export produces a valid IFC file."""
        building = _simple_building()
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            path = Path(f.name)

        exporter = IFCExporter(building)
        result = exporter.export(path)

        assert result.exists()
        assert result.stat().st_size > 0

        # Verify it's parseable IFC
        ifc = ifcopenshell.open(str(path))
        assert ifc.schema == "IFC2X3"
        path.unlink()

    def test_export_has_correct_elements(self):
        """Exported IFC contains the expected element types."""
        building = _simple_building()
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            path = Path(f.name)

        exporter = IFCExporter(building)
        exporter.export(path)

        ifc = ifcopenshell.open(str(path))

        walls = ifc.by_type("IfcWallStandardCase")
        assert len(walls) == 4

        doors = ifc.by_type("IfcDoor")
        assert len(doors) == 1

        windows = ifc.by_type("IfcWindow")
        assert len(windows) == 1

        slabs = [s for s in ifc.by_type("IfcSlab") if s.PredefinedType == "FLOOR"]
        assert len(slabs) == 1

        roofs = [s for s in ifc.by_type("IfcSlab") if s.PredefinedType == "ROOF"]
        assert len(roofs) == 1

        openings = ifc.by_type("IfcOpeningElement")
        assert len(openings) == 2

        path.unlink()

    def test_export_has_project_hierarchy(self):
        """IFC file has correct Project → Site → Building → Storey hierarchy."""
        building = _simple_building()
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            path = Path(f.name)

        exporter = IFCExporter(building)
        exporter.export(path)

        ifc = ifcopenshell.open(str(path))

        assert len(ifc.by_type("IfcProject")) == 1
        assert len(ifc.by_type("IfcSite")) == 1
        assert len(ifc.by_type("IfcBuilding")) == 1
        assert len(ifc.by_type("IfcBuildingStorey")) == 1

        project = ifc.by_type("IfcProject")[0]
        assert project.Name == "Test House"

        path.unlink()

    def test_openings_not_in_spatial_containment(self):
        """IfcOpeningElements must NOT be in IfcRelContainedInSpatialStructure.

        Openings are linked to walls via IfcRelVoidsElement only.
        Including them in spatial containment creates circular references
        that ArchiCAD reports as 'Elemente in Endlosschleife'.
        """
        building = _simple_building()
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            path = Path(f.name)

        exporter = IFCExporter(building)
        exporter.export(path)

        ifc = ifcopenshell.open(str(path))

        contained_elements = set()
        for rel in ifc.by_type("IfcRelContainedInSpatialStructure"):
            for element in rel.RelatedElements:
                contained_elements.add(element.is_a())

        assert "IfcOpeningElement" not in contained_elements

        voids_rels = ifc.by_type("IfcRelVoidsElement")
        assert len(voids_rels) == 2

        path.unlink()

    def test_global_ids_preserved_in_ifc(self):
        """Model GlobalIds must appear in the exported IFC file."""
        building = _simple_building()
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            path = Path(f.name)

        exporter = IFCExporter(building)
        exporter.export(path)

        ifc = ifcopenshell.open(str(path))

        # Project gets building's GlobalId
        project = ifc.by_type("IfcProject")[0]
        assert project.GlobalId == building.global_id

        # Storey gets story's GlobalId
        storey = ifc.by_type("IfcBuildingStorey")[0]
        assert storey.GlobalId == building.stories[0].global_id

        # Walls get their GlobalIds
        story = building.stories[0]
        ifc_wall_ids = {w.GlobalId for w in ifc.by_type("IfcWallStandardCase")}
        for wall in story.walls:
            assert wall.global_id in ifc_wall_ids

        # Door gets its GlobalId
        ifc_door = ifc.by_type("IfcDoor")[0]
        assert ifc_door.GlobalId == story.doors[0].global_id

        # Window gets its GlobalId
        ifc_window = ifc.by_type("IfcWindow")[0]
        assert ifc_window.GlobalId == story.windows[0].global_id

        path.unlink()

    def test_pset_wall_common(self):
        """Walls export Pset_WallCommon with LoadBearing and IsExternal."""
        building = _simple_building()
        # Make south wall load-bearing + external
        building.stories[0].walls[0].load_bearing = True
        building.stories[0].walls[0].is_external = True

        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            path = Path(f.name)

        exporter = IFCExporter(building)
        exporter.export(path)

        ifc = ifcopenshell.open(str(path))

        # Find property sets
        psets = ifc.by_type("IfcPropertySet")
        wall_common_psets = [p for p in psets if p.Name == "Pset_WallCommon"]
        assert len(wall_common_psets) == 4  # one per wall

        # Check the south wall's pset (first wall, load-bearing + external)
        rels = ifc.by_type("IfcRelDefinesByProperties")
        south_wall = None
        for rel in rels:
            pset = rel.RelatingPropertyDefinition
            if pset.Name == "Pset_WallCommon":
                for obj in rel.RelatedObjects:
                    if obj.Name == "South":
                        props = {p.Name: p.NominalValue.wrappedValue for p in pset.HasProperties}
                        assert props["LoadBearing"] is True
                        assert props["IsExternal"] is True
                        south_wall = obj
                        break

        assert south_wall is not None
        path.unlink()

    def test_virtual_element_export(self):
        """VirtualElements export as IfcVirtualElement."""
        from archicad_builder.models import Point2D, VirtualElement

        building = _simple_building()
        building.stories[0].virtual_elements.append(
            VirtualElement(
                name="Kitchen-Living",
                start=Point2D(x=3, y=0),
                end=Point2D(x=3, y=4),
            )
        )

        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            path = Path(f.name)

        exporter = IFCExporter(building)
        exporter.export(path)

        ifc = ifcopenshell.open(str(path))

        virtuals = ifc.by_type("IfcVirtualElement")
        assert len(virtuals) == 1
        assert virtuals[0].Name == "Kitchen-Living"

        # Virtual elements should be in spatial containment
        contained = set()
        for rel in ifc.by_type("IfcRelContainedInSpatialStructure"):
            for el in rel.RelatedElements:
                contained.add(el.is_a())
        assert "IfcVirtualElement" in contained

        path.unlink()

    def test_json_to_ifc_roundtrip(self):
        """Building → JSON → Building → IFC works."""
        building = _simple_building()
        json_str = building.model_dump_json()
        restored = Building.model_validate_json(json_str)

        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            path = Path(f.name)

        exporter = IFCExporter(restored)
        exporter.export(path)

        ifc = ifcopenshell.open(str(path))
        assert len(ifc.by_type("IfcWallStandardCase")) == 4
        path.unlink()


class TestWindowPane:
    """Window body = thin pane in the reveal (specs/window-glazing-placement.md).

    Fixture geometry: East wall start (6,0) → end (6,4), thickness 0.25.
    Wall direction (0,1), left-hand normal (−1,0); the window's local
    placement puts local y=0 at world x=6.125 (the EXTERIOR face — the
    footprint centroid is at x≈3) and local y=0.25 at x=5.875 (interior).
    """

    PANE = 0.06

    def _window_profile(self, building):
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            path = Path(f.name)
        IFCExporter(building).export(path)
        ifc = ifcopenshell.open(str(path))
        window = ifc.by_type("IfcWindow")[0]
        solid = window.Representation.Representations[0].Items[0]
        path.unlink()
        return solid.SweptArea

    def test_pane_is_thin_not_wall_thickness(self):
        profile = self._window_profile(_simple_building())
        assert profile.YDim == self.PANE  # was wall.thickness = 0.25

    def test_default_outer_pane_flush_with_exterior_face(self):
        profile = self._window_profile(_simple_building())
        # Exterior face is at local y=0 → pane spans [0, PANE], center PANE/2
        cx, cy = profile.Position.Location.Coordinates
        assert cy == self.PANE / 2
        assert cx == 1.2 / 2  # width/2, unchanged

    def test_inner_pane_flush_with_interior_face(self):
        building = _simple_building()
        building.stories[0].windows[0].pane_side = "inner"
        profile = self._window_profile(building)
        # Interior face at local y=thickness → pane spans [t−PANE, t]
        _, cy = profile.Position.Location.Coordinates
        assert abs(cy - (0.25 - self.PANE / 2)) < 1e-9

    def test_opening_still_cuts_full_wall_thickness(self):
        building = _simple_building()
        building.stories[0].windows[0].pane_side = "inner"
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            path = Path(f.name)
        IFCExporter(building).export(path)
        ifc = ifcopenshell.open(str(path))
        window = ifc.by_type("IfcWindow")[0]
        fills = [r for r in ifc.by_type("IfcRelFillsElement")
                 if r.RelatedBuildingElement == window]
        opening = fills[0].RelatingOpeningElement
        profile = opening.Representation.Representations[0].Items[0].SweptArea
        assert profile.YDim > 0.25  # full thickness + clean-cut margin
        path.unlink()

    def test_outer_pane_correct_on_concave_L_footprint(self):
        """Bbox-centroid alone flips sides on L-shaped plans (Gemini review
        2026-08-06): for the notch wall below, the bbox center (5,5) lies
        OUTSIDE the footprint, on the notch side. The floor-slab probe must
        still find the true exterior (the notch, local y=0)."""
        pts = [(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)]
        walls = [
            Wall(name=f"W{i}", start=Point2D(x=a[0], y=a[1]),
                 end=Point2D(x=b[0], y=b[1]), height=3.0, thickness=0.25)
            for i, (a, b) in enumerate(zip(pts, pts[1:] + pts[:1]))
        ]
        # Wall along the notch's west edge: (4,4) -> (4,10)
        notch_wall = next(w for w in walls
                          if {(w.start.x, w.start.y), (w.end.x, w.end.y)}
                          == {(4, 4), (4, 10)})
        window = Window(name="Window", wall_id=notch_wall.global_id,
                        position=2.0, width=1.2, height=1.5, sill_height=0.9)
        floor = Slab(name="Floor", outline=Polygon2D(
            vertices=[Point2D(x=x, y=y) for x, y in pts]), thickness=0.25)
        story = Story(name="GF", elevation=0.0, height=3.0, walls=walls,
                      slabs=[floor], windows=[window])
        building = Building(name="L House", stories=[story])
        profile = self._window_profile(building)
        # Exterior (notch, +x) is the local y=0 face of this wall; the
        # default outer pane must sit there.
        _, cy = profile.Position.Location.Coordinates
        assert cy == self.PANE / 2

    def test_outer_pane_on_reversed_wall_sits_at_far_local_face(self):
        """A wall wound the other way (exterior on the +normal side) must
        put the outer pane at local y=thickness (Codex review 2026-08-06)."""
        building = _simple_building()
        story = building.stories[0]
        east = next(w for w in story.walls if w.name == "East")
        # Reverse the winding: (6,4) -> (6,0); normal flips to +x (exterior)
        east.start, east.end = east.end, east.start
        profile = self._window_profile(building)
        _, cy = profile.Position.Location.Coordinates
        assert abs(cy - (0.25 - self.PANE / 2)) < 1e-9

    def test_invalid_pane_side_assignment_fails_loud_at_export(self):
        """Pydantic doesn't validate post-construction assignment — the
        exporter must reject garbage instead of silently rendering 'inner'."""
        import pytest
        building = _simple_building()
        building.stories[0].windows[0].pane_side = "middle"
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            path = Path(f.name)
        with pytest.raises(ValueError, match="invalid pane_side"):
            IFCExporter(building).export(path)
        path.unlink()

    def test_wall_thinner_than_pane_fails_loud(self):
        import pytest
        building = _simple_building()
        story = building.stories[0]
        east = next(w for w in story.walls if w.name == "East")
        east.thickness = 0.04  # thinner than the 0.06 pane
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            path = Path(f.name)
        with pytest.raises(ValueError, match="thinner than"):
            IFCExporter(building).export(path)
        path.unlink()


class TestDoorPane:
    """Glass doors opt into the thin-pane treatment via Door.pane_side;
    default None keeps the legacy full-thickness slab (an opaque door leaf
    filling the reveal looks fine — only glass shows the double-pane bug)."""

    PANE = 0.06

    def _door_profile(self, building):
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            path = Path(f.name)
        IFCExporter(building).export(path)
        ifc = ifcopenshell.open(str(path))
        door = ifc.by_type("IfcDoor")[0]
        solid = door.Representation.Representations[0].Items[0]
        path.unlink()
        return solid.SweptArea

    def test_default_door_keeps_full_wall_thickness(self):
        profile = self._door_profile(_simple_building())
        assert profile.YDim == 0.25

    def test_outer_pane_door_flush_with_exterior_face(self):
        building = _simple_building()
        building.stories[0].doors[0].pane_side = "outer"
        profile = self._door_profile(building)
        # South wall (0,0)->(6,0): normal (0,1); exterior (−y) is local y=0
        _, cy = profile.Position.Location.Coordinates
        assert profile.YDim == self.PANE
        assert cy == self.PANE / 2

    def test_add_door_forwards_pane_side(self):
        from archicad_builder.models.building import Building, Story
        b = Building(name="t", stories=[Story(name="GF", elevation=0, height=3)])
        b.add_wall("GF", (0, 0), (6, 0), height=3.0, thickness=0.3, name="S")
        d = b.add_door("GF", "S", position=1.0, width=0.9, height=2.1,
                       pane_side="outer")
        assert d.pane_side == "outer"

    def test_invalid_door_pane_side_fails_loud_at_export(self):
        import pytest
        building = _simple_building()
        building.stories[0].doors[0].pane_side = "sideways"
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            path = Path(f.name)
        with pytest.raises(ValueError, match="invalid pane_side"):
            IFCExporter(building).export(path)
        path.unlink()


class TestWallCornerJoins:
    """L-corner walls extend to the outer corner and overlap
    (specs/wall-corner-joins.md); collinear splits must not extend."""

    def _wall_solid(self, building, wall_name):
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            path = Path(f.name)
        IFCExporter(building).export(path)
        ifc = ifcopenshell.open(str(path))
        w = next(w for w in ifc.by_type("IfcWallStandardCase")
                 if w.Name == wall_name)
        solid = w.Representation.Representations[0].Items[0]
        placement = w.ObjectPlacement.RelativePlacement.Location.Coordinates
        path.unlink()
        return solid.SweptArea, placement

    def test_corner_walls_extend_to_outer_faces(self):
        """South wall (0,0)->(6,0), t=0.25, corners with West and East
        (both t=0.25): solid grows 0.125 on each end and shifts back."""
        profile, placement = self._wall_solid(_simple_building(), "South")
        assert abs(profile.XDim - 6.25) < 1e-9
        assert abs(placement[0] - -0.125) < 1e-9  # shifted along -direction
        assert abs(placement[1] - -0.125) < 1e-9  # normal offset unchanged

    def test_collinear_split_does_not_extend(self):
        """Two collinear segments sharing an endpoint (a finish split) butt
        flush — extending them would z-fight two coplanar faces."""
        wall_a = Wall(name="Seg A", start=Point2D(x=0, y=0),
                      end=Point2D(x=3, y=0), height=3.0, thickness=0.25)
        wall_b = Wall(name="Seg B", start=Point2D(x=3, y=0),
                      end=Point2D(x=6, y=0), height=3.0, thickness=0.25)
        story = Story(name="GF", elevation=0.0, height=3.0,
                      walls=[wall_a, wall_b])
        building = Building(name="Split", stories=[story])
        profile, placement = self._wall_solid(building, "Seg A")
        assert abs(profile.XDim - 3.0) < 1e-9
        assert abs(placement[0] - 0.0) < 1e-9

    def test_t_junction_does_not_extend(self):
        """A wall ending mid-segment of another already penetrates t/2 —
        no endpoint match, no extension."""
        long_wall = Wall(name="Long", start=Point2D(x=0, y=0),
                         end=Point2D(x=6, y=0), height=3.0, thickness=0.25)
        stub = Wall(name="Stub", start=Point2D(x=3, y=0),
                    end=Point2D(x=3, y=4), height=3.0, thickness=0.25)
        story = Story(name="GF", elevation=0.0, height=3.0,
                      walls=[long_wall, stub])
        building = Building(name="Tee", stories=[story])
        profile, _ = self._wall_solid(building, "Long")
        assert abs(profile.XDim - 6.0) < 1e-9
        # The stub's start endpoint coincides with Long's MIDDLE, not an
        # endpoint — stub must not extend either.
        profile_stub, _ = self._wall_solid(building, "Stub")
        assert abs(profile_stub.XDim - 4.0) < 1e-9


class TestCornerGlazing:
    """A window flush with a wall end that has a corner join extends through
    the joint and voids the partner wall too — butt-glazed corner windows
    (specs/wall-corner-joins.md). Fixture: East wall start = (6,0), corner
    with South (t=0.25 → ext 0.125); window moved to position 0."""

    def _export(self, building):
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            path = Path(f.name)
        IFCExporter(building).export(path)
        ifc = ifcopenshell.open(str(path))
        path.unlink()
        return ifc

    def _flush_building(self):
        building = _simple_building()
        building.stories[0].windows[0].position = 0.0
        return building

    def test_flush_window_pane_extends_through_corner(self):
        ifc = self._export(self._flush_building())
        window = ifc.by_type("IfcWindow")[0]
        profile = window.Representation.Representations[0].Items[0].SweptArea
        assert abs(profile.XDim - (1.2 + 0.125)) < 1e-9

    def test_flush_window_opening_extends_and_voids_partner(self):
        ifc = self._export(self._flush_building())
        south = next(w for w in ifc.by_type("IfcWallStandardCase")
                     if w.Name == "South")
        voids = [r for r in ifc.by_type("IfcRelVoidsElement")
                 if r.RelatingBuildingElement == south]
        # South hosts the fixture door (1 void) + the corner-glazing cut
        assert len(voids) == 2
        corner = [v.RelatedOpeningElement for v in voids
                  if v.RelatedOpeningElement.Name == "Corner Glazing Opening"]
        assert len(corner) == 1
        profile = corner[0].Representation.Representations[0].Items[0].SweptArea
        assert profile.XDim > 1.2 + 0.125  # extended + clean-cut margin

    def test_non_flush_window_stays_single_void(self):
        ifc = self._export(_simple_building())  # window at position 1.2
        assert len(ifc.by_type("IfcOpeningElement")) == 2  # door + window only

    def _corner_pair_building(self, side_a, side_b, sill_b=0.9):
        """East window flush at (6,0) with pane side side_a; a South-wall
        window flush at the same corner with side_b and sill sill_b."""
        building = self._flush_building()  # east window at position 0
        story = building.stories[0]
        south = next(w for w in story.walls if w.name == "South")
        story.windows[0].pane_side = side_a
        story.windows.append(Window(
            name="South Corner Window", wall_id=south.global_id,
            position=5.0, width=1.0, height=1.5, sill_height=sill_b,
            pane_side=side_b,
        ))  # flush at South's END = (6,0), same corner
        return building

    def _corner_pair_dims(self, building):
        ifc = self._export(building)
        return {w.Name: w.Representation.Representations[0].Items[0]
                .SweptArea.XDim for w in ifc.by_type("IfcWindow")}

    def test_two_flush_inner_panes_touch_not_cross(self):
        """Inner pane pair at one corner: the pane on the smaller wall
        GlobalId passes (ext = PANE − partner_t/2), the other butts
        (ext = −partner_t/2) — touch, no crossing (owner feedback #002)."""
        PANE = 0.06
        building = self._corner_pair_building("inner", "inner")
        story = building.stories[0]
        south = next(w for w in story.walls if w.name == "South")
        east = next(w for w in story.walls if w.name == "East")
        dims = self._corner_pair_dims(building)
        if east.global_id < south.global_id:
            expected = {"Window": 1.2 + PANE - 0.125,
                        "South Corner Window": 1.0 - 0.125}
        else:
            expected = {"Window": 1.2 - 0.125,
                        "South Corner Window": 1.0 + PANE - 0.125}
        for name, exp in expected.items():
            assert abs(dims[name] - exp) < 1e-9, (name, dims[name], exp)

    def test_outer_pane_pair_keeps_full_extension(self):
        """Pass/butt is exact only for the inner pair — outer/mixed pairs
        keep the full extension (documented limit, Codex review)."""
        dims = self._corner_pair_dims(self._corner_pair_building("outer", "outer"))
        assert abs(dims["Window"] - (1.2 + 0.125)) < 1e-9
        assert abs(dims["South Corner Window"] - (1.0 + 0.125)) < 1e-9

    def test_vertically_disjoint_panes_do_not_pass_butt(self):
        """A clerestory band and a low window at the same corner never meet
        — no shortening (Codex review: elevation was ignored)."""
        # east window: sill 0.9 h 1.5 (0.9–2.4); south window sill 2.5 → 2.5–4.0
        dims = self._corner_pair_dims(
            self._corner_pair_building("inner", "inner", sill_b=2.5))
        assert abs(dims["Window"] - (1.2 + 0.125)) < 1e-9
        assert abs(dims["South Corner Window"] - (1.0 + 0.125)) < 1e-9


class TestDoorCornerGlazing:
    """Glass doors (pane_side set) flush with a joined wall end run through
    the joint like windows — pane + opening extend, partner wall gets a twin
    void. Solid doors (pane_side=None) never extend (feedback #003/#005)."""

    def _export(self, building):
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            path = Path(f.name)
        IFCExporter(building).export(path)
        ifc = ifcopenshell.open(str(path))
        path.unlink()
        return ifc

    def _flush_door_building(self, pane_side):
        building = _simple_building()
        door = building.stories[0].doors[0]  # South wall (0,0)->(6,0)
        door.position = 0.0                  # flush at corner with West wall
        door.pane_side = pane_side
        return building

    def test_flush_pane_door_extends_and_voids_partner(self):
        ifc = self._export(self._flush_door_building("outer"))
        door = ifc.by_type("IfcDoor")[0]
        profile = door.Representation.Representations[0].Items[0].SweptArea
        assert abs(profile.XDim - (0.9 + 0.125)) < 1e-9  # West t=0.25
        west = next(w for w in ifc.by_type("IfcWallStandardCase")
                    if w.Name == "West")
        voids = [r for r in ifc.by_type("IfcRelVoidsElement")
                 if r.RelatingBuildingElement == west]
        assert len(voids) == 1
        assert voids[0].RelatedOpeningElement.Name == "Corner Glazing Opening"

    def test_flush_solid_door_does_not_extend(self):
        ifc = self._export(self._flush_door_building(None))
        door = ifc.by_type("IfcDoor")[0]
        profile = door.Representation.Representations[0].Items[0].SweptArea
        assert abs(profile.XDim - 0.9) < 1e-9
        west = next(w for w in ifc.by_type("IfcWallStandardCase")
                    if w.Name == "West")
        assert not [r for r in ifc.by_type("IfcRelVoidsElement")
                    if r.RelatingBuildingElement == west]


class TestDoorHandles:
    """Doors carry handles as IfcDiscreteAccessory products — a door must
    read as a door in every output (owner 2026-08-06). Swing = lever pair,
    sliding/glass = vertical pulls, NOTDEFINED = none."""

    def _export(self, building):
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            path = Path(f.name)
        IFCExporter(building).export(path)
        ifc = ifcopenshell.open(str(path))
        path.unlink()
        return ifc

    def test_swing_door_gets_lever_pair(self):
        ifc = self._export(_simple_building())  # fixture door: swing left
        handles = ifc.by_type("IfcDiscreteAccessory")
        assert len(handles) == 2  # one per leaf face
        assert all("Handle" in h.Name for h in handles)
        solid = handles[0].Representation.Representations[0].Items[0]
        assert abs(solid.Depth - 0.03) < 1e-9  # lever bar, not a pull

    def test_sliding_door_gets_vertical_pulls(self):
        from archicad_builder.models.elements import DoorOperationType
        building = _simple_building()
        building.stories[0].doors[0].operation_type = (
            DoorOperationType.SLIDING_TO_LEFT)
        ifc = self._export(building)
        handles = ifc.by_type("IfcDiscreteAccessory")
        assert len(handles) == 2
        solid = handles[0].Representation.Representations[0].Items[0]
        assert abs(solid.Depth - 0.35) < 1e-9  # vertical pull bar

    def test_notdefined_door_gets_no_handles(self):
        from archicad_builder.models.elements import DoorOperationType
        building = _simple_building()
        building.stories[0].doors[0].operation_type = (
            DoorOperationType.NOTDEFINED)
        ifc = self._export(building)
        assert not ifc.by_type("IfcDiscreteAccessory")

    def test_flush_door_and_window_panes_touch_not_cross(self):
        """A glass door and a window flush at the SAME corner are pass/butt
        partners too (Gemini review 2026-08-06) — without this both take
        the full extension and cross like feedback #002."""
        PANE = 0.06
        building = _simple_building()
        story = building.stories[0]
        south = next(w for w in story.walls if w.name == "South")
        west = next(w for w in story.walls if w.name == "West")
        door = story.doors[0]           # hosted on South
        door.position = 0.0             # flush at the (0,0) corner
        door.pane_side = "inner"        # pass/butt is exact for inner pairs
        story.windows[0].position = 1.2  # keep the east window non-flush
        story.windows.append(Window(
            name="West Corner Window", wall_id=west.global_id,
            position=west.length - 1.0, width=1.0, height=1.5,
            pane_side="inner",
        ))  # flush at West's END = (0,0), same corner; heights overlap
        ifc = self._export(building)
        door_dim = (ifc.by_type("IfcDoor")[0].Representation
                    .Representations[0].Items[0].SweptArea.XDim)
        win_dim = next(
            w.Representation.Representations[0].Items[0].SweptArea.XDim
            for w in ifc.by_type("IfcWindow")
            if w.Name == "West Corner Window")
        if south.global_id < west.global_id:
            assert abs(door_dim - (0.9 + PANE - 0.125)) < 1e-9
            assert abs(win_dim - (1.0 - 0.125)) < 1e-9
        else:
            assert abs(door_dim - (0.9 - 0.125)) < 1e-9
            assert abs(win_dim - (1.0 + PANE - 0.125)) < 1e-9


class TestStoreyDatum:
    """Storey elevation = finished floor level (specs/storey-datum.md).

    Floor slabs hang BELOW the datum ([elevation − thickness, elevation]);
    walls and doors sit AT the datum, windows at datum + sill. Before the
    flip the slab extruded upward and buried the bottom 25 cm of every
    wall and door (villa feedback #013/#014). These placements are the
    datum's regression guard — E052 cannot catch an exporter regression.
    """

    def _export(self, building):
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            path = Path(f.name)
        IFCExporter(building).export(path)
        ifc = ifcopenshell.open(str(path))
        path.unlink()
        return ifc

    @staticmethod
    def _z(product):
        return product.ObjectPlacement.RelativePlacement.Location.Coordinates[2]

    def test_floor_slab_hangs_below_datum(self):
        ifc = self._export(_simple_building())
        slab = next(s for s in ifc.by_type("IfcSlab")
                    if s.PredefinedType == "FLOOR")
        depth = slab.Representation.Representations[0].Items[0].Depth
        assert abs(self._z(slab) - (0.0 - 0.25)) < 1e-9   # bottom at −t
        assert abs(self._z(slab) + depth - 0.0) < 1e-9    # top face = datum

    def test_floor_slab_follows_negative_elevation(self):
        building = _simple_building()
        building.stories[0].elevation = -2.8               # villa garage
        ifc = self._export(building)
        slab = next(s for s in ifc.by_type("IfcSlab")
                    if s.PredefinedType == "FLOOR")
        assert abs(self._z(slab) - (-2.8 - 0.25)) < 1e-9

    def test_ceiling_slab_shares_floor_placement(self):
        """Legacy/unspecified (spec decision log) — asserted so a silent
        convention change becomes a loud test failure."""
        building = _simple_building()
        building.stories[0].slabs[0].is_floor = False
        ifc = self._export(building)
        slab = ifc.by_type("IfcSlab")[0]
        assert abs(self._z(slab) - (0.0 - 0.25)) < 1e-9

    def test_walls_and_door_sit_at_datum(self):
        building = _simple_building()
        building.stories[0].elevation = 1.5
        ifc = self._export(building)
        for wall in ifc.by_type("IfcWallStandardCase"):
            assert abs(self._z(wall) - 1.5) < 1e-9
        door = ifc.by_type("IfcDoor")[0]
        assert abs(self._z(door) - 1.5) < 1e-9

    def test_window_sits_at_datum_plus_sill(self):
        building = _simple_building()
        building.stories[0].elevation = 1.5
        ifc = self._export(building)
        window = ifc.by_type("IfcWindow")[0]
        assert abs(self._z(window) - (1.5 + 0.9)) < 1e-9

    def test_door_opening_sits_at_datum(self):
        building = _simple_building()
        building.stories[0].elevation = 1.5
        ifc = self._export(building)
        door = ifc.by_type("IfcDoor")[0]
        fills = [r for r in ifc.by_type("IfcRelFillsElement")
                 if r.RelatedBuildingElement == door]
        opening = fills[0].RelatingOpeningElement
        assert abs(self._z(opening) - 1.5) < 1e-9

    def test_storey_elevation_attribute_unchanged(self):
        building = _simple_building()
        building.stories[0].elevation = 1.5
        ifc = self._export(building)
        storey = ifc.by_type("IfcBuildingStorey")[0]
        assert abs(storey.Elevation - 1.5) < 1e-9
