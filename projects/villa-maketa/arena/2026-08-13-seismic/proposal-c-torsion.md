# Proposal — lane c-torsion: kill the twist, clear the shear

**Metrics line**: `E100x 272→618 /608 kN (demand 581→608, new wall's own
mass) · E100y 652 kN vs 608 ✓ · e0 3.57→0.33 m (limit 0.3r = 1.94) ·
e0y 1.08→1.16 vs 1.89, r_y 4.56→6.31 ≥ ls 4.88 — E102 cleared in BOTH
directions · area Δ 0.00 m² · glazing Δ −3.3% total (worst room 92%) ·
elements touched 6 · cost ~€4,700`

`validate --strict` exit 0. 0 errors, 0 warnings — the torsion warning
didn't just improve, it's gone, and so is the y-direction one nobody
was talking about (it was irregular via r < ls at baseline).

## The story

The villa's x-direction shear lived almost entirely on the y=0 line —
the centre of rigidity sat at y≈2.3 while the mass sits at y≈5.9. The
fix is symmetric to the diagnosis: put stiffness where the glass is.
Three cheap consolidations and one honest new wall:

1. **Living North Wall (y=8)** — the only x-bearing wall at mid-plan had
   *zero* net length. The 2.35 m clerestory band over the solid TV half
   (`Living Band Window N`) becomes masonry; its daylight moves into
   `Living Band Window` on the west facade, deepened to sill 1.80 — the
   owner's original dictation (the built 2.05 was a build choice).
   Living keeps 94% of its glazing; the pool view through the big
   slider is untouched.
2. **Room 2 south walls (y=8)** — `Room 2 South Wall West/East` stand
   exactly on the Garage North Wall. Counting them as shear walls costs
   a masonry spec and a shear tie, not new structure.
3. **Kitchen Window (y=0)** — the 1.5 m band becomes a 0.9×1.15 pane
   (92% of glazing area), returning 0.6 m of the South Wall to shear.
4. **Deck Windbreak Wall** — new 2.8×0.5 m stone wall at y=12.3,
   x1.7–4.5, under the floating Roof West edge. It is placed *in front
   of the solid half of the living facade*: the slider ends at x=2.15,
   so the living room still looks straight at the pool. It runs
   parallel to the roof span, so it carries no gravity — detailed
   gravity-released and shear-tied to the roof edge, which is the
   E065 "columns at the deck edge" option upgraded to a wall that also
   ends the torsion problem. Stone rubble to match the deck screen.

Net effect: CoR moves from y=2.29 to y=6.48 vs CoM y=6.15 — e0 drops
from 3.57 m to 0.33 m, and the added lever arm doubles Kθ, which is
what rescues the y-direction's r ≥ ls as a side effect. No room lost a
square centimetre; no furniture moved (the wall clears Deck table 2 by
15 cm).

## Cost table

| Item | Qty | Rate | € |
|---|---|---|---|
| Glazing reworked (Kitchen 1.13 + Win2 3.35 + Win7 1.76 m²) | 6.24 m² | €300/m² | 1,872 |
| Masonry infill (Win7 slot + kitchen band remainder) | 2.6 m² | €55/m² | 143 |
| Demolition, Win2 sill deepening | 0.84 m² | €25/m² | 21 |
| Deck Windbreak Wall, URM 25 cm base | 8.4 m² | €55/m² | 462 |
| — thickening to 50 cm (2.5 ×10 cm layers) | 8.4 m² | €112.5/m² | 945 |
| Strip footing under it (2.8×0.8×0.5) | 1.12 m³ | €280/m³ | 314 |
| Roof-edge shear tie (steel angle + anchors) | ~20 kg | €4.5/kg | 90 |
| Room 2 south walls: shear ties / masonry verification | lump | — | 200 |
| Subtotal | | | 4,047 |
| Site overhead +15% | | | 607 |
| **Total** | | | **~4,654** |

No earthworks, no garage move, no RC, no window deleted from any room
below 92% of its baseline daylight.

## E101 recommendation (structure type — not yet modelled)

URM at ag·S = 0.18 g has no row in EN 1998-1 Table 9.3; no wall layout
fixes that. Recommendation: **confined masonry**. RC tie-columns
25×25 at every external corner, at both ends of every shear wall
counted above (South Wall, South Wall East, Living North Wall, Master
North Wall jambs, Room 2 walls, Deck Windbreak Wall, and the x=4.5 /
x=9.5 / y=8 junctions), plus the already-planned ring beam at slab
level. Roughly 16 columns × 3 m × €90/m = €4,320, +15% ≈ **€5,000
allowance**. Payoff beyond Table 9.3 admissibility: q rises 1.5→2.0,
cutting the 608 kN demand by ~25% — every margin in this proposal
widens. The two 12 cm Room 2 partitions counted as shear walls are the
first candidates for confinement (see below). Framework gains
structure-type presets next; this is priced, not modelled.

## What the engineer must verify

- **The 12 cm partitions**: EN 1998-1 9.5.1 minimum shear-wall
  thickness will likely reject 12 cm URM. Without their 42 kN the x
  margin goes negative by ~31 kN — the confined-masonry upgrade (E101
  allowance) or +0.6 m of windbreak wall covers it. This is the one
  load-bearing assumption in the package that needs his signature.
- Pier-by-pier verification: the screen uses fvd = fvk0/γm with the
  axial-compression benefit dropped (conservative) and t·L_net with no
  slenderness or flange effects (not conservative for squat piers).
- The windbreak wall: overturning/sliding of a gravity-released panel,
  footing interface shear, and the roof-edge tie detail (vertical soft
  joint — the E065 cantilever statics must stay as waived).
- Site values are placeholders (ag 0.15 g, ground B, σ_rd 200 kPa)
  pending the hazard map and geotech report.
- Stale waivers to clean up post-arena (validation.json frozen for the
  run): E062 'Kitchen Window' and 'Living Band Window N' — both
  openings are now below the 1.25 m beam threshold or gone.

## Tried and failed

- Glazing consolidation alone maxes out at ~4.0 m² of t·L (~530 kN)
  — the footprint's URM inventory physically cannot reach 581 kN, so a
  new wall was unavoidable; every lane claiming otherwise is thickening
  something into a room.
- Kitchen-window-to-west-facade + hallway-band consolidation: moved the
  CoR east and pushed e0y past its limit — dropped at the scratch-model
  stage.
- Modeled strip footing under the new wall: framework restricts
  footings to the lowest storey — priced in the table, noted in
  build.py.
- Moving Win5 to the east facade (44 kN cheaper on the y-budget):
  rejected — it reverses the owner's photo-#31 two-pane slider
  composition for a wall the checker doesn't need.
