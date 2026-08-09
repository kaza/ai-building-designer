# Feature: Furniture vs door-swing clearance (W100)

## Status
implemented (2026-08-05)

## Why this exists
Furniture keeps getting placed inside door swing arcs ("on many places we suck
at this" — owner, 2026-08-05). A door that can't open is a real design defect,
it's invisible in 3D renders, and only sometimes obvious on the 2D plan. The
check must WARN (not error) and name both offenders, so the user can move the
furniture item in furniture.json until the warning clears.

## What it does
- **Framework** (`validators/clearance.py`):
  - `door_swing_geometry(door, wall)` — THE single source of swing truth:
    hinge point (from `operation_type`), closed ray, open ray (from
    `swing_inward` + wall normal), and the swept quarter-disc as a shapely
    Polygon (16 arc segments = 17 arc points + hinge). Allowlist:
    SINGLE_SWING_LEFT / SINGLE_SWING_RIGHT only; anything else (sliding,
    vehicle, future doubles) and degenerate input (door.width ≤ 0.05m,
    zero-length wall) returns None — no guessing. The 2D renderer's
    `_draw_door` is refactored to consume this helper, so plan arcs and W100
    can never drift apart.
  - `FurnitureFootprint` (frozen dataclass: `id`, `name`, `min_x`, `min_y`,
    `max_x`, `max_y`) — typed contract instead of raw dicts; invalid bounds
    (non-finite, min>max) raise at construction.
  - `check_furniture_clearance(story, footprints) -> list[ValidationError]` —
    for every (door, footprint) pair whose rectangle overlaps the swing
    polygon with area > 0.02 m² emit
    `W100: Furniture 'Sofa L long' blocks door 'Vila Entry Door' swing
    (overlap 0.31m²).` Severity: warning. Findings deterministically ordered
    by (door name, footprint id).
- **Project usage**: a project script builds footprints from its furniture
  data and runs the check as a pipeline gate (exit 1 on findings; the
  checked-in project must exit 0 — violations are fixed by MOVING furniture).
  Worked example: [projects/villa-maketa/spec.md](../projects/villa-maketa/spec.md)
  § Furniture v2. CLI: `archicad-builder check-furniture <project>` (exit 1 on violations; promoted from the villa 2026-08-09).

## Boundaries & edge cases
- **W100 is a conservative plan-view (2D) check** — furniture height is
  ignored; a rug or wall cabinet inside the arc still warns. No name-based
  exemptions ("low table") — accurate exemptions need leaf/vertical modeling
  that doesn't exist yet.
- Double doors: the model has no per-leaf hinge/width, so a 1.4m door modeled
  as SINGLE_SWING sweeps its full modeled 1.4m arc — that IS the modeled
  reality; no width/2 guessing. Explicit DOUBLE_* operation types (if added
  later) are unsupported → skipped.
- No room-ownership filtering: if furniture geometrically sits in the swept
  sector, its room label doesn't make the clash legitimate (and furniture on
  the other side of the wall is naturally outside the sector).
- Furniture blocking the doorway OPENING without touching the swing sector is
  a separate future rule (W101) — W100 does not claim complete doorway
  clearance.
- Sliding glass doors modeled as Window elements are invisible to this rule —
  correct, since sliding panels sweep nothing.
- Overlap tolerance 0.02 m²: area-based, not mere touching — brushing the arc
  with a corner shouldn't page anyone.

## Testing & verification (TDD)
- [ ] swing sector: 4 wall orientations × left/right hinge × in/out swing —
      sector center-of-mass lands on the geometrically correct side (16 cases)
- [ ] sector area ≈ πr²/4 and hinge/end coordinates exact for a known case
- [ ] shortest-arc regression (the 270°-wrap case)
- [ ] every unsupported operation type + degenerate width/wall → None
- [ ] footprint fully inside sector → one W100 with door + furniture names + area
- [ ] tangent / below-threshold / exactly-at-threshold overlaps
- [ ] furniture on the opposite wall side → clean
- [ ] invalid footprint bounds raise; duplicate names with distinct ids both
      reported; deterministic ordering
- [ ] renderer still draws identical arcs after the refactor (existing render
      tests stay green)
- [ ] villa GF: violations fixed by moving furniture, checker exits 0;
      colliding fixture exits 1

## Decision log
| Date | Decision | Why |
|------|----------|-----|
| 2026-08-05 | Geometric core in the framework; renderer refactored to consume the same helper | two implementations of hinge/swing conventions WILL drift (review finding, Codex) |
| 2026-08-05 | Typed FurnitureFootprint contract, check loop in the framework | raw dicts can't give stable identities/ordering (Codex); typed contract answers Gemini's coupling objection without inventing a furniture model |
| 2026-08-05 | Warning severity; project script exit 1 as gate; shipped villa exits 0 | design smell, not invalid geometry; the villa pipeline still refuses to regress |
| 2026-08-05 | Conservative 2D semantics, no height inference | vertical exemptions need leaf modeling that doesn't exist; false-positive rug beats false-negative sofa |
| 2026-08-05 | Overlap = area > 0.02 m² (not mere intersection) | matches E090 precedent; corner-brushes are noise |
| 2026-08-05 | add_door gains keyword-only operation_type / swing_inward | Door supported the fields but the builder API couldn't express them (same gap as add_wall/is_external before) |

## Lessons learned
- The very first run on a real project found 5 genuine violations — the rule
  paid for itself before it was even committed (details in the villa spec).
- Code-review round folded: threshold epsilon (float jitter made mirrored
  geometry disagree at exactly 0.02 m² — Codex tested it empirically), door
  ordering by authored data only (wall_id is a REGENERATED IFC id, orderings
  flipped between rebuilds), strict footprint type validation (bools/empty
  ids rejected), duplicate-name-safe ids in the villa runner.

## Related
[space-overlap.md](space-overlap.md) (same shapely approach),
projects/villa-maketa/spec.md (furniture data).
