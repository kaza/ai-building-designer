# Proposal — lane i-wild (free search): answer the Verstärkung question

**Metrics line**: `E100x 272→618.3 / 608.2 kN (util 0.98) · E100y
651.6 / 608.2 (util 0.93) · e0x 3.57→0.33 m (limit 0.3r = 1.94), e0y
1.16 vs 1.89, r ≥ ls BOTH directions — E102 gone entirely · structure
URM, q_eff = 1.5 (confined preset NOT declared — see below) · red
elements 10 → 0 across ULS + all four SEIS combos · area Δ 0.00 m²
(apartment 90.0 m², no wall thickened, nothing enters a room) ·
glazing: Kitchen 92%, Living 94%, all other rooms 100% (≥90%
everywhere) · elements touched 14 (3 windows, 1 wall demoted, 2 walls
re-flagged, 1 new wall, 7 RC beams) · cost ≈ €6,720 incl. overhead`

`validate --strict` exit 0 — zero unwaived errors, zero warnings.

## The story

Everyone stared at the earthquake; the board was actually lost at ULS.
Eight of the ten reds are plain gravity, and all of them are the same
defect: after the owner's 2026-08-08 experiment ("remove the ring
beams, then we can check where and how we need to make Verstärkung"),
the roof has been structurally resting on 0.2 m masonry strips over
glass. The beam-less X-ray was run precisely to answer *where the
Verstärkung belongs* — this lane's core move is simply to answer it:

1. **Seven RC ring beams / lintels** go exactly where the X-ray showed
   the bands failing (z = 2.2–2.9 hot zones): the full west facade
   (Win2+Win3's contiguous 5.25 m glass run dumped the whole Roof West
   edge into the (0,2.7) pier top — 6.6× peak), the living north band,
   the Room 2 north slider band, the east clerestory (dd9ee6a's proven
   0.70 m section), a lintel over the stair-tower gap in the south
   facade (the white roof strip there had no y=0 support at all), and
   a flush beam on the 12 cm divider that spreads the glass-corner
   reactions instead of crushing the (4.5,8) corner (6.2× peak).
   Every beam is E064-checked (max util 0.20 in the FEM, 0.73 in the
   strip engine).
2. **The Master North Wall stops lying.** It is 100% glass (D8+D9
   edge-to-edge) — as a "bearing wall" it was a masonry band arching
   its roof strip into the divider's top corner (1.40 red + the 6.2×
   corner). It is now declared the storefront it physically is, and an
   explicit RC lintel (RB Master North) carries the roof edge onto
   Room 2 West Wall and the divider. The composition, the glass and
   the room are untouched.
