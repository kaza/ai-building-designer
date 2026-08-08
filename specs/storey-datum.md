# Feature: Storey datum — slabs below, elements on top (E052)

## Status
Spec approved, implementation in progress (2026-08-06).

## Problem
The IFC exporter extruded floor slabs **upward** from the storey elevation
(slab occupied `[elevation, elevation + thickness]`) while walls, doors,
windows and staircases were placed **at** the storey elevation — the slab's
*bottom*. Result: the lower 25 cm of every wall, every door leaf and the
first turn of the garage spiral stair were buried inside the ground slab
(villa-maketa feedback #013/#014 — the owner flew inside the slab and found
door leaves starting mid-concrete). Any section drawing generated from the
IFC would show openings sunk below the finished floor. Nothing caught it.

## Contract
- **Storey elevation is the finished floor level (FFL)** — the surface you
  walk on. This is the ArchiCAD/Revit convention and now the framework's.
- **Floor slabs hang below the datum**: a floor slab (`is_floor=True`)
  occupies `[elevation − thickness, elevation]`; its top face IS the storey
  elevation. Walls, doors, windows, staircases, spaces and furniture keep
  their placement at `elevation` — they now sit *on* the slab instead of
  *inside* it. No change to `building.json` semantics: `thickness` still
  means thickness; authors never state slab z.
- **Ceiling slabs (`is_floor=False`) are unchanged** (`[elevation −
  thickness, elevation]` — identical to the new floor placement). No
  project exports ceilings; their vertical placement is legacy/unspecified
  until one does (YAGNI). `is_floor` still drives classification.
- **E052 — opening must not clash with another storey's slab** (validator,
  Phase 6, severity error): for every door and window, the opening volume
  — z-range door `[elev, elev + height]` / window `[elev + sill, elev +
  sill + height]`, 2D footprint = the opening's rectangle `width ×
  wall.thickness` centered on the wall axis (Shapely polygon, exact) —
  must not strictly overlap any slab volume `[elev₂ − t, elev₂]` on any
  OTHER storey (e.g. an upper floor slab dipping into a tall ground-floor
  door). Overlap is strict in both axes: vertical `min(tops) − max(bottoms)
  > 1e-6` (meters) AND footprint `intersection.area > 1e-6` (m² — float
  noise on flush edges must not fire) — surface/edge contact is legal.
  Self-intersecting slab outlines are normalized via Shapely `make_valid`
  before intersecting (Polygon2D permits them; crashing the validation run
  on one bad polygon helps nobody). Same-storey clashes are geometrically
  impossible under this
  convention (all slabs top out at the datum, sills are ≥ 0), so the rule
  is cross-storey by construction. Openings whose `wall_id` dangles are
  skipped — structural validation owns that finding.
- **E052 is model-level and cannot catch exporter regressions** — it
  derives slab volumes the same way the exporter does. The IFC placement
  unit tests (slab z == elevation − thickness) are the datum's regression
  guard.
- **Walkthrough: vertical flight is UNRESTRICTED — owner decision, final
  (2026-08-07).** Space/C flies through floors, ceilings, everything. No
  slab clamp, no collision, no pass-through modifier, no storey-teleport
  keys. The owner flies through floors ON PURPOSE — it is how he reviews
  the building. A swept slab clamp (+ Shift bypass + digit teleports) was
  implemented and reverted the same day ("it was never accident, i did it
  on purpose, just leave it as it was — no more no less"). **Do not
  reintroduce any vertical movement restriction in the walkthrough
  without an explicit owner request.** The confusion that motivated the
  clamp (reading one slab's two faces as "two floors") is addressed by
  the HUD position/room/storey readout and element labels instead.

## Limits
- E052 checks openings only. Furniture, staircases and roofs intersecting
  slabs are out of scope until a project hits it.
- Project data with absolute z values (villa `furniture.json`: counter-top
  sink, deck furniture) must shift with the datum — the flip is a breaking
  change for any hand-authored elevation.

## E050 — partial basements (2026-08-08)
A load-bearing wall needs aligned support below ONLY where it stands over
the lower storey's slab footprint (union of slab outlines, +0.05m mitre
buffer); portions outside stand on foundations/grade and are exempt.
Support = parallel (±15°) lower bearing walls, flat-cap buffered by
thickness/2 + 0.1; the longest contiguous unsupported inside run ≥ 0.1m
errors. A lower storey with NO slab geometry falls back to the legacy
whole-wall check — missing data must not silently exempt (Codex review).
Why: the old whole-wall rule force-modeled full basements (villa-maketa
grew a 90 m² garage as a workaround). Tests: test_e050_partial_basement.py.

## Decision log
| Date | Decision | Why |
|------|----------|-----|
| 2026-08-06 | Flip floor slabs below the datum instead of offsetting every element up by slab thickness | one change in `_create_slab` vs a per-story offset threaded through every placement; storey elevation keeps meaning "floor you stand on" (ArchiCAD convention); owner picked this option in chat |
| 2026-08-06 | Ceiling slab placement left as-is (now equal to floor) | zero exporting users; inventing a suspended-ceiling convention with no consumer is fiction |
| 2026-08-06 | E052 covers doors + windows only, cross-storey, strict overlap with 1e-6 tolerance | the class of bug actually observed; contact-at-datum is the *correct* post-flip geometry and must stay legal |
| 2026-08-06 | E052 footprint via Shapely (opening rect × slab polygon), not centerline sampling | plan review (Gemini + Codex): a slab edge flush with a wall face never touches the centerline — silent false negative; Shapely is already a dependency |
| 2026-08-06 | E052 reframed cross-storey; IFC unit tests guard the datum itself | plan review (Codex): a model-level rule that derives slab z the same way the exporter does can never catch the exporter regressing — the original claim was circular |
| 2026-08-06 | Walkthrough clamp is swept (oldY → newY vs every face), nearest face wins | plan review (Gemini + Codex): Shift flight moves >1 m/frame — a point test tunnels straight through a 15 cm deck slab |
| 2026-08-07 | Code review: Codex only (5 findings, all fixed). Gemini's code pass skipped after 4 transport failures | Gemini CLI failed every request over ~1 KB with `fetch failed` (not a 429 — tiny prompts worked); Gemini did review the plan pre-code, Codex reviewed plan AND code |
| 2026-08-07 | Lesson: regenerating the walkthrough MUST start at `archicad_builder export` | first rebuild skipped the IFC export — stale slab + new furniture = everything "sunk 25 cm" (feedbacks #015–#018); one-command rebuild goes into the 3D-presentation-layer feature |
| 2026-08-06 | ~~Walkthrough slabs solid + digit-key storey jump~~ SUPERSEDED 2026-08-07 | owner sank into slabs four times — but see next row |
| 2026-08-07 | Vertical flight unrestricted, clamp + teleports fully reverted — owner decision, FINAL | "it was never accident i did it on purpose, just leave it as it was, no more no less" — through-floor flight is his review method; the two-faces confusion is solved by HUD + labels, not by restricting movement |

## Related
[wall-corner-joins.md](wall-corner-joins.md) (the exporter owns geometry
correctness) · [browser-walkthrough.md](browser-walkthrough.md) (clamp +
storey-jump UX) · ADR-002 (severity tiers) · worked example:
projects/villa-maketa (feedback #013/#014, deck top now flush with FFL —
recorded in the project spec).
