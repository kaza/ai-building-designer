# Experiment: PyNite plate oracle — real FEM per-element loads for the L view

## Status
PROMOTED (2026-08-08 evening) — hypothesis CONFIRMED (findings.md).
The engine now lives in `src/archicad_builder/fem/` (specs/fem-xray.md):
CLI `fem <project>`, walkthrough L-cycle, published X-ray page; beam
extraction included and gated by its own analytic benchmark (gate 5).
Owner decisions still pending on the over-capacity findings.

## Hypothesis
A PyNite (MIT, pure-Python FEM) plate model of our buildings — bearing
walls and slabs meshed as conforming rectangular quads on a grid snapped
to wall lines — (a) reproduces closed-form plate/beam benchmarks within
±10%, (b) solves villa-maketa under ULS 1.35G+1.5Q (snow 1.32) with
load conservation within 2%, and (c) yields per-element utilizations
mappable back to building.json element IDs — i.e. real FEM numbers the
walkthrough Loads view can display, and an oracle that bounds the strip
engine's error.

## Why
Owner (2026-08-08): "I want a good/great open source calculation for
buildings and need some good solver, which I can take back and show in
our 3D model. It's OK to create a whole mini project out of it and it
can calculate for hours, but I want to have this information."
Three-AI panel (Codex/Gemini/Fable, logged below) unanimously rejected
adopting Karakulak (self-weight-only, frame-only, global-results-only,
AGPL, alpha) and voted continuous-strip kernel as the production engine
with PyNite as the FEM oracle. This experiment IS that oracle — and if
the FEM materially contradicts the strips, it becomes the engine
candidate instead (Codex left the meshing recipe: conforming quads
0.25–0.40 m, refinement at openings, shared slab–wall nodes, physical
tags, convergence checks, sliver rejection).

## Success Criteria
- Benchmarks: ≥4 closed-form cases pass within ±10% (moment, reaction,
  midspan deflection): simply-supported one-way strip, propped/free
  cantilever, two-span continuous, axially loaded wall panel.
- Villa: full model solves; Σ vertical reactions ≈ applied ULS load
  within 2%; per-element result mapping covers ≥95% of bearing
  elements (walls, slabs, roofs, beams).
- Side-by-side table FEM vs strip engine (output/loads.json @ 8bcb900);
  every divergence >25% explained (two-way action, continuity,
  discretization…), not hand-waved.
- Verdict: promote FEM to engine, keep as validation oracle for the
  continuous-strip kernel, or reject — with reasons.

## Constraints
- One variable at a time; benchmarks BEFORE the villa; mesh-convergence
  check (halve grid, compare) before trusting any villa number.
- Runtime is explicitly allowed to be long (owner). No <1s constraint.
- PyNiteFEA is an EXPERIMENT dependency: installed in the repo venv but
  must not be imported from src/ — promotion is a separate spec+TDD
  step (experiments/CLAUDE.md).
- The trap the whole panel named: false precision from wrong boundary
  conditions/meshing, not the solver. Every benchmark failure gets a
  root cause in the audit log before moving on.

## Setup
- Input: `projects/villa-maketa/building.json` @ 8bcb900 (record per
  attempt); strip-engine reference: `output/loads.json` @ same.
- Solver: PyNiteFEA (pip, MIT) — record exact version in attempt 01.
  Plates: `FEModel3D.add_plate`/`add_quad`, results via plate corner
  forces / moment arrays; load combos native.
- Loads (same DesignBasis as structural.py, for comparability):
  roof dead min(t,0.25)·25 + 2.0 finishes; floor dead t·25 + 1.5
  finishes + 2.0 live; snow 1.32; ULS 1.35G + 1.5Q; wall self 25 kN/m³.
- Capacities: same as structural.py (wall t·0.6·3 MPa; rc bending
  ρ0.5% fyd 435) so utilization differences isolate DEMAND differences.
- Scripts inside this dir; raw solver output under logs/.

## Panel record (2026-08-08, all three ran and proved file access)
- Gemini: Karakulak low-feasibility ("fatal feature + architecture
  mismatch"); recommends DSM on existing strips; trap = don't couple
  crossing strips into two-way.
- Fable: Karakulak "wrong loads, wrong elements, wrong results, wrong
  code, wrong license, wrong maturity"; winner = continuous E-B per
  strip; PyNite plates as oracle experiment; defensibility = printed
  assumptions + closed-form benchmark suite + per-element audit trail.
- Codex: Karakulak no, even partially (AGPL §13 analysis logged in
  session); engine = continuous-strip kernel with separated load cases
  and patterned loading; "do NOT productionize PyNite plates yet";
  biggest trap = false precision from invalid idealization.
