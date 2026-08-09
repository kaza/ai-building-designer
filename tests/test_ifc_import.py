"""IFC import + patch-based update (specs/ifc-import.md, delivery A).

The contract: our own exports round-trip losslessly (AB_Parametric psets),
foreign entities are REPORTED, never guessed, and updates PATCH the
partner's original file instead of regenerating it.
"""

import json
from pathlib import Path

import pytest

pytest.importorskip("ifcopenshell")

from archicad_builder.export.ifc import IFCExporter          # noqa: E402
from archicad_builder.importers.ifc import (                 # noqa: E402
    IfcImportError,
    import_ifc,
    import_project,
    update_ifc,
)
from archicad_builder.models import Building                 # noqa: E402

VILLA = Path(__file__).parent.parent / "projects" / "villa-maketa"


def fixture_building() -> Building:
    b = Building(name="Roundtrip Fixture", description="two walls, opening")
    b.add_story("GF", height=3.0)
    b.add_wall("GF", (0, 0), (6, 0), height=3.0, thickness=0.3,
               name="South Wall", is_external=True, load_bearing=True)
    b.add_wall("GF", (6, 0), (6, 4), height=3.0, thickness=0.3,
               name="East Wall", is_external=True, load_bearing=True)
    b.add_door("GF", "South Wall", position=1.0, width=0.9, height=2.1,
               name="Entry Door")
    b.add_window("GF", "East Wall", position=1.0, width=1.2, height=1.4,
                 sill_height=0.9, name="Kitchen Window")
    b.add_slab("GF", [(0, 0), (6, 0), (6, 4), (0, 4)], thickness=0.25,
               name="Ground Slab")
    return b


def ids_of(b: Building) -> set[str]:
    out = {b.global_id}
    for s in b.stories:
        out.add(s.global_id)
        for kind in ("walls", "slabs", "doors", "windows", "roofs",
                     "staircases", "beams", "virtual_elements", "spaces"):
            out |= {el.global_id for el in getattr(s, kind)}
        for apt in s.apartments:
            out |= {sp.global_id for sp in apt.spaces}
    return out


class TestRoundtrip:
    @pytest.fixture()
    def exported(self, tmp_path):
        b = fixture_building()
        path = tmp_path / "fixture.ifc"
        IFCExporter(b).export(path)
        return b, path

    def test_preserves_every_global_id(self, exported):
        b, path = exported
        result = import_ifc(path)
        assert ids_of(result.building) == ids_of(b)
        assert not result.unmapped

    def test_preserves_geometry_exactly(self, exported):
        b, path = exported
        imported = import_ifc(path).building
        w0, w1 = b.stories[0].walls, imported.stories[0].walls
        for a, c in zip(w0, w1):
            assert (a.start, a.end, a.thickness, a.height) == \
                (c.start, c.end, c.thickness, c.height)
        d0, d1 = b.stories[0].doors[0], imported.stories[0].doors[0]
        assert (d0.position, d0.width, d0.height, d0.wall_id) == \
            (d1.position, d1.width, d1.height, d1.wall_id)
        win0 = b.stories[0].windows[0]
        win1 = imported.stories[0].windows[0]
        assert win0.sill_height == win1.sill_height

    def test_save_load_of_imported_model_is_stable(self, exported, tmp_path):
        _, path = exported
        imported = import_ifc(path).building
        p = tmp_path / "b.json"
        imported.save(p)
        assert Building.load(p).model_dump() == imported.model_dump()

    def test_villa_roundtrips(self, tmp_path):
        villa = Building.load(VILLA / "building.json")
        path = tmp_path / "villa.ifc"
        IFCExporter(villa).export(path)
        result = import_ifc(path)
        assert not result.unmapped
        # apartment structure does not exist in IFC: apartment spaces come
        # back as storey spaces — the ID SET is what must survive
        assert ids_of(result.building) == ids_of(villa)


