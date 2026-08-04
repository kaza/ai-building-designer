# Feature: Facade detection for non-rectangular buildings

## Status
implemented

## Why this exists
E044 ("habitable room has no façade access") assumes a rectangular block with
facades only on the north/south bounding-box edges, and computes building depth
from walls flagged `is_external`. Two failures follow:

1. `Building.add_wall()` never sets `is_external`, so API-built buildings have
   building_depth = 0 and every habitable room fails E044.
2. Rooms on west/east facades, or on exterior segments of an L-shaped footprint
   (villa-maketa: Living, Master Bedroom), are false positives even when flagged.

## What it does
- `Building.add_wall()` gains `is_external: bool = False` and
  `load_bearing: bool = False` keyword params (defaults = current model defaults,
  fully backward compatible).
- E044 rewritten: a habitable room has facade access iff **any axis-aligned edge
  of its boundary polygon lies along a wall with `is_external=True`** (same
  overlap test and 0.2m tolerance as E071's `_edge_has_wall`, filtered to
  external walls).
- If a story has apartments but **zero external walls**, E044 cannot judge:
  emit one story-level warning ("W046: no external walls marked — facade checks
  skipped") instead of failing every room. Fail loud, don't guess.
  (W044/W045 are already taken by other rules.)
- "Habitable" = the existing `habitable_types` set (LIVING, BEDROOM, KITCHEN) —
  the old skip-list accidentally treated balcony/staircase/utility as habitable.
- New params are **keyword-only** (after name/description) so existing positional
  callers can't silently shift; the CLI `apply add-wall` action forwards both.

## Boundaries & edge cases
- Non-axis-aligned (diagonal) walls: out of scope, as everywhere else in the repo.
- Window presence on the facade wall is NOT checked (parity with old behavior —
  E044 checks adjacency only). Follow-up if ever needed.
- Rooms with polygon (not rect) boundaries: all edges are checked, not the bbox.

## Testing & verification
- [ ] Room on west facade (window wall) → no E044
- [ ] Interior room (no exterior edge) → E044
- [ ] L-footprint: room whose only exterior edge is a notch segment → no E044
- [ ] Story with apartments, no `is_external` walls → single W044, no per-room E044
- [ ] `add_wall(is_external=True)` sets the flag
- [ ] Block projects (3apt, 4apt) still validate to 0 errors

## Decision log
| Date | Decision | Why | Who |
|------|----------|-----|-----|
| 2026-08-04 | Edge-on-external-wall test instead of bbox y-extremes | correct for L-shapes and E/W facades | Almir + Claude |
| 2026-08-04 | W046 warning when no external walls | old code silently produced garbage; fail loud; W044 taken | review (Codex) |
| 2026-08-04 | Polygon edges enumerated modulo n incl. closing edge; ranges normalized; overlap must be positive (>1cm), not mere corner touch | review (Codex) — closing edge and CW/CCW would silently pass/fail rooms | review (Codex) |
| 2026-08-04 | Rejected: tolerance derived from wall thickness | parity with E071's fixed 0.2m; revisit if thick-wall projects appear | Claude |
| 2026-08-04 | Rejected: geometric auto-detection of external hull | future feature; explicit flag is the contract for now | Claude |

## Lessons learned
(after implementation)

## Related
[validation-waivers.md](validation-waivers.md) — villa-maketa waives its remaining
villa-vs-block warnings once this fix removes the E044 false positives.
