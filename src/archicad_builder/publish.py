"""Publish a project's built artifacts to the cloud (specs/web-deployment.md).

    archicad-builder publish villa-maketa

The deliberate release step — NOT a push side effect:
1. refuses a dirty or unpushed tree (what's live must be reproducible from git);
2. refuses a project whose pipeline did not complete cleanly for exactly
   these inputs, sources and tools (specs/project-pipeline.md) — the git
   tree can be clean while the artifacts on disk came from an older model;
3. validates EVERYTHING before uploading a single byte, so a failure
   cannot leave half a release in blob (Codex review 2026-08-09);
4. uploads the big artifacts under SHA-stamped names, then build.json
   LAST — it is the release pointer the web app reads, so a reader never
   sees a pointer to artifacts that don't exist yet.

Auth: uses the az CLI login (key lookup), no secrets in the repo.
"""
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from archicad_builder.pipeline import (
    Lock,
    freshness_problems,
    load_pipeline,
    publishable_artifacts,
)

ACCOUNT = "stbuildingdesigner"
SUBSCRIPTION = "DEV - PracticeVaultAI"
CONTAINER = "projects"
REPO = Path(__file__).resolve().parents[2]

# Which DECLARED artifacts are homepage images. The list of files comes
# from the pipeline config, never from a directory glob: a glob publishes
# whatever happens to be lying in output/, including renders from an older
# model that no step claims (CodeRabbit review 2026-08-09).
PLAN_PATTERNS = ("floor_*.png", "perspective.png", "top_down.png")


def channel_dest(project: str, channel: str | None) -> str:
    """Blob prefix for this release: the project itself, or a publish
    channel (specs/web-deployment.md). A channel must extend the owning
    project's name (`<project>--<suffix>`) so an alias can never write
    into another project's prefix."""
    if channel is None:
        return project
    prefix = f"{project}--"
    if not channel.startswith(prefix):
        sys.exit(f"channel {channel!r} must start with {prefix!r} — "
                 "aliases stay inside the owning project's namespace")
    suffix = channel[len(prefix):]
    if not suffix:
        sys.exit(f"channel {channel!r} has an empty suffix — name the "
                 "candidate (e.g. villa-maketa--b-garage)")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", suffix):
        sys.exit(f"channel suffix {suffix!r} must be lowercase kebab "
                 "([a-z0-9-]) — it becomes a URL path segment and blob "
                 "prefix")
    return channel


def run(*cmd: str) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # az failures are usually auth problems; the message is the useful
        # part and check=True threw it away
        raise subprocess.CalledProcessError(
            proc.returncode, cmd, proc.stdout,
            proc.stderr or "(no stderr)")
    return proc.stdout


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
        # LANCZOS: bicubic aliases the thin black lines of a plan drawing
        img = img.resize(
            (MAX_PLAN_WIDTH, round(img.height * MAX_PLAN_WIDTH / img.width)),
            Image.Resampling.LANCZOS)
    photographic = src_png.stem in ("perspective", "top_down")
    if photographic:
        out = tmp / (src_png.stem + ".jpg")
        img.convert("RGB").save(out, "JPEG", quality=82)
    else:
        out = tmp / src_png.name
        img.save(out, "PNG", optimize=True)
    return out


def publish(project: str, channel: str | None = None) -> None:
    dest = channel_dest(project, channel)
    project_dir = REPO / "projects" / project
    out = project_dir / "output"
    if not out.is_dir():
        sys.exit(f"no output dir for {project!r} — build it first")

    if run("git", "-C", str(REPO), "status", "--porcelain").strip():
        sys.exit("refusing to publish: working tree is dirty — commit first")
    # compare HEAD to its upstream directly: parsing "ahead" out of the
    # short status missed a detached HEAD and a missing upstream (Codex)
    local = run("git", "-C", str(REPO), "rev-parse", "HEAD").strip()
    try:
        remote = run("git", "-C", str(REPO), "rev-parse", "@{u}").strip()
    except subprocess.CalledProcessError:
        sys.exit("refusing to publish: HEAD has no upstream — push first")
    if local != remote:
        sys.exit("refusing to publish: HEAD differs from its upstream "
                 "— push first")
    sha = run("git", "-C", str(REPO), "rev-parse", "--short", "HEAD").strip()

    # A clean git tree says the SOURCE is reproducible; it says nothing
    # about the artifacts on disk. This does. The lock is held from here
    # through the last upload so a concurrent `pipeline` cannot move an
    # artifact out from under us after it passed the check.
    with Lock(project_dir):
        _publish_locked(project_dir, project, sha, out, dest)


