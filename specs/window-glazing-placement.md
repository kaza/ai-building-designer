# Feature: Window glazing placement (thin pane in the reveal)

## Status
Implemented.

## Problem
The IFC exporter modeled a window as a solid box extruded through the FULL
host-wall thickness. Downstream (OBJ → Blender → GLB) that box is rendered
as glass with a wireframe frame on every face — so each window reads as TWO
windows (one per wall face) separated by an air gap the size of the wall
thickness. Visually wrong in every render and in the walkthrough.

## Contract
- A window's body is a thin pane of fixed depth **0.06 m** (realistic frame
  depth), not the wall thickness.
- The pane sits flush with one wall face, chosen by `Window.pane_side`:
  - `"outer"` (default) — flush with the exterior face. Standard practice:
    masonry windows sit in the outer third of the reveal.
  - `"inner"` — flush with the interior face (deep outside reveal).
- The wall OPENING still cuts the full wall thickness — only the infill
  panel is thin.
- Exterior side detection: probe a point just beyond each wall face against
  the story's floor slabs — the face NOT over a floor is exterior (correct
  on concave L/U footprints where a bbox centroid falls outside the plan).
  Fallback when ambiguous (no floor slabs, or both/neither face over one,
  e.g. a wall between a room and a deck slab): the face pointing away from
  the story's wall-endpoint bbox center. Interior walls hosting windows get
  a deterministic (if architecturally meaningless) side.
- `Building.add_window(pane_side=...)` forwards the field; pydantic
  `Literal` rejects anything but `"outer"`/`"inner"` at construction/load.
- Fail loud at export: a `pane_side` outside `{"outer","inner"}` (pydantic
  skips assignment validation) and a host wall thinner than the pane depth
  both raise `ValueError`.

## Non-goals
- Opaque doors keep their full-thickness leaf (`Door.pane_side=None`,
  the default) — the double-pane artifact is only visible through glass.
  Glass doors opt in per door (`pane_side="outer"|"inner"`), same geometry
  and fail-loud rules as windows.
- Pane depth is a module constant, not per-element data (YAGNI).

## Decision log
| Date | Decision | Why |
|------|----------|-----|
| 2026-08-06 | Pane depth 0.06 m constant | typical window-frame depth; per-window config is YAGNI |
| 2026-08-06 | Default `outer` | standard building practice; projects opt into `inner` per window (worked example: villa-maketa, maquette photo #28 — see projects/villa-maketa/facade.md) |
| 2026-08-06 | Exterior side from floor-slab point-in-polygon probes, bbox centroid as fallback | plain centroid flips sides on concave footprints (Gemini review); slab probes reuse `_point_in_polygon` from queries |
| 2026-08-06 | Export-time ValueError for invalid `pane_side` and sub-pane wall thickness | pydantic doesn't validate post-construction assignment; silent "inner" fallback would violate fail-loud (Codex review) |
| 2026-08-06 | `Door.pane_side` opt-in (default None = full-thickness leaf) instead of thin leaves for all doors | only glass doors show the artifact; re-slimming every opaque door changes the whole model's look for no visible gain (worked example: villa D8/D9 outer-flush) |

## Related
[architecture.md](architecture.md) · worked example:
projects/villa-maketa/facade.md (inner-glazed band windows)
