# Villa Maketa — v1

Single-storey villa reconstructed from a physical cardboard maquette (photo, 2026-08-03).
North part of the maquette (pool + deck terrace) is out of scope for v1.

## What it is

L-shaped footprint, ~9.5 × 12m (wall centerlines), one storey at elevation 0.
Entrance at south-east, staircase down to garage (garage level itself is backlog).

```
      N
┌─────────────┬────────┬─────┐ y=12
│   TERRACE   │ ROOM 2 │     │
│  (backlog)  │ 3.5×4  │     │
├──────────┬──┴────────┤     │ y=8
│          │  MASTER   │  H  │
│  LIVING  │  3.5×3    │  A  │ y=5
│  4.5×5.5 ├─────┬─────┤  L  │
│          │BATH1│BATH2│  L  │ y=2.5
├──────────┤ passage   │     │
│ KITCHEN  ├─[STAIR↓]──┤     │ y=1.5/0
└──────────┴───────▲───┴──▲──┘ y=0
      S         stair   entrance
x:0        4.5   5→7.6  8   9.5
```

## Dimensions (from owner, wall centerlines)

| What | Value | Source |
|---|---|---|
| Living column width (E-W) | 4.5m | owner |
| Master column width (E-W) | 3.5m | owner |
| Hallway width (E-W) | 1.5m | owner |
| South wall → living north wall | 8m | owner |
| North band (Room 2 / terrace) | 4m | owner |
| Storey height | 3.0m (2.63m clear) | default; E001 needs ≥2.5m clear |
| Exterior / interior walls | 0.30m / 0.12m | default |

Given dimensions are treated as centerline distances (clear dims ~0.2–0.4m less). Owner
gave rough numbers; acceptable.

## Rooms (one apartment, "Vila")

| Space | Type | Bounds (x, y) | ~Area |
|---|---|---|---|
| Kitchen (open plan) | kitchen | 0–4.5, 0–2.5 | 11.3 |
| Living/Dining | living | 0–4.5, 2.5–8 | 24.8 |
| Bath 1 (en-suite) | bathroom | 4.5–6.58, 2.5–4.5 | 4.2 |
| Guest Bathroom | toilet | 6.58–8, 2.5–4.5 | 2.8 |
| Master Bedroom | bedroom | 4.5–8, 4.5–8 | 12.2 |
| Room 2 | bedroom | 6–9.5, 8–12 | 14.0 |
| Hallway (entry + circulation, L-shaped) | hallway | see build.py | ~12 |
| Stair to garage | staircase | 5–7.6, 0–1.5 | 3.9 |

Room 2 has two doors (per maquette close-up): south → hallway, north → terrace/deck
(exterior door near the west corner). Its window is in the east facade. Wardrobe along
the east wall is furniture — not modeled.

Master (per maquette close-up): double French doors (1.4m) onto the deck on the north
segment — no window. Bath 1 is the master **en-suite**, entered from the bedroom;
guests use the hallway WC. White T-shaped piece east of master unidentified (Q: table?)
— not modeled.

Owner changes 2026-08-04 (glass north face + TV wall):
- D7 (Room 2 → pool deck) widened to a 1.4m double door; beside it the rest of
  W3 is a floor-to-ceiling sliding glass door (Win5, 1.85m, sill 0.05).
- W6 (living north wall): full-width 4.2m sliding window (Win4, sill 0.15,
  height 2.5). Sofa L long faces it (north); coffee table between.
- West wall = TV wall: Win2/Win3 are clerestory bands (sill 1.80, top 2.55) —
  natural light from above, TV sideboard below.
- D5 (master door) sits 60cm from Master South Wall (W12).
- "window w6" in the owner's dictation interpreted as the window ON wall W6
  (= Win4) — consistent with "sofa looks toward it"; hallway window Win6
  unchanged.
Master gets its window on the short exterior north segment (x 4.5–6, faces terrace).
Kitchen↔Living is open plan — no wall between them.

## Decisions

