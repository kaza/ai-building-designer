"""[structure] preset — urm/confined (specs/seismic-lateral.md
§Structure presets and wall materials, 2026-08-13).

The preset swaps q and the Table 9.3 density row AS DATA; the confined
reward is FAIL-CLOSED: compute_seismic derives the effective type from
geometric tie-column evidence inside the computation. Waivers gate
findings (E109), never physics. Per-wall material is data-only in C1.
"""

import json

import pytest

from archicad_builder.models import Building
from archicad_builder.project_config import (
    ConfigError,
    ProjectConfig,
    Site,
    Structure,
)
from archicad_builder.seismic import compute_seismic
from archicad_builder.validators.phases import validate_seismic
from archicad_builder.validators.waivers import Waiver, WaiverConfig


def _site(ag=0.15, ground="B", **kw) -> Site:
    return Site(country="BA", ag=ag, ground_type=ground, **kw)


def _box(storeys=1, wall_material=None) -> Building:
    b = Building(name="Box")
    for i in range(storeys):
        sn = f"S{i}"
        b.add_story(sn, height=3.0, elevation=i * 3.0)
        for name, s, e in [
            (f"{sn} South", (0, 0), (6, 0)), (f"{sn} East", (6, 0), (6, 4)),
            (f"{sn} North", (6, 4), (0, 4)), (f"{sn} West", (0, 4), (0, 0)),
        ]:
            b.add_wall(sn, s, e, height=3.0, thickness=0.3,
                       name=name, is_external=True, load_bearing=True,
                       material=wall_material)
        b.add_slab(sn, [(0, 0), (6, 0), (6, 4), (0, 4)], thickness=0.25,
                   name=f"{sn} Floor")
    top = f"S{storeys - 1}"
    roof = b.add_roof(top, [(0, 0), (6, 0), (6, 4), (0, 4)],
                      thickness=0.25, name="Roof")
    roof.span_direction = "x"
    return b


def _tie(b, storey, wall, along, name):
    return b.add_column(storey, wall=wall, along=along,
                        width=0.25, depth=0.3, name=name)


def _confined_box(storeys=1) -> Building:
    """Box with full §9.5.3 evidence: corner ties + mid ties on the 6 m
    walls (gap 3 m <= 5 m); the 4 m walls are confined by the corner
    ties hosted on South/North."""
    b = _box(storeys)
    for i in range(storeys):
        sn = f"S{i}"
        for wall in (f"{sn} South", f"{sn} North"):
            for j, along in enumerate((0.0, 3.0, 6.0)):
                _tie(b, sn, wall, along, f"{wall} T{j}")
    return b


CONFINED = Structure(type="confined")


class TestConfig:
    def test_structure_block_parses(self, tmp_path):
        (tmp_path / "project.toml").write_text(
            '[structure]\ntype = "confined"\n')
        assert ProjectConfig.load(tmp_path).structure.type == "confined"

    def test_absent_block_means_urm(self, tmp_path):
        assert ProjectConfig.load(tmp_path).structure.type == "urm"

    def test_unknown_type_is_fatal(self, tmp_path):
        (tmp_path / "project.toml").write_text(
            '[structure]\ntype = "moment-frame"\n')
        with pytest.raises(ConfigError):
            ProjectConfig.load(tmp_path)

    def test_unknown_key_is_fatal(self, tmp_path):
        (tmp_path / "project.toml").write_text(
            '[structure]\ntype = "urm"\nq = 3.0\n')
        with pytest.raises(ConfigError):
            ProjectConfig.load(tmp_path)


