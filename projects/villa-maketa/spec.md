# Villa Maketa — v1

> **Project implementation record** (tier 2), not a framework spec — see
> [ADR-004](../../specs/decisions/004-framework-vs-project-spec-split.md).
> Product intent lives in [`specs/`](../../specs/); this file records what was actually built
> for this one building: dimensions, assets, pipeline order, verification commands.

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
| 2026-08-08 | Ring beams (E062): upstand segments over all 6 wide GF openings + the garage door, `add_beam_over` defaults (span/10, min 0.35; Win6 gets 0.55 deep, z_top 3.35 — hidden in the roof-edge zone); corner openings' beams extend past the wall end like real ring beams | [structural-plausibility.md](../../specs/structural-plausibility.md); the load-takedown experiment's fix, owner: "armatura" |
| 2026-08-08 | Garage rebuilt as Option A: x4.5-9.5 × y0.6-8 (~37m², 2 cars), vehicle door moved to the EAST wall (south face segments beside the stair shaft are 1.6/1.9m — a 2.4m door no longer fits); garage perimeter sits exactly under GF bearing lines x4.5/x9.5/y8; "Living East Wall" (x=4.5) marked load-bearing — the interior bearing line halves the E/W roof spans; 2 stale E050 waivers retired | owner picked A from rendered variants; enabled by the E050 partial-basement fix ([storey-datum.md](../../specs/storey-datum.md)); load-takedown attempt 04: Win6 144x→95x, Win2 25x→15x — engineered ring beams still required (future E06x) |
| 2026-08-08 | Win8 (Room 2 east clerestory, was feedback #024) removed — solid wall again | owner order after the load-takedown experiment flagged its 3.85m band at 79x plain utilization (experiments/2026-08-08_static-load-takedown) |
| 2026-08-08 | Toilets height-scaled (cloud feedback #4, from the owner's phone): `scale_by: height`, h 0.60, slots resized to the Kenney asset's honest footprint (0.42x0.63) | footprint-only scaling made them squat — same class as the #027 kitchen modules |
| 2026-08-07 | Deck Screen Return N (feedback #032): solid stone return wall (0,14)→(0.5,14), h 1.25 (= balustrade height), t 0.12 — the screen line ended at the deck NW corner while the deck edge ran 0.5m further to the pool's west corner, leaving an unguarded drop | owner circled the corner: "there should be a wall here, the height is the same as the glass fence" |
| 2026-08-07 | Room 2 north face rebuilt to maquette photo #31: centered 2-pane glass slider (fixed Win5 1.1 + sliding glass D7 1.1, both head 2.80, exact adjacency at position 1.75) with 0.65m wall stubs BOTH sides; old edge-to-edge Win5 1.85 + swing door 1.4 replaced in place (tags stable); stale W060 waiver dropped; plan reviewed by Gemini | owner: "glass doors, but a bit of walls on both sides" |
| 2026-08-06 | Storey-datum flip applied ([storey-datum.md](../../specs/storey-datum.md), feedback #013/#014): slabs now hang below their datum. Villa fallout: deck/pool/lawn tops drop from +0.15 to 0.0 (flush with GF floor), garage FFL = −2.8 (walls no longer buried 25 cm), renderer `SLAB_TOP` 0.25→0, six furniture items with absolute z shifted (sink 1.15→0.90, deck set 0.15→0), spiral stair drop 2.0→2.8 (now reaches the garage floor) and deduplicated (was built twice, once per storey) | walls/doors started 25 cm inside the ground slab — visible from inside the slab, wrong in any section drawing |
| 2026-08-05 | Full realignment to the printed maquette plan: D8 split into a 0.9+0.5 inward glass pair (D8/D9), D3 flipped south into Bath 1, D5 to the SE corner, both baths refitted, living/dining/kitchen furniture repositioned | photo comparison by 4 independent readers — full discrepancy table + owner questions in [maquette-alignment.md](maquette-alignment.md) |
| 2026-08-05 | SW pantry (reviewers' read of 15.png) added, then REMOVED same day on owner veto | owner decides what rooms exist, not photo inference — logged in maquette-alignment.md |
| 2026-08-06 | Spiral stair straddles the south facade at (6.1,−0.75)–(7.6,0.75); South Wall split around it (east segment = W15, hosts D1); cylindrical tower shell rendered project-side | maquette photo #22 — the stair tower is half outside the house |
| 2026-08-06 | Garage south face inset to y=0.6 (GF cantilevers over it); 2× E050 waived | maquette photo #22 — recessed carport-style entry; side walls keep full length so the stone reaches the corners |
| 2026-08-06 | Cycles renders opt-in (`VILLA_FULL_RENDER=1`); GLB + walkthrough regenerate every run | owner: the walkthrough website is the product |
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

Product vision and roadmap live in the FRAMEWORK spec:
[specs/browser-walkthrough.md](../../specs/browser-walkthrough.md). This section
is the villa v1 implementation record.

Goal (v1): fly through the villa with WASD + mouse (pointer lock), default
lighting good enough to read the space.

| # | Piece | How |
|---|---|---|
| 1 | `export_glb.py` | Blender headless: load `output/villa.blend`, drop render-only helpers (cameras, sky), make materials glTF-safe (procedural textures don't export — set a flat per-material `baseColorFactor` from a name→color map, same palette as render_blender.py), export `output/villa.glb` |
| 2 | `make_walkthrough.py` | plain-Python templating: validates the GLB container and writes `output/walkthrough.html` — Three.js (pinned CDN import map), `PointerLockControls`, WASD + mouse look, Shift = fast, Space/C = up/down; `HemisphereLight` + `DirectionalLight` sun; start camera at the SE entrance looking north; loads `./villa.glb` at runtime |
| 3 | Pipeline | two new steps after the Blender render (order matters: reads villa.blend) |
| 4 | `serve.py` | serves `output/` (port 8123) + `POST /feedback`: the F key freezes the view, the owner draws screen-space strokes and comments, the page POSTs a composite PNG + meta.json (camera pose, `#debug=` hash, normalized strokes with raycast element tags, comment) → `feedback/<NNN>/` (project level — owner input, not a regenerable artifact); PNG download fallback when the POST fails |

Decisions:
- **Free-fly, no collision** — walking + wall collision is backlog; free-fly answers
  "how does the space feel" today (two-way door).
- **Separate villa.glb, fetched at runtime** (owner decision 2026-08-05,
  supersedes the original base64-embedded single file): the walkthrough will be
  served from a webserver as a product feature, and a separate GLB streams,
  caches, and scales to textured furniture — an embedded blob does none of that.
  Browsers block fetch() from file://, so local viewing needs
  `python3 -m http.server 8000 -d projects/villa-maketa/output` →
  http://localhost:8000/walkthrough.html; the page detects file:// and prints
  exactly that instead of failing silently. Three.js itself comes from CDN,
  pinned import map (needs internet).
- **Materials as flat colors** — procedural shaders can't ride along into glTF without
  baking; flat colors are enough to tell floor from wall from pool. Baking = backlog.
  Unmapped procedural materials turn MAGENTA + a stdout warning (review finding, Gemini).
- **Glass keeps transmission** (KHR_materials_transmission, supported by Three.js) —
  no alpha-hack (review finding, Codex).
- ~~**Open top accepted**~~ superseded 2026-08-06: the villa gained a real
  roof ([facade.md](facade.md)); the walkthrough compensates with
  **dollhouse mode — R toggles the roof group** (roof slabs, soffit boards),
  mirroring the maquette's removable lid. Hidden roofs are skipped by
  info/measure raycasts (Three.js raycasting ignores `.visible` on its own).
  Test seam `?roof=0`, honored only under `#debug` — same rule as `?measure`.
- **`#debug[=x,y,z[,yawDeg]]` URL hash** skips pointer lock and places the camera —
  used for headless-Chrome screenshot verification and future triage.

## Furniture v2 — CC0 assets + 2D plan symbols

Owner request 2026-08-05: "standard open source furniture … in floor layout and
improved rendering". Two deliverables:

| # | Piece | How |
|---|---|---|
| 1 | `fetch_assets.py` | downloads a PINNED list of CC0 models from the Poly Haven API (`api.polyhaven.com/files/<id>`, glTF + 1k textures) into `assets/<id>/` (gitignored — reproducible via script, not committed binaries) |
| 2 | `furniture.json` | items gain optional `"asset": "<id>"`; items without it keep today's procedural boxes (per-item migration) |
| 3 | `render_blender.py` | asset loader: import glTF, uniform-scale to the item's footprint, drop to floor z, rotate per `facing`; fallback = existing procedural path |
| 4 | `render_furnished_plan.py` | parametric matplotlib symbols per type (bed w/ pillows + fold at the `head` edge, sofa backrest + cushions, toilet oriented by `facing`, sink, shower X, tub with drain, table + chairs, wardrobe rail) replacing plain rectangles — backlog #6 done in the same pass |
| 5 | Walkthrough | no code change — the page fetches `villa.glb` at runtime, and export_glb.py preserves TEX_IMAGE materials; GLB grew 0.6 → 8.5MB with 1k textures, fine for the separate-file delivery |

**Asset set v2 (owner, 2026-08-05: "modern, not Louis XIV — procedural is
banned"):** Poly Haven's furniture is largely antique, so the modern pieces
come from **Objaverse** (HuggingFace rehost of Sketchfab models; ~70 models
auditioned via headless-Blender thumbnail contact sheets). Current mapping:

| Item(s) | Asset | Source / license |
|---|---|---|
| Sofa L (one sectional replaces both L pieces) | Escuadra Victoria Izquierda II | Objaverse, CC-BY (Pablo.Portela) |
| Master + Room2 beds (incl. nightstands) | Stylized lowpoly bed | Objaverse, CC-BY (tharadelamo) |
| Dining chairs ×6 | Silla (navy cantilever) | Objaverse, CC-BY (gabymrtnz) |
| Dining table | 653 (white pedestal) | Objaverse, CC-BY (GulinAlex) |
| Deck sofa | Feathers 5 Seat | Objaverse, CC-BY (mohitoz) |
| Master desk (+ desk chair = Silla) | Meja Komputer | Objaverse, CC-BY (sutikno) |
| Armchair | mid_century_lounge_chair | Poly Haven, CC0 |
| Coffee table | modern_coffee_table_01 | Poly Haven, CC0 |
| TV sideboard | modern_wooden_cabinet | Poly Haven, CC0 |

**CC-BY obligation:** authors are recorded in `assets/licenses.json`; when the
walkthrough ships as a product page, a visible credits section is REQUIRED.
Objaverse GLBs are pinned by uid + sha256 in fetch_assets.py. Sketchfab models
have no orientation standard — `ASSET_NATIVE_FACING` in render_blender.py
records each model's verified native direction (four face −Y; `platform_bed`
faces **+X** — the nightstands' world positions are what proved it, after the
"head north" assumption survived two visual checks because head-west looked
plausible in both bedrooms. Verify orientation against a known off-center child
object, not against the silhouette).
Still procedural (acceptable, revisit on demand): kitchen counters, wardrobes,
sanitary ware, loungers, deck tables.
outdoor_table_chair_set_01 was dropped earlier — a combined table+chairs set
scaled into a 0.9m deck-table footprint turns into dollhouse furniture.
Plan-review decisions (Gemini + Codex, 2026-08-05):
| Decision | Why |
|---|---|
| Poly Haven standard trusted: origin at base, faces −Y → facing map S 0°/E +90°/N 180°/W −90°, no manual axis correction | documented PH technical standard; each asset visually validated once |
| Fit = facing rotation FIRST, then evaluated-mesh world bounds, uniform `scale = min(w-ratio, d-ratio)`, center XY, ground by mesh `min_z` | object origins lie; aspect ratios differ — containment beats stretching |
| Our procedural materials get a `ab_procedural` custom property; export_glb flattens ONLY tagged ones | name-based palette matching breaks on imported material name collisions (Codex) |
| export_glb keeps EMPTY objects that have children | blanket empty-pruning would orphan imported asset hierarchies |
| Import once per asset, linked-duplicate hierarchies per instance; prototype becomes the first instance | no stray prototype at origin; memory-cheap repeats (6 chairs) |
| Fetcher: atomic tmp→rename, md5-verified, User-Agent header, `.complete` marker, auto-generated `licenses.json` | aborted downloads must not pass the cache check (Gemini) |
| 2D symbols edge-parametrized per N/S/E/W facing, drawn directly in data coords | everything is axis-aligned, so per-edge geometry needs no rotation transform at all (simpler than the Affine2D route Codex suggested) |

W100 door-swing gate ([framework spec](../../specs/furniture-door-clearance.md)):
`check_furniture.py` builds footprints from furniture.json (id = item name,
made unique with `#n` on duplicates), runs the GF check, exits 1 on findings —
pipeline step 10. The very first run found **5 real violations** (0.18–0.71 m²);
fixes: both 1.4 m terrace doors became outward-swinging (architecturally
correct for deck doors — later superseded for D8 by the maquette-alignment
inward pair), Master desk, Room2 wardrobe and both loungers moved.
| Rejected: separate Eevee "asset test grid" script | placement logging + existing top-down render covers it (YAGNI) |

## Backlog
- Furniture in IFC (IfcFurnishingElement) if ArchiCAD needs it
- Walkthrough: walk mode with gravity + wall collision; baked textures in the GLB
- Quaternius/Kenney low-poly packs if we ever want a stylized asset set

## How to build / verify

```bash
.venv/bin/python projects/villa-maketa/build.py   # regenerates building.json
.venv/bin/python -m archicad_builder validate villa-maketa
.venv/bin/python -m archicad_builder render villa-maketa
```

## Rendering & viewing

One command (specs/project-pipeline.md) — it knows the order, skips what
it can prove is unchanged, and refuses to let a stale artifact reach the
publish step:

```bash
.venv/bin/python -m archicad_builder pipeline villa-maketa      # everything
.venv/bin/python -m archicad_builder pipeline villa-maketa --list   # just the order
.venv/bin/python -m archicad_builder freshness villa-maketa     # publishable?
```

The order lives in `pipeline.toml` (13 steps, each declaring what it
reads and writes), not in this document — a hand-written list drifts,
and this one did: it used to omit `loads` and `fem` even after
publishing started refusing a mismatched `fem-field.json`. A full clean
run is ~13 min (Blender ~1 min, FEM ~8 min); a no-op re-run is ~2 s.

The `blend` step is CHEAP by default (owner 2026-08-06: the walkthrough is
the product, regenerated every run; the ~4 min Cycles PNGs are opt-in): it
saves villa.blend and stops. `VILLA_FULL_RENDER=1` also renders
perspective.png + top_down.png — the step declares that variable, so
flipping it re-runs the render instead of silently reusing the cheap one.

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
| `walkthrough.html` | browser walkthrough (WASD + mouse, free-fly); fetches `villa.glb` — serve the folder: `python3 -m http.server 8000 -d projects/villa-maketa/output` |

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
