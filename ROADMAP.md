# Roadmap

Single source of truth for **where we are and what's left**. Status only — the *what* and *why*
live in [`specs/`](specs/), architectural choices in [`specs/decisions/`](specs/decisions/).

Last updated: 2026-08-10

**Mission: building-ready, with civil engineer validation** — the
output is optimized for perfect verifiability by a licensed engineer,
never for skipping one (README §Mission).

## Where we are

| Area | State |
|---|---|
| Framework (`src/archicad_builder/`) | ✅ working — models, 55 validator codes, generators, queries, IFC + 2D export, CLI |
| Tests | ✅ 519 passed, 1 skipped |
| `projects/3apt-corner-core` | ✅ 0 errors, IFC exports |
| `projects/4apt-centered-core` | ✅ 0 errors, IFC exports |
| `projects/villa-maketa` | ✅ 0 errors; Blender render, GLB, furniture assets, browser walkthrough + measurement tools |
| Docs | 🟡 9 framework specs + 4 ADRs; most framework subsystems still unspecced (see [architecture.md](specs/architecture.md) coverage map) |

## In flight

Seismic commission (owner, 2026-08-10) — all four phases commissioned:
- S1 ELF plausibility validators E100–E103 — [spec](specs/seismic-lateral.md)
- S2 FEM lateral load cases + combo envelope — [spec](specs/seismic-lateral.md)
- S3 foundations: footing element, soil, E104–E107 — [spec](specs/foundations.md)
- S4 engineer handoff report — [spec](specs/engineer-handoff.md)

## Next (not commissioned)

Framework:
- Scoring function — one quality number out of all validators
- Constraint solver (CSP) for macro-layout
- MCTS / self-play for micro-layout (wall positions inside apartments)
- NN training on the 4090

Walkthrough product ([spec §Roadmap](specs/browser-walkthrough.md)):
- Walk mode (gravity + wall collision)
- Baked textures in the GLB
- Any-project walkthrough (currently villa-only, project layer)

Docs hygiene:
- Write the spec when you touch an unspecced subsystem — do **not** backfill in bulk
  ([ADR-004](specs/decisions/004-framework-vs-project-spec-split.md))

## Conventions

- No code without a spec — `specs/lowercase-with-hyphens.md`, one per feature
- Spec and code ship in the **same commit**
- Open questions live inline as `> **Q-NNN OPEN**` where the context is; find them with
  `rg '^> \*\*Q-\d+ OPEN\*\*'` (currently: none)
