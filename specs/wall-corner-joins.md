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
- **Corner glazing** (the inverse case): a WINDOW flush with a joined wall
  end (`position=0` or `position+width=length`) opens the joint instead —
  its pane and opening extend through the corner by the join extension, and
  a twin opening voids the partner wall (IFC allows one void per opening),
  so two flush windows meet glass-to-glass around the corner. Below/above
  the glazing the joint stays filled. Glass DOORS (`pane_side` set)
  participate identically (villa D8/D9 ↔ Win4 across the W8 end cap,
  feedback #003); solid doors never extend. Two flush panes sharing a
  corner pass/butt instead of crossing (feedback #002).

## Limits
- Extension = partner thickness / 2 is exact for perpendicular joins. All
  current projects are axis-aligned; oblique joins would need
  t/(2·sin θ) or a true miter — out of scope until a project has one.
- Pass/butt is exact ONLY for an inner-flush pane pair with overlapping
  height bands (partner panes include flush glass doors; vertically
  disjoint panes are ignored; multi-partner corners resolve by smallest
  wall GlobalId — deterministic). Outer/outer and mixed pairs keep the
  full extension: their panes overlap inside the corner cube, which
  transparent glass hides; exact joins there need per-side plane math
  (Codex review 2026-08-06). Corner setbacks that consume a pane entirely
  raise at export.

## Decision log
| Date | Decision | Why |
|------|----------|-----|
| 2026-08-06 | Extend-and-overlap at export, all junctions (not only external walls) | interior corners have the same notch; per-wall opt-outs are a knob nobody should turn (owner asked; answered "bake it in") |
| 2026-08-06 | Skip parallel partners | collinear splits (villa W7/W16 accent/white) have no gap; overlap would z-fight coplanar faces |
| 2026-08-06 | Corner glazing via end-flush windows + twin partner-wall void | owner feedback #001 (villa): band windows must meet glass-to-glass at the W6/W7 corner; the join otherwise leaves a hidden post that only the exporter (which owns the extensions) can open |

## Related
[architecture.md](architecture.md) · worked example: projects/villa-maketa
(SW corner W1/W16, maquette review 2026-08-06)
