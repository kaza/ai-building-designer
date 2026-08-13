"""Column element — phase C1 (specs/columns.md).

Two placement modes, one element: a tie-column cast against its host
wall (rc only, both sides >= 0.15 m per EN 1998-1 §9.5.3(3), full
storey height) or a free-standing post (rc or steel, never a tie).
Columns flow model -> IFC (IfcColumn) -> render metadata -> seismic
mass (material-exclusively) -> E108 support-path check. They carry NO
shear capacity and are NOT meshed in the FEM.
"""

import pytest

from archicad_builder.models import Building
from archicad_builder.models.elements import Column
from archicad_builder.project_config import Site, Soil
from archicad_builder.seismic import compute_seismic
from archicad_builder.validators.phases import (
    validate_all_phases,
    validate_columns_support,
    validate_foundations,
    validate_seismic,
)


def _site(ag=0.15, **kw) -> Site:
    return Site(country="BA", ag=ag, ground_type="B", **kw)


def _soil_site(**kw) -> Site:
    return _site(soil=Soil(sigma_rd=200.0), **kw)


def _box(storeys=1, with_footings=False, baseslab=False) -> Building:
    """6 x 4 m box, 0.3 m bearing perimeter walls, 0.25 m slabs/roof."""
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
            b.add_footing("S0", s, e, width=0.6, height=0.5, name=name)
    return b


def _findings(building, code, site=None):
    return [e for e in validate_all_phases(building, site=site)
            if e.message.startswith(f"{code}: ")]


class TestSchema:
    def test_tie_column_via_builder(self):
        b = _box()
        c = b.add_column("S0", wall="S0 South", along=3.0,
                         width=0.6, depth=0.2, name="T1")
        assert b.stories[0].columns == [c]
        assert c.wall_id == b.stories[0].get_wall_by_name("S0 South").global_id
        assert c.is_tie
        assert c.material == "rc"

    def test_free_column_via_builder(self):
        b = _box()
        c = b.add_column("S0", at=(2.0, 2.0), width=0.2, depth=0.2,
                         material="steel", height=2.5, name="Post")
        assert not c.is_tie
        assert c.at.x == 2.0 and c.at.y == 2.0
        assert c.height == 2.5

    def test_name_must_be_non_empty(self):
        # identity/reconcile and renderer metadata are name-keyed
        with pytest.raises(ValueError, match="name"):
            Column(width=0.3, depth=0.3, at={"x": 1, "y": 1})

    def test_names_unique_per_storey(self):
        b = _box()
        b.add_column("S0", at=(2, 2), width=0.3, depth=0.3, name="C1")
        with pytest.raises(ValueError, match="C1"):
            b.add_column("S0", at=(3, 3), width=0.3, depth=0.3, name="C1")

    def test_exactly_one_placement_mode(self):
        with pytest.raises(ValueError):
            Column(name="C", width=0.3, depth=0.3)          # neither
        with pytest.raises(ValueError):
            Column(name="C", width=0.3, depth=0.3,          # both
                   wall_id="x" * 22, along=1.0, at={"x": 1, "y": 1})
        with pytest.raises(ValueError):
            Column(name="C", width=0.3, depth=0.3, wall_id="x" * 22)  # no along

    def test_tie_must_be_rc(self):
        # §9.5.3: confining elements are cast concrete — steel never ties
        with pytest.raises(ValueError, match="rc"):
            Column(name="T", width=0.3, depth=0.3, material="steel",
                   wall_id="x" * 22, along=1.0)

    def test_tie_sides_at_least_150mm(self):
        # EN 1998-1 §9.5.3(3): a 60x10 has the area and fails the clause
        with pytest.raises(ValueError, match="0.15"):
            Column(name="T", width=0.6, depth=0.1,
                   wall_id="x" * 22, along=1.0)

    def test_tie_height_is_always_full_storey(self):
        # a partial-height "confining" element is not one
        with pytest.raises(ValueError, match="height"):
            Column(name="T", width=0.3, depth=0.3,
                   wall_id="x" * 22, along=1.0, height=2.0)

    def test_free_steel_small_section_is_fine(self):
        c = Column(name="Post", width=0.1, depth=0.1, material="steel",
                   at={"x": 0, "y": 0})
        assert c.material == "steel"

    def test_along_beyond_wall_end_is_rejected(self):
        b = _box()
        with pytest.raises(ValueError, match="along"):
            b.add_column("S0", wall="S0 South", along=7.0,
                         width=0.3, depth=0.3, name="T1")

    def test_round_trips_through_json(self, tmp_path):
        b = _box()
        b.add_column("S0", wall="S0 South", along=3.0,
                     width=0.6, depth=0.2, name="T1")
        b.add_column("S0", at=(2, 2), width=0.2, depth=0.2,
                     material="steel", name="Post")
        p = tmp_path / "building.json"
        b.save(p)
        cols = Building.load(p).stories[0].columns
        assert [c.name for c in cols] == ["T1", "Post"]
        assert cols[0].wall_id and cols[1].at is not None

    def test_old_buildings_without_columns_still_load(self, tmp_path):
        b = _box()
        p = tmp_path / "building.json"
        b.save(p)
        assert Building.load(p).stories[0].columns == []

    def test_empty_columns_do_not_serialize(self, tmp_path):
        # schema addition must not churn existing building.json files
        # (villa byte-identity gate)
        p = tmp_path / "building.json"
        _box().save(p)
        assert '"columns"' not in p.read_text()

    def test_reconcile_keeps_column_ids_and_remaps_host(self):
        from archicad_builder.models.reconcile import reconcile_ids

        prev = _box()
        prev.add_column("S0", wall="S0 South", along=3.0,
                        width=0.6, depth=0.2, name="T1")
        new = _box()
        new.add_column("S0", wall="S0 South", along=3.0,
                       width=0.6, depth=0.2, name="T1")
        report = reconcile_ids(new, prev)
        assert not report.added and not report.removed
        assert (new.stories[0].columns[0].global_id
                == prev.stories[0].columns[0].global_id)
        # host reference follows the wall's reconciled id
        assert (new.stories[0].columns[0].wall_id
                == prev.stories[0].get_wall_by_name("S0 South").global_id)


