"""Download the pinned furniture set (Poly Haven + Objaverse) into assets/.

    .venv/bin/python projects/villa-maketa/fetch_assets.py

Assets are gitignored — reproducibility comes from this pinned list, not from
committed binaries. Poly Haven assets land in assets/<id>/ preserving the
glTF's relative texture paths (md5 from the live API); Objaverse assets are
single GLBs pinned by sha256 (HuggingFace rehost of Sketchfab models — the
modern pieces Poly Haven doesn't carry; owner decision 2026-08-05).
A .complete marker is written only after every file arrived, so an aborted
run never passes the cache check. licenses.json records provenance for both
sources — the Objaverse picks are CC-BY, so authors MUST stay credited.
"""
import hashlib
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
ASSETS_DIR = HERE / "assets"
RESOLUTION = "1k"
USER_AGENT = "ai-building-designer/villa-maketa (asset fetcher)"

# Pinned Poly Haven asset ids (all CC0). Mapping to furniture items lives in
# furniture.json ("asset" field).
ASSETS = [
    "mid_century_lounge_chair",
    "modern_coffee_table_01",
    "modern_wooden_cabinet",
    "outdoor_table_chair_set_01",  # deck tables (feedback #026)
]

# Pinned Objaverse models (key = the "asset" value used in furniture.json).
OBJAVERSE_BASE = "https://huggingface.co/datasets/allenai/objaverse/resolve/main/"
OBJAVERSE = {
    "sectional_sofa": {
        "uid": "0eb6c94aa40c41b480cf35de229e8e88",
        "path": "glbs/000-027/0eb6c94aa40c41b480cf35de229e8e88.glb",
        "sha256": "59a533d53544430fd81f3a4b055b430908faacc92dba2c6160270222ae1a9f0b",
        "name": "Escuadra Victoria Izquierda II", "author": "Pablo.Portela",
    },
    "deck_sofa": {
        "uid": "fbadc209177641978444636641a6d515",
        "path": "glbs/000-089/fbadc209177641978444636641a6d515.glb",
        "sha256": "bd83bd3efb4eade485114e22e34215403758dfb60ea9cdf3555bae1eab3a1cbf",
        "name": "Feathers 5 Seat", "author": "mohitoz",
    },
    "dining_chair": {
        "uid": "a653e92fad4f4721ad92fbd8f386acfe",
        "path": "glbs/000-153/a653e92fad4f4721ad92fbd8f386acfe.glb",
        "sha256": "167d3b7b56c893f528d9297a84a4067d506a36940a9aed2c5ef0b50bdc0ea574",
        "name": "Silla", "author": "gabymrtnz",
    },
    "dining_table": {
        "uid": "f0e17c71b71b48d487b7b6a27ce78bb3",
        "path": "glbs/000-017/f0e17c71b71b48d487b7b6a27ce78bb3.glb",
        "sha256": "3e7d4e51462e265d30654e9e89eb8b2605635ff806250cbb578e785b7fd95ddb",
        "name": "653", "author": "GulinAlex",
    },
    "platform_bed": {
        "uid": "fc9cbf532b6045969b9f7eeac339afd2",
        "path": "glbs/000-099/fc9cbf532b6045969b9f7eeac339afd2.glb",
        "sha256": "5d0682406b751601754be00da984acad525ca4234acdedf3bf6e61ce98438b40",
        "name": "Stylized lowpoly bed", "author": "tharadelamo",
    },
    "office_desk": {
        "uid": "1837f10d9b064fd88a607a3d391a17af",
        "path": "glbs/000-068/1837f10d9b064fd88a607a3d391a17af.glb",
        "sha256": "1e315596341cb0f33cd39c5ded2d9ca66940af01c52eac2c1ca603280e072aec",
        "name": "Meja Komputer", "author": "sutikno",
    },
}

# Kenney Furniture Kit (CC0, kenney.nl) — sanitary ware and kitchen modules
# that neither Poly Haven nor our Objaverse pins carry (feedback #021/#022/
# #025). One sha256-pinned zip; selected GLBs are extracted into
# assets/kenney_<model>/<model>.glb (one file per dir — the loader's rule).
KENNEY_KIT_URL = ("https://kenney.nl/media/pages/assets/furniture-kit/"
                  "440e0608a4-1677580847/kenney_furniture-kit.zip")
KENNEY_KIT_SHA256 = (
    "e67652d0932cee41683f74711c03d3e192a2af9979ef8e6b237711f5482d46b0")
KENNEY_MODELS = [
    "toilet", "bathroomSinkSquare", "shower",
    "kitchenSink", "kitchenStove", "kitchenFridgeLarge",
    "loungeChairRelax",
]


