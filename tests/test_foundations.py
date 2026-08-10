"""S3 foundations — StripFooting element + E104-E107 (specs/foundations.md).

E104 bearing wall on the lowest storey without a covering footing
     (BASESLAB containment exempts — the slab grounds it)
E105 factored bearing pressure (worst strip-engine station + gamma_G x
     footing self-weight) / width > sigma_rd
E106 sliding: base shear vs friction_mu x DEAD weight only (live load
     must not be credited as favorable friction — Codex plan review)
E107 rigid-body overturning about the foundation footprint toe,
     stabilizing/overturning >= 1.1
No [site.soil] -> unresolved, no findings.
"""

import pytest

from archicad_builder.models import Building
from archicad_builder.project_config import Site, Soil
from archicad_builder.validators.phases import validate_foundations


def _site(ag=0.15, sigma_rd=200.0, mu=0.5, **kw) -> Site:
    return Site(country="BA", ag=ag, ground_type="B",
                soil=Soil(sigma_rd=sigma_rd, friction_mu=mu), **kw)


def _findings(building, site, code):
    return [e for e in validate_foundations(building, site)
            if e.message.startswith(f"{code}: ")]


def _box(with_footings=True, footing_width=0.6, storeys=1,
         baseslab=False) -> Building:
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
        if i > 0 or baseslab:
            b.add_slab(sn, [(0, 0), (6, 0), (6, 4), (0, 4)], thickness=0.25,
                       name=f"{sn} Floor",
                       slab_type="BASESLAB" if (i == 0 and baseslab)
                       else "FLOOR")
    top = f"S{storeys - 1}"
    roof = b.add_roof(top, [(0, 0), (6, 0), (6, 4), (0, 4)],
                      thickness=0.25, name="Roof")
    roof.span_direction = "x"
    if with_footings:
        for name, s, e in [
            ("F South", (0, 0), (6, 0)), ("F East", (6, 0), (6, 4)),
            ("F North", (6, 4), (0, 4)), ("F West", (0, 4), (0, 0)),
        ]:
            b.add_footing("S0", s, e, width=footing_width, height=0.5,
                          name=name)
    return b


class TestSchema:
    def test_footing_round_trips_through_json(self, tmp_path):
        b = _box()
        p = tmp_path / "building.json"
        b.save(p)
        loaded = Building.load(p)
        footings = loaded.stories[0].footings
        assert len(footings) == 4
        assert footings[0].width == pytest.approx(0.6)

    def test_old_buildings_without_footings_still_load(self, tmp_path):
        b = _box(with_footings=False)
        p = tmp_path / "building.json"
        b.save(p)
        assert Building.load(p).stories[0].footings == []


class TestIfcExport:
    def test_footing_exports_as_ifc_strip_footing(self, tmp_path):
        import ifcopenshell

        from archicad_builder.export.ifc import IFCExporter

        b = _box()
        path = tmp_path / "box.ifc"
        IFCExporter(b).export(path)
        ifc = ifcopenshell.open(str(path))
        footings = ifc.by_type("IfcFooting")
        assert len(footings) == 4
        assert footings[0].PredefinedType == "STRIP_FOOTING"
        exported_ids = {f.GlobalId for f in footings}
        assert exported_ids == {f.global_id
                                for f in b.stories[0].footings}


class TestE104Coverage:
    def test_footed_walls_pass(self):
        assert _findings(_box(), _site(), "E104") == []

    def test_missing_footings_fail_per_wall(self):
        found = _findings(_box(with_footings=False), _site(), "E104")
        assert len(found) == 4

    def test_narrow_footing_fails_containment(self):
        # width 0.25 < wall thickness 0.3: wall edge overhangs the footing
        found = _findings(_box(footing_width=0.25), _site(), "E104")
        assert len(found) == 4

    def test_baseslab_exempts_walls(self):
        b = _box(with_footings=False, baseslab=True)
        assert _findings(b, _site(), "E104") == []

    def test_no_soil_config_no_findings(self):
        site = Site(country="BA", ag=0.15, ground_type="B")
        assert validate_foundations(_box(with_footings=False), site) == []
        assert validate_foundations(_box(with_footings=False), None) == []


class TestE105Bearing:
    def test_generous_soil_passes(self):
        assert _findings(_box(), _site(sigma_rd=300.0), "E105") == []

    def test_weak_soil_fails(self):
        found = _findings(_box(), _site(sigma_rd=30.0), "E105")
        assert found and "sigma_rd" in found[0].message


class TestE106Sliding:
    def test_moderate_ag_passes(self):
        assert _findings(_box(), _site(ag=0.1), "E106") == []

    def test_high_ag_low_friction_fails(self):
        found = _findings(_box(), _site(ag=0.4, mu=0.2), "E106")
        assert len(found) == 2      # both directions


class TestE107Overturning:
    def test_squat_box_passes(self):
        assert _findings(_box(), _site(), "E107") == []

    def test_tall_narrow_tower_fails(self):
        # 2 m wide, 12 m tall, strong shaking: rigid-body overturn
        b = Building(name="Tower")
        for i in range(4):
            sn = f"S{i}"
            b.add_story(sn, height=3.0, elevation=i * 3.0)
            b.add_wall(sn, (0, 0), (6, 0), height=3.0, thickness=0.2,
                       name=f"{sn} A", load_bearing=True)
            b.add_wall(sn, (0, 2), (6, 2), height=3.0, thickness=0.2,
                       name=f"{sn} B", load_bearing=True)
            b.add_wall(sn, (0, 0), (0, 2), height=3.0, thickness=0.2,
                       name=f"{sn} C", load_bearing=True)
            b.add_wall(sn, (6, 0), (6, 2), height=3.0, thickness=0.2,
                       name=f"{sn} D", load_bearing=True)
            if i > 0:
                b.add_slab(sn, [(0, 0), (6, 0), (6, 2), (0, 2)],
                           thickness=0.2, name=f"{sn} Floor")
        roof = b.add_roof("S3", [(0, 0), (6, 0), (6, 2), (0, 2)],
                          thickness=0.2, name="Roof")
        roof.span_direction = "x"
        b.add_footing("S0", (0, 0), (6, 0), width=0.5, height=0.5, name="FA")
        b.add_footing("S0", (0, 2), (6, 2), width=0.5, height=0.5, name="FB")
        b.add_footing("S0", (0, 0), (0, 2), width=0.5, height=0.5, name="FC")
        b.add_footing("S0", (6, 0), (6, 2), width=0.5, height=0.5, name="FD")
        found = _findings(b, _site(ag=0.35), "E107")
        # the 2 m plan direction tips long before the 6 m one
        assert found
        assert any("direction y" in f.message for f in found)
