"""Blender headless: build the project scene; optional Cycles renders.

Moved from projects/villa-maketa/render_blender.py (ADR-006). Runs INSIDE
Blender with cwd = the project directory:

    blender -b -P {framework}/render3d/scene_blender.py

v2 ("make it great"): procedural materials (wood planks, tiles with grout,
water, grass, plaster), Nishita sky lighting, window frames via wireframe
modifier, procedural furniture (beds/sofas built from parts, everything
beveled), DoF on the perspective camera.

Outputs:
  output/perspective.png — 3D perspective from SE
  output/top_down.png    — orthographic top view (maquette look)

"""

import json
import math
import os
import sys
import tomllib
from pathlib import Path

import bpy

# The pipeline runs every step with cwd = the project directory (ADR-006:
# this file is framework code; everything project-specific comes from the
# project's own files). Blender's Python has no pydantic — the strict
# ProjectConfig gate ran in the validate step; here plain tomllib is fine.
# Blender forwards everything after `--` to the script.
HERE = Path.cwd()
_extra = (sys.argv[sys.argv.index("--") + 1:]
          if "--" in sys.argv else [])
if not _extra:
    raise SystemExit(
        "usage: blender -b -P scene_blender.py -- <model-basename>")
MODEL = _extra[0]
CFG = (tomllib.loads((HERE / "project.toml").read_text())
       if (HERE / "project.toml").is_file() else {})
RENDER = CFG.get("render", {})
CAM = RENDER.get("camera", {})
OBJ = HERE / "output" / f"{HERE.name}.obj"
BUILDING = HERE / "building.json"
FURNITURE = HERE / "furniture.json"
OUT_PERSP = HERE / "output" / "perspective.png"
OUT_TOP = HERE / "output" / "top_down.png"

# Storey elevation = finished floor level; slabs hang below it, so the
# ground slab TOP is at z=0 (specs/storey-datum.md, feedback #013/#014).
SLAB_TOP = 0.0

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ── Material helpers ─────────────────────────────────────────────────────────


def _new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    return m, nt, bsdf


def flat_mat(name, rgba, roughness=0.7, metallic=0.0):
    m, _, bsdf = _new_mat(name)
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return m