class TestForeignEntities:
    def test_unmapped_reported_not_dropped(self, tmp_path):
        b = fixture_building()
        path = tmp_path / "f.ifc"
        exporter = IFCExporter(b)
        exporter.export(path)
        # sneak a foreign product in (no AB_Parametric pset)
        import ifcopenshell
        model = ifcopenshell.open(str(path))
        model.create_entity(
            "IfcFurnishingElement",
            GlobalId=ifcopenshell.guid.new(), Name="Partner Sofa")
        model.write(str(path))
        result = import_ifc(path)
        assert any("IfcFurnishingElement" in u and "Partner Sofa" in u
                   for u in result.unmapped)

    def test_strict_import_refuses_to_write(self, tmp_path):
        b = fixture_building()
        src = tmp_path / "f.ifc"
        IFCExporter(b).export(src)
        import ifcopenshell
        model = ifcopenshell.open(str(src))
        model.create_entity(
            "IfcFurnishingElement",
            GlobalId=ifcopenshell.guid.new(), Name="Partner Sofa")
        model.write(str(src))
        target = tmp_path / "proj"
        with pytest.raises(IfcImportError, match="unmapped"):
            import_project(src, target, strict=True)
        assert not target.exists()


class TestImportProject:
    def test_creates_project_with_source_and_provenance(self, tmp_path):
        src = tmp_path / "partner.ifc"
        IFCExporter(fixture_building()).export(src)
        target = tmp_path / "proj"
        result = import_project(src, target)
        assert (target / "building.json").is_file()
        assert (target / "import-source.ifc").read_bytes() == \
            src.read_bytes()
        record = json.loads((target / "import-source.json").read_text())
        assert record["source_sha256"]
        assert set(record["imported_ids"]) == ids_of(result.building)

    def test_refuses_existing_directory(self, tmp_path):
        src = tmp_path / "partner.ifc"
        IFCExporter(fixture_building()).export(src)
        target = tmp_path / "proj"
        target.mkdir()
        with pytest.raises(IfcImportError, match="already exists"):
            import_project(src, target)


class TestUpdateIfc:
    def test_adds_our_elements_and_keeps_theirs_untouched(self, tmp_path):
        import ifcopenshell
        src = tmp_path / "partner.ifc"
        IFCExporter(fixture_building()).export(src)
        target = tmp_path / "proj"
        import_project(src, target)

        # we add a wall to the imported model
        b = Building.load(target / "building.json")
        ours = b.add_wall("GF", (6, 4), (0, 4), height=3.0, thickness=0.3,
                          name="Our North Wall", is_external=True,
                          load_bearing=True)
        b.save(target / "building.json")

        out = update_ifc(target)
        patched = ifcopenshell.open(str(out))
        walls = patched.by_type("IfcWallStandardCase") + [
            w for w in patched.by_type("IfcWall")
            if not w.is_a("IfcWallStandardCase")]
        assert ours.global_id in {w.GlobalId for w in walls}

        # partner entities: same GlobalIds, same count, untouched
        orig = ifcopenshell.open(str(src))
        orig_ids = {e.GlobalId for e in orig.by_type("IfcRoot")}
        patched_ids = {e.GlobalId for e in patched.by_type("IfcRoot")}
        assert orig_ids <= patched_ids
        # the base file itself is pristine
        assert (target / "import-source.ifc").read_bytes() == \
            src.read_bytes()

    def test_refuses_project_without_import_source(self, tmp_path):
        (tmp_path / "p").mkdir()
        with pytest.raises(IfcImportError, match="no import source"):
            update_ifc(tmp_path / "p")


class TestUpdateIfcAllKinds:
    def test_added_door_patches_host_wall_with_opening(self, tmp_path):
        """A door WE add to THEIR wall must void that wall in the patch —
        silently skipping non-wall elements was the fail-loud violation
        found during phase review."""
        import ifcopenshell
        src = tmp_path / "partner.ifc"
        IFCExporter(fixture_building()).export(src)
        target = tmp_path / "proj"
        import_project(src, target)

        b = Building.load(target / "building.json")
        new_door = b.add_door("GF", "East Wall", position=2.5, width=0.8,
                              height=2.1, name="Our New Door")
        b.save(target / "building.json")

        out = update_ifc(target)
        patched = ifcopenshell.open(str(out))
        doors = {d.GlobalId: d for d in patched.by_type("IfcDoor")}
        assert new_door.global_id in doors
        # the void relationship targets THEIR wall
        east = next(w for w in patched.by_type("IfcWallStandardCase")
                    if w.Name == "East Wall")
        voided = [r for r in patched.by_type("IfcRelVoidsElement")
                  if r.RelatingBuildingElement == east]
        assert len(voided) == 2      # their window opening + our door


