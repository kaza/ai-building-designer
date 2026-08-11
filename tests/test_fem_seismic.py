"""S2 — FEM lateral load cases (specs/seismic-lateral.md).

compute_fem grows unfactored G/Q cases + a combo table. Without a site
it stays gravity-only (ULS = 1.35G + 1.5Q, same numbers as before —
the existing test_fem_model assertions are the regression gate). With a
site it adds EQX/EQY nodal forces at diaphragm levels scaled to the ELF
storey forces, four seismic combos, and an envelope harvest where every
element names its governing combination.
"""

import pytest

from archicad_builder.fem import compute_fem
from archicad_builder.models import Building
from archicad_builder.project_config import Site


def _site(ag=0.25) -> Site:
    return Site(country="BA", ag=ag, ground_type="B")


def _box(storeys=1) -> Building:
    b = Building(name="Box")
    for i in range(storeys):
        sn = f"S{i}"
        b.add_story(sn, height=3.0, elevation=i * 3.0)
        for name, s, e in [
            (f"{sn} South", (0, 0), (6, 0)), (f"{sn} East", (6, 0), (6, 4)),
            (f"{sn} North", (6, 4), (0, 4)), (f"{sn} West", (0, 4), (0, 0)),
        ]:
            b.add_wall(sn, s, e, height=3.0, thickness=0.3,
                       name=name, is_external=True, load_bearing=True)
        b.add_slab(sn, [(0, 0), (6, 0), (6, 4), (0, 4)], thickness=0.2,
                   name=f"{sn} Floor")
    top = f"S{storeys - 1}"
    roof = b.add_roof(top, [(0, 0), (6, 0), (6, 4), (0, 4)],
                      thickness=0.2, name="Roof")
    roof.span_direction = "x"
    return b


class TestGravityOnly:
    def test_without_site_only_uls_combo(self):
        res = compute_fem(_box(), mesh=0.4)
        assert res.combos == ["ULS"]
        assert res.balance == pytest.approx(1.0, abs=0.01)

    def test_case_balance_ledgers_per_case(self):
        res = compute_fem(_box(), mesh=0.4)
        # every gravity case closes its own vertical equilibrium
        for case in ("G", "Q"):
            cb = res.case_balance[case]
            assert cb["reacted"] == pytest.approx(cb["attached"], rel=0.01)


@pytest.fixture(scope="module")
def res():
    return compute_fem(_box(), mesh=0.4, site=_site())