| Date | Decision | Why |
|---|---|---|
| 2026-08-03 | Straight-run stair, not spiral | Model has no spiral type; backlog |
| 2026-08-04 | Spiral stair (SPIRAL_STAIR, 1.5×1.5m) replaces the straight run | matches the maquette; renderer support added (specs/spiral-stair-rendering.md) |
| 2026-08-03 | Garage level not modeled in v1 | Focus on main floor; stair placed, leads down |
| 2026-08-04 | Garage storey added: full L-footprint basement at −2.89m (2.52m clear), 2.4m vehicle door on the south wall, spiral shaft aligned with GF | E050 demands every GF load-bearing wall aligned below → basement mirrors the perimeter |
| 2026-08-04 | E011/E012/E013 waived for the villa | enclosed fire-core, 1.2m flight width and "stories[0] is ground" are block assumptions; E013+basement is a framework finding (ground floor should be the storey at elevation 0) |
| 2026-08-03 | Room 2 in v1 (not backlog) | Owner: "prava soba", part of the 12m depth |
| 2026-08-03 | No storage room in v1 | No obvious spot; expect completeness warning |
| 2026-08-03 | Second bath modeled as WC (toilet type) | E045 requires separate WC for 2+ bedrooms; maquette's 2nd bath has WC fixtures |
| 2026-08-04 | Guest bathroom ≥1.30m CLEAR between W11 and W9; shower 0.8×1.3 spans it | owner requirement; divider wall centerline at x=6.58 |
| 2026-08-04 | Bath 1 shrinks to 4.2m² (E041b warning accepted) | consequence of the 1.30m guest bath; en-suite, not adaptable housing |
| 2026-08-04 | Furnished plan via overlay script (`render_furnished_plan.py`) | reuses repo renderer, no repo change; sanitary ware + furniture from furniture.json |
| 2026-08-03 | Validators: Austrian-block rules that don't fit a villa are accepted as warnings | Villa ≠ Wohnblock |

## Preview v2 (maquette-look renders)

Goal: renders that read like the physical maquette photo. Approach — all at the
**render/project layer**, no ai-building-designer source changes:

| # | Feature | How |
|---|---|---|
| 1 | Top-down ortho view | second camera in render_blender.py → `top_down.png` |
| 2 | Materials per room/element | colored floor planes generated from building.json spaces; wall/door/window/deck materials by name |
| 3 | Deck + pool + lawn | plain Slab elements in build.py (named Deck/Pool/Lawn), colored by name in render; export to IFC as slabs |
| 4 | Furniture | `furniture.json` (axis-aligned boxes: type, bounds, height) rendered in Blender only — not in IFC, not in 2D plan (yet) |

Decisions: materials and furniture live at render layer because we have exactly one
villa (YAGNI); promote into the data model / IfcFurnishingElement only when a second
project needs them.

**Preview v3 (2026-08-04, "make it great"):** procedural shaders (plank wood via
wave texture, tiles with grout via brick texture, water, grass, plaster bump);
sky-model lighting + explicit sun; window frames (planar-dissolve + wireframe
modifier — plain wireframe draws triangulation diagonals as an X); procedural
furniture (beds with mattress/duvet/pillows, sofas with cushions, tables with
legs, counters with tops; everything beveled); per-shot exposure; perspective
camera moved to the pool side (NE) — an all-white frame has no contrast anchor.
Hard-won lesson: Blender 5 defaults to the AgX view transform, which desaturates
everything to pastel — set "Khronos PBR Neutral" (or Filmic) for arch-viz.

## Walkthrough web app (v1 — free-fly)

Goal: open one HTML file in a browser and fly through the villa with WASD + mouse
(pointer lock), default lighting good enough to read the space. Owner request 2026-08-05.

