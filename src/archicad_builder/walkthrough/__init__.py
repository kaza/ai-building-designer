"""Build the browser-walkthrough HTML page for a project.

Moved from projects/villa-maketa/make_walkthrough.py (ADR-006). The page
template lives beside this module (template.html); project taste — title,
model name, camera spawn — comes from project.toml
(specs/project-config.md). Spec: specs/browser-walkthrough.md.

Validates the GLB (magic, version, chunk lengths, no cameras/cutters left)
and writes output/walkthrough.html, which fetches ./<model>.glb at runtime.
Browsers block fetch() from file:// — serve output/ (the `serve` command),
which also receives F-key feedback.
"""

from __future__ import annotations

import json
import struct
from importlib import resources
from pathlib import Path

from archicad_builder.project_config import ProjectConfig

THREE_VERSION = "0.170.0"

# Helpers the GLB export must have pruned. Exact match on the Blender base
# name (before any ".001" suffix) — a prefix test would flag e.g. "Sunshade".
HELPER_NAMES = {"Sun", "CamPersp", "CamTop", "Target"}


class GlbError(Exception):
    """The GLB is not shippable; the message says why."""


def validate_glb(data: bytes) -> dict:
    def die(msg: str) -> None:
        raise GlbError(msg)

    if len(data) < 20:
        die(f"file too short to be a GLB ({len(data)} bytes)")
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        die(f"not a GLB (magic={magic!r})")
    if version != 2:
        die(f"unsupported glTF container version {version}")
    if length != len(data):
        die(f"header length {length} != file length {len(data)}")
    # Walk every chunk: 8-byte header + 4-byte-aligned payload, no junk.
    doc = None
    offset = 12
    while offset < length:
        if offset + 8 > length:
            die(f"truncated chunk header at offset {offset}")
        chunk_len, chunk_type = struct.unpack_from("<I4s", data, offset)
        if chunk_len % 4 != 0:
            die(f"chunk {chunk_type!r} length {chunk_len} not 4-byte aligned")
        if offset + 8 + chunk_len > length:
            die(f"chunk {chunk_type!r} overruns the file")
        if offset == 12:
            if chunk_type != b"JSON":
                die(f"first chunk is {chunk_type!r}, expected JSON")
            doc = json.loads(data[offset + 8: offset + 8 + chunk_len])
        offset += 8 + chunk_len
    if offset != length:
        die(f"{length - offset} trailing bytes after the last chunk")
    if doc.get("asset", {}).get("version") != "2.0":
        die(f"unexpected glTF asset version {doc.get('asset')}")
    if not doc.get("meshes"):
        die("GLB contains no meshes")
    if not doc.get("materials"):
        die("GLB contains no materials")
    if doc.get("cameras"):
        die("cameras leaked into the GLB — the export prune failed")
    leftovers = [
        name
        for n in doc.get("nodes", [])
        if (name := n.get("name", "")).startswith("StairwellCutter")
        or name.split(".")[0] in HELPER_NAMES
    ]
    if leftovers:
        die(f"helper objects leaked into the GLB: {leftovers}")
    print(
        f"GLB ok: {len(data) / 1024:.0f} KB, "
        f"{len(doc['meshes'])} meshes, {len(doc['materials'])} materials"
    )
    return doc


def element_tags(doc: dict) -> dict:
    """Sanitized element name -> plan tag (W3, D5, Win4, ST1).

    Mirrors Story.ensure_tags() numbering (per story, in element order) so
    the walkthrough info card and the 2D plan speak the same ids — that is
    how the owner references elements. Tags repeat per story (the garage
    has its own W1…), so non-ground stories get an initial prefix (G:W3) —
    feedback #007 showed bare garage tags read as ground-floor elements.
    """
    tags: dict[str, str] = {}
    for story in doc.get("stories", []):
        story_prefix = ("" if story.get("elevation", 0) == 0
                        else f"{(story.get('name') or 'S')[0]}:")
        for key, prefix in (("walls", "W"), ("doors", "D"),
                            ("windows", "Win"), ("staircases", "ST")):
            for i, el in enumerate(story.get(key, []), start=1):
                tag = el.get("tag") or f"{prefix}{i}"
                name = el.get("name", "")
                if name:
                    tags.setdefault(name.replace(" ", "_"),
                                    story_prefix + tag)
    return tags


def storey_bands(doc: dict) -> list:
    """[{name, elevation, height, rooms}] sorted by elevation — the viewer
    shows which storey AND room the camera is in (feedback #007: the owner
    sank through the floor into the garage without noticing; raw
    coordinates broke the feedback conversation)."""
    bands = []
    for i, s in enumerate(doc.get("stories", []), start=1):
        spaces = list(s.get("spaces", []))
        for apt in s.get("apartments", []):
            spaces.extend(apt.get("spaces", []))
        elevation = s.get("elevation", 0)
        bands.append({
            "name": s.get("name") or f"Storey {i}",
            "elevation": elevation,
            "height": s.get("height", 3.0),
            "rooms": [
                {"name": sp.get("name") or sp.get("room_type", "room"),
                 "poly": [[v["x"], v["y"]]
                          for v in sp["boundary"]["vertices"]]}
                for sp in spaces if sp.get("boundary")
            ],
        })
    return sorted(bands, key=lambda b: b["elevation"])


def render_page(doc: dict, *, model: str, title: str,
                start: tuple[float, float, float],
                loads_json: str = "{}") -> str:
    """The final HTML from the building document + project taste."""
    template = (resources.files("archicad_builder.walkthrough")
                / "template.html").read_text()
    return (template
            .replace("__THREE_VERSION__", THREE_VERSION)
            .replace("__TITLE__", title)
            .replace("__MODEL__", model)
            .replace("__START__", ", ".join(str(c) for c in start))
            .replace("__TAGS__", json.dumps(element_tags(doc),
                                            sort_keys=True))
            .replace("__STOREYS__", json.dumps(storey_bands(doc)))
            .replace("__LOADS__", loads_json))


def build_page(project_dir: Path, model: str) -> Path:
    """Validate output/<model>.glb and write output/walkthrough.html."""
    project_dir = Path(project_dir)
    out_dir = project_dir / "output"
    cfg = ProjectConfig.load(project_dir)
    validate_glb((out_dir / f"{model}.glb").read_bytes())
    doc = json.loads((project_dir / "building.json").read_text())
    loads_file = out_dir / "loads.json"
    html = render_page(
        doc, model=model, title=cfg.project.title,
        start=cfg.walkthrough.start,
        loads_json=loads_file.read_text() if loads_file.exists() else "{}")
    target = out_dir / "walkthrough.html"
    target.write_text(html, encoding="utf-8")
    tags = element_tags(doc)
    print(f"wrote {target} ({target.stat().st_size / 1024:.0f} KB; "
          f"{len(tags)} element tags; loads ./{model}.glb at runtime)")
    return target
