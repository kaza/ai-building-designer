# Audit log — static load takedown

## Attempt 01 — 2026-08-08 ~12:00
- Input: building.json @ 7519cb9 (12 openings on load-bearing GF walls).
- Command: `../../.venv/bin/python load_takedown.py` → logs/attempt-01.txt
- Result: every wide opening's 0.20 m band FAILS unreinforced by 6–144×
  (scenario A, roof as modeled); still 4–97× under realistic scenario B.
  A minimally reinforced 2Ø12 ring beam also fails for every opening
  wider than ~1.5 m (1.4–20×). Worst: Hallway Window, 5.55 m effective
  span, util 144× plain / 20× with 2Ø12. Win7 (Living Band Window N):
  57× plain, 8× with 2Ø12. Win2 (Living Glass W2): 25× / 3.5×.
- Only the Vila Entry Door passes everything (0.90 m band above it).
- Deterministic calc — re-run reproduces byte-identical output.
- Method notes / known conservatisms: tributary assigns BOTH directions'
  half-spans to a wall (real one-way slabs load one pair of walls);
  simply-supported M=qL²/8 (continuity would reduce ~30%). Neither
  conservatism is anywhere near the 6–144× margins → verdict robust.

## Attempt 03 — 2026-08-08 ~12:45 (post-Win8 removal)
- Input: building.json @ 564a51c (Win8 removed → 11 openings).
- Command: same → logs/attempt-03-post-win8.txt
- Result: Win8's 79x row is gone (wall solid). All other verdicts
  unchanged — removal of one opening does not relieve its neighbors
  (tributary loads are per-wall-strip, not redistributed). Worst
  remains Hallway Window: 144x plain / 20x with 2Ø12 over 5.55 m.

## Attempt 04 — 2026-08-08 ~14:00 (garage A + x=4.5 bearing line)
- Input: building.json with garage x4.5-9.5/y0.6-8 and Living East Wall
  load-bearing. Command: same → logs/attempt-04-garage-A.txt
- Result: E/W facade line loads drop ~35-45% (west 86→51 kN/m, east
  75→49). Win6: 144x→95x plain (20x→13x with 2Ø12); Win2: 25x→15x
  (3.5x→2.1x). North facade unchanged (the new line runs N-S). New row
  "Vila Kitchen Door" on the now-bearing x=4.5 wall passes (0.63).
- Conclusion: the bearing line is the enabler, not the cure — every wide
  opening still needs an engineered beam (ring-beam / E06x feature).

## Attempt 05 — 2026-08-08 ~15:00 (check the PLACED beams)
- Script extended: per opening, find the covering beam (E062-style) and
  check ITS section (RC, rho 0.5%) instead of the naked band.
- Result: heuristic span/10 depths undersized 4 beams under scenario B
  (realistic roof): Win7 1.50, Win4 1.28, west band 1.17, Win6 1.02.
  Kitchen 0.28 / Win2 0.42 pass. Sub-1.25m openings correctly beamless.

## Attempt 06 — 2026-08-08 ~15:05 (resized)
- Explicit depths: west band 0.40, Win4/Win7 0.45, Win6 0.60.
- Result: all beams util 0.28-0.87 under scenario B (design target —
  finding #3: the modeled 0.45m roof is visual). Scenario A (fictional
  solid slab) still shows 1.06-1.25 — documented, not chased.

## Attempt 07 — 2026-08-08 ~16:30 (true utilization + garage)
- Owner: "show me what would fail, not a light show; % of load = color;
  I want to see the garage." Emitter rewritten: walls now carry TRUE
  axial utilization (capacity = t × Φ·f_d, f_d 3.0 MPa, Φ 0.6, self-
  weight included); garage storey added — each garage wall gets the
  aligned GF wall's load + GF slab one-way strip (ULS ≈ 13.5 kN/m²) +
  self; garage door beam checked against its wall's line load.
- Result: 22 elements. Walls all quiet (u 0.08-0.25). The story is the
  beams: west band 0.87, hallway 0.86, Win7 0.85, Win4 0.73, garage
  door 0.56, rest < 0.45. Nothing over capacity.
