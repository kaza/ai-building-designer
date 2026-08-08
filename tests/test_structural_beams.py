"""Beams over openings — E060/E061 (specs/structural-plausibility.md).

E062: an opening ≥ 1.25 m wide on a load-bearing wall needs a beam over
it: parallel (±15°), laterally within 0.15 m of the wall axis, covering
the opening extent + ≥ 0.10 m bearing each side, wide enough for the wall
(width ≥ thickness − 0.05), and above the opening head
(z_top − depth ≥ head − 0.05). E063: clear span / depth within the
material limit (rc 15, steel 20, timber 12). Fixtures are test-owned.
"""

import pytest

from archicad_builder.models import (
    Beam,
    Building,
    Door,
    Point2D,
    Story,
    Wall,
    Window,
)
from archicad_builder.validators.phases import validate_phase6_vertical


def _errs(building: Building, code: str) -> list:
    return [e for e in validate_phase6_vertical(building)
            if code in e.message]


def _fixture(openings=None, beams=None, load_bearing=True):
    """One storey, one 6m bearing wall along y=0, storey height 3.0."""
    wall = Wall(
        name="Bearing South", start=Point2D(x=0, y=0), end=Point2D(x=6, y=0),
        height=3.0, thickness=0.3, load_bearing=load_bearing,
    )
    windows = []
    doors = []
    for o in openings or []:
        if isinstance(o, Window):
            o.wall_id = wall.global_id
            windows.append(o)
        else:
            o.wall_id = wall.global_id
            doors.append(o)
    ground = Story(
        name="Ground", elevation=0.0, height=3.0,
        walls=[wall], windows=windows, doors=doors, beams=beams or [],
    )
    # single storey on purpose: E060/E061 must not hide behind the
    # two-storey guard that E050-E052 need
    return Building(name="Fixture", stories=[ground])


def _band_window(width=2.5, position=1.0, sill=2.05, height=0.75):
    return Window(name="Band", wall_id="", position=position, width=width,
                  height=height, sill_height=sill)


def _beam(x0=0.8, x1=3.8, y=0.0, width=0.3, depth=0.4, z_top=3.2,
          material="rc"):
    # default z_top 3.2 = an UPSTAND: the band-window head sits at 2.80 on
    # a 3.0 wall, so a covering beam must rise into the roof zone — the
    # central lesson of the load-takedown experiment
    return Beam(name="Ring", start=Point2D(x=x0, y=y), end=Point2D(x=x1, y=y),
                width=width, depth=depth, z_top=z_top, material=material)


class TestBeamModel:
    def test_beam_defaults_and_fields(self):
        b = _beam()
        assert b.depth == 0.4 and b.width == 0.3 and b.material == "rc"

    def test_builder_add_beam(self):
        bld = Building(name="B")
        bld.add_story("S", height=3.0, elevation=0.0)
        beam = bld.add_beam("S", (0, 0), (4, 0), width=0.3, depth=0.5,
                            name="Ring Beam")
        story = bld.get_story("S")
        assert story.beams == [beam]
        assert beam.z_top == 3.0  # defaults to storey height


class TestE062MissingBeam:
    def test_wide_opening_without_beam_errors(self):
        b = _fixture(openings=[_band_window(width=2.5)])
        errors = _errs(b, "E062")
        assert len(errors) == 1
        assert "Band" in errors[0].message

    def test_wide_opening_with_covering_beam_passes(self):
        # opening x 1.0-3.5, beam x 0.8-3.8 covers + bearing
        b = _fixture(openings=[_band_window(width=2.5)],
                     beams=[_beam(0.8, 3.8)])
        assert _errs(b, "E062") == []

    def test_narrow_opening_needs_no_beam(self):
        b = _fixture(openings=[_band_window(width=1.0)])
        assert _errs(b, "E062") == []

    def test_opening_on_non_bearing_wall_needs_no_beam(self):
        b = _fixture(openings=[_band_window(width=2.5)], load_bearing=False)
        assert _errs(b, "E062") == []

    def test_beam_with_insufficient_bearing_fails(self):
        # beam ends exactly at the opening edges: no 0.1m bearing
        b = _fixture(openings=[_band_window(width=2.5)],
                     beams=[_beam(1.0, 3.5)])
        assert len(_errs(b, "E062")) == 1

    def test_beam_below_opening_head_fails(self):
        # head at 2.80; beam bottom 2.4 - 0.0? z_top 2.6, depth 0.4 -> bottom 2.2
        b = _fixture(openings=[_band_window(width=2.5)],
                     beams=[_beam(0.8, 3.8, z_top=2.6)])
        assert len(_errs(b, "E062")) == 1

    def test_offset_beam_fails(self):
        # laterally 0.4m off the wall axis
        b = _fixture(openings=[_band_window(width=2.5)],
                     beams=[_beam(0.8, 3.8, y=0.4)])
        assert len(_errs(b, "E062")) == 1

    def test_perpendicular_beam_fails(self):
        beam = Beam(name="Cross", start=Point2D(x=2, y=-2),
                    end=Point2D(x=2, y=2), width=0.3, depth=0.4, z_top=3.0)
        b = _fixture(openings=[_band_window(width=2.5)], beams=[beam])
        assert len(_errs(b, "E062")) == 1

    def test_too_narrow_beam_fails(self):
        # wall 0.30 thick, beam only 0.15 wide
        b = _fixture(openings=[_band_window(width=2.5)],
                     beams=[_beam(0.8, 3.8, width=0.15)])
        assert len(_errs(b, "E062")) == 1

    def test_wide_door_needs_beam_too(self):
        door = Door(name="Garage Door", wall_id="", position=1.0,
                    width=2.4, height=2.1)
        b = _fixture(openings=[door])
        assert len(_errs(b, "E062")) == 1
        b = _fixture(openings=[door.model_copy()],
                     beams=[_beam(0.8, 3.6, z_top=2.6, depth=0.4)])
        # beam bottom 2.2 >= door head 2.1 - 0.05 ✓
        assert _errs(b, "E062") == []