class TestConfinedPreset:
    def test_evidence_earns_q_2(self):
        res = compute_seismic(_confined_box(), _site(), structure=CONFINED)
        assert res["structure"]["declared"] == "confined"
        assert res["structure"]["effective"] == "confined"
        assert res["structure"]["q"] == 2.0
        assert res["confinement_failures"] == []
        # higher q -> lower demand than URM
        urm = compute_seismic(_box(), _site())
        assert res["Sd"] < urm["Sd"]

    def test_partition_hosted_tie_earns_no_evidence(self):
        # Codex 2026-08-15: a tie in a non-bearing partition confines
        # nothing — re-hosting a required corner tie into a partition
        # must break the evidence and drop the reward
        b = _confined_box()
        b.add_wall("S0", (0.0, 2.0), (3.0, 2.0), height=3.0,
                   thickness=0.12, name="S0 Partition",
                   load_bearing=False)
        story = next(s for s in b.stories if s.name == "S0")
        tie = next(c for c in story.columns
                   if c.name == "S0 South T0")
        partition = next(w for w in story.walls
                         if w.name == "S0 Partition")
        tie.wall_id = partition.global_id
        res = compute_seismic(b, _site(), structure=CONFINED)
        assert res["structure"]["effective"] == "urm"
        assert res["confinement_failures"]

    def test_no_structure_block_is_todays_urm(self):
        # absent block = byte-identical behaviour
        assert (compute_seismic(_box(), _site())["Fb"]
                == compute_seismic(_box(), _site(),
                                   structure=Structure())["Fb"])

    def test_missing_evidence_falls_back_to_urm(self):
        b = _confined_box()
        # remove the mid-South tie: 6 m between confining elements > 5 m
        b.stories[0].columns = [c for c in b.stories[0].columns
                                if c.name != "S0 South T1"]
        res = compute_seismic(b, _site(), structure=CONFINED)
        assert res["structure"]["effective"] == "urm"
        assert res["structure"]["q"] == 1.5
        assert any("S0 South" in f["text"]
                   for f in res["confinement_failures"])
        # numbers are the URM numbers, exactly
        assert res["Fb"] == compute_seismic(_box(), _site())["Fb"]

    def test_free_end_without_tie_is_a_failure(self):
        b = _confined_box()
        b.add_wall("S0", (2, 2), (5, 2), height=3.0, thickness=0.3,
                   name="S0 Mid", load_bearing=True)
        res = compute_seismic(b, _site(), structure=CONFINED)
        assert any("S0 Mid" in f["text"] and "free end" in f["text"]
                   for f in res["confinement_failures"])

    def test_large_opening_needs_jamb_ties(self):
        b = _confined_box()
        # 2.0 x 2.1 m = 4.2 m2 > 1.5 m2, jambs at 1.0 and 3.0; the tie
        # at 3.0 covers the right jamb, the left one is bare
        b.add_door("S0", "S0 South", position=1.0, width=2.0, height=2.1,
                   name="Big Door")
        res = compute_seismic(b, _site(), structure=CONFINED)
        assert any("Big Door" in f["text"]
                   for f in res["confinement_failures"])
        _tie(b, "S0", "S0 South", 1.0, "S0 South TJ")
        res = compute_seismic(b, _site(), structure=CONFINED)
        assert not any("Big Door" in f["text"]
                       for f in res["confinement_failures"])

    def test_small_opening_needs_no_ties(self):
        b = _confined_box()
        b.add_window("S0", "S0 South", position=1.0, width=1.0, height=1.0,
                     sill_height=0.9, name="Small Win")  # 1.0 m2 < 1.5
        res = compute_seismic(b, _site(), structure=CONFINED)
        assert res["confinement_failures"] == []

    def test_e109_names_every_missing_location(self):
        b = _confined_box()
        b.stories[0].columns = [c for c in b.stories[0].columns
                                if c.name != "S0 South T1"]
        found = [e for e in validate_seismic(b, _site(), structure=CONFINED)
                 if e.message.startswith("E109: ")]
        assert found
        assert all("S0 South" in f.message for f in found)

    def test_urm_declaration_emits_no_e109(self):
        found = [e for e in validate_seismic(_box(), _site())
                 if e.message.startswith("E109: ")]
        assert found == []

    def test_waiving_e109_never_unlocks_the_reward(self):
        # waivers gate findings, not physics (Codex blocker, spec log)
        b = _confined_box()
        b.stories[0].columns = [c for c in b.stories[0].columns
                                if c.name != "S0 South T1"]
        waivers = WaiverConfig(waivers=[
            Waiver(rule="E109", reason="we disagree")])
        res = compute_seismic(b, _site(), structure=CONFINED,
                              waivers=waivers)
        assert res["structure"]["effective"] == "urm"
        assert res["structure"]["q"] == 1.5

    def test_assumptions_print_declared_and_effective(self):
        b = _confined_box()
        b.stories[0].columns = [c for c in b.stories[0].columns
                                if c.name != "S0 South T1"]
        a = compute_seismic(b, _site(), structure=CONFINED)["_assumptions"]
        assert a["structure_declared"] == "confined"
        assert "urm" in a["structure_effective"]
        assert "eligibility" in a["confinement_evidence"]


class TestDensityTable:
    def test_band_edges_are_strict(self):
        # ag*S exactly 0.15 (ag=0.15, ground A, gamma_I=1.0) must select
        # the NEXT band — the old <=+epsilon picked the lenient column
        res = compute_seismic(_box(storeys=2), _site(ground="A"))
        e = res["storeys"][0]["x"]
        # URM, 2 storeys, band <0.20: not an acceptable construction type
        assert e["acceptable"] is False
        assert e["density_min"] is None

    def test_just_below_the_edge_keeps_the_row(self):
        res = compute_seismic(_box(storeys=2), _site(ag=0.149, ground="A"))
        assert res["storeys"][0]["x"]["density_min"] == 5.0

    def test_confined_row_verified_values(self):
        # Table 9.3 confined, 2 storeys, ag*S = 0.18 -> band <0.20: 3.5 %
        res = compute_seismic(_confined_box(storeys=2), _site(),
                              structure=CONFINED)
        assert res["storeys"][0]["x"]["density_min"] == 3.5
        assert res["storeys"][0]["x"]["acceptable"] is True

    def test_confined_single_storey_is_unresolved_not_invented(self):
        res = compute_seismic(_confined_box(), _site(), structure=CONFINED)
        assert any("not applicable" in v and "explicit analysis" in v
                   for v in res["_unresolved"].values())
        e = res["storeys"][0]["x"]
        assert e["density_min"] is None and e["acceptable"] is True


