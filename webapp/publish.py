"""Publish a project's built artifacts to the cloud (specs/web-deployment.md).

    .venv/bin/python webapp/publish.py villa-maketa

The deliberate release step — NOT a push side effect:
1. refuses a dirty or unpushed tree (what's live must be reproducible from git);
2. uploads the big artifacts under SHA-stamped names FIRST
   (villa-<sha>.glb, walkthrough-<sha>.html) plus the plan PNGs;
3. uploads build.json LAST — it is the release pointer the web app reads,
   so a reader never sees a pointer to artifacts that don't exist yet.

Auth: uses the az CLI login (key lookup), no secrets in the repo.
"""
import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

ACCOUNT = "stbuildingdesigner"
SUBSCRIPTION = "DEV - PracticeVaultAI"
CONTAINER = "projects"
REPO = Path(__file__).resolve().parent.parent

PLAN_PATTERNS = ("floor_*.png", "perspective.png", "top_down.png")


def run(*cmd: str) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def upload(src: Path, key: str, content_type: str, cache: str) -> None:
    run("az", "storage", "blob", "upload",
        "--subscription", SUBSCRIPTION, "--account-name", ACCOUNT,
        "--auth-mode", "key", "-c", CONTAINER, "-n", key,
        "-f", str(src), "--overwrite", "--content-type", content_type,
        "--content-cache-control", cache,
        "-o", "none")
    print(f"  {key}  ({src.stat().st_size / 1e6:.1f} MB)")


# SHA-named artifacts never change under their name -> browsers keep them
# forever (a repeat visit re-downloads NOTHING until a new publish changes
# the SHA). build.json is the moving pointer -> never cached.
IMMUTABLE = "public, max-age=31536000, immutable"
POINTER = "no-cache"
MAX_PLAN_WIDTH = 1400  # px — homepage renders them ~1100px wide anyway


def web_plan(src_png: Path, tmp: Path) -> Path:
    """Web copy of a plan image: capped width; photographic renders
    (perspective/top-down) become JPEG (2.5 MB -> ~200 KB), line drawings
    stay PNG."""
    img = Image.open(src_png)
    if img.width > MAX_PLAN_WIDTH:
        img = img.resize(
            (MAX_PLAN_WIDTH, round(img.height * MAX_PLAN_WIDTH / img.width)))
    photographic = src_png.stem in ("perspective", "top_down")
    if photographic:
        out = tmp / (src_png.stem + ".jpg")
        img.convert("RGB").save(out, "JPEG", quality=82)
    else:
        out = tmp / src_png.name
        img.save(out, "PNG", optimize=True)
    return out


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: publish.py <project>")
    project = sys.argv[1]
    out = REPO / "projects" / project / "output"
    if not out.is_dir():
        sys.exit(f"no output dir for {project!r} — build it first")

    if run("git", "-C", str(REPO), "status", "--porcelain").strip():
        sys.exit("refusing to publish: working tree is dirty — commit first")
    upstream = run("git", "-C", str(REPO), "status", "-sb").splitlines()[0]
    if "ahead" in upstream:
        sys.exit("refusing to publish: HEAD not pushed — push first")
    sha = run("git", "-C", str(REPO), "rev-parse", "--short", "HEAD").strip()

    glb = out / "villa.glb"
    html = out / "walkthrough.html"
    for f in (glb, html):
        if not f.exists():
            sys.exit(f"missing artifact {f} — run the build pipeline first")
    plans = sorted(p.name for pat in PLAN_PATTERNS for p in out.glob(pat))

    print(f"publishing {project} @ {sha}")
    upload(glb, f"{project}/villa-{sha}.glb", "model/gltf-binary", IMMUTABLE)
    upload(html, f"{project}/walkthrough-{sha}.html", "text/html", IMMUTABLE)
    plan_entries = []
    with tempfile.TemporaryDirectory() as td:
        for p in plans:
            web = web_plan(out / p, Path(td))
            key = f"{web.stem}-{sha}{web.suffix}"
            ctype = "image/jpeg" if web.suffix == ".jpg" else "image/png"
            upload(web, f"{project}/{key}", ctype, IMMUTABLE)
            plan_entries.append({
                "file": key,
                "caption": web.stem.replace("floor_", "").replace("_", " "),
            })

    build = {
        "sha": sha,
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": f"villa-{sha}.glb",
        "walkthrough": f"walkthrough-{sha}.html",
        "plans": plan_entries,
    }
    build_file = out / "build.json"
    build_file.write_text(json.dumps(build, indent=2))
    upload(build_file, f"{project}/build.json", "application/json", POINTER)
    print(f"live: build.json now points at {sha}")


if __name__ == "__main__":
    main()
