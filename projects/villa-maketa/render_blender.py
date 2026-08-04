"""Blender headless: maquette-style renders of the villa.

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

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ── Materials ────────────────────────────────────────────────────────────────

def make_mat(name, rgba, roughness=0.7):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = roughness
    return m


MATS = {
    "wall": make_mat("Wall", (0.93, 0.91, 0.87, 1.0)),
    "slab": make_mat("Slab", (0.82, 0.80, 0.76, 1.0)),
    "stair": make_mat("Stair", (0.62, 0.48, 0.36, 1.0)),
    "glass": make_mat("Glass", (0.6, 0.78, 0.9, 1.0), roughness=0.1),
    "door": make_mat("Door", (0.48, 0.34, 0.22, 1.0)),
    "deck": make_mat("DeckWood", (0.36, 0.22, 0.12, 1.0)),
    "pool": make_mat("PoolWater", (0.45, 0.75, 0.85, 1.0), roughness=0.05),
    "lawn": make_mat("Lawn", (0.25, 0.55, 0.15, 1.0)),
    "ground": make_mat("Ground", (0.55, 0.6, 0.55, 1.0)),
    # floors by room type
    "floor_wet": make_mat("FloorTiles", (0.42, 0.65, 0.78, 1.0), roughness=0.3),
    "floor_hall": make_mat("FloorHall", (0.72, 0.66, 0.52, 1.0), roughness=0.4),
    "floor_room": make_mat("FloorRoom", (0.93, 0.9, 0.84, 1.0)),
    "floor_kitchen": make_mat("FloorKitchen", (0.68, 0.62, 0.5, 1.0), roughness=0.3),
    # furniture
    "sofa": make_mat("Sofa", (0.75, 0.72, 0.68, 1.0)),
    "wood": make_mat("Wood", (0.55, 0.4, 0.26, 1.0)),
    "counter": make_mat("Counter", (0.85, 0.85, 0.87, 1.0), roughness=0.3),
    "bed": make_mat("Bed", (0.9, 0.88, 0.85, 1.0)),
    "wardrobe": make_mat("Wardrobe", (0.6, 0.47, 0.33, 1.0)),
    "ceramic": make_mat("Ceramic", (0.95, 0.97, 0.98, 1.0), roughness=0.15),
}

FLOOR_BY_ROOM = {
    "bathroom": "floor_wet",
    "toilet": "floor_wet",
    "hallway": "floor_hall",
    "corridor": "floor_hall",
    "kitchen": "floor_kitchen",
    "staircase": "floor_hall",
}

# ── Building shell from OBJ ──────────────────────────────────────────────────

bpy.ops.wm.obj_import(filepath=str(OBJ), forward_axis="Y", up_axis="Z")

for obj in scene.objects:
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
    elif "Door" in n:
        obj.data.materials.append(MATS["door"])
    else:
        obj.data.materials.append(MATS["wall"])

# ── Colored floor overlays per space (from building.json) ────────────────────

building = json.loads(BUILDING.read_text())


def add_polygon(name, verts2d, z, mat):
    mesh = bpy.data.meshes.new(name)
    verts = [(x, y, z) for x, y in verts2d]
    mesh.from_pydata(verts, [], [list(range(len(verts)))])
    mesh.update()
    o = bpy.data.objects.new(name, mesh)
    o.data.materials.append(mat)
    scene.collection.objects.link(o)
    return o


for story in building["stories"]:
    for apt in story.get("apartments", []):
        for sp in apt.get("spaces", []):
            key = FLOOR_BY_ROOM.get(sp["room_type"], "floor_room")
            verts = [(v["x"], v["y"]) for v in sp["boundary"]["vertices"]]
            add_polygon(f"Floor_{sp['name']}", verts, 0.26, MATS[key])  # slab top is z=0.25

# ── Furniture boxes ──────────────────────────────────────────────────────────

furniture = json.loads(FURNITURE.read_text())

for item in furniture["items"]:
    x0, y0, x1, y1 = item["bounds"]
    h = item["h"]
    z0 = item.get("z", 0.25)  # default: on top of the ground slab
    bpy.ops.mesh.primitive_cube_add(
        size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, z0 + h / 2)
    )
    cube = bpy.context.active_object
    cube.name = f"F_{item['name']}"
    cube.scale = ((x1 - x0) / 2, (y1 - y0) / 2, h / 2)
    cube.data.materials.append(MATS[item["type"]])

# ── Lights, world, ground ────────────────────────────────────────────────────

# Soft, even light — maquette-photo look, no harsh blue shadows
sun_data = bpy.data.lights.new("Sun", type="SUN")
sun_data.energy = 2.5
sun_data.angle = 0.5  # wide angular size → soft shadows
sun = bpy.data.objects.new("Sun", sun_data)
sun.rotation_euler = (math.radians(30), math.radians(-10), math.radians(40))
scene.collection.objects.link(sun)

world = bpy.data.worlds.new("World")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.95, 0.95, 0.94, 1.0)
world.node_tree.nodes["Background"].inputs[1].default_value = 1.6
scene.world = world

bpy.ops.mesh.primitive_plane_add(size=100, location=(4.75, 8, -0.29))
bpy.context.active_object.data.materials.append(MATS["ground"])

# ── Cameras ──────────────────────────────────────────────────────────────────

target = bpy.data.objects.new("Target", None)
target.location = (4.75, 7.5, 0.6)
scene.collection.objects.link(target)

persp_data = bpy.data.cameras.new("CamPersp")
persp_data.lens = 35
cam_persp = bpy.data.objects.new("CamPersp", persp_data)
cam_persp.location = (19.0, -9.0, 11.0)
scene.collection.objects.link(cam_persp)
tc = cam_persp.constraints.new(type="TRACK_TO")
tc.target = target
tc.track_axis = "TRACK_NEGATIVE_Z"
tc.up_axis = "UP_Y"

top_data = bpy.data.cameras.new("CamTop")
top_data.type = "ORTHO"
top_data.ortho_scale = 19.5  # covers 9.5 x 17.5 site + margin
cam_top = bpy.data.objects.new("CamTop", top_data)
cam_top.location = (4.75, 8.75, 30)
cam_top.rotation_euler = (0, 0, 0)  # straight down, north up
scene.collection.objects.link(cam_top)

# ── Render both views ────────────────────────────────────────────────────────

scene.render.engine = "CYCLES"
scene.cycles.samples = 64
scene.cycles.use_denoising = True

scene.camera = cam_persp
scene.render.resolution_x = 1600
scene.render.resolution_y = 1200
scene.render.filepath = str(OUT_PERSP)
bpy.ops.render.render(write_still=True)
print(f"Rendered {OUT_PERSP}")

scene.camera = cam_top
scene.render.resolution_x = 1100
scene.render.resolution_y = 2000
scene.render.filepath = str(OUT_TOP)
bpy.ops.render.render(write_still=True)
print(f"Rendered {OUT_TOP}")