class TestSeismicCombos:

    def test_four_seismic_combos_present(self, res):
        assert set(res.combos) == {"ULS", "SEIS_X+", "SEIS_X-",
                                   "SEIS_Y+", "SEIS_Y-"}

    def test_lateral_equilibrium_closes(self, res):
        # applied EQX nodal forces equal the ELF storey forces, and the
        # clamped bases react them (production support recipe — the
        # lateral path must not be shorted; Codex plan review)
        for case in ("EQX", "EQY"):
            cb = res.case_balance[case]
            assert cb["applied"] > 0
            assert cb["reacted"] == pytest.approx(cb["applied"], rel=0.01)

    def test_every_element_names_its_governing_combo(self, res):
        for e in res.elements.values():
            assert e["combo"] in res.combos
            assert set(e["combos"]) == set(res.combos)
            assert e["u"] == pytest.approx(
                max(e["combos"].values()), abs=1e-4)

    def test_envelope_never_below_uls(self, res):
        # separate Building instances have fresh GlobalIds — match by name
        uls = compute_fem(_box(), mesh=0.4)
        for e in res.elements.values():
            assert e["u"] >= uls.find(e["name"])["u"] - 1e-6

    def test_seismic_governs_some_wall_at_high_ag(self, res):
        # at ag=0.25 the in-plane shear/tension from EQ must beat pure
        # gravity somewhere — otherwise the lateral path isn't painting
        assert any(e["combo"] != "ULS" for e in res.elements.values()
                   if e["kind"] == "wall")

    def test_field_quads_carry_governing_combo_index(self, res):
        for q in res.field["quads"]:
            assert 0 <= q["cmb"] < len(res.combos)

    def test_field_quads_carry_per_combo_utilizations(self, res):
        # schema 3 / V-key views (specs/fem-xray.md): every quad ships
        # one utilization per combination, and the envelope equals the
        # max of them
        for q in res.field["quads"]:
            assert len(q["uc"]) == len(res.combos)
            assert q["u"] == pytest.approx(max(q["uc"]), abs=2e-3)

    def test_payload_uc_arrays_aligned(self, res, tmp_path):
        from archicad_builder.fem.writers import write_payloads
        write_payloads(res, tmp_path, "deadbeef")
        import json
        env = json.loads((tmp_path / "fem-field.json").read_text())
        assert env["schema"] == 4
        n = env["quads"]["n"]
        for key in ("uc", "gc"):
            assert len(env["quads"][key]) == len(env["combos"])
            assert all(len(arr) == n for arr in env["quads"][key])

    def test_payload_uc_matrix_is_exactly_transposed(self, tmp_path):
        # Codex plan review: a dimension check passes on a transposed or
        # reordered matrix — pin exact distinctive values through the
        # writer
        import json

        from archicad_builder.fem import FemResult
        from archicad_builder.fem.writers import write_payloads
        res = FemResult(
            elements={"e1": {"name": "W", "kind": "wall", "story": "S",
                             "u": 0.9, "combo": "B", "combos": {}}},
            field=dict(schema=4, coords="building-z-up", mesh=0.4, quads=[
                dict(e="e1", k="wall", u=0.21, g=0, s=0, cmb=0,
                     uc=[0.21, 0.11], gc=[0, 4],
                     c=[[0, 0, 0], [1, 0, 0], [1, 0, 1], [0, 0, 1]]),
                dict(e="e1", k="wall", u=0.42, g=0, s=0, cmb=1,
                     uc=[0.32, 0.42], gc=[1, 2],
                     c=[[1, 0, 0], [2, 0, 0], [2, 0, 1], [1, 0, 1]]),
            ]),
            intended=1.0, attached=1.0, reactions=1.0,
            combos=["A", "B"])
        write_payloads(res, tmp_path, "beef")
        env = json.loads((tmp_path / "fem-field.json").read_text())
        assert env["quads"]["uc"] == [[0.21, 0.32], [0.11, 0.42]]
        assert env["quads"]["gc"] == [[0, 1], [4, 2]]

    def test_single_combo_uc_equals_envelope(self):
        uls = compute_fem(_box(), mesh=0.4)
        for q in uls.field["quads"]:
            assert q["uc"] == [q["u"]]
            assert q["gc"] == [q.get("g", 3)]

    def test_partition_mass_shakes_with_its_storey(self):
        # non-bearing walls bucket at their storey's CEILING like the
        # ELF (Codex re-review 2026-08-10: the floor-bucketing variant
        # dropped ground-storey partition mass from the lateral ledger).
        # Coverage-style: the partition path must run and equilibrium
        # must still close with the partition's ELF share included.
        from archicad_builder.seismic import compute_seismic
        b = _box()
        b.add_wall("S0", (2, 1), (2, 3), height=3.0, thickness=0.12,
                   name="Partition", load_bearing=False)
        res = compute_fem(b, mesh=0.4, site=_site())
        elf = compute_seismic(b, _site())
        cb = res.case_balance["EQX"]
        assert cb["applied"] == pytest.approx(
            sum(f["F"] for f in elf["forces"]), rel=0.02)
        assert cb["reacted"] == pytest.approx(cb["applied"], rel=0.01)

    def test_two_storey_forces_split_by_elf(self):
        res = compute_fem(_box(2), mesh=0.4, site=_site())
        # both diaphragms loaded: EQX applied equals sum of both Fi
        from archicad_builder.seismic import compute_seismic
        elf = compute_seismic(_box(2), _site())
        applied = res.case_balance["EQX"]["applied"]
        assert applied == pytest.approx(
            sum(f["F"] for f in elf["forces"]), rel=0.02)
