# Decision 006: Projects contain data and config, never engine code

## Status
accepted

## Date
2026-08-09

## Context
After the 2026-08-09 promotions, `projects/villa-maketa/` still contained five
Python engines (3,277 lines, zero tests): build script, Blender scene builder, GLB
exporter, asset fetcher, walkthrough generator. Each mixed generic machinery with
villa-specific values. The owner's direction: "I was hoping all will go to
framework" — move all the logic out.

## The boundary rule

> A thing belongs to the **project** if a second building would need a **different
> value**. It belongs to the **framework** if a second building would need the
> **same behaviour**.

## Decision
- Engines move to `src/archicad_builder/` behind CLI commands; their villa values
  move to `projects/<name>/project.toml` ([project-config.md](../project-config.md)).
- `build.py` is the one deliberate exception: it *is* the building (dimensions and
  design decisions as code) and stays in the project, id-stable via ADR-005.
- End state of a project directory: `building.json`, `build.py`, `furniture.json`,
  `validation.json`, `pipeline.toml`, `project.toml`, docs, `assets/`, `output/`,
  `feedback/`. No other `.py`.
- Render-only decor generalizes instead of staying scripted: e.g. the villa's
  stair-tower shell derives from any spiral staircase straddling a facade
  (spiral-stair-rendering.md), terrain from `[[render.ground]]` boxes.

## Options considered

| Option | Pros | Cons |
|--------|------|------|
| A — engines stay in projects | no migration risk | 3,277 untested lines copied into every new project; fixes never propagate |
| B — engines in framework, values in config (chosen) | one tested engine; new project = data + config | config schema must exist; hard cases (decor geometry) need generalizing |
| C — engines in framework with per-project Python hooks | maximum flexibility | hooks ARE engine code in the project; boundary erodes immediately |

## Consequences
**Easier:** a second project needs no code; engine fixes reach every project; the
engines get tests for the first time.

**Harder:** genuinely one-off visual decor must either generalize into the
framework or become model/config data — "just script it in the project" is no
longer available. If that pressure becomes real, revisit against option C.

## Applies to
`projects/*/`, `src/archicad_builder/{assets,project_config}.py`,
`src/archicad_builder/export/glb.py`, `src/archicad_builder/render3d/`,
`src/archicad_builder/walkthrough/`.

## Related
[ADR-004](004-framework-vs-project-spec-split.md) — same split for specs.
[ADR-005](005-element-identity-and-reconciliation.md) — why build.py may stay.