3. **Deck Windbreak Wall** (2.8 × 0.5 m stone, y = 12.3, x 1.7–4.5,
   round-1 c-torsion's move stolen whole): the FEM shows Roof West's
   north run spanning 6.6 m unsupported from x = −0.6 to x = 6
   (hogging 2.07× over Room 2 West Wall). One off-slab wall under that
   edge kills the worst roof red, adds 1.4 m² of x-shear at the far
   north (the torsion outrigger that moves CoR onto the mass), and is
   the E065 "columns at the deck edge" decision, answered. Clears both
   deck tables (5 / 15 cm).
4. **Round-1 shear package**: Room 2 south walls become bearing (the
   Garage North Wall and its footing sit directly below), Win7
   infilled with its daylight moved into Win2 deepened to sill 1.80
   (the owner's original dictation), Kitchen band → 0.9 × 1.15 pane.

## Red elements before → after (design u, worst combo)

| Element | Before | After | Fixed by |
|---|---|---|---|
| Roof East | 1.77 ULS | 0.29 | windbreak (kills the 6.6 m north run) + real band supports |
| North Wall | 1.68 ULS | 0.33 | RB North replaces the failing band |
| West Wall South | 1.61 ULS | 0.39 | RB West continues over its top to (0,0) |
| West Wall | 1.60 ULS | 0.42 | RB West (5.25 m glass run gets a real beam) |
| Living East Wall | 1.51 ULS | 0.62 | RB Living East + storefront demotion unloads the corner |
| Roof West | 1.41 ULS | 0.40 | windbreak + RB West |
| Master North Wall | 1.40 ULS | — (storefront; RB Master North u 0.04) | honest reclassification + lintel |
| Room 2 West Wall | 1.33 ULS | 0.39 | Master-band pull removed; windbreak shares the roof |
| South Wall | 1.24 SEIS_X− | 0.45 | shear package (South Wall's EQ share drops with 4 new x-walls) |
| Roof South White | 1.19 ULS | 0.27 | RB Stair Gap lintel + RB West corner |

New elements stay calm: Deck Windbreak Wall 0.52, Room 2 south walls
0.67 / 0.45, all beams ≤ 0.20 — no round-1-style connection-peak
shame (worst new-element fragment 0.93).

## Cost table

| Item | Qty | Rate | € |
|---|---|---|---|
| Glazing reworked (Kitchen 1.04 + Win2 3.35 + Win7 1.76 m²) | 6.24 m² | €300/m² | 1,872 |
| Masonry infill (Win7 slot + kitchen band remainder) | 2.6 m² | €55/m² | 143 |
| Demolition (Win2 sill deepening + band chases for beams) | ~5.8 m² | €25/m² | 146 |
| RC ring beams / lintels (7 pcs, 33.2 m) | 4.35 m³ | €350/m³ | 1,523 |
| Deck Windbreak Wall, URM 25 cm base | 8.4 m² | €55/m² | 462 |
| — thickening to 50 cm (2.5 × 10 cm layers) | 8.4 m² | €112.5/m² | 945 |
| Strip footing under it (2.8 × 0.8 × 0.5) | 1.12 m³ | €280/m³ | 314 |
| Roof-edge shear tie (steel angle + anchors) | ~20 kg | €4.5/kg | 90 |
| Room 2 south walls to bearing spec (slab/garage-wall ties) | lump | — | 200 |
| Beam bearing pads / corner pockets (detailing list) | lump | — | 150 |
| Subtotal | | | 5,845 |
| Site overhead +15% | | | 877 |
| **Total** | | | **≈ 6,720** |

## Why NOT the confined preset (the wild lane's finding)

The shiny new q = 2.0 was tried on paper first: the fail-closed
evidence check demands tie-columns at every bearing-wall intersection,
free end, >1.5 m² opening jamb and 5 m spacing gap — on BOTH storeys.
For this villa that is ~20+ columns (≈ €6,500 at €90/m), plus three
composition-breaking conflicts: a column in the D8/D9 glass-to-glass
joint, one in the Win2/Win3 no-mullion joint, and one inside the 5.3 m
hallway clerestory. Its only numeric payoff is −22% earthquake demand
— and this design passes every gate at q = 1.5 without it. Buying
q = 2.0 here is paying €6,500 to widen margins that are already green.
The honest place for confined masonry is the E101 recommendation
below, where it has always lived.

## E101 statement

URM densities are x 2.80% / y 2.95%; EN 1998-1 Table 9.3 has NO
admissible URM row at ag·S = 0.18 g, so E101 stays waived, exactly as
documented. Note for the record: even the confined column of Table 9.3
starts at 2 storeys — a 1-storey seismic system needs *explicit
analysis* either way, and the five-combination plate FEM in this
package IS that analysis. Recommendation unchanged from round 1:
build confined (tie-columns at corners and jambs per §9.5.3, the ring
beams this package already provides), allowance ≈ €5,000–6,500, with
the three glass-joint conflicts above resolved by the engineer and
owner together (shift D9 / split Win6, or accept visible posts).

## Detailing list (fragment peaks — mesh singularities, not gated)

Only two fragments in the whole model exceed 1.0 (baseline had dozens):

1. **West Wall pier head (0, 2.73, z≈2.75), 1.96 ULS, vertical
   compression** — RB West's end bearing over the (0,2.7) pier:
   provide a C25 bearing pocket / pad under the beam end.
2. **East Wall at Win6 south jamb (9.5, 2.62, z≈2.75), 1.39 ULS,
   same mode** — RB East end bearing; same detail.

Also for the engineer: RB Master North and RB Stair Gap end anchorage
(FEM checks beam bending only — axial/shear/torsion are in the
not-modelled list); windbreak overturning/sliding as a gravity-released
panel + roof-edge tie (vertical soft joint, E065 statics stay waived);
the 12 cm Room 2 partitions and divider as shear walls (EN 1998-1
9.5.1 minimum thickness — same reservation as round 1); site values
(ag 0.15, ground B, σ_rd 200 kPa) are placeholders pending the hazard
map and geotech report.

## Stale waivers (validation.json frozen for the run)

E062 'Kitchen Window' / 'Living Glass W2' / 'Hallway Window' / 'Living
Band Window N', E100, E102 — all stale because the findings are fixed,
not because anything is hidden. Clean up post-arena.

## Tried and failed / rejected

- **Confined preset**: see above — priced, rejected on cost at this
  margin (it is the right *construction* answer via E101, but a wrong
  €6,500 as a *numbers* purchase here).
- **Free posts / tie-columns as roof props**: columns are not meshed
  in the plate FEM (specs/columns.md C1) — they cannot clear a roof
  red; only bearing walls and beams can. The windbreak wall is the
  honest version of that prop.
- **Interior bearing wall at x=8 under Roof East**: floats on the
  spanning ground slab over the garage — the round-1 "floating = DQ"
  precedent stands.
- **Roof thinning for demand**: both mass and capacity are already
  capped at 0.25 m equivalent — thinning buys nothing until it starts
  costing capacity and the brown fascia.
