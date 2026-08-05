"""Convert villa IFC to OBJ (tessellated) for rendering in Blender.

Run: .venv/bin/python projects/villa-maketa/ifc_to_obj.py
"""

from pathlib import Path

import ifcopenshell
import ifcopenshell.geom

HERE = Path(__file__).parent
IFC = HERE / "output" / "villa-maketa.ifc"
OBJ = HERE / "output" / "villa-maketa.obj"

model = ifcopenshell.open(IFC)

settings = ifcopenshell.geom.settings()
# ifcopenshell 0.8 takes string keys; older builds expose enum constants
if hasattr(settings, "USE_WORLD_COORDS"):
    settings.set(settings.USE_WORLD_COORDS, True)
else:
    settings.set("use-world-coords", True)

lines: list[str] = ["# villa-maketa"]
v_offset = 1

products = [
    p for p in model.by_type("IfcProduct")
    if p.Representation is not None
    and not p.is_a("IfcSpace")
    and not p.is_a("IfcOpeningElement")  # void boxes — they cover the real windows
]

for p in products:
    try:
        shape = ifcopenshell.geom.create_shape(settings, p)
    except Exception as e:  # noqa: BLE001 — skip unrenderable, report at end
        print(f"skip {p.is_a()} {p.Name}: {e}")
        continue
    verts = shape.geometry.verts
    faces = shape.geometry.faces
    name = f"{p.is_a()}_{(p.Name or 'unnamed').replace(' ', '_')}"
    lines.append(f"o {name}")
    for i in range(0, len(verts), 3):
        lines.append(f"v {verts[i]:.4f} {verts[i+1]:.4f} {verts[i+2]:.4f}")
    for i in range(0, len(faces), 3):
        a, b, c = faces[i] + v_offset, faces[i + 1] + v_offset, faces[i + 2] + v_offset
        lines.append(f"f {a} {b} {c}")
    v_offset += len(verts) // 3

OBJ.write_text("\n".join(lines))
print(f"Wrote {OBJ} ({len(products)} products, {v_offset - 1} vertices)")
