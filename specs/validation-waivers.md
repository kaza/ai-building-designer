# Feature: Per-project validation waivers

## Status
implemented

## Why this exists
Validators encode Austrian apartment-block rules. Other building types (villas)
trip rules that don't apply (W001 block-economy ceiling height, W060 "door too
wide" for French doors...). Today the "we know, we accept it" list lives in
prose inside project specs — the tool keeps reporting noise, and a real new
error can drown in it.

## What it does
Optional per-project file `projects/<name>/validation.json`:

```json
{
  "waivers": [
    { "rule": "W060", "reason": "master French door is genuinely 1.4m wide" },
    { "rule": "E041b", "reason": "4.2m2 en-suite; adaptable-housing rule waived" }
  ]
}
```

- `rule` = the rule code (`E044`, `W001`, `E041b`, ...), exposed as a computed
  `code` property on ValidationError (parsed once from the message prefix).
  `reason` is **mandatory** — a waiver without a reason is a config error.
- Optional `match`: substring that must also appear in the message — narrows a
  waiver to specific findings so a blanket rule waiver doesn't mask new
  violations (review finding, Gemini). Element-id targeting rejected: GUIDs are
  regenerated on every build.py run, so they are not stable waiver keys.
- Schema is strict: unknown keys rejected (`extra="forbid"`), `reason` stripped
  and non-empty, duplicate (rule, match) pairs rejected.
- `validate` / `assess` load the file (if present), partition results:
  waived findings move out of `details` and error/warning counts into a
  `waived` list (each with its reason) + `waived_count`.
- Waivers that matched nothing are reported in `stale_waivers` so dead entries
  get cleaned up instead of silently rotting.
- Malformed `validation.json` (bad JSON, missing reason, unknown keys) →
  CLI exits with `ok: false` and the parse error. Never silently ignored.

## Boundaries & edge cases
- Waiver identity is (`rule`, `match`) — `match` gives message-level targeting
  (e.g. one named bedroom). Stable `element_id` targeting is unsupported because
  GUIDs are regenerated on every build.py run.
- No environment/test-set switching: profiles are per project directory, which
  already IS the per-building-type boundary.
- Waiving a rule does not suppress it in `stale_waivers` accounting.

## Testing & verification
- [ ] Waived warning disappears from details, appears under `waived` with reason
- [ ] Counts (`errors`/`warnings`/`optimizations`) exclude waived findings
- [ ] Waiver with no matching finding → listed in `stale_waivers`
- [ ] Missing `reason` → CLI error, exit code 1
- [ ] Malformed JSON → CLI error, exit code 1
- [ ] Project without validation.json → output identical to today (no new keys
      or empty lists allowed either way, keep it stable for the AI loop)

## Decision log
| Date | Decision | Why | Who |
|------|----------|-----|-----|
| 2026-08-04 | Match by message code prefix, not a new `code` field on ValidationError | codes are uniformly `E0xx:`-prefixed; adding a field means touching every validator (~50 sites) for zero user value | Almir + Claude |
| 2026-08-04 | Per-project file, not per-environment sets | only real axis today is building type = project | Almir + Claude |

## Lessons learned
(after implementation)

## Related
[facade-detection.md](facade-detection.md) — removes villa's E044 false positives
so they never need waiving.
