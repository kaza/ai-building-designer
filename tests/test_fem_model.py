"""FEM X-ray core (specs/fem-xray.md) — building.json -> plate model.

compute_fem(building, mesh=...) meshes bearing walls / beams / slabs /
roofs as conforming quads, solves ULS gravity via PyNite, and returns
per-element design utilizations (keyed by global_id) plus a per-quad
field. Grounding: only stories at elevation <= 0 may ground; stories
above must sit on a vertically adjacent story or preflight fails.
Load accounting: intended vs attached vs reacted; dropped > 1% is a
typed error. Fixtures are test-owned; coarse meshes keep this bounded.
"""

from collections import defaultdict

import pytest

from archicad_builder.fem import (
    _principal,
    _tension_component,
    FemPreflightError,
    FemSizeError,
    compute_fem,
)
from archicad_builder.models import Building
from archicad_builder.structural import compute_loads


def _box(storey_height=3.0, roof_thickness=0.25) -> Building:
    b = Building(name="Box")
    b.add_story("GF", height=storey_height, elevation=0.0)
    for name, s, e in [
        ("South", (0, 0), (6, 0)), ("East", (6, 0), (6, 4)),
        ("North", (6, 4), (0, 4)), ("West", (0, 4), (0, 0)),
    ]:
        b.add_wall("GF", s, e, height=storey_height, thickness=0.3,
                   name=name, is_external=True, load_bearing=True)
    b.add_slab("GF", [(0, 0), (6, 0), (6, 4), (0, 4)], thickness=0.25,
               name="Floor")
    roof = b.add_roof("GF", [(0, 0), (6, 0), (6, 4), (0, 4)],
                      thickness=roof_thickness, name="Roof")
    # declared one-way span "y" so the strip engine loads South/North —
    # the same walls the FEM's two-way plate loads most (4 m < 6 m).
    roof.span_direction = "y"
    return b


@pytest.fixture(scope="module")
def box_result():
    return compute_fem(_box(), mesh=0.4)


class TestSolveAndAccounting:
    def test_load_balance_within_1pct(self, box_result):
        assert box_result.balance == pytest.approx(1.0, abs=0.01)

    def test_intended_load_fully_attached(self, box_result):
        assert box_result.attached == pytest.approx(box_result.intended,
                                                    rel=0.01)

    def test_every_bearing_element_mapped(self, box_result):
        kinds = {e["name"]: e["kind"] for e in box_result.elements.values()}
        assert kinds == {"South": "wall", "East": "wall", "North": "wall",
                         "West": "wall", "Floor": "slab", "Roof": "roof"}

    def test_elements_keyed_by_global_id(self, box_result):
        b = _box()
        wall_ids = {w.global_id for w in b.get_story("GF").walls}
        # same generator seeds differ per Building; check SHAPE not values:
        for gid, e in box_result.elements.items():
            assert isinstance(gid, str) and len(gid) > 8
            assert set(e) >= {"kind", "name", "story", "u"}
        assert len(wall_ids) == 4

    def test_healthy_box_is_below_capacity(self, box_result):
        assert all(0.0 <= e["u"] < 1.0
                   for e in box_result.elements.values())

    def test_field_quads_carry_element_ids(self, box_result):
        quads = box_result.field["quads"]
        assert len(quads) > 100
        gids = {q["e"] for q in quads}
        assert gids == set(box_result.elements)

    def test_agrees_with_strip_engine_on_solid_walls(self, box_result):
        strip = compute_loads(_box())
        fem_u = next(e["u"] for e in box_result.elements.values()
                     if e["name"] == "South")
        strip_u = strip["IfcWallStandardCase_South"]["u"]
        assert fem_u / strip_u == pytest.approx(1.0, abs=0.5)


