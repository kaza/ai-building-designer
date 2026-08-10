"""Phase B structural loads — framework load takedown (specs/structural-plausibility.md).

compute_loads(building) returns per-element results: bearing walls (axial
utilization incl. self-weight, 8-bucket profile), beams (bending utilization
against their covering opening), roof slabs (1m-strip spanning check on the
max free span between bearing lines). Validator rules: E064 beam bending
util > 1.0, E065 roof slab util > 1.0, E066 wall axial util > 1.0.
Load model (documented assumptions): roof dead = min(t, 0.25)·25 + 2.0,
snow 1.32 kN/m², ULS 1.35G + 1.5Q. Fixtures are test-owned.
"""

import pytest

def by_name(loads: dict, name: str) -> dict:
    """loads.json is keyed by GlobalId (owner 2026-08-10); tests address
    elements by their human name via the record's own name field."""
    hits = [v for k, v in loads.items()
            if not k.startswith("_") and isinstance(v, dict)
            and v.get("name") == name]
    assert len(hits) == 1, f"{name}: {len(hits)} matches"
    return hits[0]


def key_of(loads: dict, name: str) -> str:
    return next(k for k, v in loads.items()
                if not k.startswith("_") and isinstance(v, dict)
                and v.get("name") == name)


from archicad_builder.models import Building
from archicad_builder.structural import compute_loads
from archicad_builder.validators.phases import validate_structural_loads


def _box_building(with_mid_wall=False, roof_thickness=0.25,
                  storey_height=3.0) -> Building:
    """6 × 4 m box: bearing walls all around, flat roof, optional interior
    bearing wall at x=3 splitting the roof span."""
    b = Building(name="Box")
    b.add_story("GF", height=storey_height, elevation=0.0)
    for name, s, e in [
        ("South", (0, 0), (6, 0)), ("East", (6, 0), (6, 4)),
        ("North", (6, 4), (0, 4)), ("West", (0, 4), (0, 0)),
    ]:
        b.add_wall("GF", s, e, height=storey_height, thickness=0.3,
                   name=name, is_external=True, load_bearing=True)
    if with_mid_wall:
        b.add_wall("GF", (3, 0), (3, 4), height=storey_height, thickness=0.2,
                   name="Mid", is_external=False, load_bearing=True)
    b.add_slab("GF", [(0, 0), (6, 0), (6, 4), (0, 4)], thickness=0.25,
               name="Floor")
    roof = b.add_roof("GF", [(0, 0), (6, 0), (6, 4), (0, 4)],
                      thickness=roof_thickness, name="Roof")
    roof.span_direction = "x"
    return b


class TestComputeLoads:
    def test_walls_get_axial_utilization_and_profile(self):
        loads = compute_loads(_box_building())
        south = by_name(loads, "South")
        assert south["kind"] == "wall"
        assert 0.0 < south["u"] < 1.0          # a box this small never fails
        assert len(south["profile"]) == 8
        assert south["q"] > 0

    def test_interior_bearing_wall_halves_the_facade_load(self):
        without = compute_loads(_box_building(with_mid_wall=False))
        withmid = compute_loads(_box_building(with_mid_wall=True))
        # east/west walls' tributary shrinks when the mid wall takes over
        assert (by_name(withmid, "East")["q"]
                < by_name(without, "East")["q"])

    def test_beam_bending_utilization(self):
        b = _box_building()
        b.add_window("GF", "South", position=1.0, width=3.0, height=0.75,
                     sill_height=2.05, name="Band")
        b.add_beam_over("GF", "Band", depth=0.5)
        loads = compute_loads(b)
        beam = by_name(loads, "RB Band")
        assert beam["kind"] == "beam"
        assert 0.0 < beam["u"] < 1.0
        assert beam["M"] > 0

    def test_roof_slab_gets_spanning_utilization(self):
        loads = compute_loads(_box_building())
        roof = by_name(loads, "Roof")
        assert roof["kind"] == "slab"
        # 6x4 box spanning x: governing span ~6m
        assert 0.0 < roof["u"] < 1.0
        assert roof["span"] == pytest.approx(6.0, abs=0.5)

    def test_mid_wall_cuts_the_roof_span(self):
        without = compute_loads(_box_building(with_mid_wall=False))
        withmid = compute_loads(_box_building(with_mid_wall=True))
        assert (by_name(withmid, "Roof")["span"]
                < by_name(without, "Roof")["span"])

    def test_roof_dead_load_capped_at_25cm(self):
        # a 0.45 "visual" roof must not weigh more than a 0.25 structural one
        thick = compute_loads(_box_building(roof_thickness=0.45))
        norm = compute_loads(_box_building(roof_thickness=0.25))
        assert (by_name(thick, "South")["q"]
                == pytest.approx(by_name(norm, "South")["q"]))