class TestIfc:
    def _export(self, b, tmp_path, name="box.ifc"):
        from archicad_builder.export.ifc import IFCExporter
        path = tmp_path / name
        IFCExporter(b).export(path)
        return path

    def test_exports_as_ifc_column_with_object_type(self, tmp_path):
        import ifcopenshell

        b = _box()
        b.add_column("S0", wall="S0 South", along=3.0,
                     width=0.6, depth=0.2, name="T1")
        ifc = ifcopenshell.open(str(self._export(b, tmp_path)))
        cols = ifc.by_type("IfcColumn")
        assert len(cols) == 1
        assert cols[0].ObjectType == "column"
        assert cols[0].GlobalId == b.stories[0].columns[0].global_id
        # IFC2X3: PredefinedType lives on IfcColumnType, not the occurrence
        with pytest.raises(AttributeError):
            cols[0].PredefinedType  # noqa: B018

    def test_column_carries_ifc_material(self, tmp_path):
        import ifcopenshell

        b = _box()
        b.add_column("S0", at=(2, 2), width=0.2, depth=0.2,
                     material="steel", name="Post")
        ifc = ifcopenshell.open(str(self._export(b, tmp_path)))
        names = {rel.RelatingMaterial.Name
                 for rel in ifc.by_type("IfcRelAssociatesMaterial")
                 for obj in rel.RelatedObjects if obj.is_a("IfcColumn")}
        assert names == {"steel"}

    def test_export_import_export_identity(self, tmp_path):
        from archicad_builder.importers.ifc import import_ifc

        b = _box()
        b.add_column("S0", wall="S0 South", along=3.0,
                     width=0.6, depth=0.2, name="T1")
        b.add_column("S0", at=(2, 2), width=0.2, depth=0.2,
                     material="steel", height=2.5, name="Post")
        res = import_ifc(self._export(b, tmp_path))
        cols = res.building.stories[0].columns
        assert len(cols) == 2
        tie = next(c for c in cols if c.name == "T1")
        assert tie.global_id == b.stories[0].columns[0].global_id
        assert tie.wall_id == b.stories[0].columns[0].wall_id  # host ref
        assert (tie.width, tie.depth, tie.material) == (0.6, 0.2, "rc")
        post = next(c for c in cols if c.name == "Post")
        assert (post.material, post.height) == ("steel", 2.5)
        # second export round-trips to the same payloads
        res2 = import_ifc(self._export(res.building, tmp_path, "box2.ifc"))
        assert (res2.building.model_dump(mode="json", exclude_none=True)
                == res.building.model_dump(mode="json", exclude_none=True))

    def test_round_trip_does_not_duplicate_columns(self, tmp_path):
        from archicad_builder.importers.ifc import import_ifc

        b = _box()
        b.add_column("S0", wall="S0 South", along=3.0,
                     width=0.6, depth=0.2, name="T1")
        cols = import_ifc(self._export(b, tmp_path)).building.stories[0].columns
        assert len(cols) == 1

    def test_update_ifc_adds_our_column(self, tmp_path):
        import ifcopenshell

        from archicad_builder.importers.ifc import import_project, update_ifc

        # roof-free fixture: roofs export as IfcSlab and come back as
        # slabs, which reads as local edits to update-ifc (existing
        # asymmetry, out of this spec's scope)
        base = Building(name="Box")
        base.add_story("S0", height=3.0, elevation=0.0)
        base.add_wall("S0", (0, 0), (6, 0), height=3.0, thickness=0.3,
                      name="S0 South", is_external=True, load_bearing=True)
        src = self._export(base, tmp_path)
        proj = tmp_path / "proj"
        import_project(src, proj)
        b = Building.load(proj / "building.json")
        b.add_column("S0", wall="S0 South", along=3.0,
                     width=0.6, depth=0.2, name="T1")
        b.save(proj / "building.json")
        out = update_ifc(proj)
        assert len(ifcopenshell.open(str(out)).by_type("IfcColumn")) == 1