| # | Piece | How |
|---|---|---|
| 1 | `export_glb.py` | Blender headless: load `output/villa.blend`, drop render-only helpers (cameras, sky), make materials glTF-safe (procedural textures don't export — set a flat per-material `baseColorFactor` from a name→color map, same palette as render_blender.py), export `output/villa.glb` |
| 2 | `make_walkthrough.py` | plain-Python templating: base64-embed `villa.glb` into an HTML file with Three.js (CDN import map), `PointerLockControls`, WASD + mouse look, Shift = fast, Space/C = up/down; `HemisphereLight` + `DirectionalLight` sun; start camera at the SE entrance looking north; writes `output/walkthrough.html` |
| 3 | Pipeline | two new steps after the Blender render (order matters: reads villa.blend) |

Decisions:
- **Free-fly, no collision** — walking + wall collision is backlog; free-fly answers
  "how does the space feel" today (two-way door).
- **Single self-contained HTML with base64 GLB** — the GLB came out at 594KB
  (798KB HTML); double-click beats running a local web server. Three.js itself
  comes from CDN, pinned import map (needs internet).
- **Materials as flat colors** — procedural shaders can't ride along into glTF without
  baking; flat colors are enough to tell floor from wall from pool. Baking = backlog.
  Unmapped procedural materials turn MAGENTA + a stdout warning (review finding, Gemini).
- **Glass keeps transmission** (KHR_materials_transmission, supported by Three.js) —
  no alpha-hack (review finding, Codex).
- **Open top accepted** — the villa has no roof/ceiling modeled; looking up = sky.
  That IS the maquette look; a roof is a modeling task, not a walkthrough task.
- **`#debug[=x,y,z[,yawDeg]]` URL hash** skips pointer lock and places the camera —
  used for headless-Chrome screenshot verification and future triage.

## Backlog
- Furniture symbols + room colors in the 2D matplotlib plan (#6)
- Furniture in IFC (IfcFurnishingElement) if ArchiCAD needs it
- Walkthrough: walk mode with gravity + wall collision; baked textures in the GLB

## How to build / verify

```bash
.venv/bin/python projects/villa-maketa/build.py   # regenerates building.json
.venv/bin/python -m archicad_builder validate villa-maketa
.venv/bin/python -m archicad_builder render villa-maketa
```

## Rendering & viewing

Full pipeline — ORDER MATTERS (`ifc_to_obj` reads the IFC, so export first):

```bash
.venv/bin/python projects/villa-maketa/build.py                        # 1. JSON
.venv/bin/python -m archicad_builder validate villa-maketa             # 2. gate
.venv/bin/python -m archicad_builder render villa-maketa               # 3. 2D plan
.venv/bin/python projects/villa-maketa/render_furnished_plan.py        # 4. 2D + furniture
.venv/bin/python -m archicad_builder export villa-maketa               # 5. IFC
.venv/bin/python projects/villa-maketa/ifc_to_obj.py                   # 6. OBJ for Blender
/Applications/Blender.app/Contents/MacOS/Blender -b -P \
    projects/villa-maketa/render_blender.py                            # 7. 3D renders + blend
/Applications/Blender.app/Contents/MacOS/Blender -b \
    projects/villa-maketa/output/villa.blend \
    -P projects/villa-maketa/export_glb.py                             # 8. GLB (reads villa.blend)
.venv/bin/python projects/villa-maketa/make_walkthrough.py            # 9. walkthrough HTML
```

Outputs (all in `output/`, gitignored, regenerable):

| File | What |
|---|---|
| `floor_ground_floor.png` | architectural 2D plan (dims, labels) |
| `floor_ground_floor_furnished.png` | 2D plan + furniture/sanitary overlay |
| `perspective.png` | 3D pool-side perspective (Cycles) |
| `top_down.png` | orthographic maquette view |
| `villa-maketa.ifc` | BIM model (ArchiCAD/Revit/FreeCAD) |
| `villa.blend` | interactive scene with materials/furniture |
| `villa.glb` | flat-color glTF for the walkthrough |
| `walkthrough.html` | self-contained browser walkthrough (WASD + mouse, free-fly) |

Viewers:

| Viewer | How | Notes |
|---|---|---|
| **Blender** (best) | `open output/villa.blend`, press **Z → Material Preview** (viewport defaults to grey Solid) | full materials + furniture; **Rendered** mode = Cycles live |
| **FreeCAD** | `open -a FreeCAD output/villa-maketa.ifc`; in the IFC Import Options dialog keep "Load the shape", OK; if the tree shows one node, expand it; View → Fit All | GUI `Gui.open` can fail from startup scripts — `output/show_villa.py` imports via `nativeifc.ifc_import` directly |
| **Autodesk Viewer** (web) | upload `villa-maketa.ifc` to viewer.autodesk.com | free account; shareable link |

## Lessons learned

- Validators match by NAME: E022 needs a wall with "corridor" in its name; E070/E031
  need doors named "<apartment> <room> Door" / "<apartment> Entry Door".
- Pass `is_external=True` to `Building.add_wall()` for facade walls — E044 relies
  on the flag.
- E044 previously checked only north/south facades of the bounding box → false
  positives for Living and Master. Fixed 2026-08-04 (specs/facade-detection.md).
- W001 targets exactly 2.52m clear height (block economics); villa keeps 2.63m → noise.
- glTF `export_apply=True` can't realize a modifier whose target object was already
  deleted — the first walkthrough GLB shipped WITHOUT the stairwell hole (Codex code
  review caught it by counting Ground_Slab vertices; the "looks right" screenshot
  didn't). export_glb.py now applies helper-dependent modifiers before pruning, and
  verification counts vertices instead of eyeballing.

## Accepted validation results

**0 errors, 0 warnings, 5 waived, 0 stale.** The E044 false positives were fixed in
the framework (specs/facade-detection.md); the remaining villa-vs-block noise is
waived with reasons in `validation.json` (specs/validation-waivers.md).
