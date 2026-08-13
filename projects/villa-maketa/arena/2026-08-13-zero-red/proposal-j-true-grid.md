# Proposal — lane j-true-grid (the architect's ACTUAL design, decoded from the maquette)

## 0. Metrics

`E100x 272→516.7 kN capacity / demand 581.2→478.9 kN (util 0.93) ·
E100y 570.0 / 478.9 kN (util 0.84) · structure: declared confined,
EFFECTIVE confined — confinement_failures EMPTY, q = q_eff = 2.0
(T1 0.114 s, Sd 0.1998 g, W 2397 kN) · e0_x 3.57→1.59 m REGULAR,
e0_y 1.08→1.51 m REGULAR (e0 ≤ 0.30·r and r ≥ ls in BOTH directions —
E102 retired, not waived) · red elements 10→0 across ULS + all four
SEIS combos · apartment 90.0 m² untouched, GF slab−walls net ≈ +0.15 m²
(deck +1.89 m² covers the new wall footprints); garage floor 37→28 m²
BY COMMISSION (the one-car box the architect drew) · glazing: Living
90.2% of baseline, every other room 100% (≥ 90% gate) · cost ≈ €43,300
incl. 15% overhead`

`validate --strict` exit 0 — zero errors AND zero warnings. The E100,
E101, E102 waivers and four E062 waivers are now STALE: the findings no
longer exist. E101 honesty: confined masonry with ONE storey above the
seismic base is outside Table 9.3's simple rules (the confined column
starts at 2 storeys) — the engine states this in `_unresolved` instead
of inventing a row; densities for the record: x 2.31%, y 2.55% vs the
3.5% the 0.18 g URM row would demand. The building retires that waiver
by not being URM any more, not by meeting 3.5%.

## 1. The grid (owner + architect, 2026-08-13 — this is the commission)

| Axis | Line | What stands on it |
|---|---|---|
| **A** | x = 2.80 | garage WEST wall (moved), the 2A stub (60×20) in the kamin mass, the A1 post on the deck, **the beam** 2A→A1 at roof level |
| **B** | x = 6.58 | garage EAST wall (moved — aligned exactly to the Bath Divider above), ties B3, roof-level axis-B tie beam |
| **C** | x = 9.50 | East Wall (unchanged), ties C1/C2/C-mid |
| **1** | y = 12.0 | guest-room north / deck edge — ring beam + A1 post |
| **2** | y = 8.0 | the kamin/stone line — ring beam wing-tip→overhang, stub 2A, rc bearing walls x6→9.5 |
| **3** | y = 4.5 (2.5) | bath/bedroom walls — "stiffens the house"; B3 ties on the Bath Divider; rc declared (data-only) on Master South / Bath South |
| **4** | y = 0 | south facade, covered house entry — thickened stone band, jamb/corner ties |

## 2. What moved and why

**The garage moves** from x4.5–9.5 to **A–B (x2.8–6.58) × y0.6–8**: west
wall ON axis A, east wall ON axis B, north wall directly UNDER axis 2,
south face inset at y=0.6 (the floating-overhang look, unchanged). The
**vehicle entrance (2.4 m) returns to the garage SOUTH wall**
(owner-confirmed). The spiral stair does not move — the new SE corner
stops around its shaft (south wall ends at x6.1, east wall starts at
y0.75) and the spiral lands beside B, opening into the garage corner.
One-car box, 3.48 m clear width. Strip footings move with the box
(0.6–0.8 × 0.5 m, E104/E105 green at the placeholder σ_rd = 200 kPa).

**The core structural problem, solved instead of silenced**: today's
interior bearing line (Living East Wall, x=4.5) has NOTHING below it
once the box moves. The takedown reorganizes onto the architect's axes:

- Living East Wall is **demoted to a plain partition** (the room stays,
  the fiction of bearing goes — E050/E103 would rightly fail it).
- The **Bath Divider (on B) becomes the interior bearing line** — the
  garage east wall is directly below it; the architect aligned B to it.
