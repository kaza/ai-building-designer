# Feature: Project pipeline — one command rebuilds a project

## Status
SHIPPED 2026-08-09. Phase 1 of [web-deployment.md](web-deployment.md).
Worked example: `projects/villa-maketa/pipeline.toml` (13 steps).

## Why this exists
A project's artifacts are produced by a dozen steps that must run in the
right order, with three different interpreters (the venv, `python -m
archicad_builder`, and Blender), and several steps silently consume the
output of an earlier one. Getting the order wrong does not fail — it
publishes **stale artifacts that look fine**. That has already happened:
`export_glb` read a `villa.blend` from a previous run because
`render_blender.py` had been invoked with the venv python instead of
Blender, and a GLB from the wrong model went live.

The order also drifts out of the docs. The pipeline written down in the
villa spec omits `loads` and `fem` entirely, even though publishing now
refuses a `fem-field.json` whose digest does not match `building.json`.

One command, one declared order, no memory required:

```bash
archicad-builder pipeline villa-maketa
```

## What it does
- Reads `projects/<name>/pipeline.toml` — the ordered list of steps for
  that project, each declaring how to run and what it reads and writes.
- Runs the steps in order, stopping at the first non-zero exit.
- **Skips a step only when it can prove nothing changed.** The action
  digest covers the resolved command line, the step's own script source,
  the framework package source (for steps that import it), every
  declared input, the declared environment variables, and the toolchain
  versions (Python, Blender). On top of that, every declared output must
  still hash exactly as it did when the step produced it — a
  hand-patched artifact is not fresh. Every skip prints its reason;
  silence is indistinguishable from a step that ran.
- **A step's old outputs are moved aside before it runs**, so a command
  that exits 0 without writing anything fails loudly instead of
  inheriting the previous run's artifact. They are restored if the step
  fails, and the pipeline is left marked incomplete.
- **Inputs are re-hashed after the command finishes**: an edit landing
  during the eight-minute FEM must not be recorded as already built.
- Content hashes, never mtimes: `git checkout` and `git pull` rewrite
  mtimes, so a mtime-based check reports "fresh" for a model that just
  changed under it.
- `--force` runs everything, `--from <step>` resumes (and refuses if the
  skipped prefix is not fresh), `--list` prints the order without running
  anything. There is deliberately no `--only`: it is a debugging
  convenience that walks straight around the release invariant.

`archicad-builder publish <project>` moved here from `webapp/publish.py`
and gained the gate this feature makes possible: **a clean git tree says
the source is reproducible, it says nothing about the artifacts on
disk**, so publishing now recomputes every digest and refuses unless the
complete pipeline succeeded for exactly these inputs, sources and tools.
It also runs every validation before the first upload (a later failure
used to leave half a release in blob), compares HEAD to its upstream
directly instead of grepping the short status for "ahead", and takes the
artifact basename from the project config instead of the hardcoded
`villa` — a second project would have published its GLB under the
villa's name.

`archicad-builder freshness <project>` reports the same verdict on its
own, exit 1 when something is stale.

## Build profiles
Cumulative, one axis: `all` ⊃ `fem` ⊃ `web`.

| Profile | Adds | Why |
|---|---|---|
| `web` | model, GLB, 2D plans, walkthrough, load takedown | everything the site shows except the X-ray |
| `fem` (default) | the plate FEM and the X-ray page | the X-ray is the differentiating view; a `web` default would silently remove its link from the site and make `L` do nothing |
| `all` | the two Cycles renders | ~70% of a full build for two marketing images |

A step declares the cheapest profile that includes it (`profile = "fem"`)
and may declare extra environment for a profile (`env_by_profile = { all
= { AB_FULL_RENDER = "1" } }`), which is how one Blender step produces
renders under `all` and only the scene otherwise.

**A cheap build never quietly ships an expensive artifact.** If a step
outside the built profile left files on disk, they would be published,
so the release gate still demands they be current — and says how to fix
it. Rebuilding `web` after a model change therefore blocks the release
while an X-ray of the previous building is sitting there, and tells you
to run `--profile fem` or delete it. Refusing beats the alternative,
where a routine cheap publish silently drops a feature from the live
site.

## Boundaries
- The pipeline **orchestrates** steps; it does not implement them. The
  engines themselves moved into the framework on 2026-08-09 (ADR-006),
  with byte-for-byte parity checks guarding each move — superseding the
  earlier decision to keep them at the project layer until a second
  project existed. What the pipeline owns is the ORDER, the freshness
  rules and the failure modes, which is where the damage was.
- Not a build system. No parallelism, no partial-output recovery, no
  dependency graph — a declared linear order is what the domain has.
- Blender is located via `$BLENDER`, else the standard macOS path; a
  missing Blender is a loud error naming the variable, never a skipped
  step.

## Known limit: the cache is defeated by non-deterministic ids
`generate_ifc_id()` is `uuid4()`, so every `build` run rewrites every
`global_id` in `building.json`. Nothing downstream can then be reused:
changing framework code re-runs `build`, which changes `building.json`,
which cascades through IFC, OBJ, Blender, GLB, FEM and the walkthrough —
a full ~13 minute rebuild for a one-line edit. Day-to-day edits to a
project are unaffected (those genuinely change the model), and a no-op
run is still ~2 s.

