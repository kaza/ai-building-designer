# Decision 002: Validation is severity-tiered lint with a machine-readable contract

## Status
accepted — recorded retroactively

## Date
2026-08-05 (recorded); decision in force since the validator system was introduced

## Context
The core loop of this project is "AI designs → something verifies → AI reads the failures and
fixes them". That loop only closes if the verifier's output is unambiguous to a program, and
only converges if not every complaint blocks progress. A building with a tunnel-shaped room is
ugly; a building whose apartment has no bathroom is illegal. Treating both as "error" means the
AI either never finishes or learns to ignore errors.

## Options considered

| Option | Pros | Cons |
|--------|------|------|
| A — pass/fail assertions (pytest-style) | trivial to implement; binary answer | no way to express "ugly but legal"; one cosmetic complaint blocks the whole loop |
| B — severity-tiered findings (error / warning / optimization), JSON out | AI can gate on errors and treat the rest as gradient; matches lint mental model developers already have; counts give a progress signal | severity assignment is a judgment call per code; needs a waiver mechanism for known-acceptable findings |
| C — single numeric score | one number to optimize; ideal for search/MCTS | opaque — "score 0.72" tells the AI nothing about *what* to fix; weights need tuning before anything works |

## Decision
**Option B.** Every finding carries a stable code and one of three severities:

| Severity | Contract |
|---|---|
| `error` | the building is illegal or broken — must reach zero |
| `warning` | quality problem — should fix, does not block |
| `optimization` | could be better — informational |

`validate` emits JSON: `{errors, warnings, optimizations, details[{severity, message,
element_type}]}`, plus `waived` / `waived_count` / `stale_waivers` when a project has a waiver
file. Codes are namespaced by severity (`E0xx`, `W0xx`, `O0xx`), assigned once, never reused —
54 exist today.

Option C is not rejected forever: a scoring function over these findings is on the roadmap for
CSP/MCTS work. It would be built *on top of* the tiers, not instead of them.

## Consequences
**Easier:** the AI loop gates on one number (`errors == 0`) while still receiving actionable
text. Adding a check is additive — new code, new module, no changes to consumers. Human review
and machine review read the same output.

**Harder:** every new check needs a severity judgment, and getting it wrong is expensive in
both directions (a mis-tiered `error` stalls the loop; a mis-tiered `warning` ships a broken
building). Codes are permanent, so a badly named or badly scoped code lives forever.
Legitimately-acceptable findings need first-class suppression — that is why
[validation-waivers.md](../validation-waivers.md) exists rather than a `# noqa` culture.

## Applies to
`validators/` (all modules), CLI `validate` / `assess`, per-project `validation.json`, the
AI correction loop, future scoring work.

## Related
[architecture.md](../architecture.md);
[validation-waivers.md](../validation-waivers.md);
[space-overlap.md](../space-overlap.md) and [furniture-door-clearance.md](../furniture-door-clearance.md)
as worked examples of an `E` and a `W` code.
