"""Seismic ELF engine (specs/seismic-lateral.md S1).

Spectrum values are hand-computed from EN 1998-1 §3.2.2.5 with the
recommended Type 1 / Type 2 parameters (verified against the standard,
Gemini web check 2026-08-10). Design spectrum, q = 1.5:
  0..TB:   Sd = ag*S*(2/3 + T/TB*(2.5/q - 2/3))
  TB..TC:  Sd = ag*S*2.5/q
  TC..TD:  Sd = ag*S*(2.5/q)*(TC/T)        >= beta*ag
  T>=TD:   Sd = ag*S*(2.5/q)*(TC*TD/T^2)   >= beta*ag
Fixtures are test-owned synthetic boxes; no project data.
"""

import pytest

from archicad_builder.models import Building
from archicad_builder.project_config import Site
from archicad_builder.seismic import (
    SeismicBasis,
    compute_seismic,
    design_spectrum,
)


def _site(ag=0.15, country="BA", ground="B", **kw) -> Site:
    return Site(country=country, ag=ag, ground_type=ground, **kw)


def _box(storeys=1, height=3.0) -> Building:
    """6 x 4 m box, 0.3 m bearing perimeter walls, 0.25 m slabs/roof."""
    b = Building(name="Box")
    for i in range(storeys):
        sname = f"S{i}"
        b.add_story(sname, height=height, elevation=i * height)
        for name, s, e in [
            (f"{sname} South", (0, 0), (6, 0)), (f"{sname} East", (6, 0), (6, 4)),
            (f"{sname} North", (6, 4), (0, 4)), (f"{sname} West", (0, 4), (0, 0)),
        ]:
            b.add_wall(sname, s, e, height=height, thickness=0.3,
                       name=name, is_external=True, load_bearing=True)
        b.add_slab(sname, [(0, 0), (6, 0), (6, 4), (0, 4)], thickness=0.25,
                   name=f"{sname} Floor")
    top = f"S{storeys - 1}"
    roof = b.add_roof(top, [(0, 0), (6, 0), (6, 4), (0, 4)],
                      thickness=0.25, name="Roof")
    roof.span_direction = "x"
    return b


class TestDesignSpectrum:
    # Type 1, ground B: S=1.2, TB=0.15, TC=0.5, TD=2.0; ag=0.15g, q=1.5

    def test_plateau_between_tb_and_tc(self):
        sd = design_spectrum(0.3, ag=0.15, spectrum_type=1, ground="B",
                             q=1.5)
        assert sd == pytest.approx(0.15 * 1.2 * 2.5 / 1.5, rel=1e-6)  # 0.30 g

    def test_at_t_zero_starts_at_two_thirds(self):
        sd = design_spectrum(0.0, ag=0.15, spectrum_type=1, ground="B",
                             q=1.5)
        assert sd == pytest.approx(0.15 * 1.2 * 2 / 3, rel=1e-6)      # 0.12 g

    def test_descending_branch_after_tc(self):
        sd = design_spectrum(1.0, ag=0.15, spectrum_type=1, ground="B",
                             q=1.5)
        assert sd == pytest.approx(0.30 * 0.5 / 1.0, rel=1e-6)        # 0.15 g

    def test_beta_floor_governs_long_periods(self):
        # T=4.0: raw value 0.30*0.5*2.0/16 = 0.01875 g < beta*ag = 0.03 g
        sd = design_spectrum(4.0, ag=0.15, spectrum_type=1, ground="B",
                             q=1.5)
        assert sd == pytest.approx(0.2 * 0.15, rel=1e-6)

    def test_type2_ground_b_uses_its_own_table(self):
        # Type 2 B: S=1.35, TB=0.05, TC=0.25 -> plateau at T=0.1
        sd = design_spectrum(0.1, ag=0.06, spectrum_type=2, ground="B",
                             q=1.5)
        assert sd == pytest.approx(0.06 * 1.35 * 2.5 / 1.5, rel=1e-6)