class TestStructuralValidators:
    def test_healthy_box_is_quiet(self):
        assert validate_structural_loads(_box_building()) == []

    def test_overspanned_roof_fires_e065(self):
        b = Building(name="Hangar")
        b.add_story("GF", height=3.0, elevation=0.0)
        for name, s, e in [
            ("South", (0, 0), (14, 0)), ("East", (14, 0), (14, 12)),
            ("North", (14, 12), (0, 12)), ("West", (0, 12), (0, 0)),
        ]:
            b.add_wall("GF", s, e, height=3.0, thickness=0.3,
                       name=name, is_external=True, load_bearing=True)
        roof = b.add_roof("GF", [(0, 0), (14, 0), (14, 12), (0, 12)],
                          thickness=0.25, name="Big Roof")
        roof.span_direction = "x"  # 14m one-way: hopeless, as intended
        errors = [e for e in validate_structural_loads(b)
                  if "E065" in e.message]
        assert len(errors) == 1
        assert "Big Roof" in errors[0].message

    def test_overloaded_beam_fires_e064(self):
        b = _box_building()
        b.add_window("GF", "South", position=0.5, width=5.0, height=0.75,
                     sill_height=2.05, name="Huge Band")
        b.add_beam_over("GF", "Huge Band", depth=0.25)  # far too shallow
        errors = [e for e in validate_structural_loads(b)
                  if "E064" in e.message]
        assert len(errors) == 1

    def test_undeclared_span_direction_is_unresolved_not_error(self):
        b = _box_building()
        b.get_story("GF").roofs[0].span_direction = None
        loads = compute_loads(b)
        assert not [v for k, v in loads.items()
                    if not k.startswith("_") and isinstance(v, dict)
                    and v.get("name") == "Roof"]
        assert len(loads["_unresolved"]) == 1   # the roof, by gid
        assert [e for e in validate_structural_loads(b)
                if "E065" in e.message] == []

    def test_cantilever_governs_with_double_moment(self):
        # roof extends 4m past the east wall, no support: M = qL^2/2 = 8q
        # beats the 6m interior span's qL^2/8 = 4.5q -> cantilever governs
        b = _box_building()
        b.get_story("GF").roofs[0].outline.vertices[1].x = 10.0
        b.get_story("GF").roofs[0].outline.vertices[2].x = 10.0
        loads = compute_loads(b)
        roof = by_name(loads, "Roof")
        assert roof["cantilever"] is True
        assert roof["span"] == pytest.approx(4.0, abs=0.4)

    def test_load_conservation_on_simple_box(self):
        loads = compute_loads(_box_building())
        assert by_name(loads, "Roof")["balance"] == pytest.approx(1.0, abs=0.15)

    def test_non_rc_beam_is_unresolved(self):
        b = _box_building()
        b.add_window("GF", "South", position=1.0, width=3.0, height=0.75,
                     sill_height=2.05, name="Band")
        beam = b.add_beam_over("GF", "Band", depth=0.5)
        beam.material = "steel"
        loads = compute_loads(b)
        assert len(loads["_unresolved"]) == 1   # the beam, by gid

    def test_beam_without_load_data_is_not_checked(self):
        # a beam not over any opening has no bending model in Phase B
        b = _box_building()
        b.add_beam("GF", (1, 2), (5, 2), width=0.3, depth=0.3, name="Free")
        assert [e for e in validate_structural_loads(b)
                if "E064" in e.message] == []
