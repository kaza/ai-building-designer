# Finding: maquette print vs model — discrepancy list (2026-08-05)

## Source
Five owner photos of the cardboard maquette (printed architect plan glued on the
floor = source of truth). Four independent readers: Gemini (pro), Codex
(gpt-5.6-sol, images attached), a Fable subagent (25 tool-uses, crop-by-crop),
and my own calibrated crop reads (px→m via wall anchors). Coordinates: x east,
y north, meters, tolerance ±0.2–0.35 m (oblique photos).

Image key: **15** kitchen+dining+living · **16/18** master + baths top view ·
**17/19** master close-up. 17/19 confirmed as the MASTER (bath tiles visible
south of its bottom wall). **No photo shows Room 2, D1, D6, D7, the deck, or
any window clearly — those stay untouched.** A loose cardboard slab hides the
guest bath north half + Bath 1 NE corner in every photo (findings there capped
at M/L).

## Status legend
`[ ]` to fix  `[x]` fixed  `[~]` provisional (pending owner)  `[?]` open question

## Doors

| # | Item | Model (before) | Corrected (target) | Verdict | Conf |
|---|------|-----------------|--------------------|---------|------|
| D-1 `[x]` | **D8 master terrace door** | single 1.4 leaf x4.55–5.95, swings OUT | **asymmetric pair, both swing SOUTH into master**: small 0.5 leaf hinge WEST (x4.55) + large 0.9 leaf hinge EAST (x5.95), leaves meet ≈x5.05; glass (owner 2026-08-05) | 4/4 on two inward arcs; leaf sizes me 0.5+0.9 / Fable 0.4+0.8 → keep approved 1.4 opening | H |
| D-2 `[x]` | **D5 master entry** | x=8, y5.1–6.0, hinge S, opens W | same hinge S + opens W, shifted to SE corner: **y4.6–5.5** | Codex y4.55–5.45 H, Fable y4.6–5.45 hinge(8,4.6), my 19 read; Gemini's hinge-N refuted | H |
| D-3 `[x]` | **D3 bath 1 door** | x5.5–6.25, hinge W, opens N into master | **x5.25–6.0 w0.75, hinge WEST, opens SOUTH into Bath 1** | swing S: 4/4. Hinge: Fable+me W (printed open leaf at west jamb) vs Codex+Gemini E → W | H swing, M hinge |
| D-4 `[~]` | D4 guest bath door | y3.5–4.25, hinge S, opens W | **y2.8–3.55** (shifted south), hinge S, opens W — forced by toilet-south + shower-north (see B-4/B-5); print hidden under slab | Gemini read it at y2.8–3.5; Codex "≈model" M; Fable y3.8–4.3 L | M |
| D-5 `[x]` | D2 kitchen door | x=4.5, y1.6–2.5, hinge S, opens W into kitchen | **keep** | Codex: matches print (H). Fable dissents: opens E into hallway, w0.7 — logged, outvoted | M-H |
| D-6 | ~~west facade kitchen door~~ | — | DROPPED — the arc reviewers saw is unexplained after the pantry rejection; no door added anywhere | owner rejected the pantry interpretation | — |

## ~~New structure: SW pantry~~ — REJECTED by owner 2026-08-05

Reviewers (Fable H + my pier read) interpreted printed lines in the SW kitchen
corner of 15.png as a pantry room with walls at y=1.85 / x=1.3 and a door.
Owner: **"nobody wanted it — remove"**. Removed same day (walls, D10, space);
kitchen counters S+W restored to their previous bounds. Do NOT re-add without
an explicit owner request, whatever the print seems to show.

| # | Item | Target |
|---|------|--------|
| P-5 `[x]` | Breakfast counter + 3 stools | counter (1.45,1.55)–(3.1,2.05); stools 0.4² on N side at x centers 1.7/2.4/2.95, y2.1–2.5, facing S — kept (clearly printed, not part of the pantry rejection) |

## Master bedroom

| # | Item | Model (before) | Corrected | Conf |
|---|------|-----------------|-----------|------|
| M-1 `[x]` | Bed | (4.65,5.6)–(6.65,7.8) | **(4.65,4.9)–(6.65,7.1)** — consensus north edge ≈7.0 (Codex 6.95 / Fable 7.1 / me 6.9); 7.1 also keeps the D8 east-leaf swing clear (W100). Print nightstands = covered by platform_bed's integrated ones | M-H |
| M-2 `[x]` | Desk | procedural box (7.35,6.9)–(7.9,7.9) | long desk on east wall **(7.4,6.2)–(7.95,7.85)** + separate chair **(6.9,7.1)–(7.35,7.6)** facing E (dining_chair asset); desk primitive → Objaverse asset (owner: no primitives) | M |
| M-3 `[x]` | Dresser | (6.3,4.62)–(7.6,5.02) | **(6.05,4.6)–(7.05,4.95)** (west-shifted, ~1.0 long; also clears D5 swing) | M-H |

