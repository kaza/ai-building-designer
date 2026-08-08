# FEM X-ray — per-fragment structural utilization

## What it does

Every project gets a second, higher-fidelity structural view: a plate
finite-element model (PyNiteFEA, MIT) built from `building.json` at
build time, whose per-fragment utilization is browsable

- inside the walkthrough: the L key toggles the FEM X-ray (fragments
  over the ghosted building, same color ramp) — owner 2026-08-08
  evening: "we have two different L, we don't need that" — the strip
  engine keeps the validators and the aim+I numbers but has no paint
  mode, and
- as a standalone `xray.html` (orbit camera, hover tooltip = element +
  exact % of capacity, per-kind visibility toggles) published next to
  the walkthrough.

The element Loads view keeps the strip engine's numbers
([structural-plausibility.md](structural-plausibility.md) Phase B);
the X-ray carries the FEM's. Two engines, both labeled with their
assumptions, never blended in one display.

## Why

The strip engine reports one number per element. The FEM oracle
(experiment `2026-08-08_pynite-plate-oracle`) showed what that hides:
cross-panel continuity (villa Roof East 1.67 vs strip 0.76), pier/jamb
concentrations (Living East Wall 1.63 vs 0.25), load routed around
corners into specific beams (RB Living Glass W2 2.15 vs 0.68), and
stress dispersion the owner could finally *see*. Owner (2026-08-08):
"I want to have this as feature for all future projects, and I would
like to see this when I click L."

## Boundaries

- Structural plausibility screening, NOT Eurocode verification. Linear
  static, gravity ULS only (same `DesignBasis` as the strip engine).
  A licensed engineer signs real buildings.
- Axis-aligned geometry only (walls, beams, rectilinear outlines) —
  same constraint the strip engine has. Non-conforming projects fail
  loudly, never approximately.
- Capacity rulers are shared with the strip engine (wall axial with Φ,
  RC bending at ρ, beam section capacity) so utilization differences
  isolate DEMAND modeling.
- Elements the mesher cannot express are reported `unresolved`, never
  guessed — and the X-ray page prints its assumptions (solver, mesh,
  load balance) on screen.
- Design values, not peaks: plate moments are 1 m strip-averaged, wall
  base stress 0.5 m averaged; raw peaks stay in the JSON for audit.
- Wall/beam fragments are colored by the GOVERNING stress component:
  vertical compression against the axial capacity (Φ·f_d), or tensile
  stress (horizontal or vertical) against `DesignBasis.fctd` — concrete
  cracks at a fraction of its crushing strength, and the naked band over
  an opening fails in horizontal tension at its belly, not in
  compression (owner 2026-08-08: the beam-less model looked calm because
  only vertical stress was painted). The tooltip names the component and
  its magnitude in MPa. Per-element wall `u` is max(axial, tension)
  design value; `u_axial`/`u_tension` are reported separately. In-plane
  shear is documented out of scope.

## Components

- `src/archicad_builder/fem/` — mesher (one global snapped control
  grid: wall/beam axes and ends, opening jambs, outline vertices,
  story-global z lines; conforming quads, no hanging nodes), model
  assembly (supports: lowest-storey wall bases clamped, upper wall
  bases clamped only where no storey below, slab-on-grade soil DZ,
  per-node drilling restraint), harvest (design values + per-quad
  field), payload writers.
