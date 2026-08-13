# Columns — discrete vertical members (steel / reinforced concrete)

## What it does

Adds a `Column` element to the model vocabulary: a rectangular vertical
member (e.g. the 60×20 cm tie-column hidden in a stone wall, or a steel
post at a glass corner) placed on a storey at a plan position. Columns
flow through the whole chain: building model → IFC (`IfcColumn`) →
render/GLB → construction X-ray (drawn as the bright "skeleton") →
seismic mass → foundations checks → the engineer report. Columns are the
geometric evidence that a *confined masonry* classification
([seismic-lateral.md](seismic-lateral.md) §Structure presets) is real:
the classification validator counts and places them.

Owner commission 2026-08-13: the architect's strengthening grid (axes
A/B/C × 1–4, tie-columns at intersections, "stub na 2A, 60 cm u pravcu
A", steel or concrete post at the entrance corner) is inexpressible
without this element.

## API (post-review 2026-08-13: Gemini + Codex arbitration)

Two placement modes, one call:

- **Tie-column (confinement role)**: `add_column(story, wall=<wall
  name>, along=<distance from wall start>, width, depth,
  material="rc", name)` — attached to its host wall topologically
  (never by floating coordinates: the evidence check must not fight
  float tolerances — Gemini). Orientation is inferred from the host
  wall; there is NO `angle` parameter (a footgun — tie-columns are
  cast against their wall). Height is always the full storey height
  (a partial-height "confining" element is not one). Material must be
  `"rc"`; each cross-section side ≥ 150 mm (EN 1998-1 §9.5.3(3) —
  a 60×10 has the area and fails the clause; Codex).
- **Free-standing post**: `add_column(story, at=(x, y), width, depth,
  material="rc"|"steel", height=None, name)` — the steel corner post.
  Carries NO confinement role, ever (steel or not — §9.5.3 confining
  elements are cast concrete).

Names must be non-empty and unique per storey — identity/reconcile and
renderer metadata are name-keyed (Codex).

## Participation matrix

| Consumer | Behaviour |
|---|---|
| IFC export | `IfcColumn` with `ObjectType="column"` (IFC2X3: PredefinedType lives on IfcColumnType, not the occurrence — Codex), rectangle profile, material assignment; same gid/identity rules as other elements (ifc-identity.md); full export→import→export round-trip incl. dimensions, material, host reference. Plumbing checklist: Story schema, reconcile KINDS, importer _KIND_MAP + dedup scan, storey-pset exclusion, render metadata |
| Render / GLB | solid box, material-tinted; carries the standard metadata extras (`ab_kind: "column"`, `ab_material`) |
| Construction X-ray | the skeleton layer: HIGH opacity (above load-bearing walls), strong edges; hue by material — reinforced concrete joins the warm bearing family, steel renders cool steel-blue. Rationale (owner 2026-08-13): a 60×20 sliver at ghost-wall opacity would be invisible, and the X-ray's purpose is showing hidden structure — the confinement skeleton must read at a glance |
| Load view | NEUTRAL (structure-grey, not stress-coloured) in phase C1 — columns are not meshed in the plate FEM (below), and painting them with a fake utilization would lie. Requires a dedicated neutral overlay + a secondary raycast (the load view's hit test targets FEM fragments only, so an unmeshed column would be faint and unselectable without one — Codex); the aim readout says "column — frame action not modelled" |
| Seismic (ELF) | column self-weight joins the storey mass W **material-exclusively**: an embedded column adds only the density *difference* over the overlap volume with its host wall — never both full volumes (double-count, Codex). Columns contribute NO shear capacity of their own in the wall-capacity sum — their seismic value is confinement, credited exclusively through the structure preset (seismic-lateral.md). A lone column pretending to be a shear wall is exactly the fiction we refuse |
| Foundations | **E108 — geometric support-path check** (named exactly that, NOT foundation adequacy — Codex): a column base must land on a footing, a wall top of the storey below, the on-grade slab, or an aligned column below (column-on-column continuity). E050/E103/E104/E105 deliberately keep their walls-only scope; column loads do not enter footing-pressure math in C1 |
| Engineer report | columns listed with grid-style positions, material, dimensions; the not-modelled banner carries "column frame action / vertical-load shortening not in the plate FEM — engineer verifies member design" |

## Boundaries (phase C1, deliberately)

- **No FEM frame members.** The plate model stays walls/slabs/roofs;
  columns are not meshed and attract no load numerically. Consequence,
  stated honestly everywhere it matters: a steel post under a glass
  corner does not yet *relieve* the neighbouring spans in the numbers —
  it documents intent for the engineer. Meshing columns as frame
  members is phase C2, only if a design decision ever hinges on it.
- **No column-specific cost logic in the framework** — pricing stays at
  the run-brief tier (arena unit rates), like every other element.
- Beams of steel already exist (`Beam`); this spec does not touch them.

## Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-08-13 | Columns carry zero standalone shear capacity in ELF | a 0.2 m "wall" would add ~3 kN of fiction; EC8 §9 credits confinement via classification (q, table row), which is what the structure preset does — the column is evidence, not capacity |
| 2026-08-13 | X-ray renders columns as the bright skeleton, hue by material | owner: "render columns slightly differently — different role/strength"; at ghost opacity they'd vanish, and hidden tie-columns are the exact thing an X-ray exists to reveal |
| 2026-08-13 | Load view paints columns neutral, with an honest readout | not meshed ⇒ no utilization; colouring them would fabricate physics |
| 2026-08-13 | E108 column-bearing check instead of a pad-footing element | villa columns land on existing strips/garage walls; a new footing type with no user is YAGNI |

## Related

[seismic-lateral.md](seismic-lateral.md) (structure presets consume
columns as confinement evidence) · [foundations.md](foundations.md)
(E104–E107 family) · [ifc-identity.md](ifc-identity.md) ·
[fem-xray.md](fem-xray.md), [browser-walkthrough.md](browser-walkthrough.md)
(rendering contracts) · worked example: projects/villa-maketa (arena
round 2, architect grid lane).
