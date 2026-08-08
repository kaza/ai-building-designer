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
   ≥1.25 m beam requirement but jointly glass out 100% of the wall; the
   remaining 0.2 m band over them is over capacity at every mesh
   (1.02–2.15, attempt 04–05). Promotable: E062 should merge openings
   separated by less than ~a pier width into one effective opening —
   same class of shipped error the original takedown caught for single
   openings.

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
