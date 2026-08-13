# Proposal — lane a-surgeon (minimal change)

## Metrics

`E100x 272→698 kN vs demand 581→654 kN · E100y 652→672 vs 654 ·
e0 3.57→1.76 m (limit 1.81 — REGULAR, and y: 1.29 vs 1.84 also regular) ·
area Δ 0.0 m² · glazing Δ −7.3% total, worst room 90.2% (all rooms ≥ 90%) ·
elements touched 10 · cost ~€9,810 (+€5,430 E101 allowance)`

Strict validation: **exit 0, 0 errors, 0 warnings.** Demand rose 581→654 kN
because thickened walls add seismic mass — the numbers above are the
honest pair, not the baseline demand.

## The story

No new walls, no moved rooms, the garage stays where it is. The x-direction
failure is fixed by giving back to the masonry what the glass took, on the
walls that already exist. The three east-west facades are thickened
**outward** so every interior face — and therefore every square metre of
room — stays exactly where it was: South Wall (axis 1, A–B) grows 30→50 cm,
Living North Wall and North Wall (axis 3 and 4) grow 30→60 cm toward the
deck, burying the new mass in the terrace edge nobody measures. Four
openings are consolidated, never deleted: the Kitchen band becomes one
taller pane (head kept at 2.80), Win7 shrinks to a 0.60 m corner band that
still meets Win2 glass-to-glass (feedback #001 survives), the Room 2 fixed
pane and the Hallway clerestory each give up ~0.5 m to masonry piers — the
clerestory pier lands exactly under where the Room 2 partition meets the
east facade. Finally the two Room 2 partitions on axis 3 (y=8), which sit
directly on the Garage North Wall, are enlisted as the shear walls they
always secretly were. Because the new stiffness lives on the *north* side,
the centre of rigidity moves 1.7 m toward the centre of mass: the torsional
warning E102 doesn't just improve, it clears — in **both** directions.

## Cost (unit rates from the brief)

| Item | Qty | Rate | € |
|---|---|---|---|
| South Wall thickening +20 cm (2 layers × 18.3 m² face) | 36.6 m²·layers | €45/m² per 10 cm | 1,647.00 |
| Living North Wall +30 cm (3 × 13.5 m²) | 40.5 | €45 | 1,822.50 |
| North Wall +30 cm (3 × 10.5 m²) | 31.5 | €45 | 1,417.50 |
| Glazing reworked (Kitchen 1.13 + Win7 1.76 + Win5 3.03 + Win6 3.98 m²) | 9.89 m² | €300/m² | 2,966.25 |
| Masonry infill of reclaimed opening area | 2.85 m² | €55/m² | 156.75 |
| New cut for lowered kitchen sill | 0.91 m² | €25/m² | 22.75 |
| Parapet/roof edge follows thickened south wall | 0.56 m³ | €350/m³ | 196.88 |
| Tie-in of the two y=8 partitions to slab/garage wall (allowance) | lump | — | 300.00 |
| **Subtotal** | | | **8,529.63** |
| Site overhead +15% | | | 1,279.44 |
| **Total** | | | **≈ €9,810** |

For calibration: the garage-move idea starts at €3,000 of earthworks alone
before touching a single failing wall — and moving the garage adds not one
newton of x-direction shear capacity at ground floor.

## E101 — structure-type recommendation (essay, not modelled)

Plain URM has no row in EN 1998-1 Table 9.3 at ag·S = 0.18 g; no geometry
wins this. Recommendation: build the bearing walls as **confined masonry**
(EN 1998-1 §9.5) — the URM geometry above stays exactly as drawn, gaining:

- **RC tie-columns 25×25** at every shear-wall corner and free end, and at
  the jambs of the large openings (Win4, the Room 2 slider, the entry) —
  ~14 columns × 3.0 m: 42 m × €90 = €3,780.
- **Reinstate the roof-level RC ring beam** the owner deleted for looks —
  hidden inside the existing 0.45 m roof edge, so the facade doesn't change:
  ~43 m × 0.25×0.25 = 2.7 m³ × €350 = €945.
- Behaviour factor rises q = 1.5 → 2.0, cutting demand ~654 → ~490 kN,
  turning today's 44/19 kN margins into >180/180 kN — and Table 9.3 has a
  confined-masonry row at this seismicity, so E101 clears in kind.

Allowance: **€4,725 + 15% ≈ €5,430**, clearly labelled *not yet modelled —
framework gains structure-type presets next*.

## What the engineer must verify (honesty section)

- **The two y=8 partitions marked load-bearing are 12 cm walls.** They sit
  on the Garage North Wall (real support), but their shear contribution
  (~42 kN) assumes they are masonry/concrete tied into the slab above and
  wall below — if they turn out to be drywall-grade, they must be rebuilt
  as 12 cm RC (≈ €120/m² × 10.5 m² face ≈ €1,260 extra) or the margin
  shrinks from 44 to ~2 kN. This is the single most load-bearing assumption
  in the package.
- Demand model is ELF with q = 1.5 and gross wall mass; the thickened
  walls raised demand ~12.5% — a spatial model (the FEM X-ray is one) should
  confirm the torsional result now that e0 is within the regular limit.
- Outward thickening assumes the on-grade strip foundations under the
  three facades can take the wider wall (bearing was sized at placeholder
  σ_rd = 200 kPa; the real geotech report is still pending).
- fvd = 133 kPa is the placeholder URM shear strength; the compression
  benefit was dropped (conservative), so real margins should be larger.
- Two E062 waivers (Kitchen Window, Living Band Window N) went **stale**
  because the narrowed openings no longer trigger the wide-opening finding
  — a fix, but the frozen validation.json now carries two dead entries.

**Tried and failed / rejected:**
- Opening consolidation alone maxes out at ~467 kN of the needed 581 — the
  90% glazing gate binds before the masonry does; thickening was mandatory.
- Thickening due south only: cheapest per kN but drags the centre of
  rigidity south — E102 x stayed red in every south-heavy variant.
- First thickening draft ignored that added wall mass raises demand in
  BOTH directions; y-direction margin (70 kN) would have gone negative —
  hence the 0.52 m clerestory pier that keeps E100 y green.
