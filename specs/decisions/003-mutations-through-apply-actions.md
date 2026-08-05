# Decision 003: Every incremental mutation goes through `apply` JSON actions

## Status
accepted — recorded retroactively

## Date
2026-08-05 (recorded); decision in force since the CLI was introduced

## Context
The AI correction loop needs to *change* buildings, not just read them. Whatever the write
interface is, an LLM has to hit it reliably, the result has to be inspectable, and a bad edit
must not corrupt `building.json` ([ADR-001](001-json-as-single-source-of-truth.md)).

## Options considered

| Option | Pros | Cons |
|--------|------|------|
| A — AI edits `building.json` directly as text | no interface to build; maximum flexibility | one bad brace corrupts the source of truth; no invariants enforced; GlobalIds and cross-references get hand-mangled; enormous diffs for a 20cm wall move |
| B — AI writes Python that calls the model API | full expressiveness | arbitrary code execution as the edit mechanism; unreviewable; no way to reject a single bad step |
| C — declarative JSON actions through one CLI command | small closed vocabulary the model hits reliably; each action validated and echoed; JSON in, JSON out, matching the validate contract; batch is all-or-nothing | every new capability needs an action verb; expressiveness is capped by the vocabulary |

## Decision
**Option C.** `python -m archicad_builder apply <project> <actions>` is the only incremental
write path. Actions are a JSON array (accepted as an argument, `--file`, or `--stdin`) over a
closed verb set — `add-wall`, `remove-wall`, `move-wall`, `rename-wall`, `add-door`,
`remove-door`, `resize-door`, `add-window`, `remove-window`, `resize-window`, `add-slab`,
`add-staircase`, `add-apartment`, `remove-apartment`, `resize-apartment`, `add-space`,
`resize-space`, `remove-space`, `add-story`.

Each action dispatches to a `Building` API method and returns a result dict. **A batch is
all-or-nothing**: the first failing action aborts before `building.json` is written, so a bad
edit leaves the file untouched. On success the file is saved and validation runs automatically
(unless `--no-validate`), so the loop's next input comes back in the same call.

All other commands (`validate`, `assess`, `render`, `list`, `stats`, `export`) are read-only
and take plain CLI args.

## Consequences
**Easier:** every design change is a reviewable, replayable JSON record. The model never sees
raw file syntax, so it cannot produce an unparseable building. Validation feedback arrives in
the same response as the edit — one round trip per iteration. Adding a verb is a local change.

**Harder:** the vocabulary is a ceiling — anything it can't express can't be done incrementally
until a verb is added, and the temptation is to add a catch-all escape hatch (don't). No partial
success means a 20-action batch with a typo in action 19 applies nothing, which is correct but
costs a retry.

**Known boundary — bulk authoring bypasses this.** `generate` (framework generators) and
project scripts like `projects/villa-maketa/build.py` construct a `Building` in Python and
`save()` it wholesale. That is deliberate: they *create* a building from parameters rather than
*edit* one, and their output is gated by `validate` like any other. The rule is "no incremental
edits outside `apply`", not "nothing may ever call `save()`".

## Applies to
`__main__.py` (`apply`, `_dispatch_action`), `models/building.py` mutation API, the AI
correction loop, `generate`, project `build.py` scripts.

## Related
[ADR-001](001-json-as-single-source-of-truth.md);
[ADR-002](002-validators-as-severity-tiered-lint.md) — what comes back after an apply;
[architecture.md](../architecture.md).