- CLI: `archicad_builder fem <project>` → `output/fem-field.json`
  (per-quad: kind, element, u, corners) + `output/fem-loads.json`
  (per-element reference results + `_assumptions`; the walkthrough's
  element Loads view stays on the strip engine's loads.json).
- Walkthrough (`make_walkthrough.py` projects): L cycles three states;
  fragment geometry is fetched (SHA-named, immutable-cached, like the
  GLB) — not embedded — with the loading-bar pattern; building→GLB
  coordinate transform documented in the walkthrough spec.
- `publish.py`: uploads `xray.html` + field JSON; project homepage
  links the X-ray.
- Dependency: `PyNiteFEA` (MIT) becomes a project dependency (it was
  experiment-only).

## Decisions

| Date | Decision | Why |
|---|---|---|
| 2026-08-08 | FEM step is part of every project's build (no opt-out flag) | owner: "feature for all future projects"; runtime (seconds–minutes) is build-time only |
| 2026-08-08 | Field JSON fetched, not embedded | villa field is ~2 MB; embedding would double walkthrough.html and break the loading-bar contract |
| 2026-08-08 | Default mesh 0.25 m, benchmarks gate any change | villa converged 0.4→0.18 within ~10% on design values; 0.25 balances fidelity vs solve time |
| 2026-08-08 | Strip engine stays the element Loads view | fast, always available; FEM never silently replaces it (Codex: never combine two models' numbers) |
| 2026-08-08 | No baked textures (option #3) | owner: "I don't want to see this always, only when I care about load" |
| 2026-08-08 | Grounding: only stories at elevation ≤ 0 may ground (wall-base clamps / slab soil), and only where no story below covers the point; stories above 0 must sit on a vertically adjacent story or the preflight fails loudly | plan review (Gemini + Codex #1): "no storey below = ground" would clamp cantilevered upper wings into phantom foundations |
| 2026-08-08 | Everything keyed by element `global_id`; display name + story carried separately | Codex #3: 3apt repeats element names across floors |
| 2026-08-08 | Fifth solver gate: analytic deep-plate beam (station-integrated section moment vs closed form) | Codex #4: beam extraction was the one un-benchmarked path |
| 2026-08-08 | Harvest averages weighted by quad tributary length | Codex #5: refined cells near jambs were over-weighted |
| 2026-08-08 | Load accounting: intended vs attached vs reacted; any dropped load > 1% of intended is a typed error, smaller drops are `unresolved` entries | Codex #6: balance could read 1.000 while silently dropping partition loads |
| 2026-08-08 | Typed preflight (`FemPreflightError`) before meshing + quad-count estimate with configurable ceiling | Codex #7/#8: `assert` vanishes under `-O`; apartment grids can explode |
| 2026-08-08 | Released walkthrough/xray HTML pins exact `fem-field-<sha>.json` (and exact GLB name); webapp serves exact-name assets | Codex #9: pointer-resolved assets can mix two releases |
| 2026-08-08 | Walkthrough uses one enum state machine `setStructuralMode(off\|strip\|fem)`; `?loads=1` maps to `strip`, new `?xray=1` to `fem`; FEM mode raycasts fragments only; field fetch has its own progress + stale-completion guard | Codex #10–12 |
| 2026-08-08 | SUPERSEDED same evening: L is a single toggle `off ↔ fem` — the strip paint mode is gone (`?loads=1` and `?xray=1` both open the X-ray; strip engine keeps validators + aim+I numbers) | owner: "we have two different L, we don't need that, only the second one is needed" |
| 2026-08-08 | Field payload is a versioned envelope (schema, coord system, building digest, assumptions, balance, flat quantized arrays) | Codex #13 + Gemini payload review |
| 2026-08-08 | villa publish gains optional FEM artifacts (both-or-neither, digest-checked against building.json); xray-only publishing for walkthrough-less projects is future work; PyNiteFEA pinned to 3.0.x | Codex #14/#16, CodeRabbit review |
| 2026-08-08 | Tension-aware wall coloring: per-fragment governing component (vert compression vs Φ·f_d; horiz/vert tension vs fctd 1.0 MPa), component + MPa in tooltips; envelope gains parallel `g`/`s` arrays (additive, schema 1) | owner: beams looked useless in the beam-less X-ray because bands fail in bending tension, which wasn't painted |
| 2026-08-08 | Standalone X-ray page carries its view in the URL hash `#v=px,py,pz,tx,ty,tz` (camera + orbit target, `controls.update()` after restore) with the same 1 s throttled `replaceState` writer and a copy-link button; the walkthrough's own hash scheme lives in [browser-walkthrough.md](browser-walkthrough.md) | owner: refresh keeps the view; a link sent to an engineer opens at the sender's exact view |
| 2026-08-08 | Default pytest stays bounded: solver gates + box fixtures on coarse meshes; project-scale solves are pipeline/CI steps, not pytest | Codex #16 |

## Acceptance

- Closed-form benchmarks (simply-supported strip, cantilever, two-span
  continuous, in-plane wall, deep-plate beam extraction) as pytest, ±10%.
- Integration: box fixture solves, load balance within 1%, every
  bearing element mapped.
- villa-maketa and 3apt-corner-core build end-to-end with X-ray
  published; L-cycle verified in the browser at the owner's camera.

## Worked example

villa-maketa: experiment `2026-08-08_pynite-plate-oracle` (findings 1–5
are the feature's origin story; its audit log holds the meshing rules
that survived convergence).

## Related

[structural-plausibility.md](structural-plausibility.md) (strip
engine, DesignBasis) · [browser-walkthrough.md](browser-walkthrough.md)
(L-key modes, payload fetching) ·
[web-deployment.md](web-deployment.md) (publish contract).
