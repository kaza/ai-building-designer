# Feature: Spiral staircase rendering

## Status
implemented

## Why this exists
`StaircaseType.SPIRAL_STAIR` exists in the model and exports to IFC correctly,
but the 2D floor plan drew every staircase as parallel straight treads and the
Blender pipeline rendered a plain prism — a spiral stair was indistinguishable
from a straight one. villa-maketa's maquette has a spiral stair to the garage.

## What it does
- 2D floor plan (`export/floorplan.py`): when `stair_type == SPIRAL_STAIR`,
  draw the architectural spiral symbol — outline, inscribed circle, center
  pole dot, radial treads (every 30°), and a curved ascent arrow. Other types
  keep the existing straight-tread symbol.
- Blender preview (villa project script): a `SPIRAL_STAIR` staircase renders
  as a real spiral — center pole + helical wedge steps descending toward the
  garage level, clipped by the ground plane.
- villa-maketa switches its Garage Stair to `SPIRAL_STAIR` with a compact
  1.5×1.5m outline (matches the maquette); the hallway polygon carve-out and
  the W042 waiver (tunnel-shaped stair — now square) are updated accordingly.

## Boundaries & edge cases
- Non-rectangular spiral outlines: the inscribed circle uses the bounding-box
  center and the smaller half-extent as radius.
- IFC export needs no change (ShapeType passes the enum value through).

## Testing & verification
- [x] Floor plan render with SPIRAL_STAIR produces a file (smoke, tmp_path)
- [x] Floor plan render with STRAIGHT_RUN_STAIR unchanged (smoke)
- [x] IFC export round-trip: exported stair carries ShapeType=SPIRAL_STAIR
- [x] villa validates 0 errors; stale W042 waiver removed

## Decision log
| Date | Decision | Why | Who |
|------|----------|-----|-----|
| 2026-08-04 | Blender spiral built in the villa render script, not the OBJ converter | preview-layer concern; IFC keeps the plain extrusion until ArchiCAD needs flights | Claude |

## Lessons learned
(after implementation)

## Related
[../projects/villa-maketa/spec.md](../projects/villa-maketa/spec.md)
