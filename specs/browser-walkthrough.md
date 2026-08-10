# Feature: Browser walkthrough (product vision + v1)

## Status
v1 implemented at project layer (villa-maketa); framework integration is roadmap.

## Why this exists (the vision)
The framework's ultimate preview is not a PNG — it's a **"wow" moment in the
browser**: the user designs a building (JSON → validators → IFC) and then
*walks through it* game-style (WASD + mouse), served from a webserver, no
install. Every rendering feature we build (materials, furniture assets,
lighting) ladders up to that moment. 2D plans are for checking dimensions;
the walkthrough is for *feeling the space* — that's what sells a design.

Quality bar: would you show it to a client without apologizing.

## What exists today (v1)
Framework-owned since ADR-006 (`src/archicad_builder/walkthrough/`,
`render3d/`, `export/glb_blender.py`): GLB export + generated Three.js
walkthrough page with free-fly controls, object info (I), measuring (M),
dollhouse roof toggle (R), construction X-ray (G), shareable `#v=` view
links (K), and feedback mode (F — freeze, draw strokes on the view,
comment, submit; the `serve` command stores each submission as PNG +
machine-readable meta); the model streams as a separate `.glb` fetched at
runtime. Project taste (title, spawn, palette) comes from `project.toml`.
Historical build record: [projects/villa-maketa/spec.md](../projects/villa-maketa/spec.md).

### Element metadata — attributes, not names (2026-08-10)
The OBJ hop between IFC and Blender strips every property, and for a while
the page reverse-engineered semantics from mesh names (`Ifc\w+?_` regexes,
a TAGS payload, name-keyed loads). That whole class is gone. The chain now
carries REAL attributes end to end:

```
building.json ─▸ render3d/metadata.py: element_metadata(doc)
              ─▸ Blender custom props   ab_global_id / ab_kind / ab_name /
                 (stamped BEFORE face   ab_load_bearing / ab_tag
                  splits, copies inherit)
              ─▸ GLB node extras        (export_extras=True)
              ─▸ mesh.userData          (GLTFLoader, walked via _abMeta)
```

- Aim labels and feedback badges read `ab_tag` / `ab_name` (tag numbering
  mirrors the 2D plan, `G:` prefix for non-ground storeys).
- The X-ray classifies by `ab_kind` and colors by `ab_load_bearing`; a
  mesh WITHOUT metadata is furniture/decor and is hidden. A GLB with no
  metadata at all fails loud ("rebuild the GLB") — there is no name
  fallback.
- `loads.json` is keyed by GlobalId (the record carries `name` for
  humans); the loads chip joins on `ab_global_id`. The E064–E066
  validators read the name field instead of parsing keys.
- Mesh names are debugging labels for humans, nothing more. The GlobalId
  in the browser is the SAME identifier as in building.json and the IFC
  ([ifc-identity.md](ifc-identity.md)).

## Roadmap (not commissioned yet)
- Web deployment: static cloud publishing + hosted feedback loop —
  designed in [web-deployment.md](web-deployment.md) (2026-08-07).
- Generalize the scripts from villa-maketa into the framework
  (`archicad_builder export-glb <project>` + shared HTML template) —
  Phase 1 prerequisite of the web deployment.
- Walk mode: gravity + wall collision (v1 is free-fly by design).
- Baked/textured materials and CC0 furniture assets in the GLB
  (see villa spec "Furniture v2").

## Decision log