def _publish_locked(project_dir: Path, project: str, sha: str,
                    out: Path, dest: str) -> None:
    problems = freshness_problems(project_dir)
    if problems:
        sys.exit("refusing to publish: the built artifacts are not fresh:\n  "
                 + "\n  ".join(problems))
    cfg, _steps = load_pipeline(project_dir)
    model = cfg.get("model")
    if not model:
        sys.exit(f"pipeline.toml for {project!r} declares no [project] model "
                 "— that is the artifact basename (e.g. 'villa')")

    glb = out / f"{model}.glb"
    html = out / "walkthrough.html"
    for f in (glb, html):
        if not f.exists():
            sys.exit(f"missing artifact {f} — run the build pipeline first")
    import fnmatch
    declared = publishable_artifacts(project_dir)
    plans = sorted({Path(rel).name for rel in declared
                    for pat in PLAN_PATTERNS
                    if fnmatch.fnmatch(Path(rel).name, pat)
                    and (project_dir / rel).is_file()})
    stray = sorted({p.name for pat in PLAN_PATTERNS for p in out.glob(pat)}
                   - set(plans))
    if stray:
        sys.exit("refusing to publish: " + ", ".join(stray) + " sit in "
                 "output/ but no pipeline step declares them — they would "
                 "be shipped without any freshness check. Declare them "
                 "(outputs / optional_outputs) or delete them.")

    # ---- preflight: every check BEFORE the first upload ----------------
    xray = out / "xray.html"
    field = out / "fem-field.json"
    if xray.exists() != field.exists():
        sys.exit("partial FEM artifacts: need BOTH xray.html and "
                 "fem-field.json (or neither) — re-run `archicad_builder "
                 "fem` or remove the stray file")
    has_fem = xray.exists() and field.exists()
    if has_fem:
        digest = hashlib.sha256(
            (REPO / "projects" / project / "building.json").read_bytes()
        ).hexdigest()[:12]
        if json.loads(field.read_text()).get("digest") != digest:
            sys.exit("stale FEM results: fem-field.json was computed from a "
                     "different building.json — re-run `archicad_builder "
                     f"fem {project}` first")
    # release-pinning (specs/fem-xray.md): published HTML references exact
    # SHA-stamped asset names so two releases can never mix mid-session.
    wt = html.read_text().replace(f"fetch('{model}.glb')",
                                  f"fetch('{model}-{sha}.glb')")
    if f"{model}-{sha}.glb" not in wt:
        sys.exit(f"release pinning failed: fetch('{model}.glb') not found "
                 "in walkthrough.html — did make_walkthrough change?")

    # ---- materialise EVERY payload before the first upload -------------
    # transcoding a plan or reading the X-ray used to happen mid-release,
    # so a corrupt file failed after several blobs were already live
    # (Codex review 2026-08-09).
    with tempfile.TemporaryDirectory() as td:
        staged: list[tuple[Path, str, str]] = []      # (file, key, ctype)
        staged.append((glb, f"{dest}/{model}-{sha}.glb",
                       "model/gltf-binary"))
        if has_fem:
            wt = wt.replace("fem-field.json", f"fem-field-{sha}.json")
        pinned = Path(td) / "walkthrough.html"
        pinned.write_text(wt)
        staged.append((pinned, f"{dest}/walkthrough-{sha}.html",
                       "text/html"))
        if has_fem:
            staged.append((field, f"{dest}/fem-field-{sha}.json",
                           "application/json"))
            xr = Path(td) / "xray.html"
            xr.write_text(xray.read_text().replace(
                "fem-field.json", f"fem-field-{sha}.json"))
            staged.append((xr, f"{dest}/xray-{sha}.html", "text/html"))
        plan_entries = []
        for name in plans:
            web = web_plan(out / name, Path(td))
            key = f"{web.stem}-{sha}{web.suffix}"
            staged.append((web, f"{dest}/{key}",
                           "image/jpeg" if web.suffix == ".jpg"
                           else "image/png"))
            plan_entries.append({
                "file": key,
                "caption": web.stem.replace("floor_", "").replace("_", " "),
            })

        print(f"publishing {project} @ {sha}")
        for src, key, ctype in staged:
            upload(src, key, ctype, IMMUTABLE)

    build = {
        "sha": sha,
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": f"{model}-{sha}.glb",
        "walkthrough": f"walkthrough-{sha}.html",
        "plans": plan_entries,
    }
    if has_fem:
        build["xray"] = f"xray-{sha}.html"
        build["fem_field"] = f"fem-field-{sha}.json"
    build_file = out / "build.json"
    build_file.write_text(json.dumps(build, indent=2))
    upload(build_file, f"{dest}/build.json", "application/json", POINTER)
    print(f"live: build.json now points at {sha}")


def main() -> None:
    args = sys.argv[1:]
    channel = None
    if "--as" in args:
        i = args.index("--as")
        try:
            channel = args[i + 1]
        except IndexError:
            sys.exit("--as needs a channel name (e.g. villa-maketa--b)")
        args = args[:i] + args[i + 2:]
    if len(args) != 1:
        sys.exit("usage: python -m archicad_builder.publish <project> "
                 "[--as <project>--<suffix>]")
    publish(args[0], channel)


if __name__ == "__main__":
    main()