class TestGrounding:
    def test_two_story_stack_transfers_load_down(self):
        b = _box()
        b.add_story("U", height=3.0, elevation=3.0)
        for name, s, e in [
            ("U South", (0, 0), (6, 0)), ("U East", (6, 0), (6, 4)),
            ("U North", (6, 4), (0, 4)), ("U West", (0, 4), (0, 0)),
        ]:
            b.add_wall("U", s, e, height=3.0, thickness=0.3,
                       name=name, is_external=True, load_bearing=True)
        b.add_slab("U", [(0, 0), (6, 0), (6, 4), (0, 4)], thickness=0.25,
                   name="U Floor")
        roof = b.get_story("GF").roofs.pop()
        b.add_roof("U", [(0, 0), (6, 0), (6, 4), (0, 4)],
                   thickness=0.25, name="Top Roof")
        del roof
        two = compute_fem(b, mesh=0.4)
        one = compute_fem(_box(), mesh=0.4)
        gf_two = next(e for e in two.elements.values() if e["name"] == "South")
        gf_one = next(e for e in one.elements.values() if e["name"] == "South")
        assert two.balance == pytest.approx(1.0, abs=0.01)
        assert gf_two["u"] > gf_one["u"] * 1.5   # carries the upper box

    def test_elevated_story_without_support_fails_preflight(self):
        b = Building(name="Floating")
        b.add_story("U", height=3.0, elevation=3.0)
        b.add_wall("U", (0, 0), (6, 0), height=3.0, thickness=0.3,
                   name="Sky Wall", is_external=True, load_bearing=True)
        b.add_roof("U", [(0, 0), (6, 0), (6, 4), (0, 4)],
                   thickness=0.25, name="Sky Roof")
        with pytest.raises(FemPreflightError, match="Sky Wall"):
            compute_fem(b, mesh=0.4)


class TestPreflight:
    def test_non_axis_aligned_wall_fails_loud(self):
        b = _box()
        b.add_wall("GF", (0, 0), (3, 2.5), height=3.0, thickness=0.3,
                   name="Diagonal", is_external=False, load_bearing=True)
        with pytest.raises(FemPreflightError, match="Diagonal"):
            compute_fem(b, mesh=0.4)

    def test_quad_ceiling_is_enforced(self):
        with pytest.raises(FemSizeError):
            compute_fem(_box(), mesh=0.4, max_quads=50)


class TestBeams:
    def test_beam_over_opening_reports_moment(self):
        b = _box()
        b.add_window("GF", "South", position=1.0, width=3.0, height=0.75,
                     sill_height=2.05, name="Band")
        b.add_beam_over("GF", "Band", depth=0.5)
        res = compute_fem(b, mesh=0.3)
        beam = next(e for e in res.elements.values() if e["kind"] == "beam")
        assert beam["M"] > 0
        assert 0.0 < beam["u"] < 1.5
        assert res.balance == pytest.approx(1.0, abs=0.01)


class TestCodexReviewRules:
    def test_non_rc_beam_is_unresolved_band_stays(self):
        b = _box()
        b.add_window("GF", "South", position=1.0, width=3.0, height=0.75,
                     sill_height=2.05, name="Band")
        beam = b.add_beam_over("GF", "Band", depth=0.5)
        beam.material = "steel"
        res = compute_fem(b, mesh=0.3)
        assert not any(e["kind"] == "beam" for e in res.elements.values())
        assert any("steel" in u for u in res.unresolved)
        assert res.balance == pytest.approx(1.0, abs=0.01)

    def test_short_wall_does_not_vanish(self):
        b = _box()
        b.add_wall("GF", (2, 2), (4, 2), height=1.1, thickness=0.2,
                   name="Parapet", is_external=False, load_bearing=True)
        res = compute_fem(b, mesh=0.4)
        assert res.find("Parapet")["u"] >= 0.0

    def test_diagonal_roof_outline_fails_preflight(self):
        b = _box()
        b.add_roof("GF", [(0, 0), (6, 0), (3, 4)], thickness=0.25,
                   name="Wedge")
        with pytest.raises(FemPreflightError, match="Wedge"):
            compute_fem(b, mesh=0.4)

    def test_disjoint_adjacent_story_fails_preflight(self):
        b = _box()   # box occupies x 0..6, y 0..4
        b.add_story("Wing", height=3.0, elevation=3.0)
        b.add_wall("Wing", (20, 20), (26, 20), height=3.0, thickness=0.3,
                   name="Far Wall", is_external=True, load_bearing=True)
        with pytest.raises(FemPreflightError, match="Far Wall"):
            compute_fem(b, mesh=0.4)

    def test_naked_band_governs_in_tension(self):
        # a wide opening with NO beam: the band above must show tensile
        # governance and exceed its axial-only reading (fem-xray.md,
        # tension-aware coloring decision 2026-08-08)
        b = _box()
        b.add_window("GF", "South", position=1.0, width=3.0, height=0.75,
                     sill_height=2.05, name="Band")
        res = compute_fem(b, mesh=0.3)
        south = res.find("South")
        assert south["u_tension"] > south["u_axial"]
        assert south["u"] == pytest.approx(
            max(south["u_tension"], south["u_axial"]))
        tension_quads = [q for q in res.field["quads"]
                         if q["e"] == next(g for g, e in res.elements.items()
                                           if e["name"] == "South")
                         and q["g"] == 1 and q["u"] > 0.1]
        assert tension_quads, "no horizontal-tension fragments in the band"


