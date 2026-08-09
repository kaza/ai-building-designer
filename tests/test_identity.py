"""Element identity: mint on add, reconcile on rebuild (specs/ifc-identity.md).

The contract under test, in one line: a GlobalId is minted exactly once —
when the element is added — and every other path (load, save, rebuild,
export) preserves it.
"""

import json
import shutil
from pathlib import Path

import pytest

from archicad_builder.models import Building
from archicad_builder.models.ifc_id import (
    derived_ifc_id,
    generate_ifc_id,
    is_valid_ifc_id,
)
from archicad_builder.models.reconcile import (
    ReconcileError,
    reconcile_ids,
)

VILLA = Path(__file__).parent.parent / "projects" / "villa-maketa"


def two_wall_building(name="Fixture") -> Building:
    b = Building(name=name)
    b.add_story("GF", height=3.0)
    b.add_wall("GF", (0, 0), (5, 0), height=3.0, thickness=0.3,
               name="South Wall", is_external=True, load_bearing=True)
    b.add_wall("GF", (5, 0), (5, 4), height=3.0, thickness=0.3,
               name="East Wall", is_external=True, load_bearing=True)
    b.add_door("GF", "South Wall", position=1.0, width=0.9, height=2.1,
               name="Entry Door")
    b.add_window("GF", "East Wall", position=1.0, width=1.2, height=1.4,
                 name="Kitchen Window")
    return b


