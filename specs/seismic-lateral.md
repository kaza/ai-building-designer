# Feature: Seismic lateral system — ELF plausibility + FEM lateral cases

## Status

Spec'd 2026-08-10, owner commissioned S1–S4 in one go ("this is supposed
to be a real deal"). This spec covers S1 (geometry + equivalent-lateral-
force validators) and S2 (FEM lateral load cases). S3 is
[foundations.md](foundations.md), S4 is
[engineer-handoff.md](engineer-handoff.md).

## Why this exists

Everything structural in the model pushes DOWN. An earthquake pushes
SIDEWAYS, proportional to mass, and a wall resists it only in its own
plane — which is why real seismic design starts from a two-direction
grid of walls (the owner's architect collaborator built exactly such a
grid). The X-ray's `not_modelled` list names seismic as its first
exclusion; the owner wants the model to carry the lateral system and
surface its sins (torsion, discontinuity, thin wall density) before a
civil engineer ever opens the file. Mission framing: the output is
**building-ready subject to engineer sign-off** — see README mission
statement.

## Design basis (assumptions, all overridable)

- Framework: **Eurocode 8** (EN 1998-1), lateral force method
  (§4.3.3.2). No modal/response-spectrum analysis: `T1 = Ct·H^(3/4)`
  (§4.3.3.2.2), valid for buildings ≤ 40 m — every project this tool
  builds today.
- Structure type: default **unreinforced masonry bearing walls + RC
  ring beams + RC slabs** (EN 1998-1 §9), behavior factor `q = 1.5`;
  configurable per project via the `[structure]` preset (§Structure
  presets below, 2026-08-13) — confined masonry swaps q and the
  density-table row, gated on tie-column evidence. Owner 2026-08-10:
  pick the best assumption, assume change later — the change arrived.
- Country support: **BA / DE / AT** — all EC8; only National-Annex
  parameters differ. Modeled as data (per-country spectrum-type
  default + ground-type table), never code branches. `ag` is always a
  per-project input read off the national hazard map — the model has
  no map.
- Seismic mass: `G + ψE·Q` with `ψE = φ·ψ2`, `ψ2 = 0.3` (residential),
  `φ = 1.0` for the top storey and `0.5` below (EN 1998-1 §4.2.4).

## What it does

1. **`[site]` config** (project.toml, strict schema): `country`
   (`"BA"|"DE"|"AT"`), `ag` (units of g, from the national annex map),
   `ground_type` (`"A".."E"`), `importance_class` (default II →
   `γI = 1.0`), optional `spectrum_type` (default: BA→1, DE→2, AT→1).
   No `[site]` → seismic checks report `unresolved`, never guess and
   never error (same contract as undeclared `span_direction`).
2. **`SeismicBasis`** (dataclass beside `DesignBasis`): q, ψ2, φ
   rules, Ct, λ, masonry density, `fvk0` (kPa), `γM`, per-ground-type
   spectrum table (S, TB, TC, TD for spectrum types 1 and 2), wall
   density minimum table. All published in `_assumptions` and the
   handoff report.
3. **ELF computation** (`seismic.py`): per-storey seismic mass from
   element geometry (walls, slabs, roofs, finishes, ψE·live),
   `Sd(T1)` per EN 1998-1 §3.2.2.5 (with `β = 0.2` floor),
   `Fb = Sd(T1)·m·λ` (`λ = 0.85` if MORE than two storeys and
   `T1 ≤ 2·TC`, else 1.0 — EN 1998-1 §4.3.3.2.2), storey forces
   `Fi = Fb·zi·mi / Σ zj·mj`.
4. **E100 — base shear exceeds wall shear capacity** (error, per
   direction): capacity = Σ over load-bearing walls aligned (±15°)
   with the direction of `fvd·t·L`, `fvd = fvk0/γM` — the compression
   benefit (`0.4·σd`) is deliberately dropped (conservative; logged).
   Openings reduce L to net wall length (opening widths subtracted).
5. **E101 — wall density below minimum** (error, per storey and
   direction): `Σ t·L_net / floor area` vs the minimum from the
   density table (keyed by `ag·S` band and storey count — EN 1998-1
   Table 9.3 recommended values, marked as NA-overridable).
6. **E102 — torsional irregularity** (warning): per storey, center of
   mass vs center of lateral stiffness (squat-wall shear stiffness
   `k ∝ G·t·L_net/h`), structural eccentricity `e0 ≤ 0.30·r` and
   torsional radius `r ≥ ls` (EN 1998-1 §4.2.3.2); `ls` from the plan
   bounding box. Warning, not error: an irregular building may still
   be designed, it just loses the simplified analysis privileges.