- The **axis-2 line extends across x6–9.5 as rc bearing walls**
  (Room 2 south walls rebuilt 0.12 → 0.25) — the mid-support Roof East
  loses at x=4.5 comes back at y=8, standing on the garage north wall
  (west of B) and its own grade line (east of B).
- The **GF slab now spans A→B (3.78 m)** instead of 4.5→9.5 (5.0 m) —
  shorter, better; east of B it rests on fill.
- **Axis 4 stone band thickens 0.30 → 0.40** — the x-direction shear
  the old garage west wall used to anchor comes back on the grid line
  the architect drew, not on a random wall.
- **The kamin returns**: the Living Sliding Window shrinks 2.15 → 1.60
  so the wall at A × 2 is solid stone again — the 2A stub (60×20, long
  side along A) hides in that mass, exactly as drawn.

**The consoles**: the GF volume oversails the moved box on both sides —
the maquette's floating volume. Vertical seismic on cantilevers is NOT
modelled (phase C1) — flagged for the engineer, per spec.

## 3. Red elements — before → after

Design utilization (worst combo), `output/fem-loads.json`:

| Element | Baseline | Combo | j-true-grid | Combo | What fixed it |
|---|---|---|---|---|---|
| Roof East | 1.76 | ULS | 0.35 | ULS | B becomes the bearing line (Bath Divider + axis-B beam) + axis-2 rc walls x6–9.5 + axis-1 ring beam |
| North Wall | 1.68 | ULS | 0.42 | SEIS_X+ | axis-1 ring beam over Win5/D7 relieves the 0.65 m jamb piers |
| West Wall South | 1.61 | ULS | 0.46 | SEIS_Y+ | west fascia beam takes the roof edge off the corner |
| West Wall | 1.60 | ULS | 0.42 | SEIS_Y+ | west fascia beam, soffit ON the glass head (2.80) |
| Living East Wall | 1.51 | ULS | — | — | demoted to partition — not meshed; it no longer pretends to carry anything |
| Roof West | 1.41 | ULS | 0.45 | ULS | **Beam Axis A (2A→A1)** + **A1 post** + axis-1 ring beam under the deck edge |
| Master North Wall | 1.40 | ULS | — | — | wall band fully replaced by Ring Beam Axis 2 (beam u 0.15) — no masonry left to crush |
| Room 2 West Wall | 1.33 | ULS | 0.32 | SEIS_X- | deck-roof load moved to A1/axis-1; axis-2 walls share shear |
| South Wall | 1.24 | SEIS_X- | 0.36 | SEIS_X+ | q = 2.0 (−25% EQ) + 0.40 m stone band + grid x-walls |
| Roof South White | 1.19 | ULS | 0.35 | ULS | west fascia beam + axis-4 band; plate spans y to the axis-4 wall |
| Bath Divider (new duty) | 0.28* | — | 0.96 | ULS | the new interior bearing line on B — closest approach in the model, listed honestly |
| A1 Post (new) | — | — | 0.81 | ULS | 0.50×0.40 rc pier (iteration 2: 0.30 thick sat at 1.014 — the only red this lane ever produced, fixed by section) |

*baseline Bath Divider was a non-bearing partition.

ZERO elements over 1.00 in any of ULS, SEIS_X±, SEIS_Y±.

### Detailing list (reported, not gated — mesh peaks where the design value is green)

- **West Wall, u_peak 2.07 (SEIS_Y+)**, design 0.42: corner tile at the
  Win2/Win3 mullion line under in-plane shear — the *Tie W mullion*
  tie-column stands exactly there; detail its stirrup zone.
- **Bath Divider, u_peak 1.76 (ULS)**, design 0.96: bearing
  concentration where the axis-B beam seats over the divider's north
  end — padstone / local reinforcement at the B3-north tie.
- **A1 Post, u_peak 1.31 (ULS)**, design 0.81: beam-seat concentration
  at the post head (axis-1 × axis-A beams crossing) — the real
  steel/rc post head detail, engineer's sheet.
- **Wing Wall 2W, u_peak 1.19 (SEIS_X-)**, design 0.41: re-entrant
  corner at the facade joint; *Tie 2W corner* sits there.