class TestReconcile:
    def test_keeps_ids_for_matching_names(self):
        prev = two_wall_building()
        new = two_wall_building()          # same design, fresh random ids
        assert new.stories[0].walls[0].global_id != \
            prev.stories[0].walls[0].global_id
        report = reconcile_ids(new, prev)
        assert new.global_id == prev.global_id
        assert new.stories[0].global_id == prev.stories[0].global_id
        for kind in ("walls", "doors", "windows"):
            for n, p in zip(getattr(new.stories[0], kind),
                            getattr(prev.stories[0], kind)):
                assert n.global_id == p.global_id
        assert not report.added and not report.removed

    def test_remaps_wall_references_on_doors_and_windows(self):
        # a door's wall_id must point at the RECONCILED wall id, or the
        # exported IFC would reference a wall that no longer exists
        prev = two_wall_building()
        new = two_wall_building()
        reconcile_ids(new, prev)
        story = new.stories[0]
        wall_ids = {w.global_id for w in story.walls}
        assert story.doors[0].wall_id in wall_ids
        assert story.windows[0].wall_id in wall_ids
        assert story.doors[0].wall_id == prev.stories[0].doors[0].wall_id

    def test_mints_only_for_new_elements(self):
        prev = two_wall_building()
        new = two_wall_building()
        new.add_wall("GF", (5, 4), (0, 4), height=3.0, thickness=0.3,
                     name="North Wall", is_external=True, load_bearing=True)
        report = reconcile_ids(new, prev)
        # story names are case-folded in identity keys
        assert [key for key, _ in report.added] == \
            [("gf", "walls", "North Wall")]
        kept_ids = {i for _, i in report.kept}
        added_ids = {i for _, i in report.added}
        assert not kept_ids & added_ids

    def test_reports_removed(self):
        prev = two_wall_building()
        new = two_wall_building()
        removed_id = prev.stories[0].windows[0].global_id
        new.stories[0].windows.clear()
        report = reconcile_ids(new, prev)
        assert report.removed == [(("gf", "windows", "Kitchen Window"),
                                   removed_id)]

    def test_duplicate_name_is_fatal(self):
        new = two_wall_building()
        new.add_wall("GF", (0, 4), (0, 0), height=3.0, thickness=0.3,
                     name="South Wall", is_external=True, load_bearing=True)
        with pytest.raises(ReconcileError, match="South Wall"):
            reconcile_ids(new, two_wall_building())

    def test_villa_rebuild_is_byte_identical(self, tmp_path):
        """THE headline property: re-running build.py must not touch the file."""
        build = VILLA / "build.py"
        if not build.is_file():
            pytest.skip("villa build script not present")
        import subprocess
        import sys
        work = tmp_path / "villa-maketa"
        work.mkdir()
        shutil.copy(build, work / "build.py")
        shutil.copy(VILLA / "building.json", work / "building.json")
        before = (work / "building.json").read_bytes()
        proc = subprocess.run([sys.executable, str(work / "build.py")],
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        assert (work / "building.json").read_bytes() == before


class TestLoadSave:
    def test_save_is_idempotent(self, tmp_path):
        b = two_wall_building()
        p1, p2 = tmp_path / "a.json", tmp_path / "b.json"
        b.save(p1)
        Building.load(p1).save(p2)
        assert p1.read_bytes() == p2.read_bytes()

    def test_load_never_writes(self, tmp_path):
        p = tmp_path / "b.json"
        two_wall_building().save(p)
        before = p.read_bytes()
        Building.load(p)
        assert p.read_bytes() == before

    def test_missing_id_is_minted_in_memory_only(self, tmp_path):
        p = tmp_path / "b.json"
        two_wall_building().save(p)
        raw = json.loads(p.read_text())
        del raw["stories"][0]["walls"][0]["global_id"]
        p.write_text(json.dumps(raw))
        before = p.read_bytes()
        b = Building.load(p)
        assert is_valid_ifc_id(b.stories[0].walls[0].global_id)
        assert p.read_bytes() == before          # no silent persistence


class TestIdValidation:
    def test_generated_ids_are_valid(self):
        for _ in range(20):
            assert is_valid_ifc_id(generate_ifc_id())

    def test_rejects_bad_charset_and_length(self):
        assert not is_valid_ifc_id("!" * 22)
        assert not is_valid_ifc_id("0" * 21)
        assert not is_valid_ifc_id("0" * 23)
        assert not is_valid_ifc_id("z" + "0" * 21)   # first char must be 0-3
        assert not is_valid_ifc_id(None)
        assert not is_valid_ifc_id(22)


class TestDerivedIds:
    def test_golden_vectors(self):
        """Frozen expected ids. If this test fails, you changed AB_NAMESPACE,
        SEED_VERSION or the seed encoding — every relationship id in every
        exported IFC just changed. That must be a deliberate act."""
        assert derived_ifc_id("rel-voids", "wallid0000000000000000",
                              "openingid0000000000000") == \
            GOLDEN["rel-voids"]
        assert derived_ifc_id("pset", "elemid0000000000000000",
                              "Pset_WallCommon") == GOLDEN["pset"]
        assert derived_ifc_id("opening", "wallid0000000000000000",
                              "doorid0000000000000000", index=1) == \
            GOLDEN["opening-1"]

    def test_stable_and_distinct(self):
        a = derived_ifc_id("opening", "w", "d")
        assert a == derived_ifc_id("opening", "w", "d")
        assert a != derived_ifc_id("opening", "w", "d", index=1)
        assert a != derived_ifc_id("opening", "w", "e")
        assert a != derived_ifc_id("rel-fills", "w", "d")
        assert is_valid_ifc_id(a)

    def test_seed_encoding_is_injective(self):
        # '|'.join would make these collide — the JSON encoding must not
        assert derived_ifc_id("k", "a|b", "c") != derived_ifc_id("k", "a", "b|c")


GOLDEN = {
    # computed once from the frozen namespace + grammar, then pinned
    "rel-voids": "13b2KAcxvGsO0Gcm4JpVDs",
    "pset": "01O37gYyjRxhTITgLg2$DO",
    "opening-1": "15dQ026VXMxxDUyoqXnAWK",
}


class TestDeterministicExport:
    @pytest.fixture()
    def villa(self):
        pytest.importorskip("ifcopenshell")
        return Building.load(VILLA / "building.json")

    def test_export_twice_is_byte_identical(self, villa, tmp_path):
        from archicad_builder.export.ifc import IFCExporter
        a, b = tmp_path / "a.ifc", tmp_path / "b.ifc"
        IFCExporter(villa).export(a)
        IFCExporter(villa).export(b)
        assert a.read_bytes() == b.read_bytes()

    def test_header_is_pinned(self, villa, tmp_path, monkeypatch):
        monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
        from archicad_builder.export.ifc import IFCExporter, PINNED_TIME
        out = tmp_path / "v.ifc"
        IFCExporter(villa).export(out)
        header = out.read_text().split("DATA;")[0]
        # exact pinned stamp: two same-second exports must not mask a break
        assert PINNED_TIME in header
        assert "ArchiCAD Builder" in header

    def test_header_honors_source_date_epoch(self, villa, tmp_path,
                                             monkeypatch):
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "946684800")  # 2000-01-01
        from archicad_builder.export.ifc import IFCExporter
        out = tmp_path / "v.ifc"
        IFCExporter(villa).export(out)
        assert "2000-01-01T00:00:00" in out.read_text().split("DATA;")[0]

    def test_all_exported_guids_unique(self, villa, tmp_path):
        import ifcopenshell
        from archicad_builder.export.ifc import IFCExporter
        out = tmp_path / "v.ifc"
        IFCExporter(villa).export(out)
        model = ifcopenshell.open(str(out))
        ids = [e.GlobalId for e in model.by_type("IfcRoot")]
        assert len(ids) == len(set(ids)), "duplicate GlobalIds in export"

    def test_ifc_element_ids_match_json(self, villa, tmp_path):
        import ifcopenshell
        from archicad_builder.export.ifc import IFCExporter
        out = tmp_path / "v.ifc"
        IFCExporter(villa).export(out)
        model = ifcopenshell.open(str(out))
        exported = {e.GlobalId for e in model.by_type("IfcRoot")}
        for story in villa.stories:
            for kind in ("walls", "slabs", "doors", "windows", "roofs"):
                for el in getattr(story, kind):
                    assert el.global_id in exported, \
                        f"{el.name} id missing from IFC"


