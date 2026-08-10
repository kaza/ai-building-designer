"""E100-E103 seismic plausibility validators (specs/seismic-lateral.md S1).

One file per rule family, synthetic buildings, no project data.
E100 storey shear vs wall shear capacity (per direction, error)
E101 wall density vs EN 1998-1 Table 9.3 minima (error)
E102 torsional irregularity e0 > 0.30 r or r < ls (warning)
E103 lateral discontinuity: bearing wall with no aligned wall below (error)
"""

from archicad_builder.models import Building
from archicad_builder.project_config import Site
from archicad_builder.validators.phases import validate_seismic


def _findings(building, site, code):
    return [e for e in validate_seismic(building, site)
            if e.message.startswith(f"{code}: ")]


def _site(ag=0.15, country="BA", ground="B", **kw) -> Site:
    return Site(country=country, ag=ag, ground_type=ground, **kw)


def _box(wall_t=0.3, size=(6.0, 4.0), storeys=1) -> Building:
    b = Building(name="Box")
    sx, sy = size
    for i in range(storeys):
        sn = f"S{i}"
        b.add_story(sn, height=3.0, elevation=i * 3.0)
        for name, s, e in [
            (f"{sn} South", (0, 0), (sx, 0)), (f"{sn} East", (sx, 0), (sx, sy)),
            (f"{sn} North", (sx, sy), (0, sy)), (f"{sn} West", (0, sy), (0, 0)),
        ]:
            b.add_wall(sn, s, e, height=3.0, thickness=wall_t,
                       name=name, is_external=True, load_bearing=True)
        b.add_slab(sn, [(0, 0), (sx, 0), (sx, sy), (0, sy)], thickness=0.25,
                   name=f"{sn} Floor")
    top = f"S{storeys - 1}"
    roof = b.add_roof(top, [(0, 0), (sx, 0), (sx, sy), (0, sy)],
                      thickness=0.25, name="Roof")
    roof.span_direction = "x"
    return b


class TestE100BaseShear:
    def test_small_box_at_moderate_ag_passes(self):
        assert _findings(_box(), _site(ag=0.15), "E100") == []

    def test_high_ag_fails_the_weak_direction_first(self):
        # ag=0.4: Fb ~ 444 kN; y-capacity (2 x 4 m walls) 320 kN < demand,
        # x-capacity (2 x 6 m walls) 480 kN > demand
        found = _findings(_box(), _site(ag=0.4), "E100")
        assert len(found) == 1
        assert "direction y" in found[0].message

    def test_openings_reduce_shear_capacity(self):
        # a 2 m window on South cuts x-capacity 480 -> 400 < 444 demand
        b = _box()
        b.add_window("S0", "S0 South", position=2.0, width=2.0, height=1.2,
                     sill_height=0.9, name="Win")
        dirs = {f.message for f in _findings(b, _site(ag=0.4), "E100")}
        assert any("direction x" in m for m in dirs)
        assert any("direction y" in m for m in dirs)

    def test_no_site_no_findings(self):
        assert validate_seismic(_box(), None) == []


class TestE101WallDensity:
    def test_generous_walls_pass(self):
        assert _findings(_box(), _site(ag=0.05, ground="A"), "E101") == []

    def test_thin_walls_on_big_floor_fail(self):
        # 20 x 20 m, t=0.15: density per direction 40*0.15/400 = 1.5% < 2.0%
        b = _box(wall_t=0.15, size=(20.0, 20.0))
        found = _findings(b, _site(ag=0.05, ground="A"), "E101")
        assert len(found) == 2      # both directions

    def test_urm_not_acceptable_band_is_an_error(self):
        # ag*S = 0.4*1.2 = 0.48 g: beyond every Table 9.3 band for URM
        found = _findings(_box(), _site(ag=0.4), "E101")
        assert found and "not acceptable" in found[0].message


class TestE102Torsion:
    def test_symmetric_box_is_regular(self):
        assert _findings(_box(), _site(), "E102") == []

    def test_all_x_walls_on_one_edge_warns(self):
        # both x-aligned walls hug y=0; mass centroid stays at y=2
        b = Building(name="Skewed")
        b.add_story("S0", height=3.0, elevation=0.0)
        b.add_wall("S0", (0, 0), (6, 0), height=3.0, thickness=0.3,
                   name="South", load_bearing=True)
        b.add_wall("S0", (0, 0.5), (6, 0.5), height=3.0, thickness=0.3,
                   name="South2", load_bearing=True)
        b.add_wall("S0", (0, 0), (0, 4), height=3.0, thickness=0.3,
                   name="West", load_bearing=True)
        b.add_wall("S0", (6, 0), (6, 4), height=3.0, thickness=0.3,
                   name="East", load_bearing=True)
        b.add_slab("S0", [(0, 0), (6, 0), (6, 4), (0, 4)], thickness=0.25,
                   name="Floor")
        roof = b.add_roof("S0", [(0, 0), (6, 0), (6, 4), (0, 4)],
                          thickness=0.25, name="Roof")
        roof.span_direction = "x"
        found = _findings(b, _site(), "E102")
        assert found and found[0].severity == "warning"


class TestE103Continuity:
    def test_aligned_walls_pass(self):
        assert _findings(_box(storeys=2), _site(), "E103") == []

    def test_upper_wall_without_support_fails(self):
        b = _box(storeys=2)
        b.add_wall("S1", (2, 1), (5, 1), height=3.0, thickness=0.3,
                   name="Floating", load_bearing=True)
        found = _findings(b, _site(), "E103")
        assert len(found) == 1
        assert "Floating" in found[0].message

    def test_ground_storey_walls_are_exempt(self):
        # single storey: nothing above the lowest, nothing to check
        assert _findings(_box(storeys=1), _site(), "E103") == []

    def test_fully_cantilevered_upper_wall_is_flagged(self):
        # Codex code review 2026-08-10: a wall entirely OUTSIDE the lower
        # footprint on an ELEVATED storey is hanging in air, not on grade
        b = _box(storeys=2)
        b.add_wall("S1", (8, 1), (12, 1), height=3.0, thickness=0.3,
                   name="Air Wall", load_bearing=True)
        found = _findings(b, _site(), "E103")
        assert any("Air Wall" in f.message for f in found)


class TestE101StoreyCount:
    def test_basement_storeys_get_no_seismic_findings(self):
        # a rigid basement is braced by soil — E100/E101/E102 must not
        # judge it by Table 9.3 (Codex re-review 2026-08-10)
        b = _box(wall_t=0.15, size=(20.0, 20.0), storeys=2)
        site = _site(ag=0.10, seismic_base_elevation=3.0)
        for code in ("E100", "E101", "E102"):
            assert all("'S0'" not in f.message
                       for f in _findings(b, site, code))

    def test_rigid_basement_does_not_count_as_a_seismic_storey(self):
        # Codex code review 2026-08-10: Table 9.3 selects by ACTIVE
        # storeys above the seismic base, not by total storeys
        from archicad_builder.seismic import compute_seismic
        # ag*S = 0.10*1.2 = 0.12 -> Table 9.3 band <= 0.15:
        # 2 storeys need 5.0%, 1 storey needs 3.5%
        two = compute_seismic(_box(storeys=2), _site(ag=0.10))
        based = compute_seismic(_box(storeys=2),
                                _site(ag=0.10,
                                      seismic_base_elevation=3.0))
        assert two["storeys"][0]["x"]["density_min"] == 5.0
        assert based["storeys"][0]["x"]["density_min"] == 3.5
