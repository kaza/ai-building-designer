"""IFC -> OBJ (tessellated) for Blender and any other mesh consumer.

Promoted from projects/villa-maketa/ifc_to_obj.py on 2026-08-09: 52 lines
with no project-specific logic beyond a hardcoded filename, which is the
clearest possible case for framework code (ADR-004).

Openings are skipped deliberately: IfcOpeningElement is a void box, and
rendering it covers the window it was supposed to cut.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from pathlib import Path


@dataclass
class ObjResult:
    products: int
    vertices: int
    skipped: list[str] = dc_field(default_factory=list)


def _settings():
    import ifcopenshell.geom

    settings = ifcopenshell.geom.settings()
    # ifcopenshell 0.8 takes string keys; older builds expose enum constants
    if hasattr(settings, "USE_WORLD_COORDS"):
        settings.set(settings.USE_WORLD_COORDS, True)
    else:
        settings.set("use-world-coords", True)
    return settings


def ifc_to_obj(ifc_path: Path, obj_path: Path, label: str | None = None) -> ObjResult:
    """Tessellate every renderable product into one OBJ file."""
    import ifcopenshell
    import ifcopenshell.geom

    model = ifcopenshell.open(str(ifc_path))
    settings = _settings()
    lines: list[str] = [f"# {label or ifc_path.stem}"]
    skipped: list[str] = []
    v_offset = 1
    products = [
        p for p in model.by_type("IfcProduct")
        if p.Representation is not None
        and not p.is_a("IfcSpace")
        and not p.is_a("IfcOpeningElement")
    ]
    for p in products:
        try:
            shape = ifcopenshell.geom.create_shape(settings, p)
        except Exception as exc:      # noqa: BLE001 — collected and reported
            skipped.append(f"{p.is_a()} {p.Name}: {exc}")
            continue
        verts, faces = shape.geometry.verts, shape.geometry.faces
        lines.append(f"o {p.is_a()}_{(p.Name or 'unnamed').replace(' ', '_')}")
        for i in range(0, len(verts), 3):
            lines.append(
                f"v {verts[i]:.4f} {verts[i + 1]:.4f} {verts[i + 2]:.4f}")
        for i in range(0, len(faces), 3):
            a = faces[i] + v_offset
            b = faces[i + 1] + v_offset
            c = faces[i + 2] + v_offset
            lines.append(f"f {a} {b} {c}")
        v_offset += len(verts) // 3

    obj_path.parent.mkdir(parents=True, exist_ok=True)
    obj_path.write_text("\n".join(lines))
    return ObjResult(products=len(products) - len(skipped),
                     vertices=v_offset - 1, skipped=skipped)
