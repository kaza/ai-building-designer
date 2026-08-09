"""Project pipeline (specs/project-pipeline.md).

The feature exists to make a STALE artifact impossible, so most of these
tests are about the ways a step could wrongly be considered fresh:
changed sources, changed tools, tampered outputs, a step that exits 0
without writing anything, an edit landing during a long run.
"""

import json

import pytest

from archicad_builder.pipeline import (
    PipelineError,
    Step,
    freshness_problems,
    load_pipeline,
    run_pipeline,
)


@pytest.fixture
def project(tmp_path):
    """A miniature project: two steps, the second consuming the first."""
    root = tmp_path / "projects" / "toy"
    (root / "output").mkdir(parents=True)
    (root / "make_a.py").write_text(
        "from pathlib import Path\n"
        "Path('output/a.txt').write_text('A' + Path('seed.txt').read_text())\n")
    (root / "make_b.py").write_text(
        "from pathlib import Path\n"
        "Path('output/b.txt').write_text(Path('output/a.txt').read_text() + 'B')\n")
    (root / "seed.txt").write_text("seed")
    (root / "pipeline.toml").write_text(
        '[project]\nmodel = "toy"\n\n'
        '[[step]]\nname = "a"\nrun = ["{python}", "make_a.py"]\n'
        'inputs = ["seed.txt"]\noutputs = ["output/a.txt"]\n\n'
        '[[step]]\nname = "b"\nrun = ["{python}", "make_b.py"]\n'
        'inputs = ["output/a.txt"]\noutputs = ["output/b.txt"]\n')
    return root


def _state(project):
    return json.loads((project / "output" / ".pipeline.json").read_text())


class TestOrderAndOutputs:
    def test_runs_every_step_in_order(self, project):
        ran = run_pipeline(project)
        assert [r.name for r in ran] == ["a", "b"]
        assert all(r.ran for r in ran)
        assert (project / "output" / "b.txt").read_text() == "AseedB"

    def test_second_run_skips_everything_and_says_why(self, project):
        run_pipeline(project)
        ran = run_pipeline(project)
        assert not any(r.ran for r in ran)
        assert all("unchanged" in r.reason for r in ran)

    def test_changed_input_reruns_the_dependent_step(self, project):
        run_pipeline(project)
        (project / "seed.txt").write_text("SEED")
        ran = {r.name: r for r in run_pipeline(project)}
        assert ran["a"].ran and ran["b"].ran        # b consumes a's output
        assert (project / "output" / "b.txt").read_text() == "ASEEDB"

    def test_list_only_runs_nothing(self, project):
        ran = run_pipeline(project, list_only=True)
        assert [r.name for r in ran] == ["a", "b"]
        assert not (project / "output" / "a.txt").exists()

    def test_missing_declared_output_is_an_error(self, project):
        (project / "make_a.py").write_text("pass\n")     # writes nothing
        with pytest.raises(PipelineError, match="did not produce"):
            run_pipeline(project)

    def test_failing_step_stops_the_pipeline(self, project):
        (project / "make_a.py").write_text("raise SystemExit(3)\n")
        with pytest.raises(PipelineError, match="exit 3"):
            run_pipeline(project)
        assert not (project / "output" / "b.txt").exists()


class TestStaleness:
    """Every one of these was a way a stale artifact could survive."""

    def test_changed_script_source_reruns_the_step(self, project):
        run_pipeline(project)
        (project / "make_a.py").write_text(
            "from pathlib import Path\n"
            "Path('output/a.txt').write_text('CHANGED')\n")
        ran = {r.name: r for r in run_pipeline(project)}
        assert ran["a"].ran, "editing the script must invalidate its step"
        assert (project / "output" / "a.txt").read_text() == "CHANGED"

    def test_tampered_output_reruns_the_step(self, project):
        run_pipeline(project)
        (project / "output" / "a.txt").write_text("hand-edited")
        ran = {r.name: r for r in run_pipeline(project)}
        assert ran["a"].ran, "a hand-edited artifact must not be trusted"
        assert (project / "output" / "a.txt").read_text() == "Aseed"

    def test_deleted_output_reruns_the_step(self, project):
        run_pipeline(project)
        (project / "output" / "a.txt").unlink()
        assert {r.name: r for r in run_pipeline(project)}["a"].ran

    def test_reordering_the_config_reruns(self, project):
        run_pipeline(project)
        cfg = (project / "pipeline.toml").read_text().replace(
            'name = "a"', 'name = "a"\nenv = ["TOY_MODE"]')
        (project / "pipeline.toml").write_text(cfg)
        assert {r.name: r for r in run_pipeline(project)}["a"].ran

    def test_changed_env_value_reruns(self, project, monkeypatch):
        cfg = (project / "pipeline.toml").read_text().replace(
            'inputs = ["seed.txt"]', 'inputs = ["seed.txt"]\nenv = ["TOY_MODE"]')
        (project / "pipeline.toml").write_text(cfg)
        monkeypatch.setenv("TOY_MODE", "1")
        run_pipeline(project)
        monkeypatch.setenv("TOY_MODE", "2")
        assert {r.name: r for r in run_pipeline(project)}["a"].ran

    def test_corrupt_state_is_a_cache_miss_not_a_crash(self, project):
        run_pipeline(project)
        (project / "output" / ".pipeline.json").write_text("{ not json")
        ran = run_pipeline(project)
        assert all(r.ran for r in ran)

    def test_force_reruns_everything(self, project):
        run_pipeline(project)
        assert all(r.ran for r in run_pipeline(project, force=True))


