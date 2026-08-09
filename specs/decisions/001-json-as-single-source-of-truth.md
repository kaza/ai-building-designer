# Decision 001: `building.json` is the single source of truth

## Status
accepted — recorded retroactively (the code has worked this way since the first
commit); revisited and reaffirmed 2026-08-06 (see "Revisited" below)

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
exporter. Pipeline order matters (e.g. `export-obj` reads the IFC, so export must run first) and is declared in each project's `pipeline.toml` (specs/project-pipeline.md),
which makes the documented step order load-bearing rather than advisory.

## Revisited 2026-08-06 — "shouldn't we work in IFC all the time?" (owner)
Owner challenged the decision during the villa facade work: the original product
idea was IFC-native authoring with commands manipulating the IFC directly.
**Reaffirmed Option A**, with sharper reasoning than the original record:

- IFC is an **interchange** format, not an authoring format (its own spec's
  framing). Authoring in it means graph surgery: moving one wall touches
  placement chains, openings, fills, and joined neighbors by GUID reference.
- The mental model: **`build.py` is source code, IFC is the compiled binary.**
  We DO "work in IFC" where it matters — openings, corner joins, glazing are
  proper IFC entities, so ArchiCAD reads a real BIM model — but we regenerate
  the artifact instead of mutating it, for the same reason nobody patches
  binaries.
- The "commands over the model" the owner wanted exist one level up
  (`add_wall`, `add_window(pane_side=…)`, CLI `apply`); over raw IFC each
  would be reference-graph archaeology, and validators would have to
  reverse-engineer semantics back out of geometry.
- Owner feedback loop (photos/F-key → fix → re-render) turns around in
  minutes precisely because the authoritative model is small and semantic.

**Reopen trigger** (the one scenario that flips this): a human architect must
edit the model in ArchiCAD/Revit and send it BACK. That requires IFC import +
reconciliation and ends JSON's monopoly as source of truth. Until that
requirement exists, IFC-native buys pain, not capability.

## Applies to
`models/`, `export/`, all `projects/*/` scripts, `.gitignore`, the walkthrough product.

## Related
[architecture.md](../architecture.md);
[ADR-003](003-mutations-through-apply-actions.md) — how the JSON is allowed to change.
