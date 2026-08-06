# Feature: Spiral staircase rendering

## Status
implemented

## Why this exists
`StaircaseType.SPIRAL_STAIR` exists in the model and exports to IFC correctly,
but the 2D floor plan drew every staircase as parallel straight treads — a
spiral stair was indistinguishable from a straight one on the drawing.

## What it does
- 2D floor plan (`export/floorplan.py`): when `stair_type == SPIRAL_STAIR`,
  draw the architectural spiral symbol — outline, inscribed circle, center
  pole dot, radial treads (every 30°), and a curved ascent arrow. Other types
  keep the existing straight-tread symbol.
- 3D previews are a project-renderer concern (a project script may build a
  real spiral — pole + helical steps). Worked example: villa-maketa's Garage
  Stair (1.5×1.5 m, [project spec](../projects/villa-maketa/spec.md)).

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
