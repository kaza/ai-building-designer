# Arena run 2026-08-13-seismic — brief

Owner commission (2026-08-13): "fix the errors — the building would
collapse under the earthquake — with minimal cost and minimal structural
change; compare the garage-move idea against alternatives." Mechanism:
[specs/design-arena.md](../../../../specs/design-arena.md).

## The problem (baseline numbers, `output/seismic.json` @ main 44afd2a)

Ground Floor, EN 1998-1 lateral force method, ag=0.15g ground B (γI=1.0,
q=1.5 URM — **placeholder site values pending hazard map + geotech**):

| Finding | Number | Meaning |
|---|---|---|
| E100 (x) | capacity **272 kN** vs demand **581 kN** | east-west shear walls shredded by the band windows — gap 309 kN |
| E100 (y) | capacity 652 kN vs 581 kN | ✅ passes — don't break it |
| E102 | e0 = **3.57 m** vs limit 0.30·r = **2.11 m** | torsionally irregular: stiff east side, all-glass west |
| E101 | URM disallowed at ag·S = 0.18g (Table 9.3) | **unwinnable by geometry** — see rule below |

Garage storey is below the seismic base (rigid box) — exempt, leave it
working. Capacity mechanics: per direction, capacity = fvd·Σ(t·L_net)
over **load-bearing** walls within ±15° of that direction; fvd =
200/1.5 kPa; L_net subtracts every opening width. Demand Fb = Sd·W·λ.
e0 = distance from centre of mass to centre of rigidity (t·L_net
stiffness centroid): fix it by adding stiffness on the *soft* side or
rebalancing mass, not by wishing.

## Objectives (lexicographic — order matters)

1. **E100 x-direction clears unwaived** (capacity ≥ 581 kN or demand
   drops to meet capacity), E100 y stays green, **no new unwaived
   findings of any code**.
2. **E102 clears or improves** — report e0 before/after either way.
3. **Cheapest** by the unit rates below.
4. **Smallest structural change** (fewest elements touched).

Hard constraints (violating any = disqualified):
- **Zero floor-area loss**: every Space's area ≥ baseline (thickening a
  wall into a room counts as loss — the referee computes net area from
  slab minus wall footprints, not from your authored polygons).
- **Glazing preserved per room**: total window+glass-door area per room
  ≥ 90% of baseline. Consolidating a band window into taller/narrower
  panes with masonry piers between is legal and encouraged; deleting
  daylight is vandalism.
- **Program intact**: room count/types unchanged, garage still parks a
  car, all door/circulation validators stay green.
- A wall you newly mark `load_bearing` must have real support below
  (wall or footing) — the validators only check the lowest storey, so
  the referee checks this by hand. Free capacity from floating walls is
  the oldest trick in the book and it's a DQ.

## The E101 rule

No geometry can clear E101 at this site under URM — EN 1998-1 Table 9.3
simply has no row for it. Do NOT waste iterations on it. Instead your
proposal MUST include a **structure-type recommendation** (confined
masonry tie-columns / RC wall conversion — where, how many, why) with a
cost allowance at the rates below, clearly labelled "not yet modelled —
framework gains structure-type presets next". E100/E102 are the
numeric competition; E101 is the essay question.

## Frozen surfaces (any diff = disqualified)

You may edit ONLY `projects/villa-maketa/build.py` and
`projects/villa-maketa/furniture.json`. Never touch: `validation.json`,
`project.toml`, `pipeline.toml`, anything under `src/`, `specs/`,
`tests/`, or other projects. Never run `publish`. Never touch files
outside your own worktree.

## Unit rates (owner-approved approximation, ±50% — ordinal, not a quote)

| Item | Rate |
|---|---|
| Demolish wall (any) | €25 /m² face |
| New URM wall (25 cm, incl. plaster) | €55 /m² face |
| New RC wall (20 cm, incl. formwork + rebar) | €120 /m² face |
| Wall thickening (per +10 cm layer) | €45 /m² face |
| Concrete in place (footings, beams, misc.) | €350 /m³ |
| Steel section installed | €4.5 /kg |
| RC tie-column 25×25 (confined masonry) | €90 /m height |
| Window/glazing removed, moved or reworked | €300 /m² glazing |
| New strip footing | €280 /m³ |
| Garage relocation earthworks/access lump | €3,000 |
| Site overhead on everything above | +15% |

## Loop budget and commands

Max **12 inner evaluations**, then stop and submit best-so-far honestly.
Inner loop (from your worktree root, ALWAYS `.venv/bin/python` — never
the system python, never another checkout's venv):

    cd projects/villa-maketa && ../../.venv/bin/python build.py && cd ../..
    .venv/bin/python -m archicad_builder validate villa-maketa --strict
    .venv/bin/python -m archicad_builder seismic villa-maketa
    # then read projects/villa-maketa/output/seismic.json

Commit every improving iteration:
`git commit -am "<move>: x-capacity 272→431 kN, e0 3.57→2.9"`.
When done (green or budget out): run the full pipeline
`.venv/bin/python -m archicad_builder pipeline villa-maketa` (fem
profile default, ~2 min), fix anything it surfaces if cheap, write
`projects/villa-maketa/arena/2026-08-13-seismic/proposal-<lane>.md`,
commit, and `git push -u origin <your branch>`.

## proposal-<lane>.md format (the owner reads this in 5 minutes)

1. **Metrics line**: `E100x 272→? /581 kN · E100y ? · e0 3.57→? m ·
   area Δ ? m² · glazing Δ ? % · elements touched ? · cost ~€?`
2. **The story** (one paragraph, architect language, name walls by their
   build.py names and the A/B/C × 1–4 axis grid where useful).
3. **Cost table** (quantities × rates from above, itemised).
4. **E101 recommendation** (structure-type essay + allowance).
5. **What the engineer must verify** (honesty section) and what you
   tried that failed (one line each — the lab notebook is the branch).
