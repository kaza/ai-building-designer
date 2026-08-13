# Proposal — lane g-value: the value king already clears the new gate

**Headline: €4,650 total — €0 delta on the inherited genome — and the
margin audit that proves every cheaper variant fails and every
margin-buying variant costs triple.**

**Metrics line**: `E100x 618.3 / 608.2 kN ✓ · E100y 651.6 / 608.2 ✓ ·
e0 0.33 m (limit 1.94) — E102 clear both directions · structure
urm, q_eff = 1.5 (confined preset audited and REJECTED, see below) ·
red elements 10 → 0, worst element 0.893 (East Wall ULS) ·
area Δ 0.00 m² · glazing Δ −3.3 % total, worst room 92 % (inherited) ·
elements touched by this lane: 0 · cost €4,650 inherited (c-torsion) +
€0 delta`

`validate --strict` exit 0. Full pipeline green. Referee-recomputed
numbers under the round-2 framework (c6bd2fd) reproduce round 1
exactly: V = 608.2 kN, x-capacity 618.3, y 651.6.

## Credit where due

Everything structural in this design is **inherited from round 1's
c-torsion** (€4,650): Kitchen Window consolidated to 0.9×1.15, Win7
band → masonry with Win2 deepened to sill 1.80, Room 2 south walls
made load-bearing on the Garage North Wall, and the 2.8×0.5 m stone
Deck Windbreak Wall at y=12.3 under the Roof West edge.

**This lane's delta is the audit, not a wall.** The finding: those
four moves, made to kill torsion and clear E100x, *already* satisfy
round 2's any-collapse gate — because the plate FEM treats every
load-bearing wall under a roof as a support line, so the same walls
that moved the centre of rigidity also cut the roof spans and drained
the tension fields out of the ULS-red walls. Zero red elements, no
further money needed.

## Red elements before → after (the round-2 gate)

| Element | Baseline u (combo) | Now u (combo) | Fixed by (inherited) |
|---|---|---|---|
| Roof East | 1.76 (ULS) | 0.30 (ULS) | Room 2 south walls bearing → mid-plan support line |
| North Wall | 1.68 (ULS) | 0.31 (SEIS_X−) | roof load-path relief via new support lines |
| West Wall South | 1.61 (ULS) | 0.36 (SEIS_Y+) | same |
| West Wall | 1.60 (ULS) | 0.83 (ULS) | Win2 band re-cut (sill 1.80) + load path |
| Living East Wall | 1.51 (ULS) | 0.58 (SEIS_Y−) | same |
| Roof West | 1.41 (ULS) | 0.43 (ULS) | Deck Windbreak Wall under the north strip edge |
| Master North Wall | 1.40 (ULS) | 0.11 (SEIS_X−) | roof span relief |
| Room 2 West Wall | 1.33 (ULS) | 0.38 (SEIS_Y−) | Room 2 south walls bearing |
| South Wall | 1.24 (SEIS_X−) | 0.49 (SEIS_X+) | Kitchen Window consolidation (+0.6 m shear length) |
| Roof South White | 1.19 (ULS) | 0.32 (ULS) | load-path redistribution |

Worst element anywhere, any combo: **East Wall 0.893 (ULS)** — 11 %
headroom. All four SEIS combos peak at Room 2 South Wall East 0.69.

## The confined-masonry audit (why q = 2.0 is not the value play)

Declared `[structure] type = "confined"` as a probe and read the
fail-closed evidence list: **57 confinement failures**, deduplicating
(one tie can serve a free end + an intersection + a spacing cut) to
**≈ 40 tie-columns** — ≈ 9 in the garage (2.89 m) and ≈ 31 on the
ground floor (3.0 m), driven by the checker's real demands: jambs at
every opening > 1.5 m² (this villa is *made* of big glass), free ends,
every bearing-wall intersection, ≤ 5 m spacing.

| Confined route | € |
|---|---|
| ~40 tie-columns 25×25, ~118 m total | ≈ 10,600 |
| Ring-beam allowance, ~75 m of confined wall × €35 | ≈ 2,600 |
| +15 % overhead | ≈ 2,000 |
| **Total delta** | **≈ €15,200** |

