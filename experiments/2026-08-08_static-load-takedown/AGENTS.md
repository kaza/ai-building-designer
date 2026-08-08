# Experiment: Static load takedown — are the band windows carrying the roof?

## Status
COMPLETE — hypothesis CONFIRMED (attempt 01; see findings.md)

## Hypothesis
In villa-maketa, the wall band above at least one wide opening (prime
suspects: Win7 "Living Band Window N", head 2.80 on a 3.0 m wall → 0.20 m
band; the west clerestories Win2/Win3; the 2.8 m-head glass sliders) is
too shallow to carry the Eurocode roof load over its span as a plain
concrete/masonry band — i.e. utilization > 1.0 without explicit
reinforcement — meaning the model implicitly rests the roof on glass.

## Why
Owner (2026-08-08): "I am worried that Win2 and Win7 are carrying the
roof." If the takedown method proves informative, it becomes a framework
validator phase (structural plausibility, E06x class) — the owner already
expects that promotion.

## Success Criteria
- A per-opening report: span, line load, moment, band depth, utilization
  for (a) an unreinforced band and (b) a minimally reinforced RC ring
  beam (2Ø12), with a clear verdict per opening.
- Hypothesis CONFIRMED if any opening's unreinforced band utilization
  exceeds 1.0 under the as-modeled roof; REJECTED if all pass.
- Method judged promotable (or not) to a validator: does it produce
  actionable, defensible verdicts from building.json alone?

## Constraints
- Deterministic calc — "run multiple times" = re-run after each
  assumption change, one variable at a time, both load scenarios always
  reported side by side.
- This is a PLAUSIBILITY takedown, not a structural design: no FEM, no
  seismic, no wind, no deflection beyond a span/depth rule of thumb.
  A licensed engineer still signs real buildings.

## Setup
- Input: `projects/villa-maketa/building.json` @ repo HEAD (recorded in
  audit log per attempt).
- `python load_takedown.py` (repo venv: shapely available).
- Loads (documented assumptions):
  - Scenario A "as modeled": roof slab 0.45 m solid RC, 25 kN/m³ → 11.25 kN/m² dead.
  - Scenario B "realistic build-up": 0.20 m RC + 2.0 kN/m² finishes → 7.0 kN/m².
  - Snow (Austria, zone ~2, <400 m): sk 1.65, μ1 0.8 → 1.32 kN/m²
    (governs over 1.0 kN/m² non-accessible roof live; not combined).
  - ULS combo: 1.35·G + 1.5·S. Wall band self-weight 25 kN/m³.
- Tributary model: one-way strips — per wall sample point, half the
  perpendicular distance to the nearest parallel load-bearing wall
  (interior side) + full cantilevered roof overhang (exterior side),
  only where the roof outline actually covers the strip.
- Lintel model: simply supported band over effective span (opening width
  + 0.25 m bearing), M = q·L²/8. Unreinforced capacity: section modulus
  × fctd 1.0 MPa (C25/30 design tension, conservative-plain). Reinforced:
  2Ø12 B500 (As 226 mm², fyd 435 MPa), M_rd ≈ As·fyd·0.9·d.