7. **E103 — lateral discontinuity** (error): every load-bearing wall
   on a storey above the lowest must be carried by an aligned bearing
   wall below (reuses the strip engine's alignment rule). A wall that
   lands on a cantilever/console is exactly this error — the owner's
   two consoles are the motivating case. Waivable per element with a
   reason, like every other code.
8. **S2 — FEM lateral cases**: load application refactors from one
   pre-factored case `"U"` to unfactored cases `G` (dead), `Q`
   (live), `EQX`, `EQY`; combos `ULS = 1.35G + 1.5Q` (identical
   results to today — regression-gated) and `SEIS_X± / SEIS_Y± =
   G + ψE·Q ± EQ`. Lateral nodal forces: each node's tributary
   gravity weight within its storey, scaled so the storey sums to
   `Fi`, applied as FX/FY. Torsional accidental eccentricity via the
   simplified amplification `δ = 1 + 0.6·x/Le` (EN 1998-1
   §4.3.3.2.4) on nodal forces.
9. **Envelope harvest**: the fragment field publishes the worst
   utilization across combos plus the governing combo per quad;
   tooltips and element panels name the combo (`"SEIS_X+"`). The
   ELEMENT results (`fem-loads.json`) keep per-combo design values so
   an engineer can isolate which combination drives a number —
   enveloping only the (large) field payload, never the diagnostics
   (Gemini plan review). The X-ray stays ONE view — no second toggle
   (owner precedent: "two different L, we don't need that").
10. **Support recipe audit**: lateral response must not be shorted by
    the gravity-era restraints. A cantilever-shear-wall benchmark
    (closed-form tip deflection + base shear stress) joins the solver
    gates before any project solve is trusted.

## Structure presets and wall materials (2026-08-13)

The "changing type later = swapping SeismicBasis numbers" promise from
the design basis comes due: the architect's strengthening scheme
(confined masonry, [columns.md](columns.md)) is inexpressible while
`q = 1.5` URM is hardcoded.

1. **`[structure]` config** (project.toml, strict schema):
   `type = "urm" | "confined"` (default `"urm"` — absent block means
   today's behaviour, byte-identical). The preset swaps, as data:
   `q` (URM 1.5 → confined 2.0, EN 1998-1 Table 9.1), and the
   Table 9.3 wall-density row for the matching system. Values enter
   the code ONLY as verified quotes from the standard (same provenance
   rule as the existing URM row — never from memory).
2. **Confinement evidence is fail-closed and non-waivable in the
   numbers** (Codex blocker, accepted): `compute_seismic` derives an
   `effective_structure_type` itself — declared `"confined"` earns
   `q = 2.0` and the confined table row ONLY if the geometric
   eligibility evidence passes *inside the computation*. Evidence
   failing ⇒ the numbers fall back to URM (q = 1.5, URM row) AND
   **E109** findings name every missing tie-column location. Waiving
   E109 documents a disagreement; it never unlocks the reward —
   waivers gate findings, not physics. Evidence rules (quoted EN
   1998-1 §9.5.3, grounded 2026-08-13): RC tie-columns
   ([columns.md](columns.md), tie role only — steel never counts) at
   every wall intersection (where >1.5 m from the nearest confining
   element), at the free edges of every load-bearing wall, at both
   sides of openings > 1.5 m², spacing ≤ 5 m, each section side
   ≥ 150 mm, full storey height. The check is named **"geometric
   eligibility evidence"** — reinforcement, stirrups, anchorage and
   casting sequence are the engineer's, and the report says so.
   Ring beams remain the declared assumption they have been since S1
   (printed in `_assumptions`), not modelled elements.
3. **q honesty for irregular buildings** (Codex): EN 1998-1 §9.3(5)
   cuts q by 20% (floor 1.5) for elevation-irregular buildings. We
   cannot run the full §4.2.3.3 assessment; proxy: any unwaived E103
   discontinuity ⇒ `q_eff = max(1.5, 0.8·q)`, and elevation
   regularity is printed as an assumption the engineer confirms.
   Table 9.3 band edges are strict `<` (the existing `<=`+epsilon
   selects the lenient column at exact boundaries — fix with a
   regression test); the confined table starts at 2 storeys — a
   1-storey confined building gets the "simple rules not applicable,
   explicit analysis required" wording, never an invented row.
4. **Per-wall material — data only in C1** (Codex high, accepted):
   `Wall.material = "masonry" (default) | "rc"` flows to IFC
   (`IfcMaterial`), metadata extras (`ab_material`), the X-ray palette
   (concrete walls join the skeleton family, [columns.md](columns.md))
   and the report — but contributes **zero capacity or stiffness
   change**: an RC wall counts at masonry `fvd` (conservative,
   printed). The EC2-based capacity constant is DEFERRED — a flat
   positive constant is a relabel-for-free-capacity hack; it returns
   only with a bounded design domain (thickness, concrete grade,
   reinforcement floor) modelled. Uniform shear modulus in E102
   stiffness stays, printed as an assumption.
5. **Reporting**: `_assumptions` and the engineer report print the
   declared type, the EFFECTIVE type (with the fallback reason when
   they differ), q and q_eff, the density-table row in force, and the
   per-wall material split — a reviewer's first question is "what did
   you assume", so the assumption is never implicit.

## Boundaries

- Plausibility screening, NOT EN 1998 compliance. No ductility
  detailing, no capacity design, no confinement checks, no
  reinforcement. A licensed engineer signs real buildings — by
  mission statement, that sentence appears on every output.
- Lateral force method only. If `T1 > 2·TC` or > 40 m the method's
  own applicability limit is violated → typed `unresolved`, never a
  silent wrong answer.
- Masonry shear capacity ignores axial pre-compression (conservative)
  and diaphragm flexibility (slabs assumed rigid in plane — true for
  RC slabs, printed as an assumption).
- Out-of-plane wall bending under seismic stays DEFERRED (same
  reasoning as fem-xray.md: needs eccentric wall loads first).
- No wind. Wind governs over seismic in most of Germany; the report
  says so explicitly (`not_modelled`) so a calm seismic check is
  never read as lateral adequacy.
- Germany's National Annex (DIN EN 1998-1/NA) defines its OWN spectral
  shapes and soil classes (R/T/S, not A–E). `DE → Type 2` is a
  documented low-seismicity approximation, printed in the report and
  in `_assumptions` — never presented as the German NA (Gemini plan
  review 2026-08-10).
- Vertical seismic component (relevant to the consoles in high
  seismicity, EN 1998-1 §4.3.3.5.2) is NOT computed in S1/S2 — the
  handoff report flags cantilevers > 1 m as "vertical component to be
  verified by the engineer" instead of pretending.
- E100/E101 evaluate per storey using the shear at that storey
  (Σ Fi above), not just the base.

## Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-08-10 | Mission statement: building-ready **with civil engineer validation** | owner: "clearly implied in everything we are doing that someone will verify and sign off" — the tool optimizes for perfect verifiability, not for skipping the engineer |
| 2026-08-10 | Structure type assumed URM + RC ring beams, q = 1.5 | matches what the schema already models; owner: pick best assumption, changing later is a config swap, not a rewrite |
| 2026-08-10 | Multi-country = National-Annex parameter data, single EC8 code path | BA/DE/AT are all Eurocode 8; hard-coding one country's numbers would make the other two a fork |
| 2026-08-10 | ELF only, no eigen solve | 2-storey villas are the product; T1 formula is within EC8's own applicability, and PyNite modal analysis is an unproven dependency |
| 2026-08-10 | fvd = fvk0/γM, no 0.4·σd term | conservative and needs no load coupling in S1; the FEM (S2) captures the real interaction |
| 2026-08-10 | E102 torsion is a warning, E100/E101/E103 are errors | irregularity is a design constraint; missing shear capacity or a discontinuous wall is a building that falls down |
| 2026-08-10 | FEM refactors to unfactored G/Q cases + combo table | seismic combos need γ = 1.0 gravity; pre-factored loads can't be re-combined. ULS regression-gated to prove nothing moved |
| 2026-08-13 | `[structure]` presets (urm/confined) as data; default absent = urm | the promised config swap, triggered by the architect's confined-masonry grid; owner: "lets do it" |
| 2026-08-13 | Confined credit derived fail-closed INSIDE compute_seismic (effective type), never via waivable validation | Codex blocker: an E109-as-error is waivable and fires after q was already selected; physics must not be unlockable by waiver — its whole cheat catalogue dies at this root |
| 2026-08-13 | Per-wall material is data-only in C1; RC capacity constant deferred | Codex: a flat positive constant = relabel-for-free-capacity hack; conservative fallback (masonry fvd) costs nothing today |
| 2026-08-13 | q_eff = max(1.5, 0.8·q) when unwaived E103 exists; strict `<` band edges | EN 1998-1 §9.3(5) and Table 9.3 as quoted; E103 is a proxy, printed as an assumption |
| 2026-08-13 | Tie-column evidence: intersections + free edges + openings >1.5 m² + ≤5 m spacing + ≥150 mm sides (quoted §9.5.3) | Gemini flagged the missing intersections; grounded search quoted the clause (5 m, not Gemini's remembered 4) — quotes beat memory, both reviewers' numbers checked |

## Acceptance

- Closed-form pytest gates: Sd(T) spectrum values against hand-computed
  EC8 numbers (all four branches), base shear + storey distribution on
  a synthetic 2-storey box, cantilever shear wall FEM benchmark ±10%.
- E100–E103 unit tests per the validator test pattern (one file per
  code family, synthetic buildings, no project data).
- ULS regression: villa FEM design values unchanged (< 0.1%) after the
  load-case refactor.
- villa-maketa builds end-to-end with `[site]` set and seismic checks
  running in `validate`.

## Related

[structural-plausibility.md](structural-plausibility.md) (strip
engine, DesignBasis) · [fem-xray.md](fem-xray.md) (FEM,
`not_modelled` contract) · [foundations.md](foundations.md) (S3) ·
[engineer-handoff.md](engineer-handoff.md) (S4) ·
[validation-waivers.md](validation-waivers.md) (waiver mechanics) ·
projects/villa-maketa/spec.md (worked example, Bosnia site params).