def plaster_mat(name, rgba):
    """Wall plaster: subtle noise bump."""
    m, nt, bsdf = _new_mat(name)
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = 0.85
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 40.0
    noise.inputs["Detail"].default_value = 6.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.03
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def wood_mat(name, light=(0.42, 0.26, 0.14, 1), dark=(0.22, 0.12, 0.06, 1),
             plank_scale=(1.0, 12.0, 1.0), roughness=0.5):
    """Plank wood: banded wave texture distorted by noise, with bump."""
    m, nt, bsdf = _new_mat(name)
    bsdf.inputs["Roughness"].default_value = roughness
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = plank_scale
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.inputs["Scale"].default_value = 1.0
    wave.inputs["Distortion"].default_value = 4.0
    wave.inputs["Detail"].default_value = 2.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = dark
    ramp.color_ramp.elements[1].color = light
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(wave.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def tile_mat(name, tile_rgba, grout_rgba=(0.75, 0.75, 0.73, 1),
             tile_size=0.35, roughness=0.15):
    """Tiles with grout lines via brick texture (square tiles)."""
    m, nt, bsdf = _new_mat(name)
    bsdf.inputs["Roughness"].default_value = roughness
    coord = nt.nodes.new("ShaderNodeTexCoord")
    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.0
    brick.inputs["Scale"].default_value = 1.0 / tile_size
    brick.inputs["Color1"].default_value = tile_rgba
    brick.inputs["Color2"].default_value = tile_rgba
    brick.inputs["Mortar"].default_value = grout_rgba
    brick.inputs["Mortar Size"].default_value = 0.008
    if "Row Height" in brick.inputs:
        brick.inputs["Row Height"].default_value = 1.0
        brick.inputs["Brick Width"].default_value = 1.0
    nt.links.new(coord.outputs["Object"], brick.inputs["Vector"])
    nt.links.new(brick.outputs["Color"], bsdf.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.05
    nt.links.new(brick.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def water_mat(name):
    m, nt, bsdf = _new_mat(name)
    bsdf.inputs["Base Color"].default_value = (0.1, 0.45, 0.6, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.05
    bsdf.inputs["IOR"].default_value = 1.33
    for key in ("Transmission Weight", "Transmission"):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = 0.4
            break
    wave = nt.nodes.new("ShaderNodeTexNoise")
    wave.inputs["Scale"].default_value = 8.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.06
    nt.links.new(wave.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def grass_mat(name):
    m, nt, bsdf = _new_mat(name)
    bsdf.inputs["Roughness"].default_value = 0.9
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 60.0
    noise.inputs["Detail"].default_value = 8.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.08, 0.3, 0.05, 1)
    ramp.color_ramp.elements[1].color = (0.25, 0.5, 0.12, 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def glass_mat(name):
    # Light blue tint + low roughness = the maquette's mirrored-blue panes
    m, _, bsdf = _new_mat(name)
    bsdf.inputs["Base Color"].default_value = (0.62, 0.78, 0.92, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.02
    for key in ("Transmission Weight", "Transmission"):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = 0.85
            break
    return m


def srgb_hex_to_linear(hex_str):
    """sRGB hex (photo-sampled) -> linear RGBA for Blender sockets."""
    r, g, b = (int(hex_str.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (lin(r), lin(g), lin(b), 1.0)


def stone_mat(name):
    """Rubble masonry: brick texture, per-stone tint variation, deep mortar.

    Brick textures sample (x, y) of their vector — flat death on a vertical
    wall whose plane holds one of those constant. Walls here are axis-aligned,
    so u = x + y varies along ANY wall; v = z keeps courses horizontal.
    """
    m, nt, bsdf = _new_mat(name)
    bsdf.inputs["Roughness"].default_value = 0.9
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    u = nt.nodes.new("ShaderNodeMath")
    u.operation = "ADD"
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.5
    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Color1"].default_value = srgb_hex_to_linear("#B8AE9C")
    brick.inputs["Color2"].default_value = srgb_hex_to_linear("#7E7464")
    brick.inputs["Mortar"].default_value = srgb_hex_to_linear("#3E362C")
    brick.inputs["Mortar Size"].default_value = 0.014
    if "Brick Width" in brick.inputs:
        brick.inputs["Brick Width"].default_value = 0.5   # ~0.5m stones
        brick.inputs["Row Height"].default_value = 0.28   # ~0.28m courses
    # brownish patches so single stones read as different minerals
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 4.0
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[7].default_value = srgb_hex_to_linear("#6B5A44")  # B color
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    nt.links.new(coord.outputs["Object"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["X"], u.inputs[0])
    nt.links.new(sep.outputs["Y"], u.inputs[1])
    nt.links.new(u.outputs["Value"], comb.inputs["X"])
    nt.links.new(sep.outputs["Z"], comb.inputs["Y"])
    nt.links.new(comb.outputs["Vector"], brick.inputs["Vector"])
    nt.links.new(comb.outputs["Vector"], noise.inputs["Vector"])
    nt.links.new(brick.outputs["Color"], mix.inputs[6])          # A color
    nt.links.new(noise.outputs["Fac"], mix.inputs["Factor"])
    nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    nt.links.new(brick.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


# Door meshes rendered as glass panels (matched by substring against the
# IfcDoor object name). Owner request 2026-08-05.
GLASS_DOORS = (
    "Master_Bedroom_Terrace_Door",   # matches the Small leaf too
    "Bath_1_Door",
    "Room_2_Terrace_Door",           # sliding pane, photo #31 (2026-08-07)
)

# finish tag (building.json) -> MATS key. Unknown tags fail loud below.
FINISH_TO_MAT = {
    "stone_rubble": "stone",
    "accent": "accent",
    "roof_brown": "roof_brown",
    "glass": "glass",  # deck windscreen panel (feedback #004, photo #29)
}

MATS = {
    "wall": plaster_mat("Plaster", (0.8, 0.78, 0.74, 1.0)),
    "stone": stone_mat("StoneRubble"),
    "accent": flat_mat("Accent", srgb_hex_to_linear("#F4C14C"), roughness=0.5),
    "roof_brown": flat_mat("RoofBrown", srgb_hex_to_linear("#6E4E33"),
                           roughness=0.8),
    "soffit": flat_mat("Soffit", (0.92, 0.92, 0.9, 1.0), roughness=0.8),
    "slab": flat_mat("Slab", (0.78, 0.77, 0.74, 1.0), roughness=0.9),
    "stair": wood_mat("StairWood"),
    "glass": glass_mat("Glass"),
    "frame": flat_mat("Frame", (0.25, 0.25, 0.27, 1.0), roughness=0.4, metallic=0.6),
    "door": wood_mat("DoorWood", light=(0.45, 0.3, 0.17, 1), dark=(0.3, 0.18, 0.09, 1),
                     plank_scale=(1.0, 1.0, 1.0)),
    "deck": wood_mat("DeckWood", plank_scale=(6.0, 0.8, 1.0), roughness=0.6),
    "pool": water_mat("PoolWater"),
    "lawn": grass_mat("Lawn"),
    "ground": flat_mat("Ground", (0.42, 0.43, 0.42, 1.0), roughness=0.95),
    # floors by room type
    "floor_wet": tile_mat("FloorTiles", (0.55, 0.72, 0.8, 1.0), tile_size=0.3),
    "floor_hall": tile_mat("FloorHall", (0.78, 0.72, 0.6, 1.0), tile_size=0.45,
                           roughness=0.3),
    "floor_room": wood_mat("Parquet", light=(0.62, 0.45, 0.28, 1),
                           dark=(0.45, 0.3, 0.17, 1), plank_scale=(8.0, 1.2, 1.0),
                           roughness=0.35),
    "floor_kitchen": tile_mat("FloorKitchen", (0.72, 0.66, 0.55, 1.0),
                              tile_size=0.4, roughness=0.3),
    # furniture
    "sofa": flat_mat("Sofa", (0.62, 0.58, 0.52, 1.0), roughness=0.95),
    "cushion": flat_mat("Cushion", (0.8, 0.76, 0.7, 1.0), roughness=0.95),
    "wood": wood_mat("FurnitureWood", light=(0.5, 0.34, 0.2, 1),
                     dark=(0.35, 0.22, 0.11, 1), plank_scale=(2, 2, 1)),
    "counter": flat_mat("Counter", (0.9, 0.9, 0.92, 1.0), roughness=0.25),
    "countertop": flat_mat("CounterTop", (0.2, 0.2, 0.22, 1.0), roughness=0.2),
    "bed": flat_mat("BedFrame", (0.5, 0.36, 0.24, 1.0), roughness=0.6),
    "mattress": flat_mat("Mattress", (0.93, 0.92, 0.9, 1.0), roughness=0.9),
    "duvet": flat_mat("Duvet", (0.85, 0.87, 0.9, 1.0), roughness=0.95),
    "wardrobe": wood_mat("Wardrobe", light=(0.48, 0.36, 0.24, 1),
                         dark=(0.34, 0.24, 0.14, 1), plank_scale=(1, 1, 4)),
    "ceramic": flat_mat("Ceramic", (0.96, 0.97, 0.98, 1.0), roughness=0.08),
}

FLOOR_BY_ROOM = {
    "bathroom": "floor_wet",
    "toilet": "floor_wet",
    "hallway": "floor_hall",
    "corridor": "floor_hall",
    "kitchen": "floor_kitchen",
    "staircase": "floor_hall",
}

# ── Geometry helpers ─────────────────────────────────────────────────────────


def add_box(name, x0, y0, x1, y1, z0, z1, mat, bevel=0.015):
    bpy.ops.mesh.primitive_cube_add(
        size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    o = bpy.context.active_object
    o.name = name
    # size=1 cube has EDGE 1, so scale IS the edge length — dividing by 2
    # rendered every procedural box at half size, floating around its
    # center (feedback #022: countertops hovered above shrunken bodies)
    o.scale = (x1 - x0, y1 - y0, z1 - z0)
    o.data.materials.append(mat)
    if bevel:
        mod = o.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
    return o


def add_polygon(name, verts2d, z, mat):
    mesh = bpy.data.meshes.new(name)
    verts = [(x, y, z) for x, y in verts2d]
    mesh.from_pydata(verts, [], [list(range(len(verts)))])
    mesh.update()
    o = bpy.data.objects.new(name, mesh)
    o.data.materials.append(mat)
    scene.collection.objects.link(o)
    return o


# ── Building shell from OBJ ──────────────────────────────────────────────────

# ── Finish map: building.json element names -> finish tags ──────────────────
# OBJ object names are "Ifc<Type>_<name with spaces underscored>" (ifc_to_obj).
_bjson = json.loads((HERE / "building.json").read_text())
FINISHES = {}
for _story in _bjson["stories"]:
    for _kind, _prefix in (("walls", "IfcWallStandardCase"),
                           ("slabs", "IfcSlab"), ("roofs", "IfcSlab")):
        for _el in _story.get(_kind, []):
            _fin = _el.get("finish")
            if _fin is None:
                continue
            if not _fin:
                raise RuntimeError(
                    f"Empty finish tag on '{_el.get('name')}' — use null/omit "
                    f"for default, or a tag from FINISH_TO_MAT")
            if _fin not in FINISH_TO_MAT:
                raise RuntimeError(
                    f"Unknown finish tag '{_fin}' on '{_el.get('name')}' — "
                    f"add it to FINISH_TO_MAT (facade-finishes.md)")
            _key = f"{_prefix}_{(_el.get('name') or '').replace(' ', '_')}"
            if FINISHES.get(_key, _fin) != _fin:
                raise RuntimeError(
                    f"Ambiguous finish for '{_key}': duplicate element names "
                    f"with different finish tags")
            FINISHES[_key] = _fin


_finish_hits: dict[str, int] = {}


def finish_material(obj_name):
    """Material for a finish-tagged element, or None. Exact name match —
    Blender only suffixes ('.001') on name collisions, which for unique OBJ
    objects means something is wrong, so we count hits and fail below."""
    fin = FINISHES.get(obj_name)
    if fin is None:
        return None
    _finish_hits[obj_name] = _finish_hits.get(obj_name, 0) + 1
    return MATS[FINISH_TO_MAT[fin]]


bpy.ops.wm.obj_import(filepath=str(OBJ), forward_axis="Y", up_axis="Z")

for obj in list(scene.objects):
    if obj.type != "MESH":
        continue
    n = obj.name
    _fmat = finish_material(n)
    if _fmat is not None:
        obj.data.materials.append(_fmat)
        if (n.startswith("IfcWallStandardCase_")
                and FINISHES.get(n) != "glass"
                and "Deck_Screen" not in n):
            # Finishes are EXTERIOR paint: interior faces stay plaster.
            # Exterior = face normal points away from the plan centroid.
            # (glass walls and the freestanding deck screens carry their
            # finish on BOTH faces — no split.)
            obj.data.materials.append(MATS["wall"])
            for _poly in obj.data.polygons:
                _c = _poly.center
                if (_poly.normal.x * (_c.x - 4.75)
                        + _poly.normal.y * (_c.y - 6.0)) <= 0.01:
                    _poly.material_index = 1
            if FINISHES.get(n) == "accent":
                # Feedback #029: the yellow stops at the band-window head
                # (sill 2.05 + 0.75) — the strip between glass top and the
                # roof is WHITE. Bisect so the color line is exact.
                import bmesh
                _bm = bmesh.new()
                _bm.from_mesh(obj.data)
                bmesh.ops.bisect_plane(
                    _bm, geom=_bm.verts[:] + _bm.edges[:] + _bm.faces[:],
                    plane_co=(0, 0, 2.80), plane_no=(0, 0, 1))
                _bm.to_mesh(obj.data)
                _bm.free()
                for _poly in obj.data.polygons:
                    if _poly.material_index == 0 and _poly.center.z > 2.80:
                        _poly.material_index = 1
            if n == "IfcWallStandardCase_West_Wall":
                # Feedback #030: W7's yellow ends at Win3's north edge
                # (y = 8 − 3.35 = 4.65) — the slivers beside/below the
                # full-height glass read as "yellow lines" next to the
                # white W16 and must be white.
                import bmesh
                _bm = bmesh.new()
                _bm.from_mesh(obj.data)
                bmesh.ops.bisect_plane(
                    _bm, geom=_bm.verts[:] + _bm.edges[:] + _bm.faces[:],
                    plane_co=(0, 4.65, 0), plane_no=(0, 1, 0))
                _bm.to_mesh(obj.data)
                _bm.free()
                for _poly in obj.data.polygons:
                    if _poly.material_index == 0 and _poly.center.y < 4.65:
                        _poly.material_index = 1
    elif "Pool" in n:
        obj.data.materials.append(MATS["pool"])
    elif "Deck" in n:
        obj.data.materials.append(MATS["deck"])
    elif "Lawn" in n:
        obj.data.materials.append(MATS["lawn"])
    elif "Slab" in n:
        obj.data.materials.append(MATS["slab"])
    elif "Stair" in n:
        # Spiral stair: hide the IFC prism, build pole + helical steps below
        obj.hide_render = True
    elif "Window" in n:
        obj.data.materials.append(MATS["glass"])
        # Frame: duplicated box turned into bars via wireframe modifier
        frame = obj.copy()
        frame.data = obj.data.copy()
        frame.data.materials.clear()
        frame.data.materials.append(MATS["frame"])
        frame.name = obj.name + "_frame"
        dec = frame.modifiers.new("Planar", "DECIMATE")
        dec.decimate_type = "DISSOLVE"  # merge triangles into quads first
        dec.angle_limit = math.radians(5)
        mod = frame.modifiers.new("Frame", "WIREFRAME")
        mod.thickness = 0.05
        scene.collection.objects.link(frame)
    elif "Handle" in n:
        obj.data.materials.append(MATS["frame"])
    elif "Door" in n:
        # Owner 2026-08-05: terrace pair (D8/D9) and Bath 1 door (D3) are glass
        if any(g in n for g in GLASS_DOORS):
            obj.data.materials.append(MATS["glass"])
            frame = obj.copy()
            frame.data = obj.data.copy()
            frame.data.materials.clear()
            frame.data.materials.append(MATS["frame"])
            frame.name = obj.name + "_frame"
            dec = frame.modifiers.new("Planar", "DECIMATE")
            dec.decimate_type = "DISSOLVE"  # drop box-face diagonals first
            dec.angle_limit = math.radians(5)
            mod = frame.modifiers.new("Frame", "WIREFRAME")
            mod.thickness = 0.04
            scene.collection.objects.link(frame)
        else:
            obj.data.materials.append(MATS["door"])
    else:
        obj.data.materials.append(MATS["wall"])

# Every finish-tagged element must have matched exactly one imported object —
# stale OBJ output or naming drift must not silently render as plaster.
_finish_misses = {k: _finish_hits.get(k, 0) for k in FINISHES
                  if _finish_hits.get(k, 0) != 1}
if _finish_misses:
    raise RuntimeError(f"Finish join mismatches (name: hit count): {_finish_misses}")

# Door handles come from the IFC exporter as IfcDiscreteAccessory products
# ("<door name> Handle N") — framework feature, every project gets them.
# They import as separate OBJ objects and take the metal material below.

# ── Spiral staircase (pole + helical wedge steps descending to garage) ──────

def make_spiral_stair(cx, cy, radius=0.72, z_top=SLAB_TOP, drop=2.89, steps=14):
    # drop reaches the garage FFL (the caller derives it from the storey
    # elevations); 14 steps → ~0.2m risers
    # Cut a real stairwell opening through the ground slab so the spiral
    # is visible from above (a down-stair IS a hole in the floor).
    bpy.ops.mesh.primitive_cylinder_add(radius=radius + 0.03, depth=1.0,
                                        location=(cx, cy, z_top - 0.3))
    cutter = bpy.context.active_object
    cutter.name = "StairwellCutter"
    cutter.hide_render = True
    for obj in scene.objects:
        if obj.type == "MESH" and "Slab" in obj.name and "Ground" in obj.name:
            mod = obj.modifiers.new("Stairwell", "BOOLEAN")
            mod.operation = "DIFFERENCE"
            mod.object = cutter
    bpy.ops.mesh.primitive_cylinder_add(radius=0.06, depth=drop + 1.2,
                                        location=(cx, cy, z_top - drop / 2 + 0.3))
    pole = bpy.context.active_object
    pole.name = "SpiralPole"
    pole.data.materials.append(MATS["frame"])
    for i in range(steps):
        ang = math.radians(i * (360 / steps) * 1.25)
        z = z_top - 0.02 - i * (drop / steps)
        bpy.ops.mesh.primitive_cube_add(
            size=1, location=(cx + (radius / 2 + 0.05) * math.cos(ang),
                              cy + (radius / 2 + 0.05) * math.sin(ang), z))
        step = bpy.context.active_object
        step.name = f"SpiralStep{i}"
        step.scale = (radius / 2 - 0.05, 0.13, 0.02)
        step.rotation_euler = (0, 0, ang)
        step.data.materials.append(MATS["stair"])


building = json.loads(BUILDING.read_text())
# drop = ground FFL (z_top = 0) down to the lowest storey's FFL
_lowest_ffl = min(s.get("elevation", 0) for s in building["stories"])
_spiral_seen = set()  # both storeys carry the aligned staircase (E051) —
for story_ in building["stories"]:  # build the physical spiral only once
    for st in story_.get("staircases", []):
        if st.get("stair_type") == "SPIRAL_STAIR":
            vs = [(v["x"], v["y"]) for v in st["outline"]["vertices"]]
            cx = sum(x for x, _ in vs) / len(vs)
            cy = sum(y for _, y in vs) / len(vs)
            if (round(cx, 3), round(cy, 3)) in _spiral_seen:
                continue
            _spiral_seen.add((round(cx, 3), round(cy, 3)))
            r = min(max(x for x, _ in vs) - min(x for x, _ in vs),
                    max(y for _, y in vs) - min(y for _, y in vs)) / 2
            make_spiral_stair(cx, cy, radius=r, drop=-_lowest_ffl)

# ── Colored floors per space ─────────────────────────────────────────────────

building = json.loads(BUILDING.read_text())
for story in building["stories"]:
    for apt in story.get("apartments", []):
        for sp in apt.get("spaces", []):
            if sp["room_type"] == "staircase":
                continue  # stairwell is an opening, not a floor
            key = FLOOR_BY_ROOM.get(sp["room_type"], "floor_room")
            verts = [(v["x"], v["y"]) for v in sp["boundary"]["vertices"]]
            # each storey's finish sits on ITS floor, not the ground slab's
            add_polygon(f"Floor_{sp['name']}", verts,
                        story["elevation"] + 0.01, MATS[key])

# ── Procedural furniture ─────────────────────────────────────────────────────


def make_bed(name, x0, y0, x1, y1, z0):
    """Frame + mattress + duvet + two pillows. Headboard on the short
    side closest to a wall is approximated as the y1 side."""
    add_box(f"{name}_frame", x0, y0, x1, y1, z0, z0 + 0.3, MATS["bed"])
    add_box(f"{name}_mattress", x0 + 0.05, y0 + 0.05, x1 - 0.05, y1 - 0.05,
            z0 + 0.3, z0 + 0.45, MATS["mattress"], bevel=0.04)
    # duvet covers the lower 2/3
    dy = (y1 - y0)
    add_box(f"{name}_duvet", x0 + 0.03, y0 + 0.03, x1 - 0.03, y1 - dy * 0.35,
            z0 + 0.42, z0 + 0.52, MATS["duvet"], bevel=0.05)
    # pillows at the head end
    w = (x1 - x0 - 0.2) / 2
    for i in range(2):
        px0 = x0 + 0.07 + i * (w + 0.06)
        add_box(f"{name}_pillow{i}", px0, y1 - dy * 0.28, px0 + w, y1 - 0.08,
                z0 + 0.45, z0 + 0.58, MATS["cushion"], bevel=0.05)


def make_sofa(name, x0, y0, x1, y1, z0, h, facing="S"):
    """Seat + back + cushions; back sits opposite the facing direction."""
    horizontal = (x1 - x0) >= (y1 - y0)
    add_box(f"{name}_seat", x0, y0, x1, y1, z0, z0 + h * 0.55, MATS["sofa"],
            bevel=0.04)
    if horizontal:
        if facing == "N":  # looking north -> back on the south edge
            back = (x0, y0, x1, y0 + 0.22)
            cush_y = (y0 + 0.24, y1 - 0.05)
        else:              # default: back on the north edge, faces south
            back = (x0, y1 - 0.22, x1, y1)
            cush_y = (y0 + 0.05, y1 - 0.24)
        add_box(f"{name}_back", back[0], back[1], back[2], back[3],
                z0, z0 + h * 1.7, MATS["sofa"], bevel=0.04)
        n = max(1, int((x1 - x0) / 0.65))
        cw = (x1 - x0 - 0.1) / n
        for i in range(n):
            cx0 = x0 + 0.05 + i * cw
            add_box(f"{name}_cushion{i}", cx0 + 0.03, cush_y[0], cx0 + cw - 0.03,
                    cush_y[1], z0 + h * 0.55, z0 + h * 0.85, MATS["cushion"],
                    bevel=0.05)
    else:
        add_box(f"{name}_back", x1 - 0.22, y0, x1, y1, z0, z0 + h * 1.7,
                MATS["sofa"], bevel=0.04)
        n = max(1, int((y1 - y0) / 0.65))
        cw = (y1 - y0 - 0.1) / n
        for i in range(n):
            cy0 = y0 + 0.05 + i * cw
            add_box(f"{name}_cushion{i}", x0 + 0.05, cy0 + 0.03, x1 - 0.24,
                    cy0 + cw - 0.03, z0 + h * 0.55, z0 + h * 0.85,
                    MATS["cushion"], bevel=0.05)


def make_table(name, x0, y0, x1, y1, z0, h):
    """Top slab + four legs."""
    add_box(f"{name}_top", x0, y0, x1, y1, z0 + h - 0.05, z0 + h, MATS["wood"])
    leg = 0.07
    for lx, ly in ((x0 + 0.05, y0 + 0.05), (x1 - 0.05 - leg, y0 + 0.05),
                   (x0 + 0.05, y1 - 0.05 - leg), (x1 - 0.05 - leg, y1 - 0.05 - leg)):
        add_box(f"{name}_leg", lx, ly, lx + leg, ly + leg, z0, z0 + h - 0.05,
                MATS["wood"], bevel=0.01)


def make_sun_lounger(name, x0, y0, x1, y1, z0, facing="N"):
    """Pool chaise (feedback #031): slatted teak bed on low runners with
    an angled backrest at the end AWAY from `facing` (feet point that
    way). Long axis follows the footprint's long side."""
    import math as _m
    bed_h = 0.30
    long_y = (y1 - y0) >= (x1 - x0)
    # runners
    if long_y:
        for rx in (x0 + 0.03, x1 - 0.09):
            add_box(f"{name}_runner", rx, y0 + 0.05, rx + 0.06, y1 - 0.05,
                    z0, z0 + bed_h - 0.05, MATS["wood"], bevel=0.01)
    else:
        for ry in (y0 + 0.03, y1 - 0.09):
            add_box(f"{name}_runner", x0 + 0.05, ry, x1 - 0.05, ry + 0.06,
                    z0, z0 + bed_h - 0.05, MATS["wood"], bevel=0.01)
    # slatted bed: flat part covers ~60% (feet side), backrest the rest
    length = (y1 - y0) if long_y else (x1 - x0)
    flat = length * 0.6
    n_slats = 7
    step = flat / n_slats
    for i in range(n_slats):
        off = i * step
        if long_y:
            fy = y1 - off if facing == "N" else y0 + off
            s0, s1 = sorted((fy, fy - step * 0.8 if facing == "N"
                             else fy + step * 0.8))
            add_box(f"{name}_slat", x0 + 0.02, s0, x1 - 0.02, s1,
                    z0 + bed_h - 0.05, z0 + bed_h, MATS["wood"], bevel=0.005)
        else:
            fx = x1 - off if facing == "E" else x0 + off
            s0, s1 = sorted((fx, fx - step * 0.8 if facing == "E"
                             else fx + step * 0.8))
            add_box(f"{name}_slat", s0, y0 + 0.02, s1, y1 - 0.02,
                    z0 + bed_h - 0.05, z0 + bed_h, MATS["wood"], bevel=0.005)
    # backrest: single angled board rising ~50deg over the remaining 40%
    back = length - flat
    rise = back * _m.tan(_m.radians(50)) * 0.6
    if long_y:
        by0, by1 = ((y0, y0 + back) if facing == "N" else (y1 - back, y1))
        board = add_box(f"{name}_back", x0 + 0.02, by0, x1 - 0.02, by1,
                        z0 + bed_h - 0.05, z0 + bed_h, MATS["wood"],
                        bevel=0.005)
        board.rotation_euler[0] = _m.radians(-50 if facing == "N" else 50)
        board.location.z += rise / 2
        board.location.y += (back * 0.18) * (1 if facing == "N" else -1)
    else:
        bx0, bx1 = ((x0, x0 + back) if facing == "E" else (x1 - back, x1))
        board = add_box(f"{name}_back", bx0, y0 + 0.02, bx1, y1 - 0.02,
                        z0 + bed_h - 0.05, z0 + bed_h, MATS["wood"],
                        bevel=0.005)
        board.rotation_euler[1] = _m.radians(50 if facing == "E" else -50)
        board.location.z += rise / 2
        board.location.x += (back * 0.18) * (1 if facing == "E" else -1)


def make_counter(name, x0, y0, x1, y1, z0, h):
    add_box(f"{name}_body", x0, y0, x1, y1, z0, z0 + h - 0.04, MATS["counter"])
    add_box(f"{name}_top", x0 - 0.02, y0 - 0.02, x1 + 0.02, y1 + 0.02,
            z0 + h - 0.04, z0 + h, MATS["countertop"], bevel=0.01)


# ── CC0 asset furniture (Poly Haven, see fetch_assets.py) ───────────────────

ASSETS_DIR = HERE / "assets"

# Poly Haven models sit on the origin facing -Y (their documented standard),
# so "faces south" is the identity and the rest is a Z spin.
FACING_TO_ROT = {"S": 0.0, "E": 90.0, "N": 180.0, "W": 270.0}

# Objaverse (Sketchfab) models have NO orientation standard — this records
# which world direction each pinned model natively faces (verified visually).
ASSET_NATIVE_FACING = {
    "sectional_sofa": "S",
    "deck_sofa": "S",
    "dining_chair": "S",
    "dining_table": "S",
    # nightstand world positions proved the bed faces EAST natively (head
    # west) — the "head north" assumption survived two visual checks because
    # head-west happened to look plausible in both rooms
    "platform_bed": "E",
    "office_desk": "S",  # hypothesis from audition thumbnail — verify in probe
}

_asset_protos = {}  # asset id -> list of objects (imported prototype hierarchy)


def _import_asset(asset_id):
    candidates = sorted((ASSETS_DIR / asset_id).glob("*.gltf")) + \
        sorted((ASSETS_DIR / asset_id).glob("*.glb"))
    if not candidates:
        raise FileNotFoundError(
            f"asset '{asset_id}' not downloaded — run fetch_assets.py first")
    if len(candidates) > 1:
        raise RuntimeError(
            f"asset '{asset_id}' has {len(candidates)} model files — stale pin? "
            f"re-run fetch_assets.py: {[c.name for c in candidates]}")
    gltf_path = candidates[0]
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(gltf_path))
    return [o for o in bpy.data.objects if o not in before]


def _copy_hierarchy(objs):
    """Linked-duplicate a hierarchy: new objects, shared mesh data/materials."""
    mapping = {}
    for o in objs:
        c = o.copy()
        scene.collection.objects.link(c)
        mapping[o] = c
    for o, c in mapping.items():
        if o.parent in mapping:
            c.parent = mapping[o.parent]
            c.matrix_parent_inverse = o.matrix_parent_inverse.copy()
    return list(mapping.values())


def _world_bbox(objs):
    """World-space AABB over every EVALUATED mesh in the hierarchy.

    Evaluated objects, not base data — a modifier/GN/armature on an asset
    would otherwise be measured pre-deformation (origins lie either way).
    """
    from mathutils import Vector
    dg = bpy.context.evaluated_depsgraph_get()
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in objs:
        if o.type != "MESH":
            continue
        oe = o.evaluated_get(dg)
        for corner in oe.bound_box:
            w = oe.matrix_world @ Vector(corner)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
    return lo, hi


def place_asset(name, asset_id, x0, y0, x1, y1, z0, facing, target_h=None):
    """Instance a Poly Haven asset fitted into the item's footprint.

    Order matters: facing rotation FIRST, then measure, then uniform
    containment scale (min ratio — never stretch), center XY, ground by
    mesh min-z (plan-review decisions, 2026-08-05).

    target_h (feedback #027/#028): scale by HEIGHT instead — footprint
    scaling ignores the vertical axis, which produced knee-high stoves
    next to 0.9m counters and doll-sized patio sets. Height is the
    architecturally meaningful number; the bounds box then only places
    and centers. Loud warning if the footprint overflows the box >20%.
    """
    if asset_id in _asset_protos:
        objs = _copy_hierarchy(_asset_protos[asset_id])
    else:
        objs = _import_asset(asset_id)
        _asset_protos[asset_id] = objs  # prototype doubles as first instance
    root = bpy.data.objects.new(f"{name}_root", None)
    scene.collection.objects.link(root)
    for o in objs:
        if o.parent is None or o.parent not in objs:
            o.parent = root
    native = ASSET_NATIVE_FACING.get(asset_id, "S")
    root.rotation_euler[2] = math.radians(
        (FACING_TO_ROT[facing] - FACING_TO_ROT[native]) % 360)
    bpy.context.view_layer.update()
    lo, hi = _world_bbox(objs)
    w, d = hi.x - lo.x, hi.y - lo.y
    if w <= 0 or d <= 0:
        raise RuntimeError(
            f"asset '{asset_id}' has a degenerate XY bounding box "
            f"({w:.3f}x{d:.3f}) — no mesh data, or a flat model")
    if target_h is not None:
        native_h = hi.z - lo.z
        if native_h <= 0:
            raise RuntimeError(f"asset '{asset_id}' has zero height")
        s = target_h / native_h
        if max(w * s / (x1 - x0), d * s / (y1 - y0)) > 1.2:
            print(f"WARNING: {name} footprint overflows its box "
                  f"{w * s:.2f}x{d * s:.2f} vs {x1 - x0:.2f}x{y1 - y0:.2f}")
    else:
        s = min((x1 - x0) / w, (y1 - y0) / d)
    root.scale = (s, s, s)
    bpy.context.view_layer.update()
    lo, hi = _world_bbox(objs)
    root.location.x += (x0 + x1) / 2 - (lo.x + hi.x) / 2
    root.location.y += (y0 + y1) / 2 - (lo.y + hi.y) / 2
    root.location.z += z0 - lo.z
    print(f"asset {name}: {asset_id} native {w:.2f}x{d:.2f} scale {s:.2f}")


# Everything created so far is ours; export_glb.py flattens ONLY tagged
# materials, leaving imported PBR assets untouched.
for _m in bpy.data.materials:
    _m["ab_procedural"] = True

furniture = json.loads(FURNITURE.read_text())
for item in furniture["items"]:
    x0, y0, x1, y1 = item["bounds"]
    h = item["h"]
    z0 = item.get("z", SLAB_TOP)
    t = item["type"]
    name = f"F_{item['name']}"
    if item.get("asset"):
        place_asset(name, item["asset"], x0, y0, x1, y1, z0,
                    item.get("facing", "S"),
                    target_h=h if item.get("scale_by") == "height" else None)
    elif t == "bed":
        make_bed(name, x0, y0, x1, y1, z0)
    elif t == "sofa":
        make_sofa(name, x0, y0, x1, y1, z0, h, facing=item.get("facing", "S"))
    elif t == "wood" and h >= 0.7:  # tables get legs
        make_table(name, x0, y0, x1, y1, z0, h)
    elif t == "counter":
        make_counter(name, x0, y0, x1, y1, z0, h)
    elif t == "sunbed":
        make_sun_lounger(name, x0, y0, x1, y1, z0, item.get("facing", "N"))
    else:
        add_box(name, x0, y0, x1, y1, z0, z0 + h, MATS[t], bevel=0.03)

# ── Sky, sun, ground ─────────────────────────────────────────────────────────

world = bpy.data.worlds.new("World")
world.use_nodes = True
nt = world.node_tree
bg = nt.nodes["Background"]
sky = nt.nodes.new("ShaderNodeTexSky")
# Blender 5.x renamed sky models (NISHITA -> MULTIPLE_SCATTERING)
sky.sky_type = ("MULTIPLE_SCATTERING"
                if "MULTIPLE_SCATTERING" in
                sky.bl_rna.properties["sky_type"].enum_items
                else "HOSEK_WILKIE")
_sun_cfg = RENDER.get("sun", {})
for attr, val in (
        ("sun_elevation",
         math.radians(_sun_cfg.get("sky_elevation_deg", 45))),
        ("sun_rotation",
         math.radians(_sun_cfg.get("sky_rotation_deg", 135))),
        ("sun_intensity", _sun_cfg.get("sky_intensity", 0.5))):
    if hasattr(sky, attr):
        setattr(sky, attr, val)
nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
bg.inputs["Strength"].default_value = 0.45
scene.world = world

# Explicit sun for contrast and warm direct light (sky alone is too flat)
sun_data = bpy.data.lights.new("Sun", type="SUN")
sun_data.energy = _sun_cfg.get("energy", 2.2)
sun_data.angle = math.radians(_sun_cfg.get("angle_deg", 8.6))
sun_data.color = (1.0, 1.0, 1.0)
sun = bpy.data.objects.new("Sun", sun_data)
sun.rotation_euler = tuple(
    math.radians(a) for a in _sun_cfg.get("rotation_deg", (50, -10, 105)))
scene.collection.objects.link(sun)

# Sloped site (maquette photo): high ground in the north keeps deck+pool at
# GF level; low ground south/west exposes the garage's stone band. Solid
# boxes so the terrace step face is closed. Render-only site geometry.
for _i, _g in enumerate(RENDER.get("ground", [])):
    bpy.ops.mesh.primitive_cube_add(size=1, location=tuple(_g["location"]))
    _gobj = bpy.context.active_object
    _gobj.scale = tuple(_g["size"])
    _gobj.data.materials.append(MATS["ground"])
    _gobj.name = _g.get("name") or f"Ground{_i}"

# Cylindrical shells (render decor): a spiral-stair tower straddling a
# facade gets a hollow tube minus its in-house half, so the steps inside
# stay intact (spiral-stair-rendering.md). The mechanism is generic; the
# villa's tower values live in project.toml [[render.shell]].
for _si, _sh in enumerate(RENDER.get("shell", [])):
    _cx, _cy = _sh["center"]
    _z0, _z1 = _sh["z_range"]
    _depth = _z1 - _z0
    _zc = (_z0 + _z1) / 2
    bpy.ops.mesh.primitive_cylinder_add(
        radius=_sh["radius"], depth=_depth, vertices=48,
        location=(_cx, _cy, _zc))
    _tower = bpy.context.active_object
    _tower.name = _sh.get("name") or f"Shell{_si}"
    _tower.data.materials.append(MATS["wall"])
    bpy.ops.mesh.primitive_cylinder_add(
        radius=_sh["inner_radius"], depth=_depth + 0.25, vertices=48,
        location=(_cx, _cy, _zc))
    _tower_inner = bpy.context.active_object
    _tower_inner.name = f"{_tower.name}CutterInner"
    _tower_inner.hide_render = True
    _cuts = [_tower_inner]
    if "cut_y_above" in _sh:
        # cutter sized from the shell itself — hardcoded villa dimensions
        # would silently truncate a bigger tower (CodeRabbit 2026-08-09)
        _cd = 2 * _sh["radius"] + 0.5
        bpy.ops.mesh.primitive_cube_add(
            size=1,
            location=(_cx, _sh["cut_y_above"] + _cd / 2, _zc))
        _tower_back = bpy.context.active_object
        _tower_back.scale = (_cd, _cd, _depth + 0.5)
        _tower_back.name = f"{_tower.name}CutterBack"
        _tower_back.hide_render = True
        _cuts.append(_tower_back)
    for _cut in _cuts:
        _m = _tower.modifiers.new("Cut", "BOOLEAN")
        _m.operation = "DIFFERENCE"
        _m.object = _cut

# Facade decor (render-only, matching the maquette's glued-on parts —
# facade.md): white soffit boards under the brown roof (one Roof element
# stays the model truth; the soffit is a painted finish, not structure).
# Soffit boards removed (owner 2026-08-06: "SoffitWest should not exist").

# ── Cameras ──────────────────────────────────────────────────────────────────

_persp_cfg = CAM.get("perspective", {})
_top_cfg = CAM.get("top", {})
target = bpy.data.objects.new("Target", None)
target.location = tuple(_persp_cfg.get("target", (4.75, 8.5, 0.6)))
scene.collection.objects.link(target)

persp_data = bpy.data.cameras.new("CamPersp")
persp_data.lens = _persp_cfg.get("lens", 38)
persp_data.dof.use_dof = True
persp_data.dof.focus_object = target
persp_data.dof.aperture_fstop = _persp_cfg.get("dof_fstop", 5.6)
cam_persp = bpy.data.objects.new("CamPersp", persp_data)
cam_persp.location = tuple(_persp_cfg.get("location", (14.0, 21.0, 8.5)))
scene.collection.objects.link(cam_persp)
tc = cam_persp.constraints.new(type="TRACK_TO")
tc.target = target
tc.track_axis = "TRACK_NEGATIVE_Z"
tc.up_axis = "UP_Y"

top_data = bpy.data.cameras.new("CamTop")
top_data.type = "ORTHO"
top_data.ortho_scale = _top_cfg.get("ortho_scale", 19.5)
cam_top = bpy.data.objects.new("CamTop", top_data)
cam_top.location = tuple(_top_cfg.get("location", (4.75, 8.75, 30)))
cam_top.rotation_euler = (0, 0, 0)
scene.collection.objects.link(cam_top)

# ── Render ───────────────────────────────────────────────────────────────────

scene.render.engine = "CYCLES"
scene.cycles.samples = RENDER.get("samples", 128)
scene.cycles.use_denoising = True
scene.render.film_transparent = False

# AgX (default) washes everything into pastel — pick a saturating transform
for vt in ("Khronos PBR Neutral", "Filmic", "Standard"):
    try:
        scene.view_settings.view_transform = vt
        break
    except TypeError:
        continue
scene.view_settings.exposure = RENDER.get("exposure", -0.6)
print("View transform:", scene.view_settings.view_transform)

# The walkthrough GLB is the product (owner 2026-08-06) — the two Cycles
# renders (~4 min) are OPT-IN via AB_FULL_RENDER=1. Default: save the
# .blend (feeds export_glb.py) and stop.
if not os.environ.get("AB_FULL_RENDER"):
    scene.view_settings.exposure = RENDER.get("exposure", -0.6)
    bpy.ops.wm.save_as_mainfile(
        filepath=str(HERE / "output" / f"{MODEL}.blend"))
    print(f"saved {MODEL}.blend; Cycles renders skipped "
          "(set AB_FULL_RENDER=1 for PNGs)")
    raise SystemExit(0)

scene.camera = cam_persp
scene.view_settings.exposure = _persp_cfg.get("exposure", -0.85)
scene.render.resolution_x = _persp_cfg.get("resolution", (1600, 1200))[0]
scene.render.resolution_y = _persp_cfg.get("resolution", (1600, 1200))[1]
scene.render.filepath = str(OUT_PERSP)
bpy.ops.render.render(write_still=True)
print(f"Rendered {OUT_PERSP}")

scene.view_settings.exposure = RENDER.get("exposure", -0.6)
# Save the full scene for interactive viewing (open in Blender, orbit away)
bpy.ops.wm.save_as_mainfile(
    filepath=str(HERE / "output" / f"{MODEL}.blend"))

# Top-down looks INTO the rooms — lift the maquette's lid: hide roof + soffit
for _o in scene.objects:
    if _o.type == "MESH" and ("Roof" in _o.name or "Soffit" in _o.name):
        _o.hide_render = True

scene.camera = cam_top
scene.view_settings.exposure = _top_cfg.get(
    "exposure", RENDER.get("exposure", -0.6))
scene.render.resolution_x = _top_cfg.get("resolution", (1100, 2000))[0]
scene.render.resolution_y = _top_cfg.get("resolution", (1100, 2000))[1]
scene.render.filepath = str(OUT_TOP)
bpy.ops.render.render(write_still=True)
print(f"Rendered {OUT_TOP}")
