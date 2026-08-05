"""Export villa.blend to a glTF binary for the browser walkthrough.

Run headless (order matters — reads the .blend saved by render_blender.py):

    /Applications/Blender.app/Contents/MacOS/Blender -b \
        projects/villa-maketa/output/villa.blend -P projects/villa-maketa/export_glb.py

Procedural textures (wave/brick node trees) cannot ride into glTF without
baking, so every material whose Base Color is driven by a non-image node gets
a flat color from PALETTE below. Materials missing from the palette turn
magenta — loud beats subtle. Glass/pool keep their transmission (exported as
KHR_materials_transmission, supported by Three.js).
"""
import sys
from pathlib import Path

import bpy

OUT = Path(__file__).parent / "output" / "villa.glb"

# Flat stand-ins for the procedural materials in render_blender.py (midpoint
# of each wood ramp / tile color). Plain-colored materials keep their own
# base color and never hit this map.
PALETTE = {
    "Parquet": (0.55, 0.40, 0.24, 1.0),
    "DeckWood": (0.32, 0.19, 0.10, 1.0),
    "DoorWood": (0.38, 0.24, 0.13, 1.0),
    "FurnitureWood": (0.42, 0.28, 0.16, 1.0),
    "StairWood": (0.32, 0.19, 0.10, 1.0),
    "Wardrobe": (0.42, 0.31, 0.20, 1.0),
    "Lawn": (0.20, 0.42, 0.16, 1.0),
    "FloorTiles": (0.55, 0.72, 0.80, 1.0),
    "FloorHall": (0.78, 0.72, 0.60, 1.0),
    "FloorKitchen": (0.72, 0.66, 0.55, 1.0),
}
FALLBACK = (1.0, 0.0, 1.0, 1.0)  # magenta: an unmapped procedural material


def principled_of(mat):
    """The Principled BSDF actually wired to the material output, or None."""
    if not mat.node_tree:
        return None
    out = next(
        (n for n in mat.node_tree.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output),
        None,
    )
    if out is None or not out.inputs["Surface"].is_linked:
        return None
    node = out.inputs["Surface"].links[0].from_node
    return node if node.type == "BSDF_PRINCIPLED" else None


def flatten_materials():
    for mat in bpy.data.materials:
        # Only OUR procedural materials get flattened (render_blender.py tags
        # them). Imported PBR assets keep their texture chains — the exporter
        # handles TEX_IMAGE natively, and name-matching would be fooled by
        # collisions like an imported 'Sofa'.
        if not mat.get("ab_procedural"):
            continue
        bsdf = principled_of(mat)
        if bsdf is None:
            continue
        base = bsdf.inputs["Base Color"]
        if base.is_linked and base.links[0].from_node.type != "TEX_IMAGE":
            for link in list(base.links):
                mat.node_tree.links.remove(link)
            color = PALETTE.get(mat.name)
            if color is None:
                color = FALLBACK
                print(f"WARN: material '{mat.name}' not in PALETTE -> magenta")
            base.default_value = color
            print(f"flattened '{mat.name}' -> {color}")
        # Procedural normal/bump chains would only produce exporter warnings;
        # real normal maps (NORMAL_MAP node) export fine and stay.
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
        o
        for o in bpy.data.objects
        if o.type in {"CAMERA", "LIGHT"}
        # childless empties only — asset instance roots are empties WITH
        # children, and deleting those would orphan the whole hierarchy
        or (o.type == "EMPTY" and not o.children)
        or o.name.startswith("StairwellCutter")
        or o.hide_render
    }
    for obj in bpy.data.objects:
        if obj in doomed:
            continue
        for mod in list(obj.modifiers):
            if getattr(mod, "object", None) in doomed:
                mod_desc = f"{mod.type} '{mod.name}'"  # mod's RNA dies on apply
                with bpy.context.temp_override(
                    object=obj, active_object=obj, selected_objects=[obj]
                ):
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                print(f"applied {mod_desc} on '{obj.name}'")
    for o in doomed:
        print(f"pruning {o.type} '{o.name}' (hide_render={o.hide_render})")
        bpy.data.objects.remove(o, do_unlink=True)


def main():
    prune_objects()
    flatten_materials()
    result = bpy.ops.export_scene.gltf(
        filepath=str(OUT),
        export_format="GLB",
        export_apply=True,  # realizes the remaining bevel/wireframe modifiers
        export_cameras=False,
        export_lights=False,
    )
    if result != {"FINISHED"}:
        print(f"ERROR: glTF export returned {result}")
        sys.exit(1)
    size = OUT.stat().st_size
    print(f"exported {OUT} ({size / 1024:.0f} KB)")
    if size < 10_000:
        print("ERROR: GLB suspiciously small — export produced no real geometry")
        sys.exit(1)


main()
