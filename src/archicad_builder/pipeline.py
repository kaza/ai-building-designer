"""One command rebuilds a project (specs/project-pipeline.md).

A project declares its build steps in `pipeline.toml`; this runs them in
order and skips a step only when it can PROVE nothing that step depends
on has changed. The whole point is that a stale artifact cannot survive,
so the freshness rule is deliberately paranoid:

  action digest = resolved argv + working directory + the step's own
                  script source + the framework package source (for steps
                  that import it) + every declared input + the declared
                  environment variables + the toolchain versions

Skipping also requires every declared output to still hash exactly as it
did when the step produced it — a hand-edited artifact is not fresh.
Content hashes, never mtimes: `git checkout` rewrites mtimes and would
report a model that just changed under us as up to date.

Plan review (Codex + Gemini, 2026-08-09) supplied most of these rules;
each one closes a specific way a stale artifact reached the browser.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field as dc_field
from pathlib import Path

SCHEMA = 1
STATE_NAME = ".pipeline.json"
LOCK_NAME = ".pipeline.lock"
MAC_BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"


class PipelineError(RuntimeError):
    """Anything that would make the build untrustworthy. Never swallowed."""


@dataclass
class Step:
    name: str
    argv: list[str]
    inputs: list[str] = dc_field(default_factory=list)
    outputs: list[str] = dc_field(default_factory=list)
    # produced only under some conditions (the villa's Cycles renders need
    # VILLA_FULL_RENDER). Not required to exist, but hashed WHEN they do —
    # otherwise they are published without any freshness check at all,
    # which is how two-day-old renders shipped beside a fresh model
    # (CodeRabbit review 2026-08-09).
    optional_outputs: list[str] = dc_field(default_factory=list)
    env: list[str] = dc_field(default_factory=list)
    cache: bool = True
    # does this step import archicad_builder? Hashing the framework for
    # steps that don't (Blender scripts run in Blender's own interpreter,
    # fetch_assets only touches the network) meant an edit to publish.py
    # forced a 13-minute Blender+FEM rebuild (Codex review 2026-08-09).
    framework: bool | None = None

    @property
    def all_outputs(self) -> list[str]:
        return self.outputs + self.optional_outputs


@dataclass
class StepRun:
    name: str
    ran: bool
    reason: str


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _tree_sha(root: Path, pattern: str = "**/*") -> str:
    """One digest over a source tree — changing the framework invalidates
    every step that imports it (Codex: the FEM code can change while
    building.json stays identical)."""
    h = hashlib.sha256()
    for p in sorted(root.glob(pattern)):
        if "__pycache__" in p.parts or not p.is_file():
            continue
        h.update(p.relative_to(root).as_posix().encode())
        h.update(_sha(p).encode())
    return h.hexdigest()


def _package_root() -> Path:
    return Path(__file__).resolve().parent


def load_pipeline(project_dir: Path) -> tuple[dict, list[Step]]:
    cfg_path = project_dir / "pipeline.toml"
    if not cfg_path.is_file():
        raise PipelineError(
            f"no pipeline.toml in {project_dir} — a project declares its "
            "build order there; there is no implicit default")
    try:
        raw = tomllib.loads(cfg_path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise PipelineError(f"pipeline.toml is not valid TOML: {exc}") from exc

    steps: list[Step] = []
    for entry in raw.get("step", []):
        if "name" not in entry or "run" not in entry:
            raise PipelineError(f"step needs 'name' and 'run': {entry}")
        steps.append(Step(
            name=entry["name"], argv=list(entry["run"]),
            inputs=list(entry.get("inputs", [])),
            outputs=list(entry.get("outputs", [])),
            optional_outputs=list(entry.get("optional_outputs", [])),
            env=list(entry.get("env", [])),
            cache=bool(entry.get("cache", True)),
            framework=entry.get("framework")))
    if not steps:
        raise PipelineError(f"{cfg_path} declares no steps")

    seen: set[str] = set()
    claimed: dict[str, str] = {}
    later_producers: dict[str, dict[str, str]] = {}
    for i, step in enumerate(steps):
        later_producers[step.name] = {
            rel: other.name
            for other in steps[i + 1:] for rel in other.all_outputs}
    for s in steps:
        if s.name in seen:
            raise PipelineError(f"duplicate step name {s.name!r}")
        seen.add(s.name)
        for rel in s.inputs + s.all_outputs:
            resolved = (project_dir / rel).resolve()
            if not resolved.is_relative_to(project_dir.resolve()):
                raise PipelineError(
                    f"step {s.name!r} declares {rel!r}, which would escape "
                    "the project directory")
        # a step may only consume what an EARLIER step produces: consuming a
        # later step's output builds against the previous run's file, which
        # is the exact ordering bug this feature exists to prevent
        for rel in s.inputs:
            if rel in later_producers.get(s.name, ()):
                raise PipelineError(
                    f"step {s.name!r} consumes {rel!r}, which is produced by "
                    f"the later step {later_producers[s.name][rel]!r} — "
                    "declare the producer first")
        for rel in s.all_outputs:
            if rel in claimed:
                raise PipelineError(
                    f"steps {claimed[rel]!r} and {s.name!r} both produce "
                    f"{rel!r} — one output, one owner")
            claimed[rel] = s.name
    return raw.get("project", {}), steps


def _resolve_argv(step: Step, project_dir: Path, model: str,
                  project: str) -> tuple[list[str], bool]:
    """Resolved argv, plus whether this step runs Blender. Returning the
    flag beats sniffing the resolved path for the word 'blender' — a
    custom $BLENDER would silently drop the version from the digest."""
    out, uses_blender = [], False
    for token in step.argv:
        if token == "{python}":
            out.append(sys.executable)
        elif token == "{blender}":
            out.append(_blender())
            uses_blender = True
        else:
            expanded = (token.replace("{project}", project)
                             .replace("{model}", model))
            leftover = re.findall(r"\{[a-zA-Z_]+\}", expanded)
            if leftover:
                raise PipelineError(
                    f"step {step.name!r}: unknown placeholder "
                    f"{leftover[0]} in {token!r} — known: {{python}}, "
                    "{blender}, {project}, {model}")
            out.append(expanded)
    return out, uses_blender


def _blender() -> str:
    env = os.environ.get("BLENDER")
    if env:
        if not Path(env).exists():
            raise PipelineError(f"$BLENDER points at {env}, which does not exist")
        return env
    found = shutil.which("blender") or (MAC_BLENDER
                                        if Path(MAC_BLENDER).exists() else None)
    if not found:
        raise PipelineError(
            "Blender not found — set $BLENDER to the executable "
            f"(looked for 'blender' on PATH and {MAC_BLENDER})")
    return found


def _dep_versions() -> str:
    """Installed versions of the runtime dependencies. Promised in the
    docstring and the spec ("a PyNite upgrade must invalidate"), so it has
    to actually be in the digest (CodeRabbit review 2026-08-09)."""
    from importlib.metadata import PackageNotFoundError, version
    out = []
    for dist in ("PyNiteFEA", "ifcopenshell", "shapely", "numpy", "pillow",
                 "matplotlib", "scipy"):
        try:
            out.append(f"{dist}={version(dist)}")
        except PackageNotFoundError:
            out.append(f"{dist}=absent")
    return ",".join(out)


def _tool_versions(argv: list[str], cache: dict, *,
                   uses_blender: bool = False) -> str:
    """Toolchain fingerprint: a Blender or PyNite upgrade must invalidate
    results computed with the old one."""
    if "deps" not in cache:
        cache["deps"] = _dep_versions()
    parts = [f"python={sys.version.split()[0]}", cache["deps"]]
    if uses_blender:
        if "blender" not in cache:
            try:
                cache["blender"] = subprocess.run(
                    [argv[0], "--version"], capture_output=True, text=True,
                    timeout=60).stdout.splitlines()[0].strip()
            except Exception as exc:            # noqa: BLE001 - reported, not hidden
                raise PipelineError(
                    f"could not read the Blender version: {exc}") from exc
        parts.append(cache["blender"])
    return "|".join(parts)


def _action_digest(step: Step, project_dir: Path, argv: list[str],
                   tools: str) -> str:
    h = hashlib.sha256()
    h.update(f"schema={SCHEMA}\n".encode())
    h.update(("argv=" + "\x00".join(argv) + "\n").encode())
    h.update(f"cwd={project_dir.name}\n".encode())
    h.update(f"tools={tools}\n".encode())
    for name in step.env:
        # unset must differ from empty: exporting VILLA_FULL_RENDER= is not
        # the same as not exporting it
        raw = os.environ.get(name)
        h.update(f"env:{name}={'\x00UNSET' if raw is None else raw}\n".encode())
    # the step's own script is an implicit input — editing make_walkthrough
    # must rebuild the walkthrough even though building.json is untouched
    for token in argv[1:]:
        candidate = project_dir / token
        if token.endswith(".py") and candidate.is_file():
            h.update(f"src:{token}={_sha(candidate)}\n".encode())
    uses_framework = (step.framework if step.framework is not None
                      else "archicad_builder" in argv)
    if uses_framework:
        h.update(f"package={_tree_sha(_package_root())}\n".encode())
    for rel in step.all_outputs:
        # declaring a NEW output must invalidate: the old state only knows
        # the old list, so the step would be "fresh" without ever producing
        # the new artifact (Gemini review 2026-08-09)
        h.update(f"out:{rel}\n".encode())
    for rel in step.inputs:
        p = project_dir / rel
        if p.is_dir():
            raise PipelineError(
                f"step {step.name!r} declares the directory {rel!r} as an "
                "input — hashing would silently ignore its contents; list "
                "the files, or a manifest the producing step writes")
        if not p.is_file():
            # hashing a missing path to a CONSTANT froze the step forever:
            # one typo and it never invalidated again (CodeRabbit probe)
            raise PipelineError(
                f"step {step.name!r} declares the input {rel!r}, which does "
                "not exist — fix the path, or declare the step that "
                "produces it first")
        h.update(f"in:{rel}={_sha(p)}\n".encode())
    return h.hexdigest()


def _output_hashes(step: Step, project_dir: Path) -> dict[str, str]:
    """Required outputs must exist; optional ones are recorded as ABSENT so
    that appearing or disappearing is itself a change."""
    out = {}
    for rel in step.outputs:
        p = project_dir / rel
        out[rel] = _sha(p) if p.is_file() else "MISSING"
    for rel in step.optional_outputs:
        p = project_dir / rel
        out[rel] = _sha(p) if p.is_file() else "ABSENT"
    return out


def _read_state(project_dir: Path) -> dict:
    path = project_dir / "output" / STATE_NAME
    try:
        state = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"schema": SCHEMA, "complete": False, "steps": {}}
    if state.get("schema") != SCHEMA:      # a format change is a cache miss
        return {"schema": SCHEMA, "complete": False, "steps": {}}
    return state


def _write_state(project_dir: Path, state: dict) -> None:
    out = project_dir / "output"
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / (STATE_NAME + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(out / STATE_NAME)          # atomic: never a half-written state


def _stale_reason(step: Step, project_dir: Path, state: dict,
                  digest: str) -> str | None:
    """None means fresh; a string says why the step must run."""
    if not step.cache:
        return "always runs (cache = false)"
    recorded = state.get("steps", {}).get(step.name)
    if not recorded:
        return "never recorded"
    if recorded.get("action") != digest:
        return "inputs, sources, tools or environment changed"
    for rel, want in recorded.get("outputs", {}).items():
        p = project_dir / rel
        if not p.is_file():
            if want == "ABSENT":
                continue           # optional output, still absent: fine
            return f"output {rel} is missing"
        if _sha(p) != want:
            return f"output {rel} was modified after it was built"
    return None


def freshness_problems(project_dir: Path) -> list[str]:
    """Why this project's artifacts must NOT be published. Empty = good.

    Publishing off a half-finished or hand-patched tree is the failure
    this whole feature exists to prevent, so the release gate re-derives
    every digest rather than trusting the 'complete' flag alone.
    """
    try:
        cfg, steps = load_pipeline(project_dir)
    except PipelineError as exc:
        return [str(exc)]
    state = _read_state(project_dir)
    if not state.get("complete"):
        return ["the last pipeline run was incomplete — run "
                f"`archicad-builder pipeline {project_dir.name}`"]
    problems = []
    tools_cache: dict = {}
    for step in steps:
        try:
            argv, uses_blender = _resolve_argv(
                step, project_dir, cfg.get("model", ""), project_dir.name)
            digest = _action_digest(
                step, project_dir, argv,
                _tool_versions(argv, tools_cache, uses_blender=uses_blender))
        except PipelineError as exc:
            problems.append(f"{step.name}: {exc}")
            continue
        if not step.cache:
            # a gate leaves no artifact, but it still has to have RUN
            # against the current rules: editing validation.json after the
            # build would otherwise publish a model the gate never saw
            recorded = state.get("steps", {}).get(step.name)
            if not recorded or recorded.get("action") != digest:
                problems.append(
                    f"{step.name}: gate has not run against the current "
                    "inputs, sources, tools or environment")
            continue
        why = _stale_reason(step, project_dir, state, digest)
        if why:
            problems.append(f"{step.name}: {why}")
    return problems


def publishable_artifacts(project_dir: Path) -> list[str]:
    """Every artifact the pipeline DECLARES, required or optional.

    Publishing used to glob the output directory, which shipped files no
    step claimed — two-day-old Cycles renders travelled beside a fresh
    model for days because nothing checked them (CodeRabbit 2026-08-09).
    """
    _cfg, steps = load_pipeline(project_dir)
    return [rel for step in steps for rel in step.all_outputs]


class Lock:
    """One pipeline per project at a time — two concurrent runs would
    interleave their outputs and their state file."""

    def __init__(self, project_dir: Path):
        self.path = project_dir / "output" / LOCK_NAME

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise PipelineError(
                f"another pipeline is running for this project ({self.path}) "
                "— delete the lock if that is wrong") from None
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return self

    def __exit__(self, *exc):
        try:
            self.path.unlink(missing_ok=True)
        except OSError as err:
            # EXPLICIT swallow: raising here would REPLACE an in-flight
            # exception with a cleanup error, hiding why the build failed.
            # The lock is reported loudly instead, so the next run's
            # "another pipeline is running" message is not a phantom.
            print(f"pipeline: could not remove the lock {self.path}: {err}",
                  file=sys.stderr)


def run_pipeline(project_dir: Path, *, force: bool = False,
                 from_step: str | None = None,
                 list_only: bool = False) -> list[StepRun]:
    cfg, steps = load_pipeline(project_dir)
    names = [s.name for s in steps]
    if from_step and from_step not in names:
        raise PipelineError(
            f"unknown step {from_step!r} — pipeline has: {', '.join(names)}")
    if list_only:
        return [StepRun(s.name, False, "listed") for s in steps]

    model = cfg.get("model", "")
    results: list[StepRun] = []
    tools_cache: dict = {}
    with Lock(project_dir):
        state = _read_state(project_dir)
        state["complete"] = False          # incomplete until every step passes
        _write_state(project_dir, state)

        start = names.index(from_step) if from_step else 0
        if from_step:
            # resuming must not paper over a stale prefix (Codex review)
            for step in steps[:start]:
                argv, ub = _resolve_argv(step, project_dir, model,
                                         project_dir.name)
                digest = _action_digest(
                    step, project_dir, argv,
                    _tool_versions(argv, tools_cache, uses_blender=ub))
                why = _stale_reason(step, project_dir, state, digest)
                if why and step.cache:
                    raise PipelineError(
                        f"cannot start at {from_step!r}: earlier step "
                        f"{step.name!r} is not fresh ({why})")

        for step in steps[start:]:
            argv, uses_blender = _resolve_argv(step, project_dir, model,
                                               project_dir.name)
            tools = _tool_versions(argv, tools_cache,
                                   uses_blender=uses_blender)
            digest = _action_digest(step, project_dir, argv, tools)
            why = None if force else _stale_reason(step, project_dir, state,
                                                   digest)
            if why is None and not force:
                results.append(StepRun(step.name, False, "unchanged"))
                continue

            # move existing outputs aside: a step that exits 0 without
            # writing must not inherit the previous run's artifact
            backups = []
            for rel in step.all_outputs:
                p = project_dir / rel
                bak = p.with_suffix(p.suffix + ".prev")
                # a SIGKILLed run can leave an orphan .prev with no output;
                # recover it rather than stranding the artifact forever
                if bak.is_file() and not p.is_file():
                    bak.replace(p)
                if p.is_file():
                    p.replace(bak)
                    backups.append((p, bak))
            # Ctrl-C during the 8-minute FEM, or a missing executable,
            # must not leave the previous artifacts stranded as .prev
            # (Gemini review 2026-08-09) — hence BaseException.
            restore = True
            try:
                proc = subprocess.run(argv, cwd=project_dir)
                if proc.returncode != 0:
                    raise PipelineError(
                        f"step {step.name!r} failed (exit {proc.returncode}): "
                        + " ".join(argv))
                missing = [rel for rel in step.outputs
                           if not (project_dir / rel).is_file()]
                if missing:
                    raise PipelineError(
                        f"step {step.name!r} did not produce "
                        + ", ".join(missing))
                restore = False
            finally:
                # a failure while restoring must not REPLACE the real error
                # (it used to, and it stranded the lock too) — collect and
                # attach instead
                lost = []
                for p, bak in backups:
                    try:
                        bak.replace(p) if restore else bak.unlink(
                            missing_ok=True)
                    except OSError as exc:      # reported, never hidden
                        lost.append(f"{p.name}: {exc}")
                if lost:
                    print("pipeline: could not restore " + "; ".join(lost),
                          file=sys.stderr)

            # re-derive the digest AFTER the run: an input edited during a
            # long step would otherwise be recorded as already built
            after = _action_digest(step, project_dir, argv, tools)
            state.setdefault("steps", {})[step.name] = {
                "action": after,
                "outputs": _output_hashes(step, project_dir),
            }
            _write_state(project_dir, state)
            results.append(StepRun(step.name, True, why or "forced"))

        state["complete"] = (start == 0)   # a partial run is not a release
        _write_state(project_dir, state)
    return results
