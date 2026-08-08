"""E050 — load-bearing walls need support only where a storey exists below.

A bearing wall (or the portion of one) standing OUTSIDE the lower storey's
slab footprint sits on foundations/grade and needs no aligned wall below;
the portion OVER the footprint must be covered by parallel load-bearing
walls below. A lower storey without slab geometry falls back to the legacy
whole-wall alignment check (missing data must not silently exempt).
Fixtures are test-owned per specs/test-fixtures.md.
"""

from archicad_builder.models import (
    Building,
    Point2D,
    Polygon2D,
    Slab,
    Story,
    Wall,
)
from archicad_builder.validators.phases import validate_phase6_vertical


def _e050(building: Building) -> list:
    return [e for e in validate_phase6_vertical(building)
            if "E050" in e.message]


def _wall(name, x0, y0, x1, y1, load_bearing=True, thickness=0.3):
    return Wall(
        name=name, start=Point2D(x=x0, y=y0), end=Point2D(x=x1, y=y1),
        height=3.0, thickness=thickness, load_bearing=load_bearing,
    )


def _slab(vertices, thickness=0.25):
    return Slab(
        name="Basement Slab",
        outline=Polygon2D(vertices=[Point2D(x=x, y=y) for x, y in vertices]),
        thickness=thickness,
    )


BASEMENT_FOOTPRINT = [(4, 0), (10, 0), (10, 8), (4, 8)]


def _building(gf_walls, basement_walls, basement_slabs=None):
    basement = Story(
        name="Basement", elevation=-3.0, height=3.0,
        walls=basement_walls,
        slabs=basement_slabs if basement_slabs is not None
        else [_slab(BASEMENT_FOOTPRINT)],
    )
    ground = Story(name="Ground", elevation=0.0, height=3.0, walls=gf_walls)
    return Building(name="Fixture", stories=[basement, ground])


class TestE050PartialBasement:
    def test_wall_fully_outside_footprint_is_on_grade(self):
        gf = [_wall("West of basement", 0, 4, 3, 4)]
        assert _e050(_building(gf, [])) == []

    def test_wall_over_basement_without_support_errors(self):
        gf = [_wall("Over open basement", 5, 4, 9, 4)]
        errors = _e050(_building(gf, []))
        assert len(errors) == 1
        assert "Over open basement" in errors[0].message

    def test_wall_over_basement_with_aligned_support_passes(self):
        gf = [_wall("Supported", 5, 4, 9, 4)]
        below = [_wall("Basement mid wall", 5, 4, 9, 4)]
        assert _e050(_building(gf, below)) == []

    def test_wall_riding_the_footprint_boundary_needs_support(self):
        gf = [_wall("On boundary", 4, 0, 4, 8)]
        errors = _e050(_building(gf, []))
        assert len(errors) == 1
        below = [_wall("Basement west wall", 4, 0, 4, 8)]
        assert _e050(_building(gf, below)) == []

    def test_half_inside_wall_needs_support_only_inside(self):
        gf = [_wall("Half in", 2, 4, 8, 4)]
        # support covering exactly the inside portion (x 4..8)
        below = [_wall("Basement partial", 4, 4, 8, 4)]
        assert _e050(_building(gf, below)) == []
        # no support at all -> the inside 4m fails
        assert len(_e050(_building(gf, []))) == 1

    def test_perpendicular_wall_below_is_not_support(self):
        gf = [_wall("N-S over basement", 6, 1, 6, 7)]
        below = [_wall("E-W crossing", 4, 4, 10, 4)]
        assert len(_e050(_building(gf, below))) == 1

    def test_lower_storey_without_slabs_keeps_legacy_check(self):
        gf = [_wall("Unaligned", 0, 4, 3, 4)]
        b = _building(gf, [], basement_slabs=[])
        assert len(_e050(b)) == 1