class TestPrincipalStress:
    """Mohr's-circle helper — the basis of the diagonal-tension channel.

    Eigenvalues are invariant to the sign of the shear term and to
    swapping the two normal components, which is what makes the channel
    safe against PyNite's local component convention (plan review
    2026-08-08: its own comment disagrees with its code).
    """

    def test_pure_shear_is_diagonal_tension_at_45_degrees(self):
        s1, s2, theta = _principal(0.0, 0.0, 500.0)
        assert s1 == pytest.approx(500.0)
        assert s2 == pytest.approx(-500.0)
        assert abs(theta) == pytest.approx(45.0)

    def test_uniaxial_states_keep_their_axis(self):
        assert _principal(400.0, 0.0, 0.0)[2] == pytest.approx(0.0)
        assert abs(_principal(0.0, 400.0, 0.0)[2]) == pytest.approx(90.0)

    def test_hydrostatic_state_is_degenerate_but_finite(self):
        s1, s2, theta = _principal(300.0, 300.0, 0.0)
        assert s1 == pytest.approx(300.0) and s2 == pytest.approx(300.0)
        assert -90.0 <= theta <= 90.0      # defined, not NaN

    def test_shear_sign_does_not_change_magnitudes(self):
        a = _principal(200.0, -100.0, 150.0)
        b = _principal(200.0, -100.0, -150.0)
        assert a[0] == pytest.approx(b[0]) and a[1] == pytest.approx(b[1])

    def test_rotation_invariance(self):
        import math
        sx, sy, txy = 300.0, -100.0, 120.0
        for deg in (17.0, 45.0, 63.0):
            c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
            rx = sx * c * c + sy * s * s + 2 * txy * s * c
            ry = sx * s * s + sy * c * c - 2 * txy * s * c
            rt = (sy - sx) * s * c + txy * (c * c - s * s)
            assert _principal(rx, ry, rt)[0] == pytest.approx(
                _principal(sx, sy, txy)[0])


class TestShearAndTwistChannels:
    """Owner 2026-08-08 (#4): "I want all FEM elements visible, what's
    missing" — in-plane shear in walls and twist in plates used to read
    0% because Txy and Mxy were discarded."""

    def test_wall_reports_a_shear_diagnostic(self):
        b = _box()
        b.add_window("GF", "South", position=1.0, width=3.0, height=0.75,
                     sill_height=2.05, name="Band")
        res = compute_fem(b, mesh=0.3)
        south = res.find("South")
        # a STRESS, not a ratio: |txy|/fctd would read high on a wall in
        # heavy compression whose cracks are held shut (Gemini review)
        assert south["tau_max"] > 0.0        # was invisible before
        assert south["u"] >= south["u_tension"] >= 0.0

    def test_diagonal_tension_fragments_exist_near_the_opening(self):
        b = _box()
        b.add_window("GF", "South", position=1.0, width=3.0, height=0.75,
                     sill_height=2.05, name="Band")
        res = compute_fem(b, mesh=0.3)
        gid = next(g for g, e in res.elements.items() if e["name"] == "South")
        diag = [q for q in res.field["quads"]
                if q["e"] == gid and q["g"] == 4]
        assert len(diag) >= 5, "no diagonal-tension fragments in a pierced wall"
        assert max(q["u"] for q in diag) > 0.1     # not rounding noise
        assert all(q["s"] > 0 for q in diag)       # code 4 carries a TENSION

    def test_panel_element_value_includes_twist(self, box_result):
        # fragment coloring and the element number must not contradict:
        # the element design value has to see at least what the strips see
        roof = box_result.find("Roof")
        assert roof["m_principal_design"] >= max(roof["mx_design"],
                                                 roof["my_design"]) - 1e-9
        # `u == max(mx, my, mprinc)/cap` cannot fail given the line above
        # (mprinc dominates by construction) — assert the real contract:
        # the published moment IS the principal design moment.
        assert roof["M"] == pytest.approx(roof["m_principal_design"])
        assert roof["u"] == pytest.approx(
            roof["m_principal_design"] / roof["cap"])

    def test_not_modelled_list_is_published(self, box_result):
        joined = " ".join(box_result.not_modelled).lower()
        for topic in ("wind", "seismic", "buckling", "punching",
                      "foundation", "deflection"):
            assert topic in joined


