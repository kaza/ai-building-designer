"""Download a project's pinned furniture assets into assets/ (gitignored).

Moved from projects/villa-maketa/fetch_assets.py (ADR-006); the pins now
live in project.toml `[[asset]]` tables (specs/project-config.md).

Reproducibility comes from the pins, not committed binaries: Poly Haven
by upstream md5 (their API is the authority), Objaverse GLBs by sha256,
the Kenney kit zip by sha256. licenses.json is written only after every
asset arrived — the Objaverse picks are CC-BY, so authors MUST stay
credited. All verification failures raise AssetError; nothing is
"best effort".
"""

from __future__ import annotations

import hashlib
import io
import json
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from archicad_builder.project_config import (
    KenneyKitAsset,
    ObjaverseAsset,
    PolyhavenAsset,
    ProjectConfig,
)

OBJAVERSE_BASE = "https://huggingface.co/datasets/allenai/objaverse/resolve/main/"
USER_AGENT = "ai-building-designer (asset fetcher)"

Fetch = Callable[[str], bytes]          # url -> body; injectable for tests
GetJson = Callable[[str], dict]


class AssetError(Exception):
    """An asset failed to arrive or verify. The build must stop."""


def _http_fetch(url: str, timeout: int = 600) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _http_get_json(url: str) -> dict:
    return json.loads(_http_fetch(url, timeout=60))


def fetch_polyhaven(assets_dir: Path, spec: PolyhavenAsset, *,
                    fetch: Fetch, get_json: GetJson) -> dict:
    """Download one Poly Haven glTF + its texture dependencies."""
    dest_dir = assets_dir / spec.id
    marker = dest_dir / ".complete"
    files = get_json(f"https://api.polyhaven.com/files/{spec.id}")
    gltf = files["gltf"][spec.resolution]["gltf"]
    if marker.exists() and marker.read_text() != gltf["md5"]:
        # Upstream republished — a stale cache would silently diverge from
        # the provenance recorded below
        print(f"{spec.id}: upstream md5 changed, re-downloading")
        marker.unlink()
    if marker.exists():
        print(f"{spec.id}: cached")
    else:
        def download(url: str, dest: Path, md5: str) -> None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            data = fetch(url)
            actual = hashlib.md5(data).hexdigest()
            if actual != md5:
                raise AssetError(
                    f"md5 mismatch for {url}: expected {md5}, got {actual}")
            part = dest.with_suffix(dest.suffix + ".part")
            part.write_bytes(data)
            part.rename(dest)

        gltf_name = gltf["url"].rsplit("/", 1)[-1]
        download(gltf["url"], dest_dir / gltf_name, gltf["md5"])
        for rel_path, meta in gltf["include"].items():
            # API-provided path — refuse traversal out of the asset dir
            target = (dest_dir / rel_path).resolve()
            if not target.is_relative_to(dest_dir.resolve()):
                raise AssetError(
                    f"include path escapes asset dir: {rel_path!r}")
            download(meta["url"], target, meta["md5"])
        marker.write_text(gltf["md5"])
        print(f"{spec.id}: {len(gltf['include']) + 1} files")
    info = get_json(f"https://api.polyhaven.com/info/{spec.id}")
    return {
        "id": spec.id,
        "name": info.get("name", spec.id),
        "license": "CC0",
        "authors": sorted(info.get("authors", {})),
        "source": f"https://polyhaven.com/a/{spec.id}",
        "resolution": spec.resolution,
        "gltf_md5": gltf["md5"],
    }


def fetch_objaverse(assets_dir: Path, spec: ObjaverseAsset, *,
                    fetch: Fetch) -> dict:
    """Download one pinned Objaverse GLB, sha256-verified.

    Cache validity = the exact pinned file exists and hashes to the pin —
    no marker file to go stale. After a successful fetch, any OTHER model
    file in the dir (an older pin) is removed so the loader can never pick
    a stale asset.
    """
    dest_dir = assets_dir / spec.id
    dest = dest_dir / f"{spec.uid}.glb"
    if dest.exists() and hashlib.sha256(
            dest.read_bytes()).hexdigest() == spec.sha256:
        print(f"{spec.id}: cached")
    else:
        data = fetch(OBJAVERSE_BASE + spec.path)
        actual = hashlib.sha256(data).hexdigest()
        if actual != spec.sha256:
            raise AssetError(
                f"sha256 mismatch for {spec.id}: got {actual}")
        dest_dir.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(".glb.part")
        part.write_bytes(data)
        part.rename(dest)
        print(f"{spec.id}: {len(data) / 1024:.0f} KB")
    for stale in dest_dir.glob("*.gl*"):
        if stale != dest and stale.suffix in (".glb", ".gltf"):
            print(f"{spec.id}: removing stale {stale.name}")
            stale.unlink()
    return {
        "id": spec.id,
        "name": spec.name,
        "license": "CC BY 4.0 — attribution required",
        "authors": [spec.author],
        "source": f"https://sketchfab.com/3d-models/{spec.uid}",
        "via": "objaverse (huggingface.co/datasets/allenai/objaverse)",
        "sha256": spec.sha256,
    }


def fetch_kenney(assets_dir: Path, spec: KenneyKitAsset, *,
                 fetch: Fetch) -> list[dict]:
    """Extract the pinned Kenney models: one sha256-pinned zip, selected
    GLBs land in assets/kenney_<model>/<model>.glb (one file per dir —
    the loader's rule). The zip is fetched only when a model is missing."""
    missing = [m for m in spec.models
               if not (assets_dir / f"kenney_{m}" / f"{m}.glb").exists()]
    if missing:
        data = fetch(spec.url)
        actual = hashlib.sha256(data).hexdigest()
        if actual != spec.sha256:
            raise AssetError(
                f"sha256 mismatch for Kenney kit: got {actual}")
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for model in missing:
                member = f"Models/GLTF format/{model}.glb"
                dest_dir = assets_dir / f"kenney_{model}"
                dest_dir.mkdir(parents=True, exist_ok=True)
                (dest_dir / f"{model}.glb").write_bytes(zf.read(member))
                print(f"kenney_{model}: extracted")
    else:
        print("kenney models: cached")
    return [{
        "id": f"kenney_{m}",
        "name": f"Kenney Furniture Kit — {m}",
        "license": "CC0",
        "authors": ["Kenney"],
        "source": "https://kenney.nl/assets/furniture-kit",
        "kit_sha256": spec.sha256,
    } for m in spec.models]


def fetch_all(project_dir: Path, cfg: ProjectConfig, *,
              fetch: Fetch = _http_fetch,
              get_json: GetJson = _http_get_json) -> Path:
    """Fetch every pinned asset; write assets/licenses.json LAST (an
    interrupted run never leaves a complete-looking manifest)."""
    assets_dir = project_dir / "assets"
    licenses: list[dict] = []
    for spec in cfg.assets:
        if isinstance(spec, PolyhavenAsset):
            licenses.append(fetch_polyhaven(
                assets_dir, spec, fetch=fetch, get_json=get_json))
        elif isinstance(spec, ObjaverseAsset):
            licenses.append(fetch_objaverse(assets_dir, spec, fetch=fetch))
        else:
            licenses.extend(fetch_kenney(assets_dir, spec, fetch=fetch))
    assets_dir.mkdir(exist_ok=True)
    target = assets_dir / "licenses.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(licenses, indent=2))
    tmp.replace(target)      # atomic — no broken JSON on interruption
    print(f"wrote {target} ({len(licenses)} assets)")
    return target
