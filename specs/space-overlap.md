# Feature: Space overlap validation (E090)

## Status
implemented

## Why this exists
Nothing guards space polygon geometry. The published 4apt project has spaces
crossing wall centerlines (S1/S2 Kitchen extends 0.5m past the bedroom wall,
Living past its east wall) — invalid data that silently corrupted downstream
tools: the connectivity graph dropped bedroom door edges (both door probes
landed in the overlapping kitchen) and window queries attributed windows to
the wrong rooms. No validator fired.

## What it does
- New validator **E090**: within a story, no two spaces may overlap.
  Checked pairwise across ALL spaces on the story (apartment spaces and
  story-level spaces alike — a room overlapping a neighboring apartment's
  room is just as invalid).
- Overlap = shapely polygon intersection **area > 0.05 m²** (shared edges and
  corner touches are fine; centerline-aligned neighbors intersect with zero
  area). Below-tolerance slivers are ignored.
- Message carries both space names and the overlap area:
  `E090: Spaces 'A' and 'B' on 'GF' overlap by 0.83m².`
- Severity: **error** — this is broken geometry, not taste. Existing projects
  with known overlaps waive it via validation.json (see below), which keeps
  the rule honest while not rewriting published showcase data.
- Wired into `validate_all_phases`.

## Boundaries & edge cases
- Alignment-to-wall-centerline validation (space edge must sit ON a wall) is
  a separate, harder rule — out of scope; this rule only catches mutual
  overlap, which is what corrupted the tools.
- Degenerate polygons (<3 vertices) are skipped; invalid self-intersecting
  rings are repaired with `shapely.validation.make_valid` (NOT `buffer(0)`,
  which silently drops bow-tie lobes — regression-tested).
- Apartment *boundaries* may overlap spaces (they contain them) — only
  Space-vs-Space is checked.

## Testing & verification
- [ ] Two overlapping spaces → one E090 with both names and area
- [ ] Touching spaces (shared edge) → clean
- [ ] Overlap across apartments → flagged
- [ ] Sliver below 0.05 m² → ignored
- [ ] defect fixture and villa-maketa → E090-clean
- [ ] 3apt/4apt: known overlaps are waived via validation.json; CLI reports 0
      errors with E090 in the waived list

## Decision log
| Date | Decision | Why | Who |
|------|----------|-----|-----|
| 2026-08-04 | Error severity + waivers on legacy projects | rule stays honest; showcase data repair is a separate task | Almir + Claude |
| 2026-08-04 | Waivers are per-pair (`match` on both space names + story), never blanket | a blanket E090 waiver would hide NEW overlaps too (review finding, Codex) | review (Codex) |
| 2026-08-04 | strict xfail canary on generator overlap-freedom | generator draws overlapping open-plan zones; the canary forces cleanup of all E090 exemptions when the generator is repaired | review (Codex) |
| 2026-08-04 | shapely for intersection | already a dependency; hand-rolled polygon clipping is a bug farm | Claude |
| 2026-08-04 | 0.05 m² tolerance | half-thickness slivers from face-vs-centerline drawing shouldn't page anyone | Claude |

## Lessons learned
- E090 revealed the overlap pattern is EVERYWHERE in legacy data: 3apt (8),
  4apt (14), and both v2/v3 *generators* draw open-plan sub-zones overlapping
  living rooms. Blocks waive it via validation.json; generator tests exclude
  E090 explicitly with comments. Generator geometry repair is the follow-up.

## Testing & verification (result)
All checklist items covered in tests/test_space_overlap.py; blocks report
0 errors via CLI with E090 in the waived list (8 and 14 findings waived).

## Related
[test-fixtures.md](test-fixtures.md), [validation-waivers.md](validation-waivers.md)
