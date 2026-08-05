# Feature: Walkthrough measurement tools

## Status
implemented (2026-08-05)

## Why this exists
The walkthrough's product goal is "walk through the building you designed"
([browser-walkthrough.md](browser-walkthrough.md)). The natural next question
in there is always "how wide is this?" — the owner asked for a button that
shows object dimensions and point-to-point distances. Every BIM viewer ships
this UX (ruler icon, click two points, label); users expect it.

## What it does (v1)
Two tools inside `make_walkthrough.py`'s HTML template, no new files:

1. **Object info (hover key)** — press **I** while pointer-locked: raycast
   from the crosshair; the hit object's card shows in a corner HUD:
   semantic name (mesh names are already meaningful: `IfcDoor_Vila_Entry_Door`,
   `F_Sofa L long`) + world-space bounding box W × D × H in meters (2 decimals).
   Card persists until the next I-press or Esc.
2. **Ruler (M key toggles measure mode)** — while in measure mode the
   crosshair turns into a reticle; **click point A, click point B** (raycast
   hits on any geometry): a line is drawn between them with a floating label
   showing the distance in meters (plus the ΔX/ΔY/ΔZ breakdown in the HUD).
   Next click starts a new measurement; only the last one stays visible;
   **M** again or Esc exits and clears. Pointer lock stays ON — clicks
   raycast from the screen-center crosshair, which keeps aiming natural and
   sidesteps unlocked-cursor picking entirely.

Labels: `CSS2DRenderer` (ships with Three.js addons — no extra dependency).
A small always-on hint line is added to the help overlay (I — info, M — measure).

## Behavior details
- **Ancestor walk**: raycast hits child meshes (`Object_4`); walk parents to
  the semantic node (name not matching `Object_N`/empty) and take
  `Box3.setFromObject` on THAT — else the info card shows a sofa cushion.
- **Crosshair**: `mix-blend-mode: difference` so it survives white walls and
  dark corners; visible always (free-fly aiming benefits too).
- **Rubber-band**: after the first measure click, a live line follows the
  current crosshair hit until the second click.
- **Miss handling**: raycast into the sky → HUD shows "no surface hit";
  info card clears.
- **Mode indicator**: HUD line shows "MEASURE — click first point / click
  second point" while active.
- **Glass is included in raycasts** — the hit must agree with the visible
  frontmost surface, and excluding glass would make windows uninspectable.
  "Measure through glass" becomes a toggle if requested.
- **Raycast scope**: the loaded model root only.
- **Resource handling**: measurement objects live in a dedicated group with
  explicit disposal on clear/replace; the line uses `depthTest:false` + high
  `renderOrder` — consistent with the label's non-occlusion, and no z-fighting.
- **Scripted measurement**: `?measure=ax,ay,az,bx,by,bz` (exactly six finite
  numbers) is honored **only under `#debug`**, goes through the same
  `commitMeasurement()` as a click, and sets a DOM readiness marker so headless
  Chrome waits deterministically.

## Boundaries
- Measures rendered geometry (mesh raycast), not authored building.json data.
  Exact authored dimensions ("wall length 4.50") from embedded semantic data
  is a v2 idea — noted, not built (YAGNI until asked).
- No vertex/edge snapping in v1 — freehand points on surfaces. Snapping is the
  fiddly 20% that costs 80%; revisit if precision complaints arrive.
- No persistence/export of measurements.
- CSS2D labels ignore the depth buffer — a label can float "through" a wall
  when you walk away. Accepted for v1 (single live measurement); occlusion
  raycast is the known fix if it grates.
- Desktop-only interaction model (pointer lock + keys) — matches the current
  walkthrough; touch UI is a product-phase concern.

## Testing & verification
Browser feature at project layer — verified via the `#debug` headless-Chrome
path: a `#debug` extension allows scripted measurement (query params inject
two points) so a screenshot asserts the line + label render. Manual pass for
UX feel. No pytest (same precedent as the rest of the walkthrough page).

## Decision log
| Date | Decision | Why |
|------|----------|-----|
| 2026-08-05 | Crosshair-click while pointer-locked, not free-cursor picking | keeps one interaction model; no lock/unlock churn mid-measurement |
| 2026-08-05 | CSS2D labels over sprite/canvas text | crisp at any zoom, zero texture management |
| 2026-08-05 | Mesh-raycast measuring, not authored-data lookup | v1 answers "how far/big is that" — exact BIM dims are a different feature |
| 2026-08-05 | Glass included in raycasts rather than skipped | the hit must match the frontmost *visible* surface; skipping glass makes windows — a thing people measure — uninspectable |
| 2026-08-05 | Scripted measurement gated behind `#debug` | it is a test seam, not a feature; ungated URL params would become an unspecified public API |
| 2026-08-05 | Screenshot asserts render wiring only; pointer-lock UX stays a manual matrix | automating pointer-lock input in headless Chrome costs more than the bug class it would catch |

## Related
[browser-walkthrough.md](browser-walkthrough.md);
projects/villa-maketa/make_walkthrough.py (implementation site).
