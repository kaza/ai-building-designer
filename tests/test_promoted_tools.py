"""Tools promoted from the villa project to the framework (2026-08-09).

These four carried no project-specific logic beyond hardcoded paths, so
they moved up — and, more to the point, they had NO tests while they sat
in a project directory. Location was the smaller half of that problem.
"""

import json

import pytest

from archicad_builder.export.obj import ifc_to_obj
from archicad_builder.serve import next_feedback_dir, store_feedback


class TestIfcToObj:
    def test_writes_an_obj_with_faces_and_skips_openings(self, tmp_path):
        pytest.importorskip("ifcopenshell")
        from archicad_builder.export.ifc import IFCExporter
        from tests.factories import make_defect_building

        ifc = tmp_path / "m.ifc"
        IFCExporter(make_defect_building()).export(ifc)
        res = ifc_to_obj(ifc, tmp_path / "m.obj", label="m")

        text = (tmp_path / "m.obj").read_text()
        assert res.products > 0 and res.vertices > 0
        assert text.startswith("# m")
        assert "\nf " in text and "\nv " in text
        # a void box would cover the very window it cuts
        assert "IfcOpeningElement" not in text

    def test_creates_the_output_directory(self, tmp_path):
        pytest.importorskip("ifcopenshell")
        from archicad_builder.export.ifc import IFCExporter
        from tests.factories import make_defect_building

        ifc = tmp_path / "m.ifc"
        IFCExporter(make_defect_building()).export(ifc)
        deep = tmp_path / "nested" / "deeper" / "m.obj"
        ifc_to_obj(ifc, deep)
        assert deep.is_file()


class TestFeedbackStorage:
    """The storage contract, verified without standing up a server."""

    def test_numbers_submissions_sequentially(self, tmp_path):
        assert next_feedback_dir(tmp_path).name == "001"
        (tmp_path / "001").mkdir()
        assert next_feedback_dir(tmp_path).name == "002"
        (tmp_path / "017").mkdir()
        assert next_feedback_dir(tmp_path).name == "018"

    def test_ignores_non_numeric_directories(self, tmp_path):
        (tmp_path / "notes").mkdir()
        assert next_feedback_dir(tmp_path).name == "001"

    def test_stores_meta_and_decodes_the_screenshot(self, tmp_path):
        import base64

        png = base64.b64encode(b"\x89PNG-not-really").decode()
        target = store_feedback(tmp_path, {
            "comment": "this wall looks wrong",
            "camera": [1, 2, 3],
            "shot": f"data:image/png;base64,{png}",
        })
        meta = json.loads((target / "meta.json").read_text())
        assert meta["comment"] == "this wall looks wrong"
        assert "received_at" in meta          # stamped by the server
        assert "shot" not in meta             # the image is a file, not JSON
        assert (target / "shot.png").read_bytes() == b"\x89PNG-not-really"

    def test_a_submission_without_a_screenshot_still_stores(self, tmp_path):
        target = store_feedback(tmp_path, {"comment": "text only"})
        assert json.loads((target / "meta.json").read_text())["comment"]
        assert not (target / "shot.png").exists()


class TestFurnitureSymbols:
    def test_every_symbol_kind_draws_without_error(self, tmp_path):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        from archicad_builder.export.furnished_plan import draw_item

        fig, ax = plt.subplots()
        # material + name + size pick the symbol, so cover each branch
        cases = [
            ("Sofa", "sofa", 2.0), ("Bed", "bed", 2.0),
            ("Wardrobe", "wardrobe", 1.0), ("Kitchen counter", "counter", 2.0),
            ("Toilet", "ceramic", 0.6), ("Sink", "ceramic", 0.6),
            ("Bathtub", "ceramic", 1.7), ("Shower", "ceramic", 0.9),
            ("Pool lounger", "wood", 1.9), ("Dining table", "wood", 1.6),
            ("Dining chair", "wood", 0.4),      # < 0.25 m2 -> chair
            ("Mystery box", "sunbed", 1.0),     # unknown -> plain rectangle
        ]
        for i, (name, material, size) in enumerate(cases):
            draw_item(ax, {"name": name, "type": material, "facing": "N",
                           "bounds": [i * 3, 0, i * 3 + size, size]})
        assert ax.patches, "nothing was drawn"
        plt.close(fig)


class TestGlbLogic:
    """Pure decisions of the GLB export (the bpy shim stays thin)."""

    def test_palette_hit_and_magenta_fallback(self):
        from archicad_builder.export.glb_logic import FALLBACK, flat_color
        palette = {"Parquet": (0.55, 0.40, 0.24, 1.0)}
        color, warn = flat_color("Parquet", palette)
        assert color == (0.55, 0.40, 0.24, 1.0) and warn is None
        color, warn = flat_color("Mystery", palette)
        assert color == FALLBACK and "Mystery" in warn

    def test_prune_decision_table(self):
        from archicad_builder.export.glb_logic import should_prune
        cases = [
            (("CAMERA", False, "Cam", False), True),
            (("LIGHT", False, "Sun", False), True),
            (("EMPTY", False, "Loose", False), True),   # childless empty
            (("EMPTY", True, "AssetRoot", False), False),  # instance root
            (("MESH", False, "StairwellCutter1", False), True),
            (("MESH", False, "Wall", True), True),      # hidden in render
            (("MESH", False, "Wall", False), False),
        ]
        for args, expect in cases:
            assert should_prune(*args) is expect, args

    def test_read_palette_from_villa_config(self):
        from pathlib import Path

        from archicad_builder.export.glb_logic import read_palette
        text = (Path(__file__).parent.parent / "projects" / "villa-maketa"
                / "project.toml").read_text()
        palette = read_palette(text)
        assert palette["Accent"] == (0.905, 0.533, 0.072, 1.0)
        assert len(palette) == 14


class TestElementMetadata:
    """The OBJ hop strips properties; metadata.py rebuilds the link
    (stamped as Blender custom props -> glTF extras -> userData)."""

    def test_maps_names_with_kind_and_bearing(self):
        from archicad_builder.render3d.metadata import element_metadata
        doc = {"stories": [{"walls": [
            {"name": "Garage South Wall", "global_id": "g1",
             "load_bearing": True},
            {"name": "Bath Divider Wall", "global_id": "g2",
             "load_bearing": False},
        ], "roofs": [{"name": "Roof West", "global_id": "g3"}]}]}
        meta = element_metadata(doc)
        gw = meta["IfcWallStandardCase_Garage_South_Wall"]
        assert gw == {"global_id": "g1", "kind": "wall",
                      "name": "Garage South Wall", "load_bearing": True,
                      "tag": "W1"}
        assert meta["IfcWallStandardCase_Bath_Divider_Wall"][
            "load_bearing"] is False
        # roofs export as IfcSlab entities (export/ifc.py)
        assert meta["IfcSlab_Roof_West"]["kind"] == "roof"

    def test_covers_every_villa_bearing_wall(self):
        import json
        from pathlib import Path

        from archicad_builder.render3d.metadata import element_metadata
        doc = json.loads((Path(__file__).parent.parent / "projects"
                          / "villa-maketa" / "building.json").read_text())
        meta = element_metadata(doc)
        bearing = [k for k, v in meta.items() if v["load_bearing"]]
        assert len(bearing) == 15          # matches the BEARING payload
        assert "IfcWallStandardCase_Garage_West_Wall" in bearing
