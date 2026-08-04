"""Blender headless: high-quality maquette-style renders of the villa.

v2 ("make it great"): procedural materials (wood planks, tiles with grout,
water, grass, plaster), Nishita sky lighting, window frames via wireframe
modifier, procedural furniture (beds/sofas built from parts, everything
beveled), DoF on the perspective camera.

Outputs:
  output/perspective.png — 3D perspective from SE
  output/top_down.png    — orthographic top view (maquette look)

Run: /Applications/Blender.app/Contents/MacOS/Blender -b -P render_blender.py
"""

import json
import math
from pathlib import Path

import bpy

HERE = Path(__file__).parent
OBJ = HERE / "output" / "villa-maketa.obj"
BUILDING = HERE / "building.json"
FURNITURE = HERE / "furniture.json"
OUT_PERSP = HERE / "output" / "perspective.png"
OUT_TOP = HERE / "output" / "top_down.png"

SLAB_TOP = 0.25   # ground slab top (z)
DECK_TOP = 0.15

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
    m, _, bsdf = _new_mat(name)
    bsdf.inputs["Base Color"].default_value = (0.8, 0.9, 0.95, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.03
    for key in ("Transmission Weight", "Transmission"):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = 0.95
            break
    return m


MATS = {
    "wall": plaster_mat("Plaster", (0.8, 0.78, 0.74, 1.0)),
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
    o.scale = ((x1 - x0) / 2, (y1 - y0) / 2, (z1 - z0) / 2)
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

bpy.ops.wm.obj_import(filepath=str(OBJ), forward_axis="Y", up_axis="Z")

for obj in list(scene.objects):
    if obj.type != "MESH":
        continue
    n = obj.name
    if "Pool" in n:
        obj.data.materials.append(MATS["pool"])
    elif "Deck" in n:
        obj.data.materials.append(MATS["deck"])
    elif "Lawn" in n:
        obj.data.materials.append(MATS["lawn"])
    elif "Slab" in n:
        obj.data.materials.append(MATS["slab"])
    elif "Stair" in n:
        obj.data.materials.append(MATS["stair"])
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
    elif "Door" in n:
        obj.data.materials.append(MATS["door"])
    else:
        obj.data.materials.append(MATS["wall"])

# ── Colored floors per space ─────────────────────────────────────────────────

building = json.loads(BUILDING.read_text())
for story in building["stories"]:
    for apt in story.get("apartments", []):
        for sp in apt.get("spaces", []):
            key = FLOOR_BY_ROOM.get(sp["room_type"], "floor_room")
            verts = [(v["x"], v["y"]) for v in sp["boundary"]["vertices"]]
            add_polygon(f"Floor_{sp['name']}", verts, SLAB_TOP + 0.01, MATS[key])

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


def make_sofa(name, x0, y0, x1, y1, z0, h):
    """Seat + back along the longer edge + cushions."""
    horizontal = (x1 - x0) >= (y1 - y0)
    add_box(f"{name}_seat", x0, y0, x1, y1, z0, z0 + h * 0.55, MATS["sofa"],
            bevel=0.04)
    if horizontal:
        add_box(f"{name}_back", x0, y1 - 0.22, x1, y1, z0, z0 + h * 1.7,
                MATS["sofa"], bevel=0.04)
        n = max(1, int((x1 - x0) / 0.65))
        cw = (x1 - x0 - 0.1) / n
        for i in range(n):
            cx0 = x0 + 0.05 + i * cw
            add_box(f"{name}_cushion{i}", cx0 + 0.03, y0 + 0.05, cx0 + cw - 0.03,
                    y1 - 0.24, z0 + h * 0.55, z0 + h * 0.85, MATS["cushion"],
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


def make_counter(name, x0, y0, x1, y1, z0, h):
    add_box(f"{name}_body", x0, y0, x1, y1, z0, z0 + h - 0.04, MATS["counter"])
    add_box(f"{name}_top", x0 - 0.02, y0 - 0.02, x1 + 0.02, y1 + 0.02,
            z0 + h - 0.04, z0 + h, MATS["countertop"], bevel=0.01)


furniture = json.loads(FURNITURE.read_text())
for item in furniture["items"]:
    x0, y0, x1, y1 = item["bounds"]
    h = item["h"]
    z0 = item.get("z", SLAB_TOP)
    t = item["type"]
    name = f"F_{item['name']}"
    if t == "bed":
        make_bed(name, x0, y0, x1, y1, z0)
    elif t == "sofa":
        make_sofa(name, x0, y0, x1, y1, z0, h)
    elif t == "wood" and h >= 0.7:  # tables get legs
        make_table(name, x0, y0, x1, y1, z0, h)
    elif t == "counter":
        make_counter(name, x0, y0, x1, y1, z0, h)
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
for attr, val in (("sun_elevation", math.radians(45)),
                  ("sun_rotation", math.radians(135)),
                  ("sun_intensity", 0.5)):
    if hasattr(sky, attr):
        setattr(sky, attr, val)
nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
bg.inputs["Strength"].default_value = 0.45
scene.world = world

# Explicit sun for contrast and warm direct light (sky alone is too flat)
sun_data = bpy.data.lights.new("Sun", type="SUN")
sun_data.energy = 2.2
sun_data.angle = 0.15
sun_data.color = (1.0, 1.0, 1.0)
sun = bpy.data.objects.new("Sun", sun_data)
sun.rotation_euler = (math.radians(50), math.radians(-10), math.radians(105))
scene.collection.objects.link(sun)

bpy.ops.mesh.primitive_plane_add(size=200, location=(4.75, 8, -0.29))
bpy.context.active_object.data.materials.append(MATS["ground"])

# ── Cameras ──────────────────────────────────────────────────────────────────

target = bpy.data.objects.new("Target", None)
target.location = (4.75, 8.5, 0.6)
scene.collection.objects.link(target)

persp_data = bpy.data.cameras.new("CamPersp")
persp_data.lens = 38
persp_data.dof.use_dof = True
persp_data.dof.focus_object = target
persp_data.dof.aperture_fstop = 5.6
cam_persp = bpy.data.objects.new("CamPersp", persp_data)
cam_persp.location = (14.0, 21.0, 8.5)
scene.collection.objects.link(cam_persp)
tc = cam_persp.constraints.new(type="TRACK_TO")
tc.target = target
tc.track_axis = "TRACK_NEGATIVE_Z"
tc.up_axis = "UP_Y"

top_data = bpy.data.cameras.new("CamTop")
top_data.type = "ORTHO"
top_data.ortho_scale = 19.5
cam_top = bpy.data.objects.new("CamTop", top_data)
cam_top.location = (4.75, 8.75, 30)
cam_top.rotation_euler = (0, 0, 0)
scene.collection.objects.link(cam_top)

# ── Render ───────────────────────────────────────────────────────────────────

scene.render.engine = "CYCLES"
scene.cycles.samples = 128
scene.cycles.use_denoising = True
scene.render.film_transparent = False

# AgX (default) washes everything into pastel — pick a saturating transform
for vt in ("Khronos PBR Neutral", "Filmic", "Standard"):
    try:
        scene.view_settings.view_transform = vt
        break
    except TypeError:
        continue
scene.view_settings.exposure = -0.6
print("View transform:", scene.view_settings.view_transform)

scene.camera = cam_persp
scene.view_settings.exposure = -0.85
scene.render.resolution_x = 1600
scene.render.resolution_y = 1200
scene.render.filepath = str(OUT_PERSP)
bpy.ops.render.render(write_still=True)
print(f"Rendered {OUT_PERSP}")

scene.view_settings.exposure = -0.6
scene.camera = cam_top
scene.render.resolution_x = 1100
scene.render.resolution_y = 2000
scene.render.filepath = str(OUT_TOP)
bpy.ops.render.render(write_still=True)
print(f"Rendered {OUT_TOP}")