| 2026-08-08 | L toggles `off ↔ FEM x-ray` (`setStructuralMode`); `?loads=1` and `?xray=1` both map to fem; FEM mode raycasts fragments only | owner first asked for a 3-state cycle, then cut the strip paint mode the same evening ("only the second one is needed") — strip engine keeps validators + aim+I numbers ([fem-xray.md](fem-xray.md)) |
| 2026-08-08 | Top-right HUD shows a live aim readout (throttled 150 ms): element name in normal mode, element + tile % + element max in X-ray mode; I still gives the detailed numbers | owner: "the top right text should always be showing the element I am pointing to… and in load mode the stress of the tile" |
| 2026-08-08 | Building(z-up) → GLB scene transform is `(x, z, −y)`; fragments sanity-check their bbox against the model and console-warn on regression | same mapping paintByLoad already used; plan review demanded a runtime check over blind hardcoding |
| Date | Decision | Why | Who |
|------|----------|-----|-----|
| 2026-08-05 | v1 lives at project layer | one villa (YAGNI); promote when a second project or the webserver needs it | Almir + Claude |
| 2026-08-05 | Separate GLB, not base64 embed | product direction = hosted feature; streaming/caching/size | Almir |
| 2026-08-05 | Free-fly first, collision later | answers "how does the space feel" with half the work | Almir + Claude |
| 2026-08-05 | ~~Open-top scenes accepted~~ superseded 2026-08-06 | the villa now has a roof; the viewer toggles it (dollhouse mode, R) like the maquette's lid | Claude |
| 2026-08-06 | Dollhouse roof toggle is a viewer feature (R key + `?roof=0` debug seam) | aerial capture needs the lid off; hidden roofs must not swallow info/measure raycasts | Almir |
| 2026-08-06 | P key = feedback screenshot: downloads a PNG named with the exact camera (`villa-shot_x_y_z_yaw_pitch.png`) | owner reviews by screenshot; the filename doubles as a `#debug=` camera so Claude re-renders the identical view to verify fixes | Almir |
| 2026-08-06 | F key = feedback mode (mini-BCF): freeze + screen-space strokes + comment → POST /feedback → `feedback/<NNN>/{shot.png, meta.json}`; PNG download fallback on static hosting | strokes stay screen-space (camera pose is captured, so the view reproduces — 3D-anchored lines are YAGNI); meta.json carries camera, normalized strokes AND the element tags each stroke touches (raycast), so a scribble references W7/Win2 without typing; POST beats download (no Downloads-folder shuffling — owner just says "check feedback") | Almir + Claude |
| 2026-08-06 | Feedback mode overlays element tag badges (occlusion-tested, only visible elements) | owner references elements by plan tag; showing them in place removes the guesswork | Almir |
| 2026-08-06 | Camera numbers (P filename, feedback meta, `#debug=`) derive from the LOOK DIRECTION, not the raw rotation Euler | raw `rotation.x` can leave pointer-lock as e.g. 154° — replaying it flips the view (bit us on feedbacks #001/#003) | Claude |
| 2026-08-06 | A submitted feedback is a WORK ORDER, not a discussion prompt | owner (#005): analysis-then-wait on #003 read as ignoring the feedback | Almir |
| 2026-08-06 | ~~Slabs solid to vertical flight (swept clamp) + digit-key storey teleports~~ REVERTED next day | see next row | Claude |
| 2026-08-07 | Vertical flight is unrestricted — FINAL owner decision. No clamp, no collision, no modifier, no teleport keys; never restrict walkthrough movement without an explicit owner request | owner: "it was never accident i did it on purpose, just leave it as it was, no more no less" — flying through floors is how he reviews; the "two floors" confusion is handled by the HUD readout + labels ([storey-datum.md](storey-datum.md)) | Almir |
| 2026-08-08 | Submit button disables while the feedback POST is in flight (re-enabled in exitFeedback) | double-click during the seconds-long PNG upload stored the same feedback twice (cloud DB rows 1+2); one POST = one row, so the guard belongs client-side | Almir + Claude |
| 2026-08-08 | Touch controls on coarse-pointer devices: left-half drag = analog walk, right-half drag = look, ▲/▼ hold = fly, ✏ Feedback button = F-key equivalent; strokes/undo/cancel via touch (pointer events); `?touch=1` debug seam; no pointer lock on mobile (browsers reject it) | owner: "add mobile controls on mobile devices, and one button for feedback, equivalent of current one" | Almir |
| 2026-08-08 | Visual floating joystick (base+knob anchor to the finger, 45px = full speed), ☰ options menu (roof/names toggles — no R/N keys on phones), `?start=1`/`?menu=1` seams | owner mobile test: "better navigation joystick; menu for turn roof on/off and other options" | Almir |
| 2026-08-08 | After feedback submit/cancel on touch: resume walking directly, no start overlay | owner: "after submitting feedback return to normal state not blocked state" (desktop keeps the overlay — pointer lock needs a fresh gesture) | Almir |
| 2026-08-08 | Joystick grabs only touches within ~110px of its resting spot (hops to the finger inside that neighborhood); every other touch — both screen halves — is look/rotate | owner: the half-screen rule hijacked far-away left touches; "if I am far away I should be able to rotate using my finger" | Almir |
| 2026-08-08 | Loads view (L key / ☰ menu): colors every structural element by TRUE % of capacity used (beams: bending; walls: axial incl. self-weight, t×Φ·f_d capacity; garage storey included with its full load path) — one continuous gray→amber→red ramp, no bands; everything else ghosts to 10%; per-element 1D gradient textures UV-mapped along the member — beams show their bending parabola (vertex colors could not: box beams have no midspan vertices), walls follow an 8-bucket sampled load profile; I shows q/M/util per element; data embedded at build from output/loads.json (experiment `load_takedown.py --emit-json`, rerun after model changes — absent file = toggle explains itself) | owner: "render me in 3D where I could see the loads on my concrete" — the RFEM-style view, KISS edition | Almir |
| 2026-08-10 | Name parsing purged (owner: "why are we doing this through names — isn't there a real property?" then "remove them all, KISS/YAGNI"): element metadata rides the pipeline as real attributes (see § Element metadata) — TAGS payload, `Ifc\w+?_` regexes, name-keyed loads, `_ifcBase()`, the legacy `ghost` URL flag and the `--model` fallback all deleted; loads.json keyed by GlobalId. Kept: the GLB leak gate and verify-assets (fail-loud detectors, not compatibility) | the blue-garage bug was a name-lookup miss on split meshes — the fix was to stop looking things up by name at all | Almir + Claude |
| 2026-08-10 | Structure view v2, same day (owner: "in xray all should be transparent somehow" + three hologram reference images): G toggles a single CONSTRUCTION X-RAY — black background (sky/fog saved and restored), every structural element as additive-glow translucent faces + crisp `EdgesGeometry` outlines (the alignment information lives in the edges, Revit-wireframe idea); bearing walls red (faces 0.16, edges 0xff6b5e), everything else cyan (walls 0.10, slabs/roofs/openings 0.06, edges 0x7fdcff); furniture/decor hidden. Supersedes the same-day 3-state cycle whose solid red bearing walls blocked the view. URL flag `struct` | the first cut kept bearing walls opaque — "here I see the walls" | Almir + Claude |
| 2026-08-09 | Ghost mode: G key / ☰ "Ghost" toggles see-through architecture (walls, slabs, roofs at opacity 0.12, `depthWrite:false`; furniture, doors and windows stay solid). Exactly ONE mode owns the materials at a time: entering the FEM X-ray unwinds Ghost synchronously BEFORE its fetch (the snapshot must never capture ghost clones as originals), and leaving FEM — or its fetch failing — re-applies the wanted ghost. `#v=` grammar: the first 5 fields stay required numerics; everything after is a flag SET (`xray`, `ghost`; unknown flags ignored so the camera survives links from newer builds). "X-ray" = FEM stress colouring, "Ghost" = visibility — two different modes, deliberately distinct names | owner: "x-ray view to see the walls through walls" (2026-08-09) | Almir + Claude |
| 2026-08-08 | Shareable view state in the URL hash: `#v=x,y,z,yaw,pitch[,xray]` (same look-direction camera numbers as `#debug=` and the P filename, three.js coords) — written via `history.replaceState` throttled to 1 s with change detection on the formatted string (Safari hard-caps 100 calls/30 s); read once after the GLB is ready when no `#debug` is present, `xray` token turns the FEM X-ray on (existing `femFetchSeq` guard covers the toggle-while-fetching race); K key (desktop, cursor is pointer-locked) and a ☰ "Copy view link" button (touch) copy the URL synchronously in the input handler (iOS clipboard requirement); no `hashchange` listener — manual mid-session hash edits are out of scope. The X-ray is the ONE view toggle the link carries (roof/names are deliberately not: the X-ray is the state you send someone to argue about) | owner: refresh must keep the position, and a sent link must open at that position in that view; the link pins the position, not the geometry — old links open the latest model | Almir + Claude |
| 2026-08-08 | Feedback shot composited at CSS resolution (was DPR-scaled: 4-9x more pixels); on POST failure show a red notice + Retry in the panel instead of auto-downloading a PNG | owner: smaller/faster submissions; "if feedback submitting fails it should inform the user, the drawing is less important" | Almir |

## Related
Villa v1 implementation details + review lessons: `projects/villa-maketa/spec.md`
(Walkthrough section). Repo pipeline: `spec-anchored.md` structure.
