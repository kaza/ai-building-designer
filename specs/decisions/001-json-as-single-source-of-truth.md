# Decision 001: `building.json` is the single source of truth

## Status
accepted — recorded retroactively (the code has worked this way since the first commit)

## Date
2026-08-05 (recorded); decision in force since project start

## Context
A building exists in this system in many shapes at once: a pydantic model in memory, an IFC
file for ArchiCAD, a matplotlib plan PNG, a Blender scene, a glTF for the browser walkthrough.
Something has to be authoritative. If two of those can be edited, they diverge, and "which one
is the building?" becomes unanswerable — the classic BIM round-trip problem.

## Options considered

| Option | Pros | Cons |
|--------|------|------|
| A — `building.json` authoritative, everything else derived | one editable artifact; diffable in git; regeneration is a pure function; an AI can read and write it directly | every consumer needs an exporter; no round-trip from ArchiCAD |
| B — IFC authoritative | industry standard; round-trips with real CAD tools | IFC diffs are unreadable; ifcopenshell is a heavy dependency for authoring; GlobalIds churn; AI can't reason over it cheaply |
| C — Database authoritative | queryable; concurrent edits | infrastructure for a single-user design tool; kills "clone the repo and run it"; no git history of design intent |

## Decision
**Option A.** `projects/<name>/building.json` is the only authoritative representation. Every
other artifact — `.ifc`, plan PNGs, `.blend`, `.glb`, `walkthrough.html` — is derived,
regenerable, and **gitignored** (`projects/*/output/`, `*.ifc` in `.gitignore`). Regeneration
is a documented ordered pipeline, not an ad-hoc habit.

## Consequences
**Easier:** design intent lives in git as readable diffs. Validation, generation, and AI
correction all operate on one schema. Any output can be deleted and rebuilt, so a broken
export is never a lost building.

**Harder:** no import path from ArchiCAD — edits made downstream in CAD are lost by design,
and that has to be said out loud to anyone who opens the IFC. Every new output format costs an
exporter. Pipeline order matters (e.g. `ifc_to_obj` reads the IFC, so export must run first),
which makes the documented step order load-bearing rather than advisory.

## Applies to
`models/`, `export/`, all `projects/*/` scripts, `.gitignore`, the walkthrough product.

## Related
[architecture.md](../architecture.md);
[ADR-003](003-mutations-through-apply-actions.md) — how the JSON is allowed to change.