class TestRenderMetadata:
    def test_metadata_carries_kind_and_material(self):
        from archicad_builder.render3d.metadata import element_metadata

        b = _box()
        b.add_column("S0", wall="S0 South", along=3.0,
                     width=0.6, depth=0.2, name="T1")
        b.add_column("S0", at=(2, 2), width=0.2, depth=0.2,
                     material="steel", name="Post")
        meta = element_metadata(b.model_dump(mode="json", exclude_none=True))
        assert meta["IfcColumn_T1"]["kind"] == "column"
        assert meta["IfcColumn_T1"]["material"] == "rc"
        assert meta["IfcColumn_Post"]["material"] == "steel"


class TestSeismicMass:
    def test_free_rc_column_adds_full_volume(self):
        base = compute_seismic(_box(), _site())["W"]
        b = _box()
        b.add_column("S0", at=(2, 2), width=0.3, depth=0.3, name="C1")
        # 25 kN/m3 * 0.3 * 0.3 * 3.0 = 6.75 kN
        assert (compute_seismic(b, _site())["W"] - base
                == pytest.approx(6.75, abs=0.2))

    def test_free_steel_column_uses_steel_density(self):
        base = compute_seismic(_box(), _site())["W"]
        b = _box()
        b.add_column("S0", at=(2, 2), width=0.3, depth=0.3,
                     material="steel", name="C1")
        # 78.5 kN/m3 * 0.09 m2 * 3.0 m = 21.2 kN
        assert (compute_seismic(b, _site())["W"] - base
                == pytest.approx(21.2, abs=0.3))

    def test_embedded_tie_adds_nothing_material_exclusive(self):
        # the wall's own mass already covers the overlap volume at rc
        # density — counting both would double the corner (Codex)
        base = compute_seismic(_box(), _site())["W"]
        b = _box()
        b.add_column("S0", wall="S0 South", along=3.0,
                     width=0.6, depth=0.3, name="T1")
        assert compute_seismic(b, _site())["W"] == pytest.approx(base, abs=0.1)

    def test_tie_wider_than_wall_adds_only_the_overhang(self):
        base = compute_seismic(_box(), _site())["W"]
        b = _box()
        b.add_column("S0", wall="S0 South", along=3.0,
                     width=0.6, depth=0.6, name="T1")
        # outside the 0.3 wall: 0.6 * (0.6-0.3) * 3.0 * 25 = 13.5 kN
        assert (compute_seismic(b, _site())["W"] - base
                == pytest.approx(13.5, abs=0.2))

    def test_columns_add_no_shear_capacity(self):
        # a lone column pretending to be a shear wall is exactly the
        # fiction we refuse (specs/columns.md decision log)
        base = compute_seismic(_box(), _site())
        b = _box()
        b.add_column("S0", wall="S0 South", along=3.0,
                     width=0.6, depth=0.3, name="T1")
        res = compute_seismic(b, _site())
        for d in ("x", "y"):
            assert (res["storeys"][0][d]["capacity"]
                    == base["storeys"][0][d]["capacity"])


