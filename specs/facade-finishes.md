# Feature: Facade finishes (per-element color/texture)

## Status
implemented (2026-08-05)

## Why this exists
A building model whose every wall renders as identical white plaster reads as
an untextured massing model. Real buildings have designed exteriors — stone
plinths, accent volumes, colored roofs. The framework needs a way for an
element to say *what it is finished with*, without the framework caring what
that means visually.

Trigger: the villa-maketa owner asked to reproduce their maquette's facade
("add whatever is required in the framework to have color and texture of the
facade") — see the project record below for that application.

## What it does
- `Wall.finish: str | None`, `Slab.finish: str | None`, `Roof.finish: str |
  None` — an optional, free-form finish tag (e.g. `"stone_rubble"`,
  `"roof_brown"`). `None` = renderer default (unchanged behavior).
- `Building.add_wall(...)`/`add_slab(...)`/`add_roof(...)` accept `finish=`.
- Persisted in building.json only; `Building.save` excludes None fields so
  existing files stay byte-identical for elements without a finish.
- Semantics: the framework stores the tag; projects' renderers own the
  tag→material mapping and MUST fail loud on a tag they don't know
  (fail-fast against typos — Gemini plan review 2026-08-05). The framework
  never validates tag names.

## Boundaries
- No IFC transport of finish — renderers read building.json directly;
  putting the tag in IFC would be dead code (Gemini plan review 2026-08-05).
- No structured material model (colors, textures, roughness live in the
  consuming renderer, not the framework) — a finish is a *name*, deliberately.
- 2D floor plans ignore finishes entirely.

## Testing
`tests/test_facade_finishes.py`: finish persists through save/load
round-trip; add_wall/add_slab/add_roof forward it; None default keeps legacy
JSON loading; unfinished elements serialize without the key.

## Decision log
| Date | Decision | Why |
|------|----------|-----|
| 2026-08-05 | Free-string finish tag, not an enum | projects own their material vocabularies; framework stays generic |
| 2026-08-05 | ~~IfcPresentationLayerAssignment for transport~~ superseded: building.json-only | the renderer never reads IFC for finishes — IFC transport would be dead code (Gemini) |
| 2026-08-05 | `Building.save` gains exclude_none | keeps pre-finish files byte-identical; no model field uses None as a meaningful non-default value |
| 2026-08-06 | Villa specifics moved to the project tier | ADR 004: framework specs carry intent, project files carry the build record |

## Related
Worked example (stone garage band, brown roof with skylight, accent volume):
[projects/villa-maketa/facade.md](../projects/villa-maketa/facade.md).
[decisions/004-framework-vs-project-spec-split.md](decisions/004-framework-vs-project-spec-split.md).
