"""Tests for spiral staircase rendering/export (specs/spiral-stair-rendering.md)."""
import ifcopenshell

from archicad_builder.export.floorplan import render_floorplan
from archicad_builder.export.ifc import IFCExporter
from archicad_builder.models.building import Building
from archicad_builder.models.elements import StaircaseType

GF = "Ground Floor"


def _building_with_stair(stair_type: StaircaseType) -> Building:
    b = Building(name="Stair Fixture")
    b.add_story(GF, height=3.0)
    b.add_wall(GF, (0, 0), (8, 0), height=3.0, thickness=0.3, name="South",
               is_external=True)
    b.add_wall(GF, (8, 0), (8, 6), height=3.0, thickness=0.3, name="East",
               is_external=True)
    b.add_wall(GF, (8, 6), (0, 6), height=3.0, thickness=0.3, name="North",
               is_external=True)
    b.add_wall(GF, (0, 6), (0, 0), height=3.0, thickness=0.3, name="West",
               is_external=True)
    b.add_slab(GF, [(0, 0), (8, 0), (8, 6), (0, 6)], name="Slab")
    b.add_staircase(GF, [(3, 2), (4.5, 2), (4.5, 3.5), (3, 3.5)],
                    stair_type=stair_type, name="Test Stair")
    return b


class TestSpiralStairRendering:
    def test_spiral_floorplan_renders(self, tmp_path):
        b = _building_with_stair(StaircaseType.SPIRAL_STAIR)
        out = tmp_path / "spiral.png"
        render_floorplan(b.get_story(GF), out)
        assert out.exists() and out.stat().st_size > 0

    def test_straight_floorplan_still_renders(self, tmp_path):
        b = _building_with_stair(StaircaseType.STRAIGHT_RUN_STAIR)
        out = tmp_path / "straight.png"
        render_floorplan(b.get_story(GF), out)
        assert out.exists() and out.stat().st_size > 0


class TestSpiralIFCExport:
    def test_shape_type_round_trips(self, tmp_path):
        b = _building_with_stair(StaircaseType.SPIRAL_STAIR)
        out = tmp_path / "spiral.ifc"
        IFCExporter(b).export(out)
        model = ifcopenshell.open(str(out))
        stairs = model.by_type("IfcStair")
        assert len(stairs) == 1
        assert stairs[0].ShapeType == "SPIRAL_STAIR"
