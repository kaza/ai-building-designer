# Feature: Structural plausibility — beams over openings (E062/E063)

## Status
Spec'd 2026-08-08 (owner commissioned after the load-takedown experiment).
Phase A: beam element + existence/slenderness checks. Phase B (roadmap):
load-based utilization.

## Why this exists
The load-takedown experiment
([experiments/2026-08-08_static-load-takedown](../experiments/2026-08-08_static-load-takedown/findings.md))
proved villa-maketa's roof was structurally resting on glass: every wide
opening on a bearing wall had a 0.20 m band above it, 6–144× over
capacity. The model schema had no way to even EXPRESS the fix — there was
no beam/lintel element. Owner: band-window architecture is the product's
bread and butter; the model must carry the thing that makes it stand.

## What it does
1. **Beam element** (framework schema): a horizontal structural member on
   a storey. Fields: `name`, `start`/`end` (Point2D centerline), `width`
   (horizontal, ⊥ to axis), `depth` (vertical), `z_top` (m above storey
   datum; default = storey height, i.e. the beam hangs below the wall
   top / roof seat). Builder API `add_beam(story, start, end, width,
   depth, name, z_top=None)`. Exports as IfcBeam (extruded rectangle).
2. **E062 — wide opening on a bearing wall without a beam over it**
   (error): every door/window with `width ≥ 1.25 m` hosted by a
   `load_bearing` wall must have ONE beam (collinear part-beams jointly
   covering are rejected — an unmodeled joint is not a connection) whose
   centerline is parallel (±15°, modulo direction) and laterally within
   `min(0.15, wall.thickness/2)` of the wall axis, whose segment covers
   the opening extent plus ≥ 0.10 m bearing on each side (endpoint
   projection, not distance — near-miss ends must not fake bearing),
   wide enough for the wall (`width ≥ thickness − 0.05`, transverse
   bearing), positioned above the opening head
   (`z_top − depth ≥ head − 0.05`). Opening head: door = height,
   window = sill + height, both relative to the storey datum.
   Threshold 1.25 m: the takedown showed ≤1.2 m openings marginally
   survive a reinforced band; wider ones never do.
3. **E063 — implausibly slender beam** (error): the covering beam must
   satisfy `clear span / depth ≤ limit(material)` — rc 15, steel 20,
   timber 12; clear span = opening width, bearings excluded. Deeper
   analysis is Phase B.
4. `z_top` default (= storey height) is supplied by `add_beam()`, not
   the model — a Beam alone cannot know its storey. `add_beam_over()`
   sugar places an upstand over a named opening (depth heuristic
   span/10 rounded up to 0.05, min 0.35 — attempt-04 numbers).
5. Runs in the vertical/structural validator phase alongside E050–E052,
   BEFORE its two-storey guard (E062/E063 are per-storey).

## Boundaries
- Plausibility, not design: no load combinations, no reinforcement
  sizing, no deflection calc in Phase A. A licensed engineer signs real
  buildings.
- Beams carry no finish/rendering semantics beyond geometry (project
  renderers may style them).
- Openings on non-bearing walls need no beam (nothing above to carry).
- A beam far ABOVE the opening head still satisfies E062 (the masonry
  band between head and beam bottom is assumed to arch its load up) —
  bounding that gap is Phase B territory (Gemini review 2026-08-08).
- Doors are floor-level by schema (no sill field); head = height. If a
  door sill is ever added, E062's head math must follow.
- ~~Phase B (not commissioned)~~ SHIPPED 2026-08-08: `structural.py`
  computes one explicit load path — roof/floor panels with DECLARED
  one-way `span_direction` are sliced into strips (per station, disjoint
  polygon intervals never bridge); supported segments use qL²/8,
  free-edge cantilevers qL²/2 (Gemini review); reactions accumulate on
  bearing walls (station-sampled profiles), transfer to aligned walls
  below; floor panels are clipped to the storey-below footprint (on
  grade = loads the soil). Per-panel load-balance ratio is reported.
  Checks: E064 rc-beam bending util > 1 (station-sampled q over the
  opening, not whole-wall average — Codex), E065 roof panel util > 1
  (bending or span/depth deflection proxy: 30 supported / 10
  cantilever), E066 gross wall axial util > 1 (t·Φ·f_d; jamb/pier
  concentrations documented out of scope). Undeclared span directions
  and non-rc beams are `unresolved`, never errors (Codex). All
  assumptions live in `DesignBasis`; the output is labelled structural
  PLAUSIBILITY, not Eurocode compliance. CLI: `loads <project>` →
  output/loads.json (the walkthrough Loads view consumes it — slabs
  render flat-colored; walls/beams gradient).
- Phase C candidates (not commissioned): continuous Euler-Bernoulli
  beam per strip (negative moments over interior supports; reactions
  and envelope from ONE model — Codex brainstorm 2026-08-08); PyNite as
  a benchmark oracle on curated slabs before any 2D FEM dependency
  (both brainstorms: the trap is boundary conditions and meshing, not
  the solver); wall jamb/pier concentration checks; SLS deflection
  beyond the span/depth proxy.

## Worked example
projects/villa-maketa: ring-beam segments over every ≥1.25 m opening on
bearing walls, sized by the experiment's attempt-04 numbers (documented
in the project spec).

## Decision log
| Date | Decision | Why |
|---|---|---|
| 2026-08-08 | Beam is a first-class storey element, not a wall property | an opening can be spanned by one continuous ring beam crossing several walls/openings; wall-attached lintels can't express that |
| 2026-08-08 | Phase A = existence + slenderness only; utilization is Phase B | YAGNI: the takedown script already answers "how big"; the validator's job today is catching "there is no beam at all" — the class of error that shipped |
| 2026-08-08 | 1.25 m threshold, L/depth ≤ 15 | attempt-01/04 data: ≤1.2 m openings pass a reinforced band (util ≤ ~0.9); L/15 matches RC lintel practice |

## Related
[fem-xray.md](fem-xray.md) (plate-FEM oracle — the L-key X-ray; shares this spec's DesignBasis) · [storey-datum.md](storey-datum.md) (E050–E052 phase) · the load-takedown
experiment · projects/villa-maketa/spec.md (worked example).
