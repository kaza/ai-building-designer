# Proposal — lane e-wildcard (free search)

## 1. Metrics

`E100x 272→631.6 kN / demand 581→608.9 kN (util 0.96) · E100y 651.6 kN
(green, util 0.93) · e0_x 3.57→0.38 m, e0_y 1.08→1.09 m — BOTH
directions now REGULAR, E102 gone entirely · area Δ 0.0 m² (apartment
90.0 m² unchanged, no wall enters any room) · glazing Δ: Kitchen 92.9%,
Living 91.3%, all other rooms 100% of baseline (≥90% everywhere) ·
elements touched 7 (3 windows reworked, 2 walls re-flagged, 2 new walls)
· cost ~€6,300 incl. overhead`

`validate --strict` exit 0 — zero unwaived errors AND zero warnings.

## 2. The story

The x-direction dies because every east-west wall is a ribbon of glass:
the north shear line at axis y=8 contributes literally zero (Living
North Wall and Master North Wall are 100% opening). The fix plays both
ends of the capacity/torsion problem *at the same edge*. First, the
band windows consolidate into piers: the 2.35 m band over the TV wall
(Win7) becomes a 0.60 m full-height corner slot that still meets Win2
glass-to-glass at the (0,8) corner, the living slider (Win4) narrows
2.15→1.70, and the kitchen band becomes one tall pane over the counter
— every room keeps ≥90% of its glass, and 4.2 m of solid masonry
returns to the shear lines. Second, the two Room 2 south walls on axis
y=8 become load-bearing — the Garage North Wall and its strip footing
sit directly below, so the load path is as real as the x=4.5 divider's.
Third — the move no other lane's charter allows — two 2.4 m **wing
walls** extend the y=8 and y=12 shear lines *past* the building
corners as coplanar garden walls: the yellow accent plane slides past
the glass corner to frame the deck (a classic Barragán gesture), and a
matching wall at the NE corner screens the pool deck from the east
driveway. Standing off-slab on their own footings they cost no floor
area, and being at the far north they are torsion outriggers: the
centre of rigidity moves from y=2.29 to y=5.67, on top of the centre
of mass. The storey stops twisting — e0 drops 3.57→0.38 m and both
directions pass the full regularity check (e0 ≤ 0.30·r *and* r ≥ ls),
which the baseline failed even in y.

## 3. Cost table

| Item | Quantity | Rate | € |
|---|---|---|---|
| Glazing reworked (Kitchen 1.13 + Win4 5.91 + Win7 1.76 m²) | 8.80 m² | €300/m² | 2,640 |
| New URM infill masonry (piers on Living North + South walls) | 4.0 m² | €55/m² | 220 |
| Demolition for new full-height slot cuts | 1.8 m² | €25/m² | 46 |
| Wing walls, URM 30 cm (2 × 2.4 m × 3.0 m) | 14.4 m² | €55/m² | 792 |
| RC tie-columns 25×25 confining wing ends + facade junctions | 4 × 3.0 m | €90/m | 1,080 |
| Strip footings under wings (2 × 2.4 × 0.6 × 0.5 m) | 1.44 m³ | €280/m³ | 403 |
| Room 2 south walls to bearing spec (anchors, tie into slab) | lump | — | 300 |
| Subtotal | | | 5,481 |
| Site overhead 15% | | | 822 |
| **Total** | | | **≈ 6,300** |

## 4. E101 recommendation — confined masonry conversion

*(not yet modelled — framework gains structure-type presets next)*

URM has no Table 9.3 row at ag·S = 0.18 g, so no geometry wins E101.
The recommendation is **confined masonry**, not RC-wall conversion:
it keeps the maquette's massing, raises the behaviour factor q from
1.5 to ~2.0 (demand −25% on top of the numbers above), and Table 9.3
readmits the construction type at this seismicity with the wall
densities this plan already provides (x 2.86%, y 2.95%). Scope:
RC tie-columns 25×25 at every external corner, at the bearing-wall
junctions (x=4.5, x=8 lines, y=8 line), and flanking every opening
wider than 1.5 m on a bearing wall — ~14 columns; plus the continuous
RC ring beam at roof level that the owner's "remove the beams" X-ray
experiment took out (confined masonry makes it mandatory again, which
also retires the seven waived E062 findings for free). Allowance:
14 × 3.0 m × €90 = €3,780 + ring beam ~3.1 m³ × €350 = €1,090 →
**≈ €5,600 incl. 15% overhead**. The wing walls are confined by the
four tie-columns already priced in section 3. Alternative (RC wall
conversion of the x=4.5 divider + corridor walls) was rejected: ~3×
the cost for a single-storey seismic box that confined masonry already
satisfies.

## 5. What the engineer must verify, and what failed

Verify:
- fvd here is fvk0/γm = 133 kPa with the 0.4·σd compression benefit
  deliberately dropped; real verification per EN 1996-1-1/EN 1998-1
  with actual axial loads (will only help).
- **Wing-wall shear transfer**: each wing works as an in-plane
  lengthening of an existing shear wall through the corner joint, but
  most of its length stands beyond the roof diaphragm — the connection
  to the facade wall and the roof edge member must be detailed (the
  four tie-columns are priced for this); out-of-plane stability of the
  free ends rides on the same columns.
- The 12 cm Room 2 south walls as shear walls: slenderness and
  top/bottom connection (same precedent as the x=4.5 divider already
  counted by the engine).
- Demand rose 581→609 kN from the wings' own mass — accounted for in
  the pass margins above (x 0.96, y 0.93 utilisation).
- Two E062 waivers went stale because the narrowed openings dropped
  below the 1.25 m beam threshold — expected, harmless.

Failed along the way (lab notebook = this branch):
- Wing walls flagged `is_external` inflated the BGF envelope → new
  E032 "šupak" + W031; re-classed as garden walls (deck-screen class).
- Stair-tower enclosure walls: rejected before modelling — south-side
  stiffness moves the centre of rigidity the wrong way (torsion worse).
- Demand-side roof thinning: rejected — seismic mass is already capped
  at 0.25 m equivalent, and going thinner traded the maquette's brown
  fascia for ~40 kN.
- Bath/Master south walls (y=2.5/4.5) as shear walls: impossible — the
  open garage span below offers no support (floating = DQ), and a
  garage pier wall would cost the second parking stall.
