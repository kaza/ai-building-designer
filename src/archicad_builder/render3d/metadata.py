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
}


def element_metadata(doc: dict) -> dict[str, dict]:
    """OBJ object name -> {global_id, kind, name, load_bearing}."""
    out: dict[str, dict] = {}
    for story in doc.get("stories", []):
        for kind, prefix in _PREFIX.items():
            for el in story.get(kind, []):
                name = el.get("name") or ""
                if not name:
                    continue
                key = f"{prefix}_{name.replace(' ', '_')}"
                out[key] = {
                    "global_id": el.get("global_id", ""),
                    "kind": kind[:-1] if kind.endswith("s") else kind,
                    "name": name,
                    "load_bearing": bool(el.get("load_bearing")),
                }
    return out
