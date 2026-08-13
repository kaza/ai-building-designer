"""Element metadata for the 3D scene — stdlib only (runs inside Blender).

The OBJ hop strips every property, leaving only mesh names. This module
rebuilds the link: scene_blender stamps each imported object with custom
properties (ab_global_id, ab_kind, ab_load_bearing, ab_name) from
building.json, the glTF export carries them as node extras, and the
walkthrough reads real attributes instead of parsing names (owner
2026-08-10: "why don't we have a real attribute for that").
"""

from __future__ import annotations

# building.json collection -> the IFC class ifc_to_obj names objects with
# (roofs are exported as IfcSlab entities — see export/ifc.py)
_PREFIX = {
    "walls": "IfcWallStandardCase",
    "slabs": "IfcSlab",
    "roofs": "IfcSlab",
    "doors": "IfcDoor",
    "windows": "IfcWindow",
    "staircases": "IfcStair",
    "beams": "IfcBeam",
    "columns": "IfcColumn",
}

# kinds whose material is a rendering attribute (specs/columns.md,
# specs/seismic-lateral.md §wall materials). Beams also carry a material
# field in JSON, but only these drive the X-ray palette.
_MATERIAL_KINDS = {"walls", "columns"}


# plan-tag prefixes, mirroring Story.ensure_tags numbering (per story, in
# element order) so the walkthrough and the 2D plan speak the same ids.
# Non-ground stories get an initial prefix (G:W3) — feedback #007.
_TAG_PREFIX = {"walls": "W", "doors": "D", "windows": "Win",
               "staircases": "ST"}


def element_metadata(doc: dict) -> dict[str, dict]:
    """OBJ object name -> {global_id, kind, name, load_bearing, tag}."""
    out: dict[str, dict] = {}
    for story in doc.get("stories", []):
        story_prefix = ("" if story.get("elevation", 0) == 0
                        else f"{(story.get('name') or 'S')[0]}:")
        for kind, prefix in _PREFIX.items():
            for i, el in enumerate(story.get(kind, []), start=1):
                name = el.get("name") or ""
                if not name:
                    continue
                tag = ""
                if kind in _TAG_PREFIX:
                    tag = story_prefix + (
                        el.get("tag") or f"{_TAG_PREFIX[kind]}{i}")
                key = f"{prefix}_{name.replace(' ', '_')}"
                material = ""
                if kind in _MATERIAL_KINDS:
                    # walls: None/absent = masonry legacy default —
                    # rendered as "" so old GLBs stay byte-identical
                    material = el.get("material") or ""
                out[key] = {
                    "global_id": el.get("global_id", ""),
                    "kind": kind[:-1] if kind.endswith("s") else kind,
                    "name": name,
                    "load_bearing": bool(el.get("load_bearing")),
                    "tag": tag,
                    "material": material,
                }
    return out
