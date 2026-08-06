# Feature: Wall corner joins (junction cleanup at export)

## Status
Implemented.

## Problem
Walls are modeled as centerline segments and extruded start→end. At an
L-corner two walls share an endpoint, so each solid stops at the corner
POINT — the square outside the centerlines (thickness × thickness) belongs
to neither wall. Every convex corner shows a gap from outside. T-junctions
don't gap (a wall butting mid-segment already penetrates half the partner).

## Contract
- Junction cleanup is **baked into the IFC exporter for all walls** — no
  API flag, no validator rule. It is geometry correctness of the 3D output,
  not a design decision; the JSON model stays pure centerlines (validators,
  floor plans, tags untouched).
- At each wall end, if another wall on the same story has an endpoint at
  the same point (tolerance 1e-6) and is NOT parallel, the solid extends
  lengthwise by the largest such partner's half-thickness. Both corner
  walls extend, overlapping in the corner cube — visually identical to a
  mitered join in renders/GLB/IFC viewers at a fraction of the geometry
  ("extend and overlap", CAD option #1; miter rejected as invisible-but-5×
  -the-code).
- **Collinear partners never extend** (wall split into segments, e.g. a
  finish-color split): they butt flush with no gap, and overlapping them
  would z-fight two coplanar faces (possibly different materials).
- Openings are unaffected: doors/windows are placed from `wall.start` in
  world coordinates; only the wall solid grows.

## Limits
- Extension = partner thickness / 2 is exact for perpendicular joins. All
  current projects are axis-aligned; oblique joins would need
  t/(2·sin θ) or a true miter — out of scope until a project has one.

## Decision log
| Date | Decision | Why |
|------|----------|-----|
| 2026-08-06 | Extend-and-overlap at export, all junctions (not only external walls) | interior corners have the same notch; per-wall opt-outs are a knob nobody should turn (owner asked; answered "bake it in") |
| 2026-08-06 | Skip parallel partners | collinear splits (villa W7/W16 accent/white) have no gap; overlap would z-fight coplanar faces |

## Related
[architecture.md](architecture.md) · worked example: projects/villa-maketa
(SW corner W1/W16, maquette review 2026-08-06)
