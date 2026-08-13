# Proposal — lane f-grid (the architect's strengthening grid, confined masonry)

## 1. Metrics

`E100x 272→493.6 kN / demand 581→467.5 kN (util 0.95) · E100y 651.6 kN
/ 467.5 kN (util 0.72) · structure: declared confined, EFFECTIVE
confined — confinement_failures EMPTY, q = q_eff = 2.0 (demand −22%
at T1 = 0.11 s) · e0_x 3.57→0.63 m, e0_y 1.08→1.18 m — BOTH directions
torsionally REGULAR (e0 ≤ 0.30·r and r ≥ ls), E102 gone · red elements
10→0 across ULS + all four SEIS combos · area Δ +0.15 m² net
(apartment 90.0 m² untouched; deck +1.2 m² covers the 0.81 m² of new
pier/wing footprints) · glazing: Living 91.2%, every other room 100%
of baseline (≥90% gate) · cost ≈ €24,300 incl. 15% overhead`

`validate --strict` exit 0 — zero errors AND zero warnings; the E100,
E101 and E102 waivers are now STALE (the findings no longer exist —
cleared, not waived).

## 2. The story — the colleague's grid, taken literally

The owner's architect drew a strengthening grid: lettered axes A
(x = 4.5, the garage west wall and Living East Wall), B/C (x = 9.5,
garage east wall below, East Wall above), and numbered axes 1 (y = 12,
guest-room north), 2 (y = 8, the kamin line), 3 (y = 2.5/4.5, the bath
walls, "to stiffen the house"), 4 (y = 0, the entry facade). This lane
implements that drawing as **confined masonry** — the classification
the framework now rewards only when the geometry proves it.

**Confinement, earned fail-closed.** 27 ground-floor rc tie-columns —
including the architect's hidden **60×20 stub at 2A, long side along
axis A**, buried in the Living East Wall where the y = 8 band beams
land — plus 9 garage ties cover every load-bearing wall intersection,
every free wall end (the stair-gap edges at 4, the garage door jambs on
B), both jambs of every opening over 1.5 m², and ≤ 5 m spacing on every
bearing wall. `confinement_failures` is empty, so the seismic engine
grants q = 2.0: demand drops 581 → 467 kN before a single wall is
added. Ties standing off the garage box (facade corners on axes 1 and
4, the west facade) get rc **foundation piers to the garage founding
level with their own pads** — one founding depth for the whole house,
no differential settlement against the basement box, and a clean E108
support path for every column.

**The x-direction, closed with three small moves.** The band-window
facades gave axis 2 literally zero shear length. (1) Win7 shrinks
2.35 → 0.55 m — the NW living corner returns to solid masonry (1.6 m)
and Living keeps 91.2% of its glass; (2) the Room 2 south walls on
axis 2 become rc bearing walls — the Garage North Wall and its footing
sit directly below; (3) three **pergola piers on axis 1** and a 1.2 m
**wing wall on axis 2** west of the facade (off-slab, own footing)
finish the ledger: 493.6 kN capacity against 467.5 demand. The same
walls move the centre of rigidity onto the centre of mass — e0_x
0.63 m, both directions fully regular, E102 retired.

**The roof reds died of span-shortening, as predicted.** The deck roof
(x < 6, y 8–12.6 minus the skylight) was a floating balcony hung off
glass — Roof East 1.76, Roof West 1.41, and the pier/corner crush
family behind North Wall 1.68 and Room 2 West 1.33. The three axis-1
pergola piers plus a continuous **ring-beam grid hidden in the 0.45 m
roof-fascia depth** (axes 1 and 2 and both window facades, 0.30×0.50 —
0.30×0.60 over the 5.3 m hallway band on C) turn the floating edges
into supported lines. Roof East 1.76 → 0.32, Roof West 1.41 → 0.24,
every wall red gone. The fascia beams are the confined-masonry ring
beam the owner removed on 2026-08-08 to "see where Verstärkung
belongs" — the beam-less X-ray answered, and the grid puts them back
exactly there, invisible inside the brown fascia band.

The one artefact worth confessing: iteration 1 left a 5 cm wall sliver
between the band-window heads (2.80) and the beam soffits (2.85); it
carried the whole roof edge in horizontal tension (East Wall 183%).
The soffits now sit directly on the glass head — the sliver, and the
last two reds, no longer exist.

## 3. Red elements — before → after

Design utilization (worst combo), `output/fem-loads.json`:

| Element | Baseline | Combo | f-grid | Combo | What fixed it |
|---|---|---|---|---|---|
| Roof East | 1.76 | ULS | 0.32 | ULS | pergola piers (axis 1) + axis-1/2 ring beams + bearing Room 2 south walls |
| North Wall | 1.68 | ULS | 0.38 | SEIS_X+ | axis-1 ring beam over Win5/D7 + piers relieve the 0.65 m jamb piers |
| West Wall South | 1.61 | ULS | 0.32 | SEIS_Y+ | west fascia beam takes the roof edge off the corner |
| West Wall | 1.60 | ULS | 0.47 | SEIS_Y+ | west fascia beam, soffit at the glass head (2.80) |
| Living East Wall | 1.51 | ULS | 0.56 | SEIS_Y- | y=8 ring beam spreads the corner load; 2A stub confines the junction |
| Roof West | 1.41 | ULS | 0.24 | ULS | pergola piers + axis-1 ring beam under the deck-roof fingers |
| Master North Wall | 1.40 | ULS | 0.07 | ULS | axis-2 ring beam over the glass doors |
| Room 2 West Wall | 1.33 | ULS | 0.34 | SEIS_Y- | wing load moved to axis-1 piers |
| South Wall | 1.24 | SEIS_X- | 0.47 | SEIS_X+ | q = 2.0 (−22% EQ) + new x-walls share the shear |
| Roof South White | 1.19 | ULS | 0.33 | ULS | west fascia beam supports the corner strip |
| East Wall (regression risk) | 0.78 | ULS | 0.53 | ULS | 0.30×0.60 fascia beam over the 5.3 m hallway band |