The fix belongs in the model layer, not here: an IFC `GlobalId` is
supposed to be a PERSISTENT identity for an element across versions of
the model, so deriving it deterministically is more correct than
regenerating it. That is its own change with its own blast radius (every
element, every IFC export) and is not folded into this one.

## Config format
`projects/<name>/pipeline.toml`:

```toml
[project]
model = "villa"          # artifact basename: villa.blend, villa.glb

[[step]]
name    = "build"
run     = ["{python}", "build.py"]
outputs = ["building.json"]

[[step]]
name    = "fem"
run     = ["{python}", "-m", "archicad_builder", "fem", "{project}"]
inputs  = ["building.json"]
outputs = ["output/fem-field.json", "output/xray.html"]

[[step]]
name    = "validate"     # a gate: no artifact, so never cached
run     = ["{python}", "-m", "archicad_builder", "validate", "{project}", "--strict"]
inputs  = ["building.json", "validation.json"]
cache   = false
```

`run` is plain argv executed with `shell=False` in the project
directory. `{python}` resolves to the running interpreter, `{blender}`
to `$BLENDER` or the standard macOS path, `{project}` and `{model}` to
the project name and artifact basename. Paths are project-relative and
may not escape the project directory; two steps may not claim the same
output.

## Failure modes (all loud)
| Situation | Behaviour |
|---|---|
| step exits non-zero | pipeline stops there, prints the step name and the exit code |
| declared output missing after a step ran | error — the step lied about what it produces |
| `pipeline.toml` missing | error naming the file; no implicit default order |
| unknown `--from` step | error listing the valid names |
| a step exits 0 but writes no output | error — its previous output was moved aside, so there is nothing to mistake for fresh |
| two steps claim one output, or a path escapes the project | config error at load time, before anything runs |
| two pipelines run at once | second one refuses; a lock file lives in `output/` |
| Blender not found | error naming `$BLENDER` |

## Acceptance
- `pipeline --list` prints the villa's steps in order.
- A second run with nothing changed skips every skippable step and says
  why; CHANGING `building.json` re-runs everything downstream of it (touching it does not — the rule is content, not mtime).
- Corrupting a recorded hash re-runs the step rather than trusting state.
- `publish` refuses when anything is stale, and says which step.
- Verified on the villa (2026-08-09): 13 steps ran clean end to end;
  a second run skipped 11 and took 1.8 s; `touch building.json` changed
  nothing (content, not mtime); editing `make_walkthrough.py` re-ran
  exactly one step; hand-editing `walkthrough.html` made `freshness`
  refuse to publish.

## Decision log
| Date | Decision | Why |
|------|----------|-----|
| 2026-08-09 | Orchestrate the existing scripts; do NOT generalise `make_walkthrough.py` / `render_blender.py` yet | the ordering bug is what shipped a wrong GLB; the 2500 lines of villa-specific rendering code have never been exercised by a second project, so their "generic" shape is guesswork until one exists |
| 2026-08-09 | Content hashes, not mtimes | a `git checkout` rewrites mtimes and would make a stale model look fresh — the exact lie this feature exists to prevent |
| 2026-08-09 | Every skip prints its reason | a silent skip is indistinguishable from a step that ran, which is how the stale GLB survived review |
| 2026-08-09 | Declarative TOML per project, not a Python hook | the order is data; keeping it data means `--list` can print it and a reviewer can read it without running anything. Gemini proposed a `pipeline.py` with decorators — rejected because listing the order would then mean importing and executing project code |
| 2026-08-09 | Record OUTPUT hashes too, and move outputs aside before a step runs | both reviewers, independently: "output exists" is not freshness. It accepts a hand-edited artifact and a command that exits 0 without writing |
| 2026-08-09 | The action digest includes package source, env vars and tool versions | Codex: the FEM code or PyNite can change while `building.json` is byte-identical, and `VILLA_FULL_RENDER` changes what a step produces |
| 2026-08-09 | `publish` re-derives every digest instead of trusting the `complete` flag | a partial run, a manual script invocation, or an interrupted build can leave a plausible-looking mixture that a clean git tree does not catch |
| 2026-08-09 | `validate` gained `--strict`; the pipeline gate uses it | the command has always exited 0, so the "gate" step in the documented pipeline could never fail a build (Codex found this by reading the code) |
| 2026-08-09 | No `--only` | it bypasses the release invariant for a debugging convenience |
| 2026-08-09 | A step declares the environment it RUNS with (`env_set`), and the villa's Cycles renders are ordinary cached outputs instead of env-gated ones | the renders were produced only when the operator remembered `VILLA_FULL_RENDER=1`, so a plain run silently shipped a release without them, and publishing globbed whatever stale copies were lying around. The cache pays the ~4 min once |
| 2026-08-09 | Cumulative profiles `web`/`fem`/`all`, defaulting to `fem`; artifacts left by a step outside the built profile block the release instead of shipping or being dropped | owner asked for a web-only default with opt-in FEM and renders. Measured: web ~9 s of work, FEM ~104 s, renders ~259 s — so the renders are the only thing worth gating, and defaulting below `fem` would remove the X-ray link from the site on every routine publish |
| 2026-08-09 | The release gate compares against the environment RECORDED for each step, not the current shell | publishing must not require reproducing the shell the build ran in; what matters is that nothing changed since, and the output hashes capture what was produced |

## Related
[web-deployment.md](web-deployment.md) (Phase 1), the villa's worked
example in `projects/villa-maketa/spec.md` (Rendering & viewing).
