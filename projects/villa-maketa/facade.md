# Villa Maketa — facade build record

Project-tier record (ADR 004): what THIS villa does with the framework's
[facade finishes](../../specs/facade-finishes.md). Source of truth for the
look: owner's maquette photo, west facade, 2026-08-05 (pool left = north).

## Finish mapping
| Element | finish tag | Material (Cycles + GLB flat fallback) |
|---|---|---|
| All garage exterior walls | `stone_rubble` | procedural rubble masonry: brick texture, randomized stone tint beige/gray/brown (#B8AE9C base), deep mortar #3E362C (photo-sampled #4A4136 washed out under the render's view transform — darkened after the first probe) |
| GF exterior walls | default | white plaster |
| NEW roof (2 Roof elements) | `roof_brown` | fascia+top rust-brown #6E4E33 (photo-sampled #96704F rendered salmon under sun + view transform — darkened after the first probe); white soffit = render-decor plate under the roof |
| Deck/pool/lawn slabs | (unchanged) | existing |

## Geometry
- **Roof** via `Roof` model + `add_roof` (FLAT; IFC places roofs at story
  elevation + height): bounding rect of the GF footprint (covers the deck
  notch too, as in the photo) with 0.6 m overhang: (−0.6,−0.6)–(10.1,12.6).
  Skylight aperture ≈(2.3,9.2)–(4.3,11.2) over the deck: TWO polygons
  (C-shaped west part + east strip) — plain framework primitives, no
  render-time booleans (Gemini plan review).
- **Removable roof, like the maquette's lid**: perspective render + GLB keep
  the roof; the top_down render hides roof objects; the walkthrough toggles
  it with R (dollhouse mode).
- ~~Garage window band~~ REMOVED (owner 2026-08-06): the garage is
  underground — the glazed strip in the photo was a misread of the maquette.
  Do not re-add.
- ~~Accent volume~~ REMOVED (owner 2026-08-06): the yellow box in the photo
  was a misinterpreted facade. Corrected reading: **the SW corner L (South
  Wall + West Wall) is painted yellow outside** (`finish="accent"`, mustard
  #F4C14C, exterior faces only — interiors stay plaster), and **the L's
  windows (Win1/Win2/Win3) run from the roof down to 1.80 m** (sill 1.8,
  height 1.2) so the wall below carries the TV and light falls from above.
- **Sloped render site**: two ground boxes with a step at y≈7.5 — high in
  the north (deck+pool at GF level), low south/west (−3.15) so the stone
  band shows. The white plinth in the photo is the maquette's base board —
  not modeled.
- **Blue glazing tint**: Glass material tinted light blue + low roughness
  for the photo's mirrored-blue look.

## Renderer finish lookup (render_blender.py)
Name-join building.json → OBJ objects (`IfcWallStandardCase_<name>`,
`IfcSlab_<name>`), checked BEFORE the type-default branches. Fail loud:
unknown finish tag, empty tag, duplicate finished names, or a finished
element that doesn't match exactly one imported object → RuntimeError.
GlobalId-in-OBJ-names (Codex suggestion) rejected: it would break the
walkthrough's name-based tag/display map.
Colors: `srgb_hex_to_linear()` feeds Cycles sockets; export_glb.py PALETTE
carries matching linear entries (StoneRubble/Accent/RoofBrown/Soffit).

## Decision log
| Date | Decision | Why |
|------|----------|-----|
| 2026-08-05 | Two-level render ground (step at y≈7.5) instead of one low plane | one low plane leaves deck+pool floating 3 m in the air on the north; the site reads as a slope |
| 2026-08-05 | Accent volume + white soffit as render-only decor | splitting West Wall cascades into E050 alignment + window rehosting (Codex); two stacked Roofs would coincide (IFC pins roofs at story top) |
| 2026-08-05 | Name-join for finish lookup, fail-loud on duplicates/unknown tags | GlobalId-in-OBJ-names breaks the walkthrough's name-based tag map; villa names are unique |
| 2026-08-05 | Roof/mortar colors darkened from photo samples | sun + view transform washed the sampled values to salmon/pale |
| 2026-08-06 | Garage windows removed | garage is underground (owner); photo strip was a misread |
| 2026-08-06 | Accent volume → yellow L walls (South+West) with roof-to-1.8 window band | owner corrected the facade reading; volume was never real geometry |
| 2026-08-06 | Wall finishes paint EXTERIOR faces only (normal vs plan centroid) | "yellow from outside" — interiors stay plaster; also fixes stone leaking into the garage interior |
| 2026-08-06 | West wall living stretch (y4.5–8) = floor-to-ceiling glazing (Win2 slot reused in place as "Living Glass Wall" — tags stable); TV sideboard moved to the north wall | owner: "the yellow wall is part concrete part glass"; photo #20's big panes sit on the north half |
| 2026-08-06 | Stair tower shell + recessed garage face (photo #22) | tower = hollow C-shell render decor at (6.85,0) r0.92, full height; model truth = the straddling staircase + split walls; E050 ×2 waived for the cantilever |
| 2026-08-06 | W6 east half = floor-to-roof glass (Win4 slot, w2.0), west half solid yellow wrapping into W7; band windows Win1/Win2/Win7 sill 2.05 (= true 1.80 above the floor — model sills start at the wall base, 0.25 below the slab top; caught by the owner with the measure tool) with head 2.80 matching Win4's reveal | owner corrections; the solid W6 half is the TV wall — resolves the print's "crossed unit" question (L-6) |
| 2026-08-06 | Win3 = full-height glass from Win2's end to the white south third; west-facade south third + W1 + W15 are WHITE (yellow = W6 west half + W7 only); W16 "West Wall South" split off (garage mirror W9) | owner corrections via photos #21/#26 |
| 2026-08-06 | Roof = TWO clean rectangles, tops flush at 3.45: brown (y2.7–12.6, overhang, skylight) + white south band (flush with the wall faces, NO overhang). No raised parapet, no soffit boards — the intermediate readings (0.75 parapet, wrap-around brown, soffit under-boards) were owner-rejected | verified from the owner's own P-shot camera |
| 2026-08-06 | ALL windows glaze `pane_side="inner"` (thin 6 cm pane flush with the interior face — [specs/window-glazing-placement.md](../../specs/window-glazing-placement.md)); framework default stays outer | old full-thickness window boxes read as double windows 30 cm apart (owner); maquette photo #28 shows the panes recessed to the inner face, the yellow volume and roof floating over the glass |
| 2026-08-06 | Glass terrace doors D8/D9 = thin pane `pane_side="outer"` (flush with the deck facade); D3 and opaque doors keep the full-thickness leaf | same double-pane bug as the windows (owner); owner picked outer here |

## Related
[specs/facade-finishes.md](../../specs/facade-finishes.md) (framework
contract) · [spec.md](spec.md) · [maquette-alignment.md](maquette-alignment.md)