class TestIdsCli:
    def run_ids(self, project_dir, *args):
        import subprocess
        import sys
        return subprocess.run(
            [sys.executable, "-m", "archicad_builder", "ids",
             str(project_dir), *args],
            capture_output=True, text=True)

    @pytest.fixture()
    def project(self, tmp_path):
        d = tmp_path / "proj"
        d.mkdir()
        two_wall_building().save(d / "building.json")
        return d

    def test_clean_project_passes(self, project):
        proc = self.run_ids(project, "--strict")
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_flags_duplicates(self, project):
        raw = json.loads((project / "building.json").read_text())
        raw["stories"][0]["walls"][1]["global_id"] = \
            raw["stories"][0]["walls"][0]["global_id"]
        (project / "building.json").write_text(json.dumps(raw))
        proc = self.run_ids(project, "--strict")
        assert proc.returncode != 0
        assert "duplicate" in proc.stdout.lower()

    def test_flags_invalid(self, project):
        raw = json.loads((project / "building.json").read_text())
        raw["stories"][0]["walls"][0]["global_id"] = "not-a-guid"
        (project / "building.json").write_text(json.dumps(raw))
        proc = self.run_ids(project, "--strict")
        assert proc.returncode != 0
        assert "invalid" in proc.stdout.lower()

    def test_reports_and_repairs_missing(self, project):
        raw = json.loads((project / "building.json").read_text())
        del raw["stories"][0]["walls"][0]["global_id"]
        (project / "building.json").write_text(json.dumps(raw))
        proc = self.run_ids(project, "--strict")
        assert proc.returncode != 0
        assert "missing" in proc.stdout.lower()

        proc = self.run_ids(project, "--repair")
        assert proc.returncode == 0
        repaired = json.loads((project / "building.json").read_text())
        assert is_valid_ifc_id(
            repaired["stories"][0]["walls"][0]["global_id"])
        # and now strict passes
        assert self.run_ids(project, "--strict").returncode == 0


class TestReconcilePrevValidation:
    def test_duplicate_id_in_prev_is_fatal(self):
        prev = two_wall_building()
        prev.stories[0].walls[1].global_id = \
            prev.stories[0].walls[0].global_id
        with pytest.raises(ReconcileError, match="duplicate GlobalId"):
            reconcile_ids(two_wall_building(), prev)

    def test_invalid_id_in_prev_is_fatal(self):
        prev = two_wall_building()
        prev.stories[0].walls[0].global_id = "not-a-guid"
        with pytest.raises(ReconcileError, match="invalid GlobalId"):
            reconcile_ids(two_wall_building(), prev)


class TestReconcileStoreys:
    def test_case_only_storey_rename_keeps_ids(self):
        prev = two_wall_building()
        new = two_wall_building()
        new.stories[0].name = "gf"           # was "GF" — case-only change
        report = reconcile_ids(new, prev)
        assert not report.added and not report.removed
        assert new.stories[0].global_id == prev.stories[0].global_id
        assert new.stories[0].walls[0].global_id == \
            prev.stories[0].walls[0].global_id

    def test_duplicate_storey_names_are_fatal(self):
        from archicad_builder.models.building import Story
        prev = two_wall_building()
        prev.stories.append(Story(name="gf", height=3.0))   # empty twin
        with pytest.raises(ReconcileError, match="storeys share the name"):
            reconcile_ids(two_wall_building(), prev)
