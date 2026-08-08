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