class TestUpdateIfcFailLoud:
    def make_project(self, tmp_path):
        src = tmp_path / "partner.ifc"
        IFCExporter(fixture_building()).export(src)
        target = tmp_path / "proj"
        import_project(src, target)
        return target

    def test_edited_imported_element_is_refused(self, tmp_path):
        """We edited THEIR wall locally — regenerating from the pristine
        source would silently revert it (CodeRabbit H1)."""
        target = self.make_project(tmp_path)
        b = Building.load(target / "building.json")
        b.stories[0].walls[0].thickness = 0.5
        b.save(target / "building.json")
        with pytest.raises(IfcImportError, match="edited locally"):
            update_ifc(target)

    def test_added_space_is_refused_not_dropped(self, tmp_path):
        from archicad_builder.models.geometry import Point2D, Polygon2D
        from archicad_builder.models.spaces import RoomType, Space
        target = self.make_project(tmp_path)
        b = Building.load(target / "building.json")
        b.stories[0].spaces.append(Space(
            name="Our New Room", room_type=RoomType.BEDROOM,
            boundary=Polygon2D(vertices=[Point2D(x=0, y=0),
                                         Point2D(x=1, y=0),
                                         Point2D(x=1, y=1)])))
        b.save(target / "building.json")
        with pytest.raises(IfcImportError, match="spaces"):
            update_ifc(target)

    def test_deleted_imported_element_is_reported(self, tmp_path, capsys):
        target = self.make_project(tmp_path)
        b = Building.load(target / "building.json")
        removed = b.stories[0].windows.pop()
        b.save(target / "building.json")
        update_ifc(target)
        assert removed.global_id in capsys.readouterr().out


class TestImportWarnings:
    def test_partner_resized_door_warns(self, tmp_path):
        import ifcopenshell
        src = tmp_path / "f.ifc"
        IFCExporter(fixture_building()).export(src)
        model = ifcopenshell.open(str(src))
        door = model.by_type("IfcDoor")[0]
        door.OverallWidth = 1.5          # partner widened it in CAD
        model.write(str(src))
        result = import_ifc(src)
        assert any("disagrees" in w for w in result.warnings)

    def test_dangling_wall_reference_warns(self, tmp_path):
        import json as _json
        src = tmp_path / "f.ifc"
        b = fixture_building()
        IFCExporter(b).export(src)
        import ifcopenshell
        model = ifcopenshell.open(str(src))
        # partner deleted the window's host wall but kept the window: point
        # the window pset at a wall id that is not in the file
        for entity in model.by_type("IfcWindow"):
            for rel in model.get_inverse(entity):
                if rel.is_a("IfcRelDefinesByProperties") and \
                        rel.RelatingPropertyDefinition.Name == "AB_Parametric":
                    prop = rel.RelatingPropertyDefinition.HasProperties[0]
                    payload = _json.loads(prop.NominalValue.wrappedValue)
                    payload["wall_id"] = "0000000000000000000000"
                    prop.NominalValue = model.create_entity(
                        "IfcText", _json.dumps(payload, sort_keys=True))
        model.write(str(src))
        result = import_ifc(src)
        assert any("not survive a re-export" in w for w in result.warnings)


class TestCodexFinalRound:
    def test_entity_global_id_beats_stale_pset_copy(self, tmp_path):
        """A partner regenerating GUIDs must win over our pset copy —
        'verbatim' means THEIR id (Codex 2026-08-09)."""
        import ifcopenshell
        src = tmp_path / "f.ifc"
        IFCExporter(fixture_building()).export(src)
        model = ifcopenshell.open(str(src))
        wall = model.by_type("IfcWallStandardCase")[0]
        new_gid = ifcopenshell.guid.new()
        wall.GlobalId = new_gid              # pset json keeps the old id
        model.write(str(src))
        result = import_ifc(src)
        walls = {w.global_id for s in result.building.stories
                 for w in s.walls}
        assert new_gid in walls

    def test_update_refuses_non_metre_source(self, tmp_path):
        import ifcopenshell
        src = tmp_path / "partner.ifc"
        IFCExporter(fixture_building()).export(src)
        target = tmp_path / "proj"
        import_project(src, target)
        # partner re-exports in millimetres
        model = ifcopenshell.open(str(target / "import-source.ifc"))
        for ua in model.by_type("IfcUnitAssignment"):
            for unit in ua.Units:
                if getattr(unit, "UnitType", None) == "LENGTHUNIT":
                    unit.Prefix = "MILLI"
        model.write(str(target / "import-source.ifc"))
        with pytest.raises(IfcImportError, match="METRE"):
            update_ifc(target)
