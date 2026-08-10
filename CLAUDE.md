# ai-building-designer — project rules

## Always publish (owner order, 2026-08-11)

When work that changes a project's web deliverables (walkthrough, X-ray,
field payloads, engineer report) is finished and committed: **push, run
the pipeline, and `publish` — every time, without being asked.** The
owner reviews on the live site; "done but only on your disk" is not
done. The publish command's own gates (pushed HEAD, fresh pipeline
ledger) are the safety net — never work around them.

## Spec tiers — keep them isolated (ADR 004)

Two kinds of document are both called "spec". Never mix them:

- **Tier 1 — framework specs** (`specs/*.md`): generic intent only — what a
  feature does, why, boundaries, framework-level decisions. Nothing
  project-specific: no villa coordinates, hex colors, asset lists, pipeline
  commands, or magic numbers. Linking *down* to one project file as a worked
  example is allowed; embedding its content is not.
- **Tier 2 — project specs** (`projects/<name>/*.md`): the build record of
  one building — dimensions, wishes, finish mappings, decisions made for that
  project. A project may have several spec files (e.g. villa-maketa has
  `spec.md`, `facade.md`, `maquette-alignment.md`). Links *up* to the owning
  framework spec.

When a change touches both tiers, write both files in the same commit and
cross-link them. If you catch project detail inside `specs/`, move it out —
that is a defect, not a style choice.

Full rationale: [specs/decisions/004-framework-vs-project-spec-split.md](specs/decisions/004-framework-vs-project-spec-split.md).
