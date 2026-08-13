# Design arena — competing agents on one design problem

## What it does

Given one design problem on one project (e.g. "the villa fails seismic —
fix it with minimal cost and minimal structural change"), the arena runs
several AI solver lanes in parallel. Each lane starts from the same frozen
baseline commit, works alone in its own git worktree on its own branch,
mutates **only the project's build script** (plus `furniture.json` when
rooms move), iterates against the pipeline's machine-checkable outputs
(validator findings, `output/seismic.json` margins, FEM utilizations), and
submits a proposal: the branch itself plus a `proposal.md` with the fix
story, before/after numbers and a cost estimate. A referee re-checks every
candidate, the survivors are published side by side as **publish channels**
of the same project, and the owner picks the winner on the live site. The
winning branch lands via a normal merge commit; losers are tagged and
deleted.

The pipeline is the fitness function. The arena adds no new physics — it
adds isolation, competition and honest comparison on top of the checks the
framework already runs.

## Boundaries

- **Agents never score themselves.** Ranking uses only what the referee
  recomputes from the candidate's mutated files on top of the baseline.
  A lane's own pipeline runs are its private feedback loop, nothing more.
- **Frozen surfaces.** A candidate diff may touch only
  `projects/<name>/build.py` and `projects/<name>/furniture.json`.
  Everything else — `validation.json` (waiving a finding is not fixing
  it), `project.toml` (site facts are facts), `pipeline.toml`, `src/`,
  `specs/`, `tests/` — is frozen; any diff there disqualifies the lane.
  Framework gaps a lane hits are *reported* in its proposal, never patched
  inline.
- **Run baseline un-waives the target findings.** The arena starts from a
  run branch where the waivers for the findings under attack are stripped,
  so "change nothing" scores red, not green.
- **Candidates never publish as the project.** Deploys are keyed by
  project name; candidates publish only through channels (below), only by
  the referee, only after the DQ checks. The CLAUDE.md always-publish rule
  applies to the merged winner on main.
- **Cost is ordinal.** Quantity deltas (concrete m³, masonry m², steel kg,
  glazing m²) are first-class; the € figure uses the unit-rate table in
  the run brief (owner-approved approximations) and ranks options — it is
  not a construction quote.
- The arena is generic; everything project- or run-specific (the problem,
  targets, lanes, budgets, rates) lives in a Tier-2 run brief:
  `projects/<name>/arena/<run-id>/brief.md` (worked example:
  projects/villa-maketa/arena/2026-08-13-seismic/).

## Mechanism

1. **Brief** (Tier-2, owner-approved): problem, target findings, hard
   constraints (floor area preserved, glazing preserved per room, program
   intact), lane strategies, iteration budget, unit rates.
2. **Baseline**: branch `arena/<run-id>/base` from main — strips the
   target waivers, adds the brief. Lanes branch from it:
   `arena/<run-id>/<lane>`, worktree each, own venv (an editable install
   resolves the framework from the *imported* package — a worktree running
   the main checkout's venv would evaluate the wrong tree).
3. **Lane loop**: mutate → rebuild → `validate --strict` + `seismic` →
   read margins → keep or revert → commit each improvement (the branch
   history is the lab notebook) → on green or budget-out, full
   fem-profile pipeline, write `proposal.md`, push.
4. **Referee** (orchestrator, not the lanes): frozen-surface diff check →
   full pipeline re-run in the lane's worktree → metrics extracted from
   artifacts, not from the proposal prose → publish surviving candidates
   to channels.
5. **Decision**: owner walks the channels, picks. Winner: `git merge
   --no-ff`. Losers: tag `arena/<run-id>/<lane>-final`, delete branch.
   Channels and worktrees are torn down; the merged winner republishes as
   the plain project.

## Publish channels

`archicad-builder publish <project> --as <channel>` uploads the same
artifact set under the blob prefix `<channel>/` instead of `<project>/`
and the web app serves it at `/<channel>/…` exactly like a project (the
app is generic over the path segment; the channel needs a `projects` DB
row, inserted/removed by the operator). Guard: the channel must start
with `<project>--` — an alias can never clobber another project's prefix.
All existing publish gates (clean tree, pushed HEAD, freshness ledger)
run unchanged in the candidate's worktree.

## Known limits (pilot honesty)

- **E101 is unwinnable by geometry** at villa seismicity: EN 1998-1
  Table 9.3 gives no URM row at ag·S ≥ 0.20·g·... band — only a
  structure-type change (confined masonry / RC walls) reaches a different
  row, and the framework cannot express one yet (single hardcoded URM
  basis, no per-wall material, no columns). Pilot lanes therefore target
  E100/E102 numerically and must state a structure-type *recommendation*
  with a cost allowance for E101 instead of pretending. The
  `[structure]` preset + `Wall.material` is the first post-pilot feature.
- ELF + plate FEM is a screening model: accidental torsion, vertical
  seismic on cantilevers, detailing are not modelled — every proposal
  carries the engineer-verification banner (mission: building-ready
  *with* civil-engineer validation).
- Lanes run with the operator's credentials on one machine (no sandbox
  jail in the pilot); the referee's frozen-surface check is the security
  boundary that matters for scoring.

## Decision log

| Date | Decision | Why |
|------|----------|-----|
| 2026-08-13 | Worktree-per-lane, branch is the proposal unit | owner sketched branch-per-agent; worktrees let N branches run N pipelines concurrently (per-dir output/ + lock); internal panel, Codex and Gemini all converged on it |
| 2026-08-13 | Referee re-computes; agent output is never trusted for ranking | strongest three-way consensus (panel "referee-by-construction", Codex "clean-room evaluator", Gemini "immutable validation") |
| 2026-08-13 | Strip target waivers on the run branch | red-team finding: E100–E102 are waived on main, so the unchanged baseline scores green and "do nothing" wins |
| 2026-08-13 | Channels (`--as`), not project copies or branch-published names | copies duplicate the Tier-2 record; channels reuse every existing gate and the owner's review medium is the live site (owner: "publish each of them so I can walk through") |
| 2026-08-13 | Lexicographic fitness (gates → cost → change-delta), no weighted sum | ordered owner criteria; a weighted sum lets cheap concrete buy back a shredded facade |
| 2026-08-13 | Pilot now with URM-only physics; E101 handled as documented recommendation | owner: "do the first test run now"; structure-type preset is real feature work and follows the pilot |
| 2026-08-13 | Unit rates are owner-waved approximations (±50%) in the brief | owner: "do any approximation of the cost — more important to run" |
