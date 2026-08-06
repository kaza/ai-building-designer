# Feature: Facade finishes (per-element color/texture)

## Status
implemented (2026-08-05)

## Why this exists
The owner's maquette (photo 2026-08-05, west facade) has a designed exterior:
rubble-stone garage band, mustard accent volume, brown-fascia roof with a deep
overhang, blue reflective glazing. Our model renders every wall as identical
white plaster — the exterior reads as an untextured massing model. The owner
asked to "make the details look exactly like this; add whatever is required in
the framework to have color and texture of the facade (for above and garage
below)".

## What it does
### Framework (src/archicad_builder)
- `Wall.finish: str | None`, `Slab.finish: str | None`, `Roof.finish: str |
  None` — an optional, free-form finish tag (e.g. `"stone_rubble"`,
  `"accent"`, `"roof_brown"`). `None` = renderer default (unchanged behavior).
- `Building.add_wall(...)`/`add_slab(...)`/`add_roof(...)` accept `finish=`.
- Persisted in building.json only; `Building.save` excludes None fields so
  existing files stay byte-identical for elements without a finish.
- Semantics: the framework stores the tag; projects' renderers own the
  tag→material mapping and MUST fail loud on a tag they don't know
  (fail-fast against typos — Gemini plan review 2026-08-05). The framework
  never validates tag names.

### Villa project (projects/villa-maketa)
Mapping the maquette photo (west facade; pool left = north):
| Element | finish tag | Material (Cycles + GLB flat fallback) |
|---|---|---|
| All garage exterior walls | `stone_rubble` | procedural rubble masonry: brick texture, randomized stone tint beige/gray/brown (#B8AE9C base), deep mortar #3E362C (photo-sampled #4A4136 washed out under the render's view transform — darkened after the first probe) |
| GF exterior walls | default | existing white plaster |
| Accent volume walls (S end of west facade per photo) | `accent` | mustard #F4C14C, roughness 0.5 |
| NEW roof (2 Roof elements) | `roof_brown` | fascia+top rust-brown #6E4E33 (photo-sampled #96704F rendered salmon under sun + view transform — darkened after the first probe); white soffit = render-decor plate under the roof |
| Deck/pool/lawn slabs | (unchanged) | existing |

Geometry additions (villa build.py + render_blender.py):
- **Roof** via the existing `Roof` model + `add_roof` (FLAT; IFC already
  places roofs at story elevation + height): bounding rect of the GF
  footprint (covers the deck notch too, as in the photo) with 0.6 m overhang:
  (−0.6,−0.6)–(10.1,12.6). Skylight aperture ≈(2.3,9.2)–(4.3,11.2) over the
  deck: composed from TWO polygons per layer (C-shaped west part + east
  strip) — plain framework primitives, no render-time booleans (Gemini).
  Each layer is doubled: 0.05 white soffit board (`roof_soffit`) under a
  0.20 brown slab (`roof_brown`) — gives the photo's white underside without
  per-face material hacks (Codex: one object = one material).
- **Removable roof, like the maquette's lid**: perspective render + GLB keep
  the roof; the top_down render hides roof objects (interior views stay
  useful).
- **Garage window band**: 2 windows on the garage west wall, width 1.8,
  positions 2.2 and 4.6 (from wall start (0,8)), sill 1.4, height 0.8 — real
  Window elements; fits the 2.89 wall, no perpendicular-wall crossings.
- **Accent volume** (yellow box, south end of west facade): render-level
  decor volume in render_blender.py (≈(−0.5,0.4)–(0.05,2.6), z 0.45–2.45,
  mustard) tagged as facade decor. NOT building geometry: splitting West Wall
  would cascade into E050 vertical-alignment + Win2/Win3 rehosting (Codex);
  the maquette itself has it as a glued-on box. Revisit if the owner wants a
  real bay.
- **Exposed garage**: render ground plane drops to garage floor level (−3.15)
  so the stone band is visible, matching the maquette on its table. The white
  plinth in the photo is the maquette's base board — not modeled.
- **Blue glazing tint**: existing Glass material gets a light blue tint +
  higher reflectivity to match the photo's mirrored-blue look.

Renderer finish lookup: name-join building.json → OBJ objects
(`IfcWall_<name>`, `IfcSlab_<name>`), checked BEFORE the type-default
branches; unknown finish tag or duplicate finished name → RuntimeError
(fail loud). GlobalId-in-OBJ-names (Codex suggestion) rejected: it would
break the walkthrough's name-based tag/display map.
Colors: one `srgb_hex_to_linear()` helper feeds both Cycles sockets and the
GLB flat palette (Codex: sRGB hex ≠ linear socket values); export_glb.py
palette gains StoneRubble/Accent/RoofBrown/RoofSoffit entries.

## Boundaries
- No terrain modeling (slopes, driveway cut) — ground is one flat plane at
  garage level. Revisit when the owner wants site context.
- No IFC transport of finish at all — the Blender renderer reads finishes
  from building.json (names are the join key with OBJ objects); putting the
  tag in IFC would be dead code (Gemini plan review 2026-08-05).
- The GLB/walkthrough gets flat baseColor approximations of the finishes
  (procedural textures don't survive glTF export — existing flatten path).
- 2D floor plans ignore finishes entirely.

## Testing
- Framework: unit tests — finish persists through Building save/load
  round-trip; add_wall/add_slab forward it; None default keeps old JSON
  loading (backward compat with existing building.json files).
- Villa: rebuild + validate green; render smoke via existing probe screenshots.

## Open questions
none blocking — colors sampled from the photo; owner review of the first
render decides fine-tuning.

## Decision log
| Date | Decision | Why |
|------|----------|-----|
| 2026-08-05 | Free-string finish tag, not an enum | projects own their material vocabularies; framework stays generic |
| 2026-08-05 | ~~IfcPresentationLayerAssignment for transport~~ superseded: building.json-only | the renderer never reads IFC for finishes — IFC transport would be dead code (Gemini) |
| 2026-08-05 | Roof hole cut in Blender, not in the Slab model | Slab has no hole support; stairwell precedent; adding polygon holes to the model is a separate framework feature |
| 2026-08-05 | Two-level render ground (step at y≈7.5) instead of one low plane | one low plane leaves deck+pool floating 3 m in the air on the north; the site reads as a slope |
| 2026-08-05 | Accent volume + white soffit as render-only decor | splitting West Wall cascades into E050 alignment + window rehosting (Codex); two stacked Roofs would coincide (IFC pins roofs at story top) |
| 2026-08-05 | Name-join for finish lookup, fail-loud on duplicates/unknown tags | Codex proposed GlobalId-in-OBJ-names, but that breaks the walkthrough's name-based tag map; villa names are unique |
