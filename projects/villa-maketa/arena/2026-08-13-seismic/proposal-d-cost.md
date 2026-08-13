# Proposal — lane d-cost (cheapest euro total that clears the gates)

## 1. Metrics line

`E100x 272→654.3 kN vs demand 581.2→615.4 kN (mass-corrected) · E100y 651.6 kN ✅ ·
e0 3.57→2.46 m (E102y cleared outright: r 4.56<ls 4.88 → r 5.96>ls 4.97) ·
area Δ 0.0 m² · glazing Δ per room ≥ +0% (Kitchen +1.3%, Living +0.2%) ·
elements touched 8 · cost ~€3,081`

`validate --strict` exit 0. Note the demand moved: my own 133 kN of new
masonry raised Fb from 581.2 to 615.4 kN — capacity is quoted against the
raised demand, not the flattering old one.

## 2. The story

The x-direction problem is that the band windows sliced every east-west
wall into ribbons; the fix is to buy back shear length at the lowest rate
on the table, which is *paperwork first, masonry leaf second*. Both Room 2
south partitions (`Room 2 South Wall West/East`, the y=8 line) stand
directly on the `Garage North Wall` — flagging them load-bearing costs
nothing and E103 machine-verifies the shear path. The two worst band
windows are consolidated, not deleted: the `Kitchen Window` becomes a tall
backsplash pane (0.6×1.9 m) over the counter and `Living Band Window N`
becomes one full-height corner pane hard against the W7 corner, so the
feedback #001 corner-glass detail survives and the TV wall stays solid —
each room keeps ≥100% of its glazing while the walls regain 2.6 m of net
length. The remaining gap is closed with four 25 cm URM shear-skin leaves
laid tight against the *outer* face of existing solid stretches — two on
the white south facade flanking the kitchen pane (`Shear Skin South W/E`),
two as pilaster leaves behind the solid stubs flanking the Room 2 slider
(`Shear Skin North E/W`). Outside the slab, so zero interior floor area is
lost and no opening is blocked; the north pair sits on the soft, all-glass
side, which is why e0 drops from 3.57 to 2.46 m and the y-direction
torsion warning clears entirely. A fifth leaf by the entry door was built
and then deleted: stiffening the already-stiff south edge made torsion
*worse* while costing money — the lab notebook (branch history) has the
body.

## 3. Cost table (rates per brief, referee-recomputable)

| Item | Quantity | Rate | € |
|---|---|---|---|
| Load-bearing flags, Room 2 south partitions (no construction) | 2 walls | — | 0.00 |
| Shear Skin South W — new 25 cm URM, 1.95 m × 3.0 m | 5.85 m² | €55/m² | 321.75 |
| Shear Skin South E — new 25 cm URM, 3.55 m × 3.0 m | 10.65 m² | €55/m² | 585.75 |
| Shear Skin North E — new 25 cm URM, 0.80 m × 3.0 m | 2.40 m² | €55/m² | 132.00 |
| Shear Skin North W — new 25 cm URM, 0.80 m × 3.0 m | 2.40 m² | €55/m² | 132.00 |
| Strip footings under the 4 leaves, 7.1 m × 0.4 × 0.5 m | 1.42 m³ | €280/m³ | 397.60 |
| Kitchen Window rework → 0.6×1.9 m backsplash pane | 1.14 m² | €300/m² | 342.00 |
| — masonry infill of the old band | 1.13 m² | €55/m² | 61.88 |
| — demolition cut for the new pane | 1.14 m² | €25/m² | 28.50 |
| Living Band Window N rework → 0.65×2.75 m corner pane | 1.79 m² | €300/m² | 536.25 |
| — masonry infill of the old band | 1.76 m² | €55/m² | 96.94 |
| — demolition cut for the new pane | 1.79 m² | €25/m² | 44.69 |
| **Subtotal** | | | **2,679.36** |
| Site overhead | +15% | | 401.90 |
| **Total** | | | **€3,081.26** |

Rate-table arbitrage, stated openly: a new 25 cm leaf is €55/m² while
thickening the same wall 25 cm costs €112.5/m² (2.5 × €45). Same t·L_net,
half the price — so the design lays leaves, not layers.

## 4. E101 recommendation (structure-type essay — not yet modelled)

URM has no row in EN 1998-1 Table 9.3 at ag·S = 0.18 g; no geometry wins
this. Recommendation: **convert the ground floor to confined masonry** —
it reuses every wall (and every euro) above as-is and is the cheapest
structure type with a code row at this seismicity. Concretely: RC
25×25 cm tie-columns at each end of every primary shear line and at the
jambs of the two large glass openings — SW corner (0,0), kitchen-pane
jambs, stair-tower jambs (6.1,0)/(7.6,0), entry corner (9.5,0), NE corner
(9.5,12), Room 2 slider stubs, (6,8)/(4.5,8) junctions, and the W8/x=4.5
interior bearing line — **12 columns × 3.0 m**, tied by a continuous
25×25 cm RC bond beam at slab level (~50 m), which incidentally is the
Verstärkung the owner deferred when the E062 ring beams were removed.
Confined masonry also lifts q from 1.5 toward 2.0, i.e. cuts the elastic
demand by ~25% before a single extra wall is built. RC wall conversion
(€120/m²) is the fallback only if the national annex rejects confined
masonry for the two all-glass facades.

Allowance (same rates, clearly labelled **not yet modelled — framework
gains structure-type presets next**): 12 tie-columns × 3.0 m × €90 =
€3,240 + bond beam 50 m × 0.0625 m² = 3.13 m³ × €350 = €1,094 → subtotal
€4,334, +15% = **€4,984**.

## 5. What the engineer must verify (and what failed)

- fvd here is a screening value (fvk0 200/γm 1.5 kPa, compression benefit
  dropped, placeholder site ag 0.15 g / ground B pending hazard map and
  geotech). Real masonry class, mortar, and site data may move every
  number; margins quoted are x 6.3%, y 5.9% against the mass-corrected
  demand.
- The skin leaves are counted as independent shear area (fvd·t·L). The
  engine scores exactly that, but on site they must be doweled/keyed to
  the existing walls and to the roof diaphragm to act at all — connection
  detailing is the engineer's, and the leaves need their new strip
  footings tied to the existing ones (footings priced; the framework
  models no footings under on-grade GF walls, matching the existing
  facade convention).
- The two flagged partitions are 12 cm walls; the engineer should confirm
  12 cm URM may be counted as shear wall (EN 1996/1998 minimum thickness
  is NA-dependent) — if rejected, the deleted entry-door leaf goes back
  in (+€199 pre-overhead, and e0 worsens to ~2.59).
- Two E062 waivers ("Kitchen Window", "Living Band Window N") are now
  stale: the reworked panes are narrow enough that no lintel finding
  fires. validation.json is frozen for the arena; prune them after.
- Facade note for the owner: the south face gains a 25 cm ledge standing
  proud of the white roof band (roof not extended — €386 saved); the
  Room 2 slider gains two 25 cm pilasters. Cosmetic, reversible, cheap.
- Tried and failed/rejected: entry-door skin leaf (worsened e0 — removed);
  moving the kitchen window to the west facade (+18 kN x but −40 kN y
  margin my own added mass could not afford); wall thickening (double the
  price of a new leaf per m² of shear area, see §3).
