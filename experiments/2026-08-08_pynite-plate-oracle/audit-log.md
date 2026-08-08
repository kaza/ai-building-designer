# Audit log — PyNite plate oracle

## Attempt 01 — 2026-08-08 17:47 (install + first benchmark)
- Installed PyNiteFEA 3.0.0 (uv, repo venv; scipy 1.18.0 came with it).
  Experiment-only dep — must not be imported from src/.
- `benchmarks.py ss_strip` → logs/attempt-01.txt: simply supported
  4 m strip, 0.125 m quads. Mx 19.995 vs 20.0 (qL²/8), deflection
  ratio 0.998 vs 5qL⁴/384EI, ΣRz exact. PASS.
- Support recipe that works: fix in-plane DOFs (DX, DY, RZ) at every
  node — quads have no drilling stiffness — pin DZ only on support
  edges. This is the boundary-condition trap the panel warned about,
  solved at benchmark scale first, deliberately.

## Attempt 02 — 2026-08-08 17:52 (remaining 3 benchmarks)
- `benchmarks.py cantilever two_span wall_axial` → logs/attempt-02.txt.
- Cantilever: root Mx ratio 1.062 (extrapolated at root face — quad
  recovery overshoots slightly), tip deflection 0.994, ΣRz exact. PASS.
- Two-span continuous: hogging Mx 0.960 (element-center sample sits
  0.0625 m off the support peak — understates, root cause understood),
  center reaction 1.25qL and end 0.375qL both ~1.000. PASS.
- Wall in-plane: base reaction exact, mid-height σ_y ratio 1.008. PASS.
- Success criterion 1 met: 4/4 cases, 13/13 checks within ±10% (11/13
  within 1%). Verdict: solver + our boundary-condition recipe are
  trustworthy; any villa weirdness from here on is MESHING/IDEALIZATION,
  not PyNite.

## Attempt 03 — 2026-08-08 18:05 (first villa solve, mesh 0.4)
- `villa_fem.py --mesh 0.4` → logs/villa-fem-mesh0.4.json: 5162 nodes,
  5024 quads, built 0.1 s, solved 22.4 s. Load balance EXACTLY 1.0000
  (4817.2 kN applied = reacted).
- Raw per-element u (peak-quad sampling): Roof East 1.90, Living East
  Wall 1.82, North Wall 1.69, Roof South 1.51, Roof West 1.50, everything
  else ≤ 0.45.
- NOT yet trustworthy: (a) roof u uses the single worst quad — corner/
  wall-end peaks are singularity-driven and mesh-dependent, real design
  uses strip-averaged moments; (b) wall u sampled at jamb concentrations
  (structural.py documents jambs as out of scope — FEM sees them; may be
  REAL but needs averaging vs singularity check); (c) Master North Wall
  reads exactly 0.00 — suspicion: disconnected from the load path. All
  three go to attempt 04 before any comparison with the strip engine.

## Attempt 04 — 2026-08-08 18:15 (design-value extraction, mesh 0.4)
- Peak-quad sampling replaced by 1 m strip-averaged design moments
  (plates) and 0.5 m station-averaged base stress at each wall's LOWEST
  existing quad row (walls). Peaks still reported alongside.
- Master North Wall mystery solved: not disconnected — it is 1.5 m long
  and its two terrace doors (0.95 + 0.55, h 2.8) cover 100% of its
  length; the element is only the 0.2 m band above glass (base z 2.90).
  u 2.15 axial-basis. FINDING candidate: E062's per-opening ≥1.25 m
  threshold is evaded by ADJACENT openings that jointly span the wall —
  no beam was required, none exists, FEM says the band fails.
- Roof East u 1.69 (strips: 0.76): deck-cantilever hogging continues
  across the shared x=4.3 edge into Roof East (plate continuity between
  separately-modeled roof panels — strips are per-panel and cannot see
  this). Roof West drops 1.95 → 1.21 (two-way action relieves the
  cantilever). Roof South u 1.17 unexplained yet.
- All headline numbers PENDING mesh convergence (attempt 05): singular
  values grow with refinement, real ones stabilize.

