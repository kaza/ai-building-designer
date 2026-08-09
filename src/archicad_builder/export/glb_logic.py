"""Pure decisions for the GLB export — importable WITHOUT bpy.

The Blender shim (glb_blender.py) runs inside Blender's bundled Python,
which has neither pydantic nor this venv — so everything testable lives
here, stdlib-only, and the shim stays a thin bpy adapter (ADR-006).
"""

from __future__ import annotations

import tomllib

FALLBACK = (1.0, 0.0, 1.0, 1.0)   # magenta: an unmapped procedural material


def read_palette(project_toml_text: str) -> dict[str, tuple]:
    """Palette from project.toml text. Lenient here (stdlib only) — the
    strict ProjectConfig gate runs in the pipeline's `validate` step before
    any Blender step, so a malformed file never reaches this code."""
    raw = tomllib.loads(project_toml_text)
    palette = raw.get("appearance", {}).get("palette", {})
    return {name: tuple(rgba) for name, rgba in palette.items()}


def flat_color(material_name: str,
               palette: dict[str, tuple]) -> tuple[tuple, str | None]:
    """(rgba, warning) for a procedural material's flat stand-in."""
    color = palette.get(material_name)
    if color is None:
        return FALLBACK, (f"material '{material_name}' not in palette "
                          "-> magenta")
    return color, None


def should_prune(obj_type: str, has_children: bool, name: str,
                 hide_render: bool) -> bool:
    """Objects the walkthrough must not contain.

    Childless empties only — asset instance roots are empties WITH
    children, and deleting those would orphan the whole hierarchy.
    """
    return (obj_type in {"CAMERA", "LIGHT"}
            or (obj_type == "EMPTY" and not has_children)
            or name.startswith("StairwellCutter")
            or hide_render)
