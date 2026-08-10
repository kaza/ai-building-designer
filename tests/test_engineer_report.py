"""S4 — engineer handoff report (specs/engineer-handoff.md).

One self-contained HTML from building.json + project.toml + the
analysis outputs. Missing inputs render as red NOT RUN sections —
a partial report must LOOK partial. Waived findings surface with their
mandatory reasons. The report computes nothing new.
"""

import json

from archicad_builder.models import Building
from archicad_builder.report import build_report


def _project(tmp_path, with_loads=True, with_seismic=True,
             with_site=True):
    b = Building(name="Box")
    b.add_story("GF", height=3.0, elevation=0.0)
    for name, s, e in [
        ("South", (0, 0), (6, 0)), ("East", (6, 0), (6, 4)),
        ("North", (6, 4), (0, 4)), ("West", (0, 4), (0, 0)),
    ]:
        b.add_wall("GF", s, e, height=3.0, thickness=0.3,
                   name=name, is_external=True, load_bearing=True)
    b.add_slab("GF", [(0, 0), (6, 0), (6, 4), (0, 4)], thickness=0.25,
               name="Floor")
    roof = b.add_roof("GF", [(0, 0), (6, 0), (6, 4), (0, 4)],
                      thickness=0.25, name="Roof")
    roof.span_direction = "x"
    b.add_footing("GF", (0, 0), (6, 0), width=0.6, height=0.5, name="F S")
    b.save(tmp_path / "building.json")
    if with_site:
        (tmp_path / "project.toml").write_text(
            '[site]\ncountry = "BA"\nag = 0.15\nground_type = "B"\n'
            "[site.soil]\nsigma_rd = 200.0\n")
    out = tmp_path / "output"
    out.mkdir()
    if with_loads:
        (out / "loads.json").write_text(json.dumps({
            "walls-1": {"kind": "wall", "name": "South", "u": 0.4,
                        "q": 50.0, "profile": [0.4] * 8},
            "roof-1": {"kind": "slab", "name": "Roof", "u": 0.6,
                       "span": 6.0, "M": 40.0, "cantilever": True,
                       "balance": 1.0},
            "_unresolved": {}, "_assumptions": {"basis": "plausibility"},
        }))
    if with_seismic:
        (out / "seismic.json").write_text(json.dumps({
            "W": 648.0, "H": 3.0, "T1": 0.114, "Sd": 0.2568,
            "lambda": 1.0, "Fb": 166.4, "base": 0.0,
            "forces": [{"story": "GF", "z": 3.0, "W": 648.0, "F": 166.4}],
            "storeys": [{"story": "GF", "story_id": "x", "V": 166.4,
                         "floor_area": 24.0,
                         "x": {"capacity": 480.0, "density": 15.0,
                               "density_min": 3.5, "acceptable": True,
                               "e0": 0.0, "r": 3.16, "ls": 2.08,
                               "regular": True},
                         "y": {"capacity": 320.0, "density": 10.0,
                               "density_min": 3.5, "acceptable": True,
                               "e0": 0.0, "r": 3.87, "ls": 2.08,
                               "regular": True}}],
            "_unresolved": {},
            "_assumptions": {"basis": "seismic plausibility", "q": 1.5,
                             "spectrum_type": 1},
        }))
    (tmp_path / "validation.json").write_text(json.dumps({
        "waivers": [{"rule": "E065",
                     "reason": "deck cantilever pending owner decision"}]}))
    return tmp_path


class TestReport:
    def test_mission_banner_and_sections(self, tmp_path):
        html = build_report(_project(tmp_path))
        assert "licensed civil engineer" in html
        assert "Seismic" in html and "Foundations" in html
        assert "166.4" in html            # Fb surfaces
        assert "F S" in html              # footing schedule

    def test_missing_loads_renders_not_run(self, tmp_path):
        html = build_report(_project(tmp_path, with_loads=False))
        assert "NOT RUN" in html

    def test_complete_inputs_have_no_not_run(self, tmp_path):
        html = build_report(_project(tmp_path))
        # fem is legitimately absent -> exactly the FEM section says so
        assert html.count("NOT RUN") == 1

    def test_waiver_reasons_surface(self, tmp_path):
        html = build_report(_project(tmp_path))
        assert "deck cantilever pending owner decision" in html

    def test_no_site_marks_seismic_unresolved(self, tmp_path):
        html = build_report(_project(tmp_path, with_seismic=False,
                                     with_site=False))
        assert "unresolved" in html.lower()

    def test_cantilever_inventory_flags_vertical_component(self, tmp_path):
        html = build_report(_project(tmp_path))
        assert "vertical seismic component" in html.lower()
        assert "Roof" in html

    def test_self_contained_no_external_refs(self, tmp_path):
        html = build_report(_project(tmp_path))
        assert "http://" not in html and "https://" not in html

    def test_stale_analysis_is_flagged(self, tmp_path):
        # Codex code review 2026-08-10: editing building.json and
        # rerunning ONLY `report` must not look like a complete handoff
        import os
        import time
        proj = _project(tmp_path)
        time.sleep(0.05)
        (proj / "building.json").touch()
        html = build_report(proj)
        assert "STALE" in html

    def test_fem_unresolved_surfaces(self, tmp_path):
        proj = _project(tmp_path)
        (proj / "output" / "fem-loads.json").write_text(json.dumps({
            "w1": {"kind": "wall", "name": "South", "u": 0.5,
                   "combo": "ULS"},
            "_assumptions": [], "_not_modelled": ["wind"],
            "_unresolved": ["roof 'R': pitched roofs are not meshed"],
        }))
        html = build_report(proj)
        assert "pitched roofs are not meshed" in html
        assert "wind" in html   # exclusions merge verbatim

    def test_unresolved_dicts_render_as_text_not_repr(self, tmp_path):
        # Gemini code review 2026-08-10: _esc(dict) printed raw Python
        # repr into the engineer-facing page
        proj = _project(tmp_path)
        seis = json.loads((proj / "output" / "seismic.json").read_text())
        seis["_unresolved"] = {"elf": "T1 outside applicability"}
        (proj / "output" / "seismic.json").write_text(json.dumps(seis))
        html = build_report(proj)
        assert "T1 outside applicability" in html
        assert "{&#x27;" not in html and "{'" not in html