## Attempt 05 — 2026-08-08 18:40 (mesh convergence 0.4 / 0.25 / 0.18)
- `compare.py` over the three runs. Balance 1.0000 at every mesh.
  Converged (≤10% drift at refinement): Roof East 1.71 (strip 0.76 —
  UNDER ×2.2), Living East Wall 1.56 (0.25 — UNDER ×6.2), North Wall
  1.32 (0.14 — UNDER ×9.4), Roof West 1.35 (1.95 — strip conservative,
  two-way relief), Ground Slab 0.35, all garage walls ≈ strip values.
- Mildly drifting: Roof South White 1.20→1.35 (11%); Master North Wall
  band 2.15→1.32→1.02 (29% — a 0.2 m band over full-width glass is a
  BEAM, wall axial basis is the wrong ruler; the durable fact is that
  NO beam exists there and every mesh says over capacity).
- Interpretation: strip vs FEM diverges exactly where the panel
  predicted — cross-panel continuity (deck cantilever hogging anchors
  into Roof East across the shared x=4.3 edge) and pier/jamb
  concentrations (E066's documented out-of-scope). Where neither
  applies, the two engines agree (garage walls within ~10%).

## Attempt 06 — 2026-08-08 18:50 (L-view payload + local demo)
- villa_fem.py emits logs/fem-loads-mesh*.json in the walkthrough
  Loads-view schema (u + 8-bucket wall profiles, _assumptions incl.
  solver, mesh, balance).
- make_fem_demo.py assembles a LOCAL demo (scratchpad, production
  output/ untouched): shipped walkthrough.html with the FEM payload
  swapped in (beams keep strip values, bannered), villa.glb copied,
  served on localhost:8787, opened in the owner's browser with
  ?start=1&loads=1. Production pipeline unchanged.

## Attempt 07 — 2026-08-08 19:20 (per-fragment X-ray view)
- Owner: "increase resolution, understand which fragments are stressed."
- villa_fem.py emits per-quad field (logs/fem-field-mesh0.18.json,
  17 352 fragments, u at each quad center); write_xray.py renders them
  as a standalone three.js page (same color ramp as the walkthrough,
  fragments shrunk 6% for visible seams, hover tooltip = element +
  exact %, kind toggles). Served at localhost:8787/xray.html, verified
  (HTTP 200, extracted module passes node --check), opened in browser.
- Banner states beams are NOT in the model yet — bands over beamed
  openings still over-read until beams are meshed (owner has not yet
  ordered that step).

## Attempt 08 — 2026-08-08 19:45 (ring beams meshed into the model)
- Owner go ("yes yes yes"). Beams meshed as deep plate strips with true
  width/depth (incl. upstand above wall top); wall cells inside a beam
  box skipped; beam self-weight added; beam bending harvested by
  integrating horizontal membrane stress over the section per station,
  u vs beam_moment_capacity (same ruler as the strip engine).
- mesh 0.4 → 0.18 with beams (solve 375 s, balance 1.0000 both):
  RB Living Glass W2 1.93→2.15, RB Living Sliding 1.16→1.25 — the two
  beams at the deck corner pick up the cantilever's back-forces the
  strip engine never routed to them (strips: 0.68 / 0.22).
  All other beams relieved as designed: Band N 0.23, Band 0.21,
  Hallway 0.18, Kitchen 0.04, Garage door 0.01.
- Master North band: 0.86 (0.4) → 0.33 avg / 0.69 peak (0.18) — the
  neighbouring ring beam (extends 0.15 m past corners) now bridges the
  band. The VILLA-specific failure softens below capacity; the generic
  validator gap (adjacent openings jointly evade E062's 1.25 m
  threshold with no rule firing) still stands.
- Roof East 1.67 / Roof South 1.36 / Roof West 1.27 / Living East Wall
  1.63 / North Wall 1.31 — stable with beams present; roof findings
  survive.
- xray.html + walkthrough-fem.html regenerated from the 0.18 outputs
  (beams now colored by their own bending utilization), verified 200 +
  node --check, x-ray reopened in browser.