What it buys: seismic demand 608 → 456 kN (−25 %). What it does NOT
buy: anything the gate scores — the red list above was ULS-governed,
and q touches only the SEIS combos. What it could delete: at most the
windbreak wall (≈ €1,700 of the €4,650) — and even that fails, because
the windbreak is the torsion fix (e0 0.33 → ~3.5 without it, E102
regression) *and* the Roof West support. Net: spend ≈ €15k to un-spend
≤ €0. Rejected. (E101 therefore stays waived per the brief; under URM
there is no Table 9.3 row to clear — density 2.8 % / 2.95 % is stated
for the record, vs the confined row's 3.5 % it also would not clear.)

Probe reverted; `project.toml` is untouched in this submission.

## Why nothing is deletable (the cheaper-variant audit)

The x margin is 10.1 kN. Every inherited item's E100x contribution
(t·L_net × fvd ≈ 135 kN/m²):

| Deletion candidate | Saves € | Costs kN | Result |
|---|---|---|---|
| Windbreak 0.5 → 0.45 m thin | ≈ 190 | −19 | 599 < 608 ✗ (also E102) |
| Kitchen Window back to 1.5×0.75 | ≈ 480 | −20 | 598 < 608 ✗ |
| Win7 band restored (glass) | ≈ 1,530 | −95 | ✗, e0 regresses too |
| Room 2 walls back to non-bearing | ≈ 200 | −42 | ✗, Roof East/Room 2 W reds return |

The inherited genome is pareto-minimal: every euro in it is
load-bearing. The margin is thin (1.66 %) but **deterministic** — the
referee recomputes the same framework on the same geometry; this is a
stopwatch, not a dice roll. This lane re-ran the full chain on the
round-2 framework to prove it: identical to the tenth of a kN.

## Detailing list (corner hot-spots — reported, not gated)

Per the brief, mesh-singularity peaks at opening corners
(`u_peak`, element u stays green):

1. **West Wall, peak 1.54 (ULS)** — Win2/Win3 shared jamb corner.
   Detailing: bed-joint reinforcement or a lintel extension at the
   glass-to-glass corner; the element field is 0.83.
2. **East Wall, peak 1.10 (ULS)** — Hallway Window jamb. Standard
   lintel bearing extension; element field 0.89.
3. Watch item below threshold: Deck Windbreak Wall peak 0.98 (SEIS_X−)
   at the roof-edge shear tie — confirms round 1's demand that the tie
   detail be engineered (angle + anchors are priced in the inherited
   table).

These are the same "2 corner hot-spots" flagged on c-torsion in round
1, now quantified.

## Cost table

Inherited (c-torsion, round 1 — unchanged):

| Item | € |
|---|---|
| Glazing rework 6.24 m² × €300 | 1,872 |
| Masonry infill (Win7 slot + kitchen band) | 143 |
| Demolition (Win2 sill deepening) | 21 |
| Deck Windbreak Wall URM + thickening to 0.5 m | 1,407 |
| Strip footing 1.12 m³ × €280 | 314 |
| Roof-edge shear tie ~20 kg × €4.5 | 90 |
| Room 2 shear ties / masonry verification | 200 |
| Overhead +15 % | 607 |
| **Inherited total** | **4,654** |
| **Lane g-value delta** | **0** |
| **Total** | **≈ €4,650** |

## Hard constraints (round-1 set, unchanged)

Zero net floor-area loss (no interior wall moved), per-room glazing ≥
90 % (worst 92 %, Kitchen), rooms/program intact, Room 2 south bearing
walls sit on the Garage North Wall, garage parks the car (untouched).

## What the engineer must verify

Unchanged from the inherited round-1 list: the 12 cm Room 2 partitions
as shear walls (EN 1998-1 9.5.1 minimum thickness — the one signature
this package needs), windbreak overturning/sliding + footing interface,
roof-edge tie detail, and the placeholder site values (ag 0.15 g,
ground B, σ_rd 200 kPa). If the hazard map comes back worse than the
placeholder, the confined audit above is the priced fallback — €15.2k
buys 25 % demand relief with the tie layout already enumerated by the
evidence checker (57-item list in this round's probe).