class TestPublishGate:
    def test_complete_pipeline_reports_no_problems(self, project):
        run_pipeline(project)
        assert freshness_problems(project) == []

    def test_interrupted_pipeline_is_not_publishable(self, project):
        (project / "make_b.py").write_text("raise SystemExit(1)\n")
        with pytest.raises(PipelineError):
            run_pipeline(project)
        assert any("incomplete" in p for p in freshness_problems(project))

    def test_never_run_pipeline_is_not_publishable(self, project):
        assert freshness_problems(project)

    def test_edit_after_a_complete_run_is_caught(self, project):
        run_pipeline(project)
        (project / "seed.txt").write_text("changed after the build")
        problems = freshness_problems(project)
        assert any("a" in p for p in problems)


class TestConfig:
    def test_missing_config_names_the_file(self, tmp_path):
        (tmp_path / "output").mkdir()
        with pytest.raises(PipelineError, match="pipeline.toml"):
            load_pipeline(tmp_path)

    def test_unknown_from_step_lists_valid_names(self, project):
        with pytest.raises(PipelineError, match="a, b"):
            run_pipeline(project, from_step="nope")

    def test_from_step_requires_a_fresh_prefix(self, project):
        with pytest.raises(PipelineError, match="not fresh"):
            run_pipeline(project, from_step="b")

    def test_from_step_runs_the_tail_once_the_prefix_is_fresh(self, project):
        run_pipeline(project)
        ran = {r.name: r for r in run_pipeline(project, from_step="b",
                                               force=True)}
        assert ran["b"].ran and "a" not in ran

    def test_outputs_may_not_escape_the_project(self, project):
        (project / "pipeline.toml").write_text(
            (project / "pipeline.toml").read_text().replace(
                '"output/a.txt"', '"../../escaped.txt"'))
        with pytest.raises(PipelineError, match="escape"):
            load_pipeline(project)

    def test_steps_may_not_claim_the_same_output(self, project):
        (project / "pipeline.toml").write_text(
            (project / "pipeline.toml").read_text().replace(
                '"output/b.txt"', '"output/a.txt"'))
        with pytest.raises(PipelineError, match="both"):
            load_pipeline(project)

    def test_step_names_are_unique(self, project):
        (project / "pipeline.toml").write_text(
            (project / "pipeline.toml").read_text().replace(
                'name = "b"', 'name = "a"'))
        with pytest.raises(PipelineError, match="duplicate"):
            load_pipeline(project)


def test_step_is_a_plain_record():
    s = Step(name="x", argv=["{python}", "y.py"], inputs=[], outputs=[],
             env=[], cache=True)
    assert s.name == "x" and s.cache is True


class TestReviewFindings:
    """Each of these was a live way a stale artifact could be published
    (Gemini code review 2026-08-09)."""

    def test_editing_a_gates_input_blocks_publishing(self, project):
        cfg = (project / "pipeline.toml").read_text() + (
            '\n[[step]]\nname = "gate"\n'
            'run = ["{python}", "gate.py"]\n'
            'inputs = ["rules.txt"]\ncache = false\n')
        (project / "pipeline.toml").write_text(cfg)
        (project / "gate.py").write_text("pass\n")
        (project / "rules.txt").write_text("v1")
        run_pipeline(project)
        assert freshness_problems(project) == []
        (project / "rules.txt").write_text("v2")     # rules changed after
        problems = freshness_problems(project)
        assert any("gate" in p for p in problems), (
            "a gate that never ran against the current rules must block "
            "the release")

    def test_declaring_a_new_output_reruns_the_step(self, project):
        run_pipeline(project)
        (project / "make_a.py").write_text(
            "from pathlib import Path\n"
            "Path('output/a.txt').write_text('Aseed')\n"
            "Path('output/a2.txt').write_text('second')\n")
        cfg = (project / "pipeline.toml").read_text().replace(
            '"output/a.txt"]\n', '"output/a.txt", "output/a2.txt"]\n', 1)
        (project / "pipeline.toml").write_text(cfg)
        run_pipeline(project)
        assert (project / "output" / "a2.txt").exists(), (
            "a newly declared output must be produced, not assumed fresh")

    def test_a_crashing_step_does_not_strand_the_previous_output(self, project):
        run_pipeline(project)
        before = (project / "output" / "a.txt").read_text()
        (project / "make_a.py").write_text("raise SystemExit(9)\n")
        with pytest.raises(PipelineError):
            run_pipeline(project)
        assert (project / "output" / "a.txt").read_text() == before
        assert not list((project / "output").glob("*.prev"))

    def test_missing_executable_restores_the_output(self, project):
        run_pipeline(project)
        before = (project / "output" / "a.txt").read_text()
        (project / "pipeline.toml").write_text(
            (project / "pipeline.toml").read_text().replace(
                '["{python}", "make_a.py"]', '["./no-such-binary"]'))
        with pytest.raises((PipelineError, OSError)):
            run_pipeline(project)
        assert (project / "output" / "a.txt").read_text() == before

    def test_directory_input_is_rejected_loudly(self, project):
        (project / "data").mkdir()
        (project / "pipeline.toml").write_text(
            (project / "pipeline.toml").read_text().replace(
                'inputs = ["seed.txt"]', 'inputs = ["data"]'))
        with pytest.raises(PipelineError, match="directory"):
            run_pipeline(project)