class TestComponentLabelling:
    """The component codes are what the tooltip says out loud, so the
    bins and the degenerate cases are part of the contract."""

    @pytest.mark.parametrize(("angle", "code"), [
        (0.0, 1), (22.5, 1), (-22.5, 1), (22.51, 4), (45.0, 4),
        (-45.0, 4), (67.49, 4), (67.5, 2), (-90.0, 2), (90.0, 2),
    ])
    def test_bin_boundaries(self, angle, code):
        assert _tension_component(angle) == code

    def test_near_hydrostatic_state_is_not_labelled_diagonal(self):
        # a collapsed Mohr circle has NO principal direction; an absolute
        # epsilon against stresses of order 1e3 used to manufacture a
        # confident "diagonal tension" out of the last bits of the solve
        assert _tension_component(_principal(1e6, 1e6, 1e-6)[2]) != 4
        assert _tension_component(_principal(1e6, 1e6 + 1e-3, 0.0)[2]) != 2

    def test_solid_wall_base_is_governed_by_vertical_compression(self,
                                                                 box_result):
        gid = next(g for g, e in box_result.elements.items()
                   if e["name"] == "South")
        frags = [q for q in box_result.field["quads"] if q["e"] == gid]
        zmin = min(min(c[2] for c in q["c"]) for q in frags)
        base = [q for q in frags if min(c[2] for c in q["c"]) <= zmin + 1e-6]
        assert all(q["g"] == 0 for q in base)   # not relabelled by the new path
        assert all(q["s"] < 0 for q in base)    # s is a COMPRESSIVE stress
        assert box_result.find("South")["u"] == pytest.approx(
            box_result.find("South")["u_axial"])


class TestDesignValueContract:
    def test_tau_max_is_a_stress_not_a_ratio(self):
        b = _box()
        b.add_window("GF", "South", position=1.0, width=3.0, height=0.75,
                     sill_height=2.05, name="Band")
        south = compute_fem(b, mesh=0.3).find("South")
        assert "u_shear" not in south      # the rename IS the contract
        assert south["tau_max"] > 10.0     # kN/m2 — a ratio would read < 1

    def test_fragment_peaks_are_published_not_hidden(self, box_result):
        """Fragments legitimately exceed the element design value; the
        peak has to be visible so the difference is auditable rather than
        looking like a contradiction (Codex review)."""
        peak = defaultdict(float)
        for q in box_result.field["quads"]:
            peak[q["e"]] = max(peak[q["e"]], q["u"])
        for gid, e in box_result.elements.items():
            assert e["u_peak"] == pytest.approx(peak[gid], abs=1e-3)
            assert e["u_peak"] >= e["u"] - 1e-3

    def test_design_values_converge_between_meshes(self):
        """Overlap-weighted windows, so refining the mesh must not move
        the published numbers much. Measured 0.40 -> 0.25 on this pierced
        box: u_axial +4.2%, roof principal +8.0%, u_tension +13.4%,
        tau_max -15.6% (centre-based windows drifted up to 29%). The
        tension/shear pair stays looser because an opening corner is a
        genuine singularity — that caveat is in the spec, not hidden
        behind a tolerance nobody reads."""
        b = _box()
        b.add_window("GF", "South", position=1.0, width=3.0, height=0.75,
                     sill_height=2.05, name="Band")
        coarse = compute_fem(b, mesh=0.4)
        fine = compute_fem(b, mesh=0.25)
        for key in ("u_tension", "u_axial"):
            assert fine.find("South")[key] == pytest.approx(
                coarse.find("South")[key], rel=0.15), key
        assert fine.find("Roof")["m_principal_design"] == pytest.approx(
            coarse.find("Roof")["m_principal_design"], rel=0.15)
