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

## What exists today (v1, villa-maketa project layer)
- `projects/villa-maketa/export_glb.py` — Blender scene → `villa.glb`
  (flat-color materials, helpers pruned, stairwell boolean applied).
- `projects/villa-maketa/make_walkthrough.py` — validates the GLB container
  and writes `walkthrough.html`: Three.js (pinned CDN import map),
  PointerLockControls free-fly (WASD, Shift, Space/C), hemisphere + sun
  lighting, `#debug` camera hash for headless triage.
- Delivery: **separate `villa.glb` fetched at runtime** (owner decision
  2026-08-05; supersedes the base64-embedded single file). A separate GLB
  streams, caches, and scales to textured assets — a blob does none of that.
  Browsers block `fetch()` from `file://`, so local viewing is
  `python3 -m http.server 8000 -d projects/villa-maketa/output`; the page
  detects `file://` and says exactly that.

## Roadmap (not commissioned yet)
- Webserver feature: serve any project's walkthrough (`/projects/<name>/walk`).
- Generalize the two scripts from villa-maketa into the framework
  (`archicad_builder export-glb <project>` + shared HTML template).
- Walk mode: gravity + wall collision (v1 is free-fly by design).
- Baked/textured materials and CC0 furniture assets in the GLB
  (see villa spec "Furniture v2").

## Decision log
| Date | Decision | Why | Who |
|------|----------|-----|-----|
| 2026-08-05 | v1 lives at project layer | one villa (YAGNI); promote when a second project or the webserver needs it | Almir + Claude |
| 2026-08-05 | Separate GLB, not base64 embed | product direction = hosted feature; streaming/caching/size | Almir |
| 2026-08-05 | Free-fly first, collision later | answers "how does the space feel" with half the work | Almir + Claude |
| 2026-08-05 | Open-top scenes accepted | maquette look; roofs are a modeling feature, not a viewer concern | Claude |

## Related
Villa v1 implementation details + review lessons: `projects/villa-maketa/spec.md`
(Walkthrough section). Repo pipeline: `spec-anchored.md` structure.
