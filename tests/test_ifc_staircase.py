"""Tests for IFC export of staircase elements."""

import tempfile
from pathlib import Path

import ifcopenshell

from archicad_builder.models import Building
from archicad_builder.generators.shell import generate_shell
from archicad_builder.generators.core import place_vertical_core
from archicad_builder.generators.corridor import carve_corridor
from archicad_builder.generators.apartments import subdivide_apartments


class TestStaircaseIFCExport:
    """Tests for IFC export of staircase elements."""

    def test_staircase_exported_as_ifc_stair(self):
        """Staircase model should export as IfcStair in IFC."""
        b = generate_shell(num_floors=1, width=10, depth=8)
        b.add_staircase(
            "Ground Floor",
            vertices=[(2, 2), (4.5, 2), (4.5, 7), (2, 7)],
            name="Main Stair",
        )
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            ifc_path = Path(f.name)
        b.export_ifc(ifc_path)

        ifc_file = ifcopenshell.open(str(ifc_path))
        stairs = ifc_file.by_type("IfcStair")
        assert len(stairs) == 1
        assert stairs[0].Name == "Main Stair"
        ifc_path.unlink()

    def test_multi_storey_staircase_export(self):
        """Staircases on multiple floors should all export."""
        b = generate_shell(num_floors=3, width=10, depth=8)
        place_vertical_core(b, core_x=3, core_y=0)
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            ifc_path = Path(f.name)
        b.export_ifc(ifc_path)

        ifc_file = ifcopenshell.open(str(ifc_path))
        stairs = ifc_file.by_type("IfcStair")
        assert len(stairs) == 3  # one per floor

        storeys = ifc_file.by_type("IfcBuildingStorey")
        assert len(storeys) == 3
        ifc_path.unlink()

    def test_staircase_shape_type(self):
        """IfcStair should have the correct ShapeType."""
        b = generate_shell(num_floors=1, width=10, depth=8)
        b.add_staircase(
            "Ground Floor",
            vertices=[(0, 0), (2, 0), (2, 4), (0, 4)],
            name="Test",
        )
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            ifc_path = Path(f.name)
        b.export_ifc(ifc_path)

        ifc_file = ifcopenshell.open(str(ifc_path))
        stair = ifc_file.by_type("IfcStair")[0]
        assert stair.ShapeType == "STRAIGHT_RUN_STAIR"
        ifc_path.unlink()

    def test_spaces_exported_as_ifc_space(self):
        """Rooms should export as IfcSpace in IFC."""
        b = generate_shell(num_floors=1, width=16, depth=12)
        place_vertical_core(b, core_x=6.75, core_y=3.5)
        carve_corridor(b, corridor_y=5.0, corridor_width=1.5)
        subdivide_apartments(b, "Ground Floor", corridor_y=5.0, corridor_width=1.5)
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            ifc_path = Path(f.name)
        b.export_ifc(ifc_path)

        ifc_file = ifcopenshell.open(str(ifc_path))
        spaces = ifc_file.by_type("IfcSpace")
        assert len(spaces) == 16  # 4 apartments × 4 rooms
        # Check that room names are exported
        space_names = [s.Name for s in spaces]
        assert any("Living" in n for n in space_names)
        assert any("Bathroom" in n for n in space_names)
        assert any("Bedroom" in n for n in space_names)
        ifc_path.unlink()

    def test_full_building_ifc_roundtrip(self):
        """Complete building with all element types should export cleanly."""
        b = generate_shell(num_floors=2, width=16, depth=12)
        place_vertical_core(b, core_x=6, core_y=0)
        # Add windows
        b.add_window("Ground Floor", "South Wall", position=2.0, width=1.5, height=1.5)
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
            ifc_path = Path(f.name)
        b.export_ifc(ifc_path)

        ifc_file = ifcopenshell.open(str(ifc_path))
        # Verify all expected types exist
        assert len(ifc_file.by_type("IfcWallStandardCase")) > 0
        assert len(ifc_file.by_type("IfcSlab")) > 0
        assert len(ifc_file.by_type("IfcStair")) > 0
        assert len(ifc_file.by_type("IfcDoor")) > 0
        assert len(ifc_file.by_type("IfcWindow")) > 0
        ifc_path.unlink()