def fetch_kenney() -> list[dict]:
    """Extract the pinned Kenney models. The zip is fetched only when a
    model is missing and is not kept — the sha256 pin makes re-downloads
    reproducible."""
    missing = [m for m in KENNEY_MODELS
               if not (ASSETS_DIR / f"kenney_{m}" / f"{m}.glb").exists()]
    if missing:
        req = urllib.request.Request(
            KENNEY_KIT_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=600) as r:
            data = r.read()
        actual = hashlib.sha256(data).hexdigest()
        if actual != KENNEY_KIT_SHA256:
            sys.exit(f"ERROR: sha256 mismatch for Kenney kit: got {actual}")
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for model in missing:
                member = f"Models/GLTF format/{model}.glb"
                dest_dir = ASSETS_DIR / f"kenney_{model}"
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
        "kit_sha256": KENNEY_KIT_SHA256,
    } for m in KENNEY_MODELS]


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def download(url: str, dest: Path, md5: str) -> None:
    """Atomic download: write to .part, verify md5, rename."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read()
    actual = hashlib.md5(data).hexdigest()
    if actual != md5:
        sys.exit(f"ERROR: md5 mismatch for {url}: expected {md5}, got {actual}")
    part.write_bytes(data)
    part.rename(dest)


def fetch_asset(asset_id: str) -> dict:
    """Download one asset's glTF + dependencies. Returns license info."""
    dest_dir = ASSETS_DIR / asset_id
    marker = dest_dir / ".complete"
    files = get_json(f"https://api.polyhaven.com/files/{asset_id}")
    gltf = files["gltf"][RESOLUTION]["gltf"]
    if marker.exists() and marker.read_text() != gltf["md5"]:
        # Upstream republished the asset — a stale cache would silently
        # diverge from the provenance we record below.
        print(f"{asset_id}: upstream md5 changed, re-downloading")
        marker.unlink()
    if marker.exists():
        print(f"{asset_id}: cached")
    else:
        gltf_name = gltf["url"].rsplit("/", 1)[-1]
        download(gltf["url"], dest_dir / gltf_name, gltf["md5"])
        for rel_path, meta in gltf["include"].items():
            # API-provided path — refuse traversal out of the asset dir
            target = (dest_dir / rel_path).resolve()
            if not target.is_relative_to(dest_dir.resolve()):
                sys.exit(f"ERROR: include path escapes asset dir: {rel_path!r}")
            download(meta["url"], target, meta["md5"])
        marker.write_text(gltf["md5"])
        total = sum(f.stat().st_size for f in dest_dir.rglob("*") if f.is_file())
        print(f"{asset_id}: {len(gltf['include']) + 1} files, {total / 1024:.0f} KB")
    info = get_json(f"https://api.polyhaven.com/info/{asset_id}")
    return {
        "id": asset_id,
        "name": info.get("name", asset_id),
        "license": "CC0",
        "authors": sorted(info.get("authors", {})),
        "source": f"https://polyhaven.com/a/{asset_id}",
        "resolution": RESOLUTION,
        "gltf_md5": gltf["md5"],
    }


def fetch_objaverse(key: str, spec: dict) -> dict:
    """Download one pinned Objaverse GLB, sha256-verified.

    Cache validity = the exact pinned file exists and hashes to the pin —
    no marker file to go stale (review finding, Codex). After a successful
    fetch, any OTHER model file in the dir (from an older pin) is removed so
    the loader can never pick a stale asset.
    """
    dest_dir = ASSETS_DIR / key
    dest = dest_dir / f"{spec['uid']}.glb"
    if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() == spec["sha256"]:
        print(f"{key}: cached")
    else:
        dest_dir.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(
            OBJAVERSE_BASE + spec["path"], headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=600) as r:
            data = r.read()
        actual = hashlib.sha256(data).hexdigest()
        if actual != spec["sha256"]:
            sys.exit(f"ERROR: sha256 mismatch for {key}: got {actual}")
        part = dest.with_suffix(".glb.part")
        part.write_bytes(data)
        part.rename(dest)
        print(f"{key}: {len(data) / 1024:.0f} KB")
    for stale in dest_dir.glob("*.gl*"):
        if stale != dest and stale.suffix in (".glb", ".gltf"):
            print(f"{key}: removing stale {stale.name}")
            stale.unlink()
    return {
        "id": key,
        "name": spec["name"],
        "license": "CC BY 4.0 — attribution required",
        "authors": [spec["author"]],
        "source": f"https://sketchfab.com/3d-models/{spec['uid']}",
        "via": "objaverse (huggingface.co/datasets/allenai/objaverse)",
        "sha256": spec["sha256"],
    }


def main():
    licenses = [fetch_asset(a) for a in ASSETS]
    licenses += [fetch_objaverse(k, s) for k, s in sorted(OBJAVERSE.items())]
    licenses += fetch_kenney()
    ASSETS_DIR.mkdir(exist_ok=True)
    target = ASSETS_DIR / "licenses.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(licenses, indent=2))
    tmp.replace(target)  # atomic — an interrupted run never leaves broken JSON
    print(f"wrote {target} ({len(licenses)} assets)")


main()
