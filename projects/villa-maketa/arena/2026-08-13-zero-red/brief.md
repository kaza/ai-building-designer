# Arena round 2: zero-red — brief

Owner amendment (2026-08-13): *"the problem is ANY collapse"*. Round 1
cleared the earthquake shear error; this round the winning gate is the
whole building: **no element over capacity under any load combination**
— walk the load view's worst-case stop and find nothing red.

Mechanism: [specs/design-arena.md](../../../../specs/design-arena.md).
Round-1 record: [../2026-08-13-seismic/brief.md](../2026-08-13-seismic/brief.md).

## New powers since round 1 (framework @ c6bd2fd)

1. **Columns exist** (specs/columns.md). Tie-column (confinement):
   `b.add_column(GF, wall="<wall name>", along=<center dist from wall
   start>, width=0.25, depth=0.25, material="rc", name="Tie A2")` —
   rc only, each side ≥ 0.15 m, full storey height, orientation from
   the host wall. Free post: `b.add_column(GF, at=(x, y), width=0.3,
   depth=0.3, material="rc"|"steel", name="...")` — never counts for
   confinement.
2. **Confined masonry preset**. `project.toml` may gain:
   ```toml
   [structure]
   type = "confined"
   ```
   Declaring it earns **q = 2.0 (−25% earthquake demand)** ONLY if the
   geometry passes the fail-closed evidence check inside the seismic
   engine: rc tie-columns at every load-bearing wall intersection
   (>1.5 m from the nearest tie), at the free ends of every bearing
   wall, at both sides of openings > 1.5 m², spacing ≤ 5 m along
   every bearing wall. Failures are listed in
   `output/seismic.json → confinement_failures` (your gradient: place
   columns until the list is empty) and as E109 findings. Cheating is
   pointless — the numbers fall back to unreinforced masonry q = 1.5
   automatically.
3. **Frozen-file rule is now path-precise**: `project.toml [structure]`
   is EDITABLE; `[site]` (and everything else frozen in round 1)
   remains frozen. The referee diffs the toml and disqualifies any
   change outside `[structure]`.
4. `Wall.material = "rc"` exists but is data-only (no capacity bonus
   this round) — declare it where the design intends concrete; it
   renders in the skeleton palette and prints in the report.

## Round-1 results (your starting knowledge — read the proposals)

| Lane | Cost | E100x | e0 | Red elements | Verdict |
|---|---|---|---|---|---|
| c-torsion | €4,650 | 618/608 | 0.33 | 0 | value king; 2 corner hot-spots left |
| b-garage | €9,300 | 708/642 | 1.18 | 0 | all-green; terrace-fin connection peaks 210% |
| e-wildcard | €6,300 | 632/609 | 0.38 | 1 (Roof West ULS) | wing-wall idea proven |
| a-surgeon | €9,810 | 698/654 | 1.76 | 2 | opening consolidation maxes at ~467 kN alone |
| d-cost | €3,081 | 654/615 | 2.46 | 4, one REGRESSION | cheap by breaking the East Wall — do not repeat |

Proposals + full stories: `../2026-08-13-seismic/proposal-*.md` (on the
round-1 branches; summaries above suffice). Lessons that transfer:
demand rises with added mass (walls you add tax you), the y-direction
margin is thin (~70 kN), corner tiles at openings are detailing (not
gated), element-level red IS gated.

## The gate (lexicographic, referee-recomputed)

1. `validate --strict` exit 0 — E100 both directions, zero new
   findings. E101: waived unless you genuinely clear the confined
   Table 9.3 row (3.5% density at 0.18g — hard; clearing it and
   retiring the waiver is a headline, not a requirement. If you adopt
   the confined preset honestly state density vs 3.5%).
2. **ZERO red elements**: every element's design utilization ≤ 1.00 in
   `output/fem-loads.json` across ULS and all four SEIS combos —
   including the baseline's old roof/wall reds (Roof East 1.76, Roof
   West 1.41, North Wall 1.68, West Wall 1.60/1.61, Living East 1.51,
   Master North 1.40, Room 2 West 1.33, Roof South White 1.19, South
   Wall 1.24 SEIS). These are now YOUR problem: roof reds respond to
   span-shortening (bearing walls/supports under them), section, or
   load-path changes; wall reds to the same moves that fixed round 1.
3. E102 torsion: clear or quantified improvement.
4. Cheapest (rates below), then fewest elements touched.
5. Hard constraints unchanged from round 1: zero net floor-area loss
   (referee computes slab − wall footprints), per-room glazing ≥ 90%
   of baseline, rooms/program intact, new bearing walls supported
   below, garage parks a car.

Corner-tile peaks (mesh singularities at openings) are REPORTED as the
detailing list, not gated — but a NEW element whose connection peaks
absurdly (round 1's 310% shear skin) will be named in the referee table.

## Unit rates (owner-approved approximation, ±50% — ordinal)

Round-1 table plus:

| Item | Rate |
|---|---|
| RC tie-column 25×25 incl. rebar, cast in wall | €90 /m height |
| RC tie-column 60×20 (the architect's 2A stub) | €130 /m height |
| Steel post installed (HEA-ish) | €4.5 /kg (≈ €350 for 3 m of HEA140) |
| Ring-beam upgrade allowance (if you claim confined) | €35 /m of confined wall |
| All round-1 rates | unchanged (demolish €25/m², URM wall €55/m², RC wall €120/m², thickening €45/m²/10cm, concrete €350/m³, glazing rework €300/m², footing €280/m³, +15% overhead |

## Loop and submission

Max **15 evaluations** (roof physics needs the FEM: after big moves run
`.venv/bin/python -m archicad_builder fem villa-maketa` (~2 min) and
read `fem-loads.json`, not just seismic.json). Commit improving
iterations with numbers. Finish: full pipeline green, write
`projects/villa-maketa/arena/2026-08-13-zero-red/proposal-<lane>.md`
(round-1 format + a "red elements before→after" table + the detailing
list), push your branch.
