"""fetch-assets engine (specs/project-config.md, ADR-006).

Network is stubbed — these tests verify the CONTRACT: pins are enforced,
partial downloads never pass the cache check, licenses.json records
provenance, and a hash mismatch is fatal, not a warning.
"""

import hashlib
import io
import json
import zipfile

import pytest

from archicad_builder.assets import (
    AssetError,
    fetch_all,
    fetch_kenney,
    fetch_objaverse,
)
from archicad_builder.project_config import (
    KenneyKitAsset,
    ObjaverseAsset,
    ProjectConfig,
)


def obja(sha256: str) -> ObjaverseAsset:
    return ObjaverseAsset(
        source="objaverse", id="sofa", uid="u123", path="glbs/x/u123.glb",
        sha256=sha256, name="Sofa Name", author="author1")


class TestObjaverse:
    def test_downloads_verifies_and_records(self, tmp_path):
        data = b"GLB-BYTES"
        spec = obja(hashlib.sha256(data).hexdigest())
        info = fetch_objaverse(tmp_path, spec, fetch=lambda url: data)
        assert (tmp_path / "sofa" / "u123.glb").read_bytes() == data
        assert info["authors"] == ["author1"]
        assert "CC BY" in info["license"]

    def test_hash_mismatch_is_fatal_and_writes_nothing(self, tmp_path):
        spec = obja("0" * 64)
        with pytest.raises(AssetError, match="sha256 mismatch"):
            fetch_objaverse(tmp_path, spec, fetch=lambda url: b"WRONG")
        assert not (tmp_path / "sofa" / "u123.glb").exists()

    def test_cached_file_is_not_refetched(self, tmp_path):
        data = b"GLB-BYTES"
        spec = obja(hashlib.sha256(data).hexdigest())
        (tmp_path / "sofa").mkdir(parents=True)
        (tmp_path / "sofa" / "u123.glb").write_bytes(data)

        def boom(url):
            raise AssertionError("network hit despite valid cache")
        fetch_objaverse(tmp_path, spec, fetch=boom)

    def test_stale_sibling_models_are_removed(self, tmp_path):
        data = b"GLB-BYTES"
        spec = obja(hashlib.sha256(data).hexdigest())
        (tmp_path / "sofa").mkdir(parents=True)
        (tmp_path / "sofa" / "old-pin.glb").write_bytes(b"stale")
        fetch_objaverse(tmp_path, spec, fetch=lambda url: data)
        assert not (tmp_path / "sofa" / "old-pin.glb").exists()


class TestKenney:
    def make_zip(self, models):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for m in models:
                zf.writestr(f"Models/GLTF format/{m}.glb", f"GLB:{m}")
        return buf.getvalue()

    def test_extracts_pinned_models(self, tmp_path):
        data = self.make_zip(["toilet", "shower"])
        spec = KenneyKitAsset(
            source="kenney-kit", id="kenney", url="https://x/kit.zip",
            sha256=hashlib.sha256(data).hexdigest(),
            models=["toilet", "shower"])
        infos = fetch_kenney(tmp_path, spec, fetch=lambda url: data)
        assert (tmp_path / "kenney_toilet" / "toilet.glb").read_text() \
            == "GLB:toilet"
        assert len(infos) == 2 and infos[0]["license"] == "CC0"

    def test_kit_hash_mismatch_is_fatal(self, tmp_path):
        spec = KenneyKitAsset(
            source="kenney-kit", id="kenney", url="https://x/kit.zip",
            sha256="0" * 64, models=["toilet"])
        with pytest.raises(AssetError, match="sha256 mismatch"):
            fetch_kenney(tmp_path, spec, fetch=lambda url: b"nope")


class TestFetchAll:
    def test_writes_licenses_only_after_every_asset(self, tmp_path):
        data = b"GLB"
        (tmp_path / "project.toml").write_text(f'''
[[asset]]
source = "objaverse"
id = "sofa"
uid = "u1"
path = "p"
sha256 = "{hashlib.sha256(data).hexdigest()}"
name = "n"
author = "a"
''')
        cfg = ProjectConfig.load(tmp_path)
        out = fetch_all(tmp_path, cfg, fetch=lambda url: data,
                        get_json=lambda url: {})
        licenses = json.loads(out.read_text())
        assert [entry["id"] for entry in licenses] == ["sofa"]

    def test_a_failing_asset_leaves_no_manifest(self, tmp_path):
        (tmp_path / "project.toml").write_text('''
[[asset]]
source = "objaverse"
id = "sofa"
uid = "u1"
path = "p"
sha256 = "0000000000000000000000000000000000000000000000000000000000000000"
name = "n"
author = "a"
''')
        cfg = ProjectConfig.load(tmp_path)
        with pytest.raises(AssetError):
            fetch_all(tmp_path, cfg, fetch=lambda url: b"WRONG",
                      get_json=lambda url: {})
        assert not (tmp_path / "assets" / "licenses.json").exists()