ZERO elements over 1.00 in any of ULS, SEIS_X±, SEIS_Y±.

## 4. Cost

| Item | Quantity | Rate | € |
|---|---|---|---|
| RC tie-columns 25×25, GF (26, cast in wall) | 78.0 m | €90/m | 7,020 |
| The 2A stub, 60×20 in the Living East Wall | 3.0 m | €130/m | 390 |
| RC tie-columns 25×25, garage storey (9) | 26.0 m | €90/m | 2,340 |
| Foundation piers under off-garage ties (15, to garage founding level) | 43.4 m | €90/m | 3,903 |
| Pier pads 0.7×0.7×0.5 (15) | 3.68 m³ | €280/m³ | 1,029 |
| Fascia ring beams, axes 1 + 2 + west + east (31.5 m, cast with roof edge) | 4.89 m³ | €350/m³ | 1,713 |
| Ring-beam upgrade allowance, remaining confined walls | 48.7 m | €35/m | 1,705 |
| Pergola piers, rc 0.5×0.3 (3) | 4.5 m² | €120/m² | 540 |
| Wing wall 2W, rc 1.2×3.0 | 3.6 m² | €120/m² | 432 |
| Room 2 south walls: demolish partition + rebuild rc bearing | 10.5 m² | €145/m² | 1,523 |
| Win7 glazing rework | 1.35 m² | €300/m² | 405 |
| Masonry infill at Win7 band | 1.35 m² | €55/m² | 74 |
| Deck slab extension (west edge +0.20 m) | 0.18 m³ | €350/m³ | 63 |
| Subtotal | | | 21,137 |
| Site overhead 15% | | | 3,171 |
| **Total** | | | **≈ €24,300** |

Not the cheapest lane and unapologetic about it: the money is the
confinement itself (ties + piers ≈ €14.7 k) — the thing that earns
q = 2.0, retires E101's URM impossibility honestly, and is the system
the architect drew.

## 5. Detailing list (reported, not gated)

Local peaks above 1.0 where the design value is green — mesh
singularities at re-entrant corners and supports, for the engineer's
detail sheets, `u_peak` in fem-loads.json:

- **West Wall, u_peak 1.63 (ULS)** at (0, 2.73, z 2.68): local
  compression at the top of the 5 cm masonry pier beside Win3's south
  jamb — the west fascia beam's south seat. Detail: beam bearing onto
  the *Tie 3 west* tie-column (which sits exactly there) with a
  padstone; design value is 0.47.
- **East Wall, u_peak 1.19 (ULS)** at (9.5, 2.62, z 2.68): the same
  mechanism at the east fascia beam's south seat over the hallway-band
  jamb; *Tie C hall jamb S* takes it. Design value 0.53.
- **Room 2 South Wall East, u_peak 0.99 (SEIS_X+)** at (9.27, 8.0):
  jamb pier of the Room 2 door under in-plane shear — under 1.0, listed
  because it is the closest approach in the whole model.

## 6. E101 / Table 9.3 honesty

Confined masonry with **one storey above the seismic base** is outside
Table 9.3's simple rules (the confined column starts at 2 storeys) —
the engine states this in `_unresolved` instead of inventing a row, and
E101 produces no finding. Densities for the record: x 2.23%, y 2.94%
vs the 3.5% the 0.18 g URM row would demand — the waiver retires
because the building is no longer URM, not because 3.5% is met. The
E100/E102 waivers are stale for the better reason: the findings are
gone.

## 7. What the engineer must verify

- Tie-column reinforcement, stirrups, anchorage into the pier pads and
  ring beams, and the casting sequence (masonry first, ties poured
  against toothed masonry) — the model proves §9.5.3 *geometry* only.
- The 60×20 stub at 2A and both facade fascia beams: bearing at the
  glazing heads (soffit sits on the window frames at z 2.80).
- Foundation piers: 2.89 m buried columns — buckling length and pad
  bearing at the placeholder σ_rd = 200 kPa (geotech report pending).
- Column frame action is NOT in the plate FEM (specs/columns.md C1):
  the pergola piers are meshed as wall stubs, the tie-columns carry no
  numerical load — their seismic value is the confinement class.
- ag = 0.15 g is still the placeholder pending the BAS EN 1998-1 map.

## 8. What the grid did and didn't buy

The confined preset bought −22% demand, which is why 493.6 kN of
x-capacity clears a gate that took round-1 lanes ~630+ kN of wall.
The ring-beam grid — not more masonry — is what killed the ULS reds:
nine of ten baseline reds were the roof edge riding on glass or on
5 cm slivers. What the grid did NOT buy: numerical credit for the
tie-columns themselves (phase C1 keeps them out of the FEM), so the
2A stub protects the A2 junction in the classification and on the
engineer's sheet, not in the utilization table.
