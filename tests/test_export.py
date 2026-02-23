"""Tests for IFC export."""

import tempfile
from pathlib import Path

import ifcopenshell

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
from archicad_builder.export.ifc import IFCExporter


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
        from archicad_builder.models import VirtualElement, Point2D

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
