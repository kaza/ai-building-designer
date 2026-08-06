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
- **Accent volume** (mustard box, south end of west facade, #F4C14C):
  render-level decor volume in render_blender.py (≈(−0.5,0.4)–(0.05,2.6),
  z 0.45–2.45). NOT building geometry: splitting West Wall would cascade
  into E050 vertical-alignment + Win2/Win3 rehosting (Codex); the maquette
  itself has it as a glued-on box. Revisit if the owner wants a real bay.
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

## Related
[specs/facade-finishes.md](../../specs/facade-finishes.md) (framework
contract) · [spec.md](spec.md) · [maquette-alignment.md](maquette-alignment.md)
