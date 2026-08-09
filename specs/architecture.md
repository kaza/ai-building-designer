# Feature: System architecture & spec coverage map

## Status
implemented — reverse-engineered record (2026-08-05)

## Why this exists
The framework was built before spec-anchored development was adopted here, so most of
`src/archicad_builder/` has working code and no spec. Two problems follow: a reader can't
tell *intended* behavior from *incidental* behavior, and there is no obvious place to put a
spec when a subsystem finally gets touched.

This document is that place. It records the intended responsibility of each subsystem in one
line and names the spec slot each one will occupy. It is deliberately **thin** — a map, not a
substitute for the specs it points at. Bulk-backfilling 30+ specs for code nobody is editing
would produce documents that rot before they are read ([ADR-004](decisions/004-framework-vs-project-spec-split.md)).

## What it does

### The pipeline

```
building.json  ──► Building (pydantic)  ──► validators ──► validation report (JSON)
 (source of                   │                                     │
  truth, hand-               │                                     └──► AI reads failures,
  or AI-authored)            │                                          emits `apply` actions
                             ├──► export/ifc.py       ──► .ifc  (ArchiCAD/Revit)
                             ├──► export/floorplan.py ──► .png  (2D plan)
                             └──► project scripts     ──► .blend / .glb / walkthrough.html
```

Everything downstream of `building.json` is a **derived, regenerable artifact** and is
gitignored ([ADR-001](decisions/001-json-as-single-source-of-truth.md)). All mutation goes
through the CLI `apply` command as JSON actions ([ADR-003](decisions/003-mutations-through-apply-actions.md)).

### Subsystem map and spec coverage

`specs/` column: a link means the intent is written down. **`unspecced`** means the code is
the only record — write the spec *in the same commit* as your next change to that subsystem.

| Subsystem | Intended responsibility | Spec |
|---|---|---|
| `models/building.py` | `Building` + `Story` — the root aggregate that everything else validates and exports | `unspecced` → `building-model.md` |
| `models/elements.py` | Walls, slabs, doors, windows, roofs | `unspecced` → `building-model.md` |
| `models/geometry.py` | Geometric primitives (points, rects, polygons) shared by all elements | `unspecced` → `geometry-primitives.md` |
| `models/spaces.py` | Rooms, apartments, spatial relationships | `unspecced` → `space-model.md` |
| `models/ifc_id.py`, `models/reconcile.py` | Stable IFC GlobalId generation + rebuild reconciliation — IDs must survive regeneration | [ifc-identity.md](ifc-identity.md) |
| `validators/structural.py`, `building.py`, `spaces.py`, `connectivity.py`, `phases.py` | 54 severity-tiered checks (E/W/O) over a loaded `Building` | `unspecced` → `validation-model.md` (severity contract in [ADR-002](decisions/002-validators-as-severity-tiered-lint.md)) |
| `validators/codes.py` | Austrian OIB building-code compliance | `unspecced` → `austrian-building-code.md` |
| `validators/reachability.py` | BFS over the connectivity graph — every room reachable from the entrance | `unspecced` → `validation-model.md` |
| `validators/snap.py` | Auto-fix sub-tolerance wall endpoint gaps | `unspecced` → `wall-snapping.md` |
| `validators/spaces.py` (E090 path) | Space polygons must not overlap | [space-overlap.md](space-overlap.md) |
| `validators/clearance.py` | W100 — furniture must not block door swings | [furniture-door-clearance.md](furniture-door-clearance.md) |
| `validators/waivers.py` | Per-project suppression of known-acceptable findings | [validation-waivers.md](validation-waivers.md) |
| `generators/shell.py`, `core.py`, `corridor.py`, `template.py`, `apartments.py`, `building_4apt.py` | Phased layout synthesis: shell → core → corridor → apartments → per-floor stamping | `unspecced` → `layout-generation.md` |
| `queries/connectivity.py`, `wall_rooms.py`, `spatial.py`, `slice.py` | Read-only context extraction so an AI can reason about a building without loading all of it | `unspecced` → `reasoning-queries.md` |
| `queries/mermaid.py` | Connectivity graph as a mermaid diagram | `unspecced` → `reasoning-queries.md` |
| `export/ifc.py` | IFC4 export via ifcopenshell | `unspecced` → `ifc-export.md` |
| `export/floorplan.py`, `overview.py` | matplotlib 2D plans + all-stories overview | partly: [facade-detection.md](facade-detection.md), [spiral-stair-rendering.md](spiral-stair-rendering.md) → rest `unspecced` as `plan-rendering.md` |
| `vision/prompt.py`, `corrections.py` | Gemini reads a rendered plan and returns corrections applied back to the model | `unspecced` → `vision-corrections.md` |
| `__main__.py` (CLI) | The only entry point: `validate`, `assess`, `render`, `list`, `stats`, `export`, `apply`, `generate` | `unspecced` → `cli-contract.md` (mutation contract in [ADR-003](decisions/003-mutations-through-apply-actions.md)) |
| `tests/` | Fixture ownership policy | [test-fixtures.md](test-fixtures.md) |

### Project layer

`projects/<name>/` holds a building's `building.json`, its project-specific scripts, and a
project spec (`spec.md`) that is an **implementation record**, not a framework spec. Framework
specs in `specs/` own the product intent; project specs record what was actually built for that
one building and link up to the framework spec. See [ADR-004](decisions/004-framework-vs-project-spec-split.md).

Currently: `3apt-corner-core`, `4apt-centered-core` (JSON only),
`villa-maketa` (full pipeline + [spec.md](../projects/villa-maketa/spec.md)).

## Boundaries & edge cases
- This document is a map. It does **not** describe algorithms, tolerances, or edge cases —
  those belong in the per-subsystem spec named in the table.
- The `unspecced → name.md` names are reservations, not promises. If a better decomposition
  becomes obvious when you write the spec, use it and fix the row.
- Counts (54 codes, 519 tests) drift. [ROADMAP.md](../ROADMAP.md) is the place for current
  numbers; this table is about responsibility, not size.

## Testing & verification
No behavior of its own. The check is a review question: does the table still name every
non-`__init__` module under `src/archicad_builder/`?

```bash
find src -name "*.py" | grep -v __pycache__ | grep -v __init__ | sort
```

## Decision log
| Date | Decision | Why |
|------|----------|-----|
| 2026-08-05 | One architecture map + reserved spec names, instead of backfilling ~15 subsystem specs | specs describe intent for code being *changed*; a spec written for untouched code is fiction with a filename. This gives future work a designated home at ~1% of the volume |
| 2026-08-05 | `unspecced` markers live in this table, not as empty stub files | empty stubs read as "spec exists" in a directory listing and silently satisfy "no code without a spec" |
| 2026-08-05 | Reserved names are per-subsystem, not one giant `framework.md` | a monolith spec gets edited by everyone and reviewed by no one |

## Related
[ROADMAP.md](../ROADMAP.md) — current status;
[decisions/](decisions/) — ADRs 001–004;
all feature specs in this directory.