- **Living North Wall, u_peak 1.11 (SEIS_X-)**, design 0.57: kamin
  jamb beside Win7 — the 2A-stub/kamin zone, confined by design.
- **West Wall South, u_peak 1.01 (SEIS_Y+)**, design 0.46: corner tile
  at (0,0); *Tie 4-west corner* covers it.

## 4. Cost (owner-approved rates, ±50% — the REAL number, not a flattering one)

| Item | Quantity | Rate | € |
|---|---|---|---|
| New pit / excavation (owner lump) | 1 | €3,000 | 3,000 |
| Old garage walls demolition (24.5 m × 2.89) | 70.8 m² | €25/m² | 1,770 |
| Old garage slab break-out | 37.0 m² | €25/m² | 925 |
| Old strip footings break-out (approx.) | lump | — | 500 |
| New garage walls, stone URM (22.3 m × 2.89) | 64.5 m² | €55/m² | 3,549 |
| New strip footings (A 0.8 / B 0.8 / 2 0.8 / 4 0.6 wide) | 8.6 m³ | €280/m³ | 2,409 |
| New garage slab 0.25 | 7.0 m³ | €350/m³ | 2,447 |
| RC tie-columns 25×25, GF (26 × 3.0 m) | 78.0 m | €90/m | 7,020 |
| **The 2A stub, 60×20** (kamin mass) | 3.0 m | €130/m | 390 |
| RC tie-columns 25×25, garage (8 × 2.89 m) | 23.1 m | €90/m | 2,080 |
| Foundation piers under off-box ties (21 × 2.89 m) | 60.7 m | €90/m | 5,463 |
| Pier pads 0.7×0.7×0.5 (20 — one pier sits on the A footing) | 4.9 m³ | €280/m³ | 1,372 |
| Fascia ring beams: axes 1, 2, **A (2A→A1)**, B, west (35.9 m, 0.30×0.50) | 5.38 m³ | €350/m³ | 1,883 |
| Ring-beam upgrade allowance, remaining confined walls | 39 m | €35/m | 1,365 |
| **A1 post**, rc 50×40 (modelled as meshed pier) | 1.5 m² | €120/m² | 180 |
| Wing wall 2W (axis-2 line past the west glass) | 3.6 m² | €120/m² | 432 |
| Room 2 south walls: demolish partition + rebuild rc 0.25 bearing | 10.5 m² | €25+€120/m² | 1,523 |
| South stone band thickening 0.30→0.40 | 18.3 m² | €45/m²/10cm | 824 |
| Win4 glazing rework | 1.51 m² | €300/m² | 454 |
| Masonry infill at Win4 (the kamin return) | 1.51 m² | €55/m² | 83 |
| Subtotal | | | 37,669 |
| Site overhead 15% | | | 5,650 |
| **Total** | | | **≈ €43,300** |

This is the expensive option and unapologetic about it: ~€19k over the
f-grid stationary version, of which ~€15k is the box move itself
(demolition, pit, new walls/footings/slab). The rest is the same
confinement grid every green lane needs. It is the design the architect
actually drew.

## 5. Confinement evidence

`output/seismic.json → confinement_failures` is **EMPTY** — earned on
the first evaluation, fail-closed: q = q_eff = 2.0. The evidence grid:

- **27 GF tie-columns** including the architect's **2A stub (60×20,
  long side along A)** hosted in the kamin wall at (2.8, 8), plus one
  tie in the demoted Living East partition that doubles as the D9 jamb
  and the (4.5, 8) junction evidence.
- **8 garage ties** on the moved box (corners, vehicle-door jambs,
  ≤ 5 m spacing) — the hatched tie marks the architect printed along B
  exist in the model as *GTie B stair/mid/B2*.
- Every tie NOT standing over a garage wall line has an **rc foundation
  pier to the box founding level** (21 piers, 20 pads — one lands on
  the widened A strip footing): one founding depth, no differential
  settlement, and a green E108 support path for every column.
- The **A1 post earns NO confinement credit** (free-standing member,
  specs/columns.md) — its tie ring is its own pier's evidence, nothing
  more. Stated so the referee doesn't have to catch it.

