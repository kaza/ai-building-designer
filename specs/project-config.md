# Feature: Project domain config — `project.toml`

## Status
implemented (2026-08-09)

## Why this exists
The goal of ADR-006 is a project directory with **zero engine code** — only the
building, its data, and its documents. But the villa's engine scripts carried the
villa's *taste* as Python constants: the GLB palette, the render cameras and sun, the
pinned furniture list, the walkthrough spawn point. Moving the engines into the
framework requires somewhere for those values to live. That somewhere is
`projects/<name>/project.toml`.

## What it does
`archicad_builder.project_config.ProjectConfig.load(project_dir)` parses
`project.toml` into a strict, fully-defaulted pydantic model:

| Table | Values | Consumed by |
|---|---|---|
| `[project]` | `title` (default: directory name) | walkthrough page |
| `[appearance.palette]` | Blender material name → flat RGBA for glTF | `export-glb` |
| `[render]` | `sun`, `samples`, `exposure`, `[render.camera.perspective]`, `[render.camera.top]`, `[[render.ground]]` terrain boxes | `render-3d` |
| `[walkthrough]` | `start` camera spawn | `walkthrough` |
| `[[asset]]` | pinned furniture: `polyhaven` / `objaverse` / `kenney-kit` (discriminated by `source`) | `fetch-assets` |

Rules:
- **Strict**: unknown table/key, malformed color, out-of-range channel, duplicate
  asset id, invalid TOML — all `ConfigError`. A palette typo used to mean silently
  magenta geometry.
- **Fully defaulted**: a project with no `project.toml` gets working defaults.
- **Freshness is the pipeline's**: any step consuming the config declares
  `inputs = ["project.toml"]` in `pipeline.toml`, so the existing content-hash
  machinery rebuilds on a config change. Nothing new to hash.
- `pipeline.toml` remains exclusively the build graph (`[project] model` + steps).
  Putting these tables there was rejected in plan review: `load_pipeline()` ignores
  unknown tables, so a palette change would never have invalidated the GLB.

## Boundaries & edge cases
- The palette keys are **Blender material names**, not building.json finishes; the
  finish → material mapping is framework code. Cross-validation (every finish used
  must resolve to a palette entry) lives with that mapping, not here.
- Objaverse entries pin `sha256` and carry `name`/`author` because the picks are
  CC-BY — attribution is a license obligation, not metadata decoration.
- `walkthrough.start` is (x, eye-height, z) in the walkthrough's Three.js frame.

## Related
[ADR-006](decisions/006-projects-contain-no-engine-code.md) — the boundary rule.
[project-pipeline.md](project-pipeline.md) — how config changes propagate to rebuilds.