class TestE108SupportPath:
    def test_column_on_footing_passes(self):
        b = _box(with_footings=True)
        b.add_column("S0", wall="S0 South", along=3.0,
                     width=0.6, depth=0.3, name="T1")
        assert validate_columns_support(b) == []

    def test_column_on_baseslab_passes(self):
        b = _box(baseslab=True)
        b.add_column("S0", at=(2, 2), width=0.3, depth=0.3, name="C1")
        assert validate_columns_support(b) == []

    def test_column_in_the_void_fails(self):
        b = _box(with_footings=True)
        b.add_column("S0", at=(2, 2), width=0.3, depth=0.3, name="C1")
        found = validate_columns_support(b)
        assert len(found) == 1
        assert found[0].message.startswith("E108: ")
        assert "support path" in found[0].message
        assert "C1" in found[0].message

    def test_upper_column_over_bearing_wall_passes(self):
        b = _box(storeys=2, with_footings=True)
        b.add_column("S1", wall="S1 South", along=3.0,
                     width=0.6, depth=0.3, name="T1")
        assert validate_columns_support(b) == []

    def test_upper_column_mid_span_fails(self):
        b = _box(storeys=2, with_footings=True)
        b.add_column("S1", at=(3, 2), width=0.3, depth=0.3, name="C1")
        found = validate_columns_support(b)
        assert len(found) == 1 and "C1" in found[0].message

    def test_column_on_column_continuity_passes(self):
        b = _box(storeys=2, baseslab=True)
        b.add_column("S0", at=(3, 2), width=0.3, depth=0.3, name="C0")
        b.add_column("S1", at=(3, 2), width=0.3, depth=0.3, name="C1")
        assert validate_columns_support(b) == []

    def test_wall_rules_stay_walls_only(self):
        # E050/E103/E104/E105 deliberately keep their walls-only scope
        # (specs/columns.md); an unsupported column is E108's finding
        b = _box(storeys=2, with_footings=True)
        b.add_column("S1", at=(3, 2), width=0.3, depth=0.3, name="C1")
        site = _soil_site()
        for code in ("E050", "E103", "E104", "E105"):
            with_col = _findings(b, code, site=site)
            assert not any("C1" in f.message for f in with_col)
        base = _box(storeys=2, with_footings=True)
        for code in ("E104", "E105"):
            assert len(validate_foundations(b, site)) == \
                len(validate_foundations(base, site))
        assert len(validate_seismic(b, site)) == len(validate_seismic(base, site))


class TestFemOverlay:
    def test_fem_result_carries_neutral_column_boxes(self):
        from archicad_builder.fem import compute_fem

        b = _box()
        b.add_column("S0", wall="S0 South", along=3.0,
                     width=0.6, depth=0.3, name="T1")
        res = compute_fem(b, mesh=0.5)
        assert len(res.columns) == 1
        c = res.columns[0]
        assert c["name"] == "T1" and c["material"] == "rc"
        assert (c["x"], c["y"]) == (3.0, 0.0)
        assert (c["z0"], c["z1"]) == (0.0, 3.0)
        # columns are NOT meshed — no quads, no element entry
        assert all(e["kind"] != "column" for e in res.elements.values())
        assert any("column frame action" in n for n in res.not_modelled)

    def test_no_columns_no_envelope_noise(self):
        from archicad_builder.fem import compute_fem

        res = compute_fem(_box(), mesh=0.5)
        assert res.columns == []
        assert not any("column" in n for n in res.not_modelled)

    def test_envelope_json_includes_columns(self, tmp_path):
        import json

        from archicad_builder.fem import compute_fem
        from archicad_builder.fem.writers import write_payloads

        b = _box()
        b.add_column("S0", at=(2, 2), width=0.2, depth=0.2,
                     material="steel", name="Post")
        write_payloads(compute_fem(b, mesh=0.5), tmp_path, "deadbeef")
        env = json.loads((tmp_path / "fem-field.json").read_text())
        assert env["columns"][0]["name"] == "Post"
