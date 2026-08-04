# Feature: Test fixture ownership policy

## Status
implemented

## Why this exists
Framework tests used to depend on `projects/` — live, user-owned artifacts.
When `sample-4storey-v3` was deleted before publication, 69 tests errored for
months; when showcase data evolved (E032 šupaks fixed), count-assertions
silently went stale. Tests need data they own.

## What it does
Rules for what test data a test may assert against:

| Assertion kind | Allowed data source |
|---|---|
| Exact facts (node counts, names, dimensions, error sets) | **test-owned only**: builders from `tests/factories.py`, or frozen JSON under `tests/fixtures/` |
| Smoke checks (loads, renders, validates without crashing, 0-errors-via-CLI) | may use `projects/` — loose assertions that survive design evolution |

- `tests/factories.py` holds shared synthetic-building builders (e.g.
  `make_defect_building()`); tests compose these instead of hand-rolling
  wall/space geometry inline.
- `projects/` is never a test contract. A design change in a project must not
  be able to break an exact framework assertion.
- Known data quirks in published projects that tests *observe* (not require)
  are documented in-place with comments.

## Boundaries & edge cases
- Frozen JSON fixtures under `tests/fixtures/` are allowed but discouraged —
  builders are self-documenting and survive schema migrations via the API.
- CLI integration tests necessarily run against `projects/` (the CLI resolves
  by project name); keep their assertions at the smoke level or waiver-aware.

## Decision log
| Date | Decision | Why | Who |
|------|----------|-----|-----|
| 2026-08-04 | Builders over frozen JSON | schema changes migrate through the API for free | Almir + Claude |

## Lessons learned
- The original sin was a *path* to a sibling project directory plus one
  `.parent` too many — neither could fail loudly at collection time.

## Related
[space-overlap.md](space-overlap.md) — the framework-level invariant that
makes bad fixture geometry impossible to miss.