## Bathrooms

| # | Item | Model (before) | Corrected | Conf |
|---|------|-----------------|-----------|------|
| B-1 `[x]` | Bath 1 sinks | ONE sink (6.05,3.95)–(6.5,4.4) | **two-basin vanity on WEST wall (4.6,3.0)–(5.1,4.3)** | H (4/4) |
| B-2 `[x]` | Bath 1 toilet | (6.05,2.7)–(6.5,3.25) facing W | **(5.5,2.7)–(5.95,3.3) facing N** (south wall, center-west) | H |
| B-3 `[x]` | Bath 1 bathtub | (4.65,2.65)–(6.35,3.4) | **DELETE** — zone is plain tile in print | M-H |
| B-4 `[x]` | Guest toilet | (6.7,3.95)–(7.15,4.42) N wall | **(6.7,2.85)–(7.15,3.3), back to divider, facing E** | H |
| B-5 `[~]` | Guest shower | (6.64,2.56)–(7.94,3.36) S | **(6.64,3.64)–(7.94,4.44) N** — print hidden under slab; provisional (owner's full-width 0.8×1.3 kept, moved off the printed toilet). D4 moved south (D-4) so its swing clears | L-M |
| B-6 `[x]` | Guest sink | (6.68,3.3)–(7.08,3.7) | **(6.68,3.32)–(7.08,3.6)** squeezed between toilet and shower on the divider; zone half-hidden | M |

## Living / dining

| # | Item | Model (before) | Corrected | Conf |
|---|------|-----------------|-----------|------|
| L-1 `[x]` | Sofa | (0.75,4.9)–(2.5,6.2) facing N, west side | **(3.45,5.0)–(4.4,7.15) back to east wall, facing W** (print: straight 3-seater; our sectional asset kept — revisit if render looks off) | H |
| L-2 `[x]` | Armchairs | one, (3.1,5.1)–(3.95,5.95) facing W | **two**: #1 NE (3.3,7.1)–(4.15,7.9) facing S; #2 (2.9,4.1)–(3.75,4.95) facing N. Print draws both rotated ~30° — our pipeline is axis-aligned 90°-step; accepted approximation (rotation support = YAGNI until owner asks) | H count, M pos |
| L-3 `[x]` | Coffee table | (0.9,6.5)–(1.8,7.1) | **(2.3,5.2)–(3.1,6.6)** long axis N-S | M-H |
| L-4 `[x]` | Dining table | (0.9,3.1)–(2.3,4.3) N-S | **(0.7,3.15)–(2.5,4.1) long axis E-W**; 6 chairs = **3 N + 3 S** (x centers 0.9/1.6/2.3), none at ends | H |
| L-5 `[?]` | TV sideboard | (0.2,4.8)–(0.65,6.3) west wall | keep for now — west wall unverifiable in photos; sofa-faces-west is consistent | — |
| L-6 `[?]` | North-wall crossed unit | none | element exists at ≈(0.65,7.65)–(1.95,8.0) (fireplace? TV? closet?) and conflicts with Win4's 4.2 m span — **owner question** | M exists / L identity |

## Open questions for owner
1. **L-6 / Win4**: what is the crossed box on the living north wall at x≈0.7–2.0 (fireplace / TV / closet)? How wide is the sliding glazing really?
2. **B-5 / D-4**: guest-bath shower position and D4 door — hidden under the loose slab in every photo; current fix is provisional. One photo with the slab lifted settles it.
3. **D2 swing** (minor): Codex says print matches model (opens west into kitchen); Fable reads it opening east into the hallway. Kept as-is.
4. **Bath 1 has no bathing fixture** after removing the tub (Gemini review catch): the print shows only vanity + toilet in the visible zone; if a shower/tub exists it's in the NE corner hidden under the slab — same photo as question 2 settles it.

## Decision log
| Date | Decision | Why |
|------|----------|-----|
| 2026-08-05 | 17/19 = master, not Room 2 | bath tiles south of its bottom wall; topology matches 16/18 |
| 2026-08-05 | 18's "extra wall + hallway box" reinterpreted as east-wall desk strip | resolves the D5 arc-side contradiction; Codex+Gemini concur |
| 2026-08-05 | Pantry room instead of a west facade door | Fable's read explains the arc all three saw; printed floor exists on both sides of the door wall (my crop) |
| 2026-08-05 | D3 hinge west despite 2-2 split | the printed OPEN leaf is drawn at the west jamb (two independent reads) |
| 2026-08-05 | D8 kept at the approved 1.4 opening with 0.5+0.9 leaves | owner approved the 1.4 opening 2026-08-04; reviewers' span reads differ by <0.3 |
| 2026-08-05 | Armchair rotations approximated axis-aligned | furniture pipeline is 90°-step; arbitrary rotation is scope creep until asked |
| 2026-08-05 | Shower north + D4 south (provisional) | printed toilet (H) evicts both from their old spots; their own zone is physically hidden |