class TestComputeSeismic:
    def test_single_storey_box_base_shear(self):
        # Weights: walls 20m*0.3*3.0*25 = 450 kN; roof 24m2*(0.25*25+2.0)
        # = 198 kN (snow psi2=0); ground slab on grade excluded.
        # W = 648 kN. T1 = 0.05*3^0.75 = 0.114 s < TB -> rising branch:
        # Sd = 0.15*1.2*(2/3 + (0.114/0.15)*1.0) = 0.2568 g
        # lambda = 1.0 (single storey). Fb = 0.2568 * 648 = 166.4 kN
        res = compute_seismic(_box(1), _site())
        assert res["T1"] == pytest.approx(0.1140, abs=0.0005)
        assert res["W"] == pytest.approx(648.0, rel=0.01)
        assert res["Fb"] == pytest.approx(166.4, rel=0.02)

    def test_two_storey_box_distributes_forces_by_height(self):
        res = compute_seismic(_box(2), _site())
        forces = {f["story"]: f["F"] for f in res["forces"]}
        # level z=6 (S1: walls 450 + roof 198 = 648 at top, phi=1.0)
        # level z=3 (S0: walls 450 + S1 floor slab 24*(0.25*25+1.5)+psiE*Q)
        # top level carries more than half despite similar mass (z-weighting)
        assert forces["S1"] > forces["S0"] * 0.9
        assert res["Fb"] == pytest.approx(forces["S0"] + forces["S1"],
                                          rel=1e-6)

    def test_lambda_is_085_only_above_two_storeys(self):
        # EN 1998-1 4.3.3.2.2: lambda=0.85 needs MORE than two storeys
        two = compute_seismic(_box(2), _site())
        assert two["T1"] == pytest.approx(0.1917, abs=0.001)
        assert two["lambda"] == pytest.approx(1.0)
        three = compute_seismic(_box(3), _site())
        assert three["lambda"] == pytest.approx(0.85)

    def test_floor_live_enters_mass_with_psi_e(self):
        heavy = SeismicBasis()
        res_a = compute_seismic(_box(2), _site(), heavy)
        # doubling psi2 must increase total weight (upper floor slab live)
        heavier = SeismicBasis(psi2=0.6)
        res_b = compute_seismic(_box(2), _site(), heavier)
        assert res_b["W"] > res_a["W"]

    def test_ground_slab_carries_no_seismic_mass(self):
        b = _box(1)
        big = Building(name="BoxBigSlab")
        # identical box but with a huge on-grade slab: same W
        big.add_story("S0", height=3.0, elevation=0.0)
        for name, s, e in [
            ("S0 South", (0, 0), (6, 0)), ("S0 East", (6, 0), (6, 4)),
            ("S0 North", (6, 4), (0, 4)), ("S0 West", (0, 4), (0, 0)),
        ]:
            big.add_wall("S0", s, e, height=3.0, thickness=0.3,
                         name=name, is_external=True, load_bearing=True)
        big.add_slab("S0", [(-10, -10), (20, 0), (20, 14), (-10, 14)],
                     thickness=0.25, name="S0 Floor")
        roof = big.add_roof("S0", [(0, 0), (6, 0), (6, 4), (0, 4)],
                            thickness=0.25, name="Roof")
        roof.span_direction = "x"
        assert (compute_seismic(big, _site())["W"]
                == pytest.approx(compute_seismic(b, _site())["W"], rel=0.01))

    def test_importance_class_scales_demand(self):
        res_ii = compute_seismic(_box(1), _site())
        res_iii = compute_seismic(_box(1), _site(importance_class="III"))
        assert res_iii["Fb"] == pytest.approx(res_ii["Fb"] * 1.2, rel=0.01)

    def test_spectrum_type_defaults_by_country(self):
        res_ba = compute_seismic(_box(1), _site(country="BA"))
        res_de = compute_seismic(_box(1), _site(country="DE", ag=0.06))
        assert res_ba["_assumptions"]["spectrum_type"] == 1
        assert res_de["_assumptions"]["spectrum_type"] == 2

    def test_assumptions_are_published(self):
        res = compute_seismic(_box(1), _site())
        a = res["_assumptions"]
        assert a["q"] == 1.5
        assert "plausibility" in a["basis"].lower()

    def test_storey_shear_includes_own_diaphragm(self):
        # ground storey shear is the FULL base shear (inclusive sum —
        # Codex plan review: "above" must not skip the current level)
        res = compute_seismic(_box(1), _site())
        assert res["storeys"][0]["V"] == pytest.approx(res["Fb"], abs=0.1)

    def test_seismic_base_excludes_lower_diaphragms(self):
        res = compute_seismic(_box(2), _site(seismic_base_elevation=3.0))
        forces = {f["story"]: f["F"] for f in res["forces"]}
        assert forces["S0"] == 0.0
        assert forces["S1"] > 0.0
        # H measured from the base: 6 - 3 = 3 m
        assert res["H"] == pytest.approx(3.0)


class TestWallNetLength:
    def test_overlapping_openings_cut_once(self):
        from archicad_builder.seismic import wall_net_length
        b = _box(1)
        b.add_window("S0", "S0 South", position=2.0, width=2.0, height=1.0,
                     sill_height=0.9, name="W1")
        b.add_window("S0", "S0 South", position=3.0, width=2.0, height=1.0,
                     sill_height=0.9, name="W2")
        s = b.stories[0]
        wall = s.get_wall_by_name("S0 South")
        # union of [2,4] and [3,5] is 3 m, not 4 m
        assert wall_net_length(s, wall) == pytest.approx(3.0)
