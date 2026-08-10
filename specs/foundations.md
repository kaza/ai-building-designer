# Feature: Foundations — footings, soil, and force-into-the-ground checks

## Status

Spec'd 2026-08-10 (S3 of the seismic commission — see
[seismic-lateral.md](seismic-lateral.md)).

## Why this exists

The schema has no foundation element: the lowest storey's walls are
clamped into mathematical bedrock and `SlabType.BASESLAB` is the only
foundation-shaped token in the codebase. "Take the force into the
earth" is currently implemented as "the earth is an infinitely strong
boolean." For a building-ready handoff the load path must END
somewhere real: a footing with a width, on a soil with a bearing
capacity, checked for pressure, sliding and overturning.

## What it does

1. **`StripFooting` element** (framework schema, lowest storey only):
   `name`, `start`/`end` (Point2D centerline, like Wall), `width`
   (horizontal, ⊥ axis), `height` (vertical), material rc. Builder
   `add_footing(story, start, end, width, height, name)`. Exports as
   IfcFooting (extruded rectangle, top at storey elevation). Pad
   footings and rafts are NOT modeled (see Boundaries); a BASESLAB
   slab may serve as a raft only in the engineer's judgment, not the
   validator's.
2. **`[site.soil]` config**: `sigma_rd` (design bearing resistance,
   kPa — from the project's geotechnical report; no default, soil is
   not guessable), `friction_mu` (base friction coefficient, default
   0.5). No `[site.soil]` → foundation checks `unresolved`.
3. **E104 — bearing wall without a footing** (error): every
   load-bearing wall on the lowest storey must be covered by a
   footing whose centerline is parallel (±15°) and laterally within
   `min(0.15, wall.thickness/2)`, covering the wall extent with
   ≥ 0.10 m projection past each end, and `width ≥ wall.thickness`
   (same geometric contract as E062's beam-over-opening, pointed
   down). Walls standing on a BASESLAB (slab-on-grade footprint
   containment) are exempt — the slab grounds them, as the FEM
   already assumes.
4. **E105 — soil bearing pressure exceeded** (error): per footing,
   `(worst wall base line load from the strip engine + footing
   self-weight) / width > sigma_rd`. Uses the strip engine's
   station-sampled wall profiles — peaks, not averages.
5. **E106 — sliding under base shear** (error, per direction):
   `Fb > friction_mu · N_total` where N is the unfactored gravity
   weight (G + ψE·Q, consistent with the seismic mass). Passive earth
   pressure is ignored (conservative, logged).
6. **E107 — seismic overturning** (error, per direction): rigid-body
   check about each plan edge: `M_overturning = Σ Fi·zi` vs
   `M_stabilizing = N · d_edge`, require ratio ≥ 1.1. Crude and
   global by design — a villa that fails a rigid-body overturn is
   news the owner wants before the engineer does.
7. **FEM**: footings are NOT meshed; wall-base clamps stay. The
   `not_modelled` list shrinks from "foundations, soil bearing,
   settlement, uplift and sliding" to "soil–structure interaction,
   settlement" — bearing/sliding/overturning move to the checked
   column of the handoff report.

## Boundaries

- EC7 lite: one bearing number from the geotech report, no drained/
  undrained distinction, no settlement, no groundwater, no passive
  pressure. The report prints exactly this list.
- E105 checks GRAVITY bearing pressure only. The seismic increase on
  the compression edge (moment eccentricity, the M/W term) is NOT
  computed — it is a named `not_modelled` entry, never a silent gap
  (Gemini plan review 2026-08-10).
- Strip footings only. Pads (under columns — the schema has no
  columns) and rafts are YAGNI until a project needs them.
- EN 1998-5 foundation tie-beams: NOT validated. Strip footings under
  a full wall grid are inherently tied; the handoff report carries a
  standing note for the engineer instead of a fake check.
- Footings don't render in the walkthrough/plans (underground);
  they appear in IFC and the handoff report only.

## Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-08-10 | `sigma_rd` has no default | soil strength varies 50–600 kPa across normal sites; a default would be an invented geotech report. Fail to `unresolved` instead |
| 2026-08-10 | E104 reuses E062's coverage geometry, pointed down | one battle-tested contract (parallel, lateral offset, end projection, width) instead of a second slightly different one |
| 2026-08-10 | Overturning is rigid-body global, ratio ≥ 1.1 | KISS: catches gross geometry sins (tall narrow wing, heavy console); per-wall uplift is FEM/engineer territory |

## Acceptance

- E104–E107 unit tests per the validator pattern (synthetic buildings
  with/without footings, sliding/overturning constructed to fail).
- IFC round-trip: footing exports as IfcFooting with correct geometry.
- villa-maketa: footings under the bearing grid, checks pass or carry
  reasoned waivers.

## Related

[seismic-lateral.md](seismic-lateral.md) (base shear feeding
E106/E107) · [structural-plausibility.md](structural-plausibility.md)
(strip engine wall base loads) · [engineer-handoff.md](engineer-handoff.md)
(where the soil assumptions surface) · [ifc-identity.md](ifc-identity.md).