class TestE063Slenderness:
    def test_slender_beam_over_opening_errors(self):
        # span 2.5m, depth 0.12 -> L/d ~ 20.8 > 15 (rc)
        b = _fixture(openings=[_band_window(width=2.5)],
                     beams=[_beam(0.8, 3.8, depth=0.12, z_top=3.0)])
        errors = _errs(b, "E063")
        assert len(errors) == 1

    def test_stocky_beam_passes(self):
        # span 2.5m, depth 0.4 -> L/d 6.25
        b = _fixture(openings=[_band_window(width=2.5)],
                     beams=[_beam(0.8, 3.8, depth=0.4)])
        assert _errs(b, "E063") == []

    def test_steel_beam_gets_higher_limit(self):
        # span 2.5, depth 0.14: rc fails (17.9 > 15), steel passes (< 20)
        rc = _fixture(openings=[_band_window(width=2.5)],
                      beams=[_beam(0.8, 3.8, depth=0.14)])
        steel = _fixture(openings=[_band_window(width=2.5)],
                         beams=[_beam(0.8, 3.8, depth=0.14, material="steel")])
        assert len(_errs(rc, "E063")) == 1
        assert _errs(steel, "E063") == []

    def test_beam_not_over_any_opening_is_not_checked(self):
        # slender but spans a solid wall stretch — Phase A stays quiet
        b = _fixture(openings=[], beams=[_beam(0.5, 5.5, depth=0.1)])
        assert _errs(b, "E063") == []


class TestTemplateCopy:
    def test_stamp_floor_template_copies_beams(self):
        from archicad_builder.generators.template import stamp_floor_template

        bld = Building(name="B")
        bld.add_story("T", height=3.0, elevation=0.0)
        bld.add_story("U", height=3.0, elevation=3.0)
        bld.add_beam("T", (0, 0), (4, 0), width=0.3, depth=0.5, name="RB")
        stamp_floor_template(bld, "T", ["U"])
        upper = bld.get_story("U")
        assert len(upper.beams) == 1
        assert upper.beams[0].global_id != bld.get_story("T").beams[0].global_id


class TestBeamIfcExport:
    def test_beam_round_trips_building_json(self):
        bld = Building(name="B")
        bld.add_story("S", height=3.0, elevation=0.0)
        bld.add_beam("S", (0, 0), (4, 0), width=0.3, depth=0.5, name="RB")
        doc = bld.model_dump(mode="json")
        again = Building.model_validate(doc)
        assert again.stories[0].beams[0].name == "RB"

    def test_beam_exports_as_ifcbeam(self, tmp_path):
        # diagonal beam on a basement storey: placement must be absolute
        # (elevation + z_top - depth), geometry must survive rotation
        pytest.importorskip("ifcopenshell")
        from archicad_builder.export.ifc import IFCExporter

        bld = Building(name="B")
        bld.add_story("S", height=3.0, elevation=-3.0)
        bld.add_beam("S", (1, 1), (4, 4), width=0.3, depth=0.5, name="RB",
                     z_top=3.2)
        out = tmp_path / "b.ifc"
        IFCExporter(bld).export(str(out))
        import ifcopenshell
        f = ifcopenshell.open(str(out))
        beams = f.by_type("IfcBeam")
        assert len(beams) == 1
        assert beams[0].Name == "RB"
        z = beams[0].ObjectPlacement.RelativePlacement.Location.Coordinates[2]
        assert abs(z - (-3.0 + 3.2 - 0.5)) < 1e-6

    def test_zero_length_beam_rejected(self):
        with pytest.raises(Exception):
            Beam(name="dot", start=Point2D(x=1, y=1), end=Point2D(x=1, y=1),
                 width=0.3, depth=0.4, z_top=3.0)