class TestOptionalOutputs:
    """The villa's Cycles renders only exist under VILLA_FULL_RENDER, and
    publishing globbed them anyway — two-day-old renders shipped beside a
    fresh model because nothing declared them (CodeRabbit 2026-08-09)."""

    def _with_optional(self, project):
        (project / "pipeline.toml").write_text(
            (project / "pipeline.toml").read_text().replace(
                'outputs = ["output/a.txt"]',
                'outputs = ["output/a.txt"]\n'
                'optional_outputs = ["output/extra.txt"]'))

    def test_absent_optional_output_is_fine(self, project):
        self._with_optional(project)
        run_pipeline(project)
        assert freshness_problems(project) == []

    def test_present_optional_output_is_hashed(self, project):
        self._with_optional(project)
        (project / "make_a.py").write_text(
            "from pathlib import Path\n"
            "Path('output/a.txt').write_text('Aseed')\n"
            "Path('output/extra.txt').write_text('render')\n")
        run_pipeline(project)
        assert freshness_problems(project) == []
        (project / "output" / "extra.txt").write_text("hand edited")
        assert any("extra.txt" in p for p in freshness_problems(project))

    def test_declared_artifacts_include_optional_ones(self, project):
        from archicad_builder.pipeline import publishable_artifacts
        self._with_optional(project)
        assert "output/extra.txt" in publishable_artifacts(project)


class TestDigestScope:
    def test_missing_declared_input_is_loud(self, project):
        (project / "pipeline.toml").write_text(
            (project / "pipeline.toml").read_text().replace(
                '"seed.txt"', '"sed.txt"'))       # typo
        with pytest.raises(PipelineError, match="sed.txt"):
            run_pipeline(project)

    def test_unknown_placeholder_is_rejected(self, project):
        (project / "pipeline.toml").write_text(
            (project / "pipeline.toml").read_text().replace(
                '"make_a.py"', '"{modell}.py"'))
        with pytest.raises(PipelineError, match="modell"):
            run_pipeline(project)

    def test_unset_env_differs_from_empty(self, project, monkeypatch):
        (project / "pipeline.toml").write_text(
            (project / "pipeline.toml").read_text().replace(
                'inputs = ["seed.txt"]', 'inputs = ["seed.txt"]\nenv = ["TOY"]'))
        monkeypatch.delenv("TOY", raising=False)
        run_pipeline(project)
        monkeypatch.setenv("TOY", "")
        assert {r.name: r for r in run_pipeline(project)}["a"].ran

    def test_framework_edits_only_touch_framework_steps(self, project,
                                                        monkeypatch):
        import archicad_builder.pipeline as mod
        (project / "pipeline.toml").write_text(
            (project / "pipeline.toml").read_text().replace(
                'name = "b"', 'name = "b"\nframework = true'))
        run_pipeline(project)
        monkeypatch.setattr(mod, "_tree_sha", lambda *a, **k: "DIFFERENT")
        ran = {r.name: r for r in run_pipeline(project)}
        assert ran["b"].ran, "a framework step must follow the package"
        assert not ran["a"].ran, (
            "a step that does not import the framework must not rebuild "
            "because an unrelated module changed")


class TestOrdering:
    def test_a_step_may_not_consume_a_later_steps_output(self, project):
        (project / "pipeline.toml").write_text(
            '[project]\nmodel = "toy"\n\n'
            '[[step]]\nname = "b"\nrun = ["{python}", "make_b.py"]\n'
            'inputs = ["output/a.txt"]\noutputs = ["output/b.txt"]\n\n'
            '[[step]]\nname = "a"\nrun = ["{python}", "make_a.py"]\n'
            'inputs = ["seed.txt"]\noutputs = ["output/a.txt"]\n')
        with pytest.raises(PipelineError, match="later step"):
            load_pipeline(project)

    def test_orphaned_backup_is_recovered(self, project):
        run_pipeline(project)
        good = (project / "output" / "a.txt").read_text()
        # simulate a SIGKILLed run: output quarantined, process gone
        (project / "output" / "a.txt").replace(
            project / "output" / "a.txt.prev")
        run_pipeline(project)
        assert (project / "output" / "a.txt").read_text() == good
        assert not list((project / "output").glob("*.prev"))