class TestQEff:
    def _discontinuous(self):
        b = _confined_box(storeys=2)
        # bearing wall on S1 with nothing under it: E103. It carries its
        # own end ties so the confinement evidence still passes.
        b.add_wall("S1", (1, 2), (5, 2), height=3.0, thickness=0.3,
                   name="S1 Mid", load_bearing=True)
        _tie(b, "S1", "S1 Mid", 0.0, "S1 Mid T0")
        _tie(b, "S1", "S1 Mid", 4.0, "S1 Mid T1")
        return b

    def test_unwaived_e103_cuts_q_20pct(self):
        # EN 1998-1 §9.3(5) proxy: q_eff = max(1.5, 0.8*q)
        res = compute_seismic(self._discontinuous(), _site(),
                              structure=CONFINED)
        assert res["structure"]["q"] == 2.0
        assert res["structure"]["q_eff"] == 1.6
        assert "9.3(5)" in res["_assumptions"]["q_eff_note"]

    def test_waived_e103_restores_q(self):
        waivers = WaiverConfig(waivers=[
            Waiver(rule="E103", reason="engineered transfer accepted")])
        res = compute_seismic(self._discontinuous(), _site(),
                              structure=CONFINED, waivers=waivers)
        assert res["structure"]["q_eff"] == 2.0

    def test_urm_floor_is_15(self):
        b = _box(storeys=2)
        b.add_wall("S1", (1, 2), (5, 2), height=3.0, thickness=0.3,
                   name="S1 Mid", load_bearing=True)
        res = compute_seismic(b, _site())
        # 0.8 * 1.5 = 1.2 floors at 1.5 — demand does not move: same
        # building with the E103 waived computes the identical Fb
        assert res["structure"]["q_eff"] == 1.5
        waived = compute_seismic(b, _site(), waivers=WaiverConfig(
            waivers=[Waiver(rule="E103", reason="engineered transfer")]))
        assert res["Fb"] == waived["Fb"]


class TestWallMaterial:
    def test_material_is_data_only_in_c1(self):
        # an RC wall counts at masonry fvd — zero capacity change
        rc = compute_seismic(_box(wall_material="rc"), _site())
        masonry = compute_seismic(_box(), _site())
        for d in ("x", "y"):
            assert (rc["storeys"][0][d]["capacity"]
                    == masonry["storeys"][0][d]["capacity"])
        assert rc["Fb"] == masonry["Fb"]

    def test_default_wall_serializes_without_material(self):
        # byte-identity: existing building.json files must not change
        dump = _box().stories[0].walls[0].model_dump(mode="json",
                                                     exclude_none=True)
        assert "material" not in dump

    def test_material_flows_to_ifc(self, tmp_path):
        import ifcopenshell

        from archicad_builder.export.ifc import IFCExporter

        b = _box(wall_material="rc")
        path = tmp_path / "box.ifc"
        IFCExporter(b).export(path)
        ifc = ifcopenshell.open(str(path))
        names = {rel.RelatingMaterial.Name
                 for rel in ifc.by_type("IfcRelAssociatesMaterial")
                 for obj in rel.RelatedObjects
                 if obj.is_a("IfcWallStandardCase")}
        assert names == {"rc"}

    def test_default_wall_gets_no_ifc_material(self, tmp_path):
        import ifcopenshell

        from archicad_builder.export.ifc import IFCExporter

        path = tmp_path / "box.ifc"
        IFCExporter(_box()).export(path)
        assert not ifcopenshell.open(str(path)).by_type(
            "IfcRelAssociatesMaterial")

    def test_material_in_render_metadata(self):
        from archicad_builder.render3d.metadata import element_metadata

        b = _box(wall_material="rc")
        meta = element_metadata(b.model_dump(mode="json", exclude_none=True))
        assert meta["IfcWallStandardCase_S0_South"]["material"] == "rc"
        plain = element_metadata(
            _box().model_dump(mode="json", exclude_none=True))
        assert plain["IfcWallStandardCase_S0_South"]["material"] == ""


class TestReport:
    def test_report_shows_structure_basis(self, tmp_path):
        from archicad_builder.report import build_report

        b = _confined_box()
        b.stories[0].walls[0] = b.stories[0].walls[0].model_copy(
            update={"material": "rc"})
        b.save(tmp_path / "building.json")
        (tmp_path / "project.toml").write_text(
            '[structure]\ntype = "confined"\n'
            '[site]\ncountry = "BA"\nag = 0.15\nground_type = "B"\n')
        out = tmp_path / "output"
        out.mkdir()
        res = compute_seismic(b, _site(), structure=CONFINED)
        (out / "seismic.json").write_text(json.dumps(res))
        html = build_report(tmp_path)
        assert "declared" in html and "effective" in html
        assert "q_eff" in html
        assert "geometric eligibility" in html
        assert "not" in html and "9.5.3" in html   # compliance disclaimer
        assert "masonry" in html and "rc" in html  # material split
        assert "T1" in html                        # columns listed
