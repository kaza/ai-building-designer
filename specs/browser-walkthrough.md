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
Implemented at the project layer for villa-maketa: GLB export + generated
Three.js walkthrough page with free-fly controls, object info (I), measuring
(M), dollhouse roof toggle (R), and feedback mode (F — freeze, draw strokes
on the view, comment, submit; the serving script stores each submission as
PNG + machine-readable meta); the model streams as a separate `.glb`
fetched at runtime. Implementation record, file list, and the decisions
behind each piece: [projects/villa-maketa/spec.md](../projects/villa-maketa/spec.md)
§ Walkthrough (ADR 004 — project detail lives at the project tier).

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
| 2026-08-08 | Feedback shot composited at CSS resolution (was DPR-scaled: 4-9x more pixels); on POST failure show a red notice + Retry in the panel instead of auto-downloading a PNG | owner: smaller/faster submissions; "if feedback submitting fails it should inform the user, the drawing is less important" | Almir |

## Related
Villa v1 implementation details + review lessons: `projects/villa-maketa/spec.md`
(Walkthrough section). Repo pipeline: `spec-anchored.md` structure.
