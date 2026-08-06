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
(M), and dollhouse roof toggle (R); the model streams as a separate `.glb`
fetched at runtime. Implementation record, file list, and the decisions
behind each piece: [projects/villa-maketa/spec.md](../projects/villa-maketa/spec.md)
§ Walkthrough (ADR 004 — project detail lives at the project tier).

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
| 2026-08-05 | ~~Open-top scenes accepted~~ superseded 2026-08-06 | the villa now has a roof; the viewer toggles it (dollhouse mode, R) like the maquette's lid | Claude |
| 2026-08-06 | Dollhouse roof toggle is a viewer feature (R key + `?roof=0` debug seam) | aerial capture needs the lid off; hidden roofs must not swallow info/measure raycasts | Almir |

## Related
Villa v1 implementation details + review lessons: `projects/villa-maketa/spec.md`
(Walkthrough section). Repo pipeline: `spec-anchored.md` structure.
