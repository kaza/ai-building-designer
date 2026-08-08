"""FEM X-ray core (specs/fem-xray.md) — building.json -> plate model.

compute_fem(building, mesh=...) meshes bearing walls / beams / slabs /
roofs as conforming quads, solves ULS gravity via PyNite, and returns
per-element design utilizations (keyed by global_id) plus a per-quad
field. Grounding: only stories at elevation <= 0 may ground; stories
above must sit on a vertically adjacent story or preflight fails.
Load accounting: intended vs attached vs reacted; dropped > 1% is a
typed error. Fixtures are test-owned; coarse meshes keep this bounded.
"""

import pytest

from archicad_builder.fem import (
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
