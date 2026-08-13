# Proposal — lane b-garage (arena 2026-08-13-seismic)

## 1. Metrics

`E100x 272→708 /581→642 kN (demand rose with added mass; margin +10.1%) ·
E100y 652→664 vs 642 ✅ green · e0x 3.57→1.18 m (limit 1.90, REGULAR) ·
e0y irregularity (r 4.56 < ls 4.88) also cleared: r 6.53 ≥ ls 4.95 ·
area Δ 0.00 m² (all inner faces byte-identical) · glazing Δ −6.6% total,
worst room 90.35% (Living) — every room ≥ 90% · elements touched 14 ·
cost ~€9,300 (incl. 15% overhead)`

`validate --strict` exit 0 — zero errors, zero warnings, 18 waived,
2 stale (see §5).

Axis grid used below — letters = N–S lines, numbers = E–W lines:

```
A x=0 · B x=4.5 (garage west wall) · C x=9.5 (garage east wall)
1 y=0 (south band) · 2 y=2.5/4.5 (baths) · 3 y=8 (garage north wall)
4 y=12 (north facade)
```

## 2. The story

We began by building the architect's centring scheme literally —
garage box shifted to x2.5–7.5 so the ground floor cantilevers over it
on both sides — and the engine refuted it with receipts (commit
853f226): capacity stayed 272 kN and e0 stayed 3.57 m to the
centimetre, because the garage is a rigid box below the seismic base
and moving it moves **no ground-floor wall**; it only orphaned bearing
line B (E050+E103, 7.45 m of 'Living East Wall' left standing on air)
and would have cost ~€9,200 in demolition, rebuild and earthworks. The
garage's real seismic gift is different: its north wall **is** axis 3.
So the box stays exactly where the owner put it, and the ground floor
re-centres its *stiffness* over it instead of its mass: the two Room 2
partitions standing on the garage north wall (axis 3, 'Room 2 South
Wall West/East') become bearing shear walls; the band glazing on axes
3 and 4 consolidates into the same square metres of glass as taller,
narrower panes ('Living Band Window N' becomes a full-height corner
slot, Win4/Win5/Kitchen narrow within the 90% rule), growing masonry
piers where there was ribbon; the mostly-solid walls on axes 1 and 4
thicken **outward** (south band 0.30→0.45 m, Room 2 north 0.30→0.60 m
— centerlines shift out, inner faces and room areas untouched, the
white parapet reads one shade chunkier); and a new 1.5 m 'Terrace Fin
Wall' extends axis 4 westward from the Room 2 corner, carrying the
roof's north edge over the covered terrace. Net effect: the x-capacity
nearly triples to 708 kN, and the centre of rigidity travels 2.4 m
north to sit almost under the centre of mass — e0 1.18 m, torsionally
regular in **both** directions, which no amount of box-shuffling below
the base could ever have bought.

## 3. Cost (unit rates from brief.md)

| # | Item | Qty | Rate | € |
|---|------|-----|------|---|
| 1 | South Wall thicken +15 cm (axis 1), 6.25×3.0 m face | 18.75 m² | 1.5 × €45/m² | 1,266 |
| 2 | South Wall East thicken +15 cm (axis 1) | 6.15 m² | 1.5 × €45/m² | 415 |
| 3 | North Wall thicken +30 cm (axis 4) | 10.95 m² | 3 × €45/m² | 1,478 |
| 4 | Terrace Fin Wall, new URM 1.5×3.0 m (axis 4) | 4.5 m² | €55/m² | 248 |
| 5 | Fin strip footing 1.5×0.6×0.5 m | 0.45 m³ | €280/m³ | 126 |
| 6 | Roof South edge extension (flush with 0.45 walls) | 0.66 m³ | €350/m³ | 231 |
| 7 | Glazing reworked: Kitchen 1.13 + Win4 5.91 + Win5 3.03 + Win7 1.76 | 11.83 m² | €300/m² | 3,548 |
| 8 | Masonry infill at narrowed openings | 3.9 m² | €55/m² | 215 |
| 9 | Demolition for Win7 full-height slot + kitchen sill | 1.9 m² | €25/m² | 48 |
| 10 | Room 2 partitions to shear duty (tie to slab, repoint) | lump | — | 500 |
| | Subtotal | | | 8,075 |
| | Site overhead +15% | | | 1,211 |
| | **Total** | | | **~9,286** |
| | Garage demolition / relocation / €3,000 earthworks | — | — | **0** |

The lane that was priced to be the most expensive submits with the
garage untouched: the €3k earthworks lump plus ~€6.2k demolition and
rebuild are exactly what the refuted centring variant would have burned
for zero seismic gain.

## 4. E101 recommendation (structure type — not yet modelled)

URM has no row in EN 1998-1 Table 9.3 at ag·S = 0.18 g; no geometry
fixes that. Recommendation: **confined masonry**. RC tie-columns
25×25 at every facade corner and wall junction and flanking the two
remaining wide openings (Win4, D8/D9) — 14 columns × 3.0 m — tied by
the ring-beam layer the owner already deferred ("Verstärkung"
decision pending, E062 waivers). The thickened axes 1/4 and the new
fin take the tie-columns without touching room area. Allowance:
14 × 3.0 m × €90 = €3,780 → **€4,350 incl. 15%**. Alternative where
the engineer prefers it: cast the Terrace Fin and the 12 cm interior
spine (axis B) as RC walls (€120/m² premium ≈ €900). Not yet modelled
— framework gains structure-type presets next; q would rise from 1.5
toward 2.0–2.5 and cut the 642 kN demand by ~25–40%, turning today's
margins into comfort.

## 5. What the engineer must verify / honest gaps

- **12 cm partitions as shear walls** (Room 2 south pair, axis 3, and
  the pre-existing 'Living East Wall'): fvd = 133 kPa on a 12 cm leaf
  is the framework's assumption; the engineer confirms leaf, ties and
  the connection to the garage north wall below.
- **E100 y margin is 3.3%** (664 vs 642 kN) — green but thin; the
  thickening that fixed x also raised total demand 581→642 kN. If the
  engineer wants slack: narrowing the Hallway Window 5.3→5.0 m within
  its glazing budget buys +12 kN for ~€100.
- **Fin footing depth**: modelled on the garage storey (the framework
  keeps footings on the lowest storey, E104); really a frost-depth
  strip at ~−0.8 m on soil outside the box.
- **Site values are placeholders** (ag 0.15 g, ground B, σ_rd 200 kPa)
  — every number moves with the real hazard map + geotech report.
- **2 stale waivers** (E062 Kitchen Window / Living Band Window N):
  their openings dropped below the 1.25 m beam threshold, findings
  vanished; validation.json is frozen for the arena, cleanup afterwards.
- Room 2's east window stub grew 0.65→0.85 m and the brown roof's
  north overhang reads 0.15 m (was 0.45) past the thickened face —
  cosmetic drift from photo #31/#24, owner to bless.

Tried and failed (lab notebook = this branch):
- Centred garage box x2.5–7.5 (commit 853f226 message): capacity and
  e0 unchanged, E050+E103 broke line B, ~€9.2k — refuted, reverted.
- Bath/Master south walls (axis 2) as bearing: dead end — they stand
  over the garage's interior air; any box move that puts a wall under
  them either breaks the spiral-stair connection or shrinks the bay
  below one car.
- Symmetric (inward) thickening: rejected — eats room area, instant DQ.
