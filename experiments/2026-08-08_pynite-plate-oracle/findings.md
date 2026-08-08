# Findings — PyNite plate oracle (2026-08-08)

1. **A real FEM oracle is buildable from building.json alone.** Walls
   and slabs as conforming quads on one snapped control grid (all wall
   axes / jambs / outline vertices; story-global z lines), drilling
   DOFs restrained per node, garage-void-aware supports: 4/4 closed-form
   benchmarks within ±10% (11/13 checks within 1%), villa load balance
   exactly 1.0000 at every mesh, 22 s (0.4 m) to ~5 min (0.18 m)
   (attempts 01–03, 05). PyNiteFEA 3.0.0, MIT, pip — viable as a
   validation oracle. The panel's warning held: every wrong number along
   the way was meshing/extraction, never the solver.

2. **E062 is evaded by adjacent openings.** Master North Wall (1.5 m)
   carries two terrace doors (0.95 + 0.55 m) that individually duck the
   ≥1.25 m beam requirement but jointly glass out 100% of the wall — no
   rule fires, no beam exists. Without beams in the model the naked
   0.2 m band reads over capacity at every mesh (1.02–2.15, attempts
   04–05); with the real ring beams meshed (attempt 08) the neighbouring
   beam's corner extension bridges it down to 0.33 avg / 0.69 peak — so
   THIS villa survives by an accident of an adjacent beam, not by
   design. Promotable: E062 should merge openings separated by less
   than ~a pier width into one effective opening.

5. **The deck cantilever loads the corner beams, not just the roof.**
   With beams meshed (attempt 08, converged 0.4→0.18): RB Living Glass
   W2 at 2.15 and RB Living Sliding Window at 1.25 — the cantilever's
   back-forces anchor into the two beams at the deck corner. The strip
   engine rated them 0.68/0.22 because per-panel strips never route
   roof forces around a corner. Every other beam is relieved as
   designed (0.01–0.23). Any fix for the deck (columns / shorter roof /
   thicker edge) must re-check these two members.

3. **Per-panel strips understate moments where panels are continuous.**
   The deck cantilever's hogging anchors across the shared Roof West /
   Roof East edge: FEM says Roof East 1.71 vs strip 0.76 (UNDER ×2.2,
   converged, attempt 05); Roof South shows the same effect (≥1.2 vs
   0.76). Conversely two-way action relieves the cantilever itself:
   Roof West 1.35 vs strip 1.95. The strip engine treats each roof
   polygon as an island; the real roof is one continuous plate. Phase C
   continuous-strip work must either join coplanar adjoining panels or
   keep this FEM as the check that catches it.

4. **Pier/jamb concentrations are real and measurable.** Walls hosting
   the wide openings concentrate base stress far above the whole-wall
   average the strip engine reports: North Wall 1.32 vs 0.14, Living
   East Wall 1.56 vs 0.25 (converged, attempt 05). E066's gross-average
   basis is fine for solid walls (garage walls agree within ~10%) and
   misleading for punched ones — the documented "jamb concentrations
   out of scope" is now a quantified gap, not a footnote.