## 6. What the engineer must verify

- **Cantilever vertical seismic**: the GF consoles over the moved box
  and the deck-roof edge — vertical component NOT in the plate FEM
  (phase C1 banner). Also the existing GF slab reinforcement for the
  new A→B span arrangement and the fill under its eastern bay.
- **A-beam connections**: the 2A-stub-to-beam joint (moment or pinned —
  the model assumes plate continuity), the beam seat on the A1 post,
  and both fascia-beam bearings on the glazing heads (soffit at 2.80
  sits ON the frames).
- **A1 post anchorage**: modelled as a meshed 50×40 rc pier because
  phase C1 does not mesh columns (specs/columns.md); the built member
  (steel HEA or rc) needs a real base plate / anchorage into its
  foundation pier and pad — and it earns NO confinement credit.
- Tie-column reinforcement, stirrups, anchorage into pads and ring
  beams, casting sequence (masonry toothed, ties poured after) — the
  model proves §9.5.3 GEOMETRY only.
- Foundation piers: 2.89 m buried rc columns — buckling and pad bearing
  at placeholder σ_rd = 200 kPa (geotech report pending); ag = 0.15 g
  placeholder pending the BAS EN 1998-1 map.
- The stair-tower shaft now sits OUTSIDE the box wall line (east of B)
  — waterproofing/retaining detail at the shaft-to-box junction.

## 7. Sažetak za arhitektu (bosanski)

Garaža je pomjerena tačno na Vašu mrežu: zapadni zid na osu **A**,
istočni na osu **B** (poravnat sa pregradnim zidom kupatila), sjeverni
zid direktno ispod ose **2** — kamin linije. Ulaz za auto je vraćen na
JUŽNI zid garaže, a spiralno stepenište ostaje gdje jeste i slijeće uz
B. Stub **2A (60×20, duža strana u pravcu A)** sakriven je u masi
kamina; na uglu terase stoji stub **A1**, a između njih, na osi A u
nivou krova, ide **greda** (izvedena kao armirani beton — čelična u
proračunu ne nosi) koja nosi ivicu krova iznad staklene zone. Kuća je
proračunata kao **omeđeno ziđe** (confined masonry): vertikalni serklaži
na svim raskrsnicama nosivih zidova, krajevima i uz otvore — dokaz
geometrije je prošao, pa kuća zaslužuje q = 2,0. Nijedan element više
nije preko nosivosti ni u jednoj kombinaciji (ULS + sve četiri
seizmičke). Konzole — "lebdeći volumen" — označene su inženjeru za
provjeru vertikalnog seizmičkog djelovanja. Cijena je realna, ne
uljepšana: ≈ €43.300 sa svim rušenjem, iskopom i serklažima.

## 8. What the true geometry bought (vs f-grid's stationary version)

**Bought**: the actual commission — a garage where the architect put
it, spans that make sense (GF slab 5.0 → 3.78 m over the box; Roof East
6.58→9.5 = 2.92 m to C), an interior bearing line (B) that was already
a wall, and torsional regularity in BOTH directions with e0_x collapsing
3.57 → 1.59 m. The beam the architect asked for (2A→A1) plus the A1
post replace f-grid's three pergola piers — one support instead of
three, and it is the drawn one. Ten baseline reds die the same way
f-grid's did (fascia ring beams + span shortening), at u ≤ 0.46.

**Broke, and had to be fixed**: (1) demoting Living East Wall orphaned
the roof seam x4.3–6.58 — the axis-B roof beam bridging the Bath
Divider to axis 2 is the repair, and the divider becomes the model's
closest approach (0.96); (2) the x-direction shear ledger lost the old
garage west wall — recovered on the grid (0.40 m axis-4 band, axis-2 rc
walls, kamin return at Win4, wing wall); (3) the A1 post itself was
this lane's only self-inflicted red (1.014 at 0.30 thick — cleared at
0.40). Cost honesty: ~€19k over f-grid, almost all of it the box move
(demolition, pit, new stone walls, footings, slab) — the price of
building the maquette instead of approximating it.
