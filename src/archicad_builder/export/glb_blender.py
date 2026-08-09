"""Blender shim: export the loaded .blend to a glTF binary (GLB).

Runs INSIDE Blender (bundled Python — no venv, no pydantic):

    blender -b projects/<name>/output/<model>.blend \
        -P {framework}/export/glb_blender.py

Moved from projects/villa-maketa/export_glb.py (ADR-006). The palette now
comes from the project's project.toml; pure decisions live in glb_logic.py
(tested in the venv); this file is the thin bpy adapter.

Procedural textures (wave/brick node trees) cannot ride into glTF without
baking, so every material whose Base Color is driven by a non-image node
gets a flat color from the palette. Materials missing from the palette turn
magenta — loud beats subtle. Glass/pool keep their transmission (exported
as KHR_materials_transmission, supported by Three.js).
"""
import sys
from pathlib import Path

import bpy

# stdlib-only bootstrap: make glb_logic importable from inside Blender
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from archicad_builder.export.glb_logic import (  # noqa: E402
    flat_color,
    read_palette,
    should_prune,
)

if not bpy.data.filepath:
    sys.exit("usage: blender -b <project>/output/<model>.blend "
             "-P glb_blender.py — no .blend is loaded")
BLEND = Path(bpy.data.filepath)                  # projects/<p>/output/<m>.blend
PROJECT_DIR = BLEND.parent.parent
OUT = BLEND.parent / (BLEND.stem + ".glb")


def principled_of(mat):
    """The Principled BSDF actually wired to the material output, or None."""
    if not mat.node_tree:
        return None
    out = next(
        (n for n in mat.node_tree.nodes
         if n.type == "OUTPUT_MATERIAL" and n.is_active_output),
        None,
    )
    if out is None or not out.inputs["Surface"].is_linked:
        return None
    node = out.inputs["Surface"].links[0].from_node
    return node if node.type == "BSDF_PRINCIPLED" else None


def flatten_materials(palette):
    for mat in bpy.data.materials:
        # Only OUR procedural materials get flattened (the scene builder
        # tags them). Imported PBR assets keep their texture chains — the
        # exporter handles TEX_IMAGE natively, and name-matching would be
        # fooled by collisions like an imported 'Sofa'.
        if not mat.get("ab_procedural"):
            continue
        bsdf = principled_of(mat)
        if bsdf is None:
            continue
        base = bsdf.inputs["Base Color"]
        if base.is_linked and base.links[0].from_node.type != "TEX_IMAGE":
            for link in list(base.links):
                mat.node_tree.links.remove(link)
            color, warning = flat_color(mat.name, palette)
            if warning:
                print(f"WARN: {warning}")
            base.default_value = color
            print(f"flattened '{mat.name}' -> {color}")
        # Procedural normal/bump chains would only produce exporter
        # warnings; real normal maps (NORMAL_MAP node) export fine and stay.
        normal = bsdf.inputs["Normal"]
        if normal.is_linked and normal.links[0].from_node.type != "NORMAL_MAP":
            for link in list(normal.links):
                mat.node_tree.links.remove(link)


def prune_objects():
    """Drop everything the walkthrough must not contain.

    Modifiers referencing a doomed helper (the stairwell booleans) must be
    applied BEFORE the helper dies — export_apply=True can't realize a
    modifier whose object is already gone (review finding, Codex: the GLB
    shipped without the stairwell hole).
    """
    doomed = {
        o for o in bpy.data.objects
        if should_prune(o.type, bool(o.children), o.name, o.hide_render)
    }
    for obj in bpy.data.objects:
        if obj in doomed:
            continue
        for mod in list(obj.modifiers):
            if getattr(mod, "object", None) in doomed:
                mod_desc = f"{mod.type} '{mod.name}'"  # RNA dies on apply
                with bpy.context.temp_override(
                    object=obj, active_object=obj, selected_objects=[obj]
                ):
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                print(f"applied {mod_desc} on '{obj.name}'")
    for o in doomed:
        print(f"pruning {o.type} '{o.name}' (hide_render={o.hide_render})")
        bpy.data.objects.remove(o, do_unlink=True)


def main():
    toml_path = PROJECT_DIR / "project.toml"
    palette = read_palette(
        toml_path.read_text()) if toml_path.is_file() else {}
    prune_objects()
    flatten_materials(palette)
    result = bpy.ops.export_scene.gltf(
        filepath=str(OUT),
        export_format="GLB",
        export_apply=True,  # realizes remaining bevel/wireframe modifiers
        export_cameras=False,
        export_lights=False,
    )
    if result != {"FINISHED"}:
        print(f"ERROR: glTF export returned {result}")
        sys.exit(1)
    size = OUT.stat().st_size
    print(f"exported {OUT} ({size / 1024:.0f} KB)")
    if size < 10_000:
        print("ERROR: GLB suspiciously small — export produced no real "
              "geometry")
        sys.exit(1)


main()
