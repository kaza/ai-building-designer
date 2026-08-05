# Decision 004: Two spec tiers, and specs are written on touch — not backfilled

## Status
accepted

## Date
2026-08-05

## Context
Two documentation problems arrived together.

1. **Two kinds of document were both called "spec".** `specs/browser-walkthrough.md` describes
   what the walkthrough *should be* as a product; `projects/villa-maketa/spec.md` describes what
   was actually built for one villa — asset lists, pipeline step order, magic numbers. Mixing
   them makes the product intent unreadable and the project record unmaintainable.
2. **Most of the framework has no spec at all.** `src/archicad_builder/` was written before
   spec-anchored development was adopted here. The rule says "no code without a spec", and taken
   literally that implies backfilling ~15 subsystem specs for code nobody is currently editing.

## Options considered

| Option | Pros | Cons |
|--------|------|------|
| A — backfill every subsystem spec now | rule satisfied literally; complete coverage | ~15 documents describing code from the outside, none of them reviewed against a real change; they rot immediately and then actively mislead. Days of work for zero decisions changed |
| B — empty stub files per subsystem | cheap; a filename exists to fill in | a directory listing shows "spec exists" when it doesn't. Worse than nothing: it launders the violation |
| C — one architecture map that reserves a spec name per subsystem; write the real spec on the next touch | honest about what is and isn't specified; gives future work a designated home; ~1% of Option A's volume | coverage stays partial for a long time; requires discipline at commit time |
| D — flatten the tiers (project specs move into `specs/`) | one directory to look in | villa asset tables and pipeline commands would drown eight framework specs; project files belong next to the project they can be run from |

## Decision
**C for coverage, and keep the two tiers (reject D).**

**Tier 1 — framework specs**, `specs/lowercase-with-hyphens.md`. Product and framework intent:
what it does, why, boundaries, decision log. Long-lived, low-volatility.

**Tier 2 — project implementation records**, `projects/<name>/spec.md`. What was actually built
for one building: dimensions, asset lists, pipeline order, verification commands. Links *up* to
the framework spec that owns the intent; the framework spec links *down* as an example.

**Coverage rule:** [specs/architecture.md](../architecture.md) names every framework subsystem
with either a spec link or an `unspecced → reserved-name.md` marker. When you change an
unspecced subsystem, write that spec **in the same commit** as the code. Bulk backfilling is
explicitly not wanted.

## Consequences
**Easier:** a reader knows immediately whether they are holding intent or a build log. Specs
that exist were written by someone making a real decision, so they carry rationale rather than
restated code. New work has an obvious destination and no naming debate.

**Harder:** coverage is honestly partial, and `unspecced` markers will sit there for months —
that is a visible reminder, not a bug. The rule now has a commit-time obligation that is easy to
skip under pressure; the reserved-name table is the only thing making the skip obvious. Two tiers
mean two files can drift apart, so the cross-links are load-bearing.

## Applies to
`specs/` (all), `specs/architecture.md`, `projects/*/spec.md`, `ROADMAP.md`, and the review
question on every PR that touches `src/`.

## Related
[architecture.md](../architecture.md) — the coverage map this decision creates;
[ROADMAP.md](../../ROADMAP.md);
[browser-walkthrough.md](../browser-walkthrough.md) ↔ [projects/villa-maketa/spec.md](../../projects/villa-maketa/spec.md)
as the worked example of the two tiers.
