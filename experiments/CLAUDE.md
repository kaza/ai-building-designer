# Experiments

Exploratory work — hypotheses about the models we build, not features.
Process, scaffold and rules: the blueprint playbook
(`~/Documents/GitHub/ai-dev-blueprint/how-to-run-experiments.md`).

Layout: `YYYY-MM-DD_<short-description>/` with `AGENTS.md` (hypothesis,
why, success criteria, setup), `audit-log.md` (one entry per attempt,
updated immediately), optional `findings.md`, scripts INSIDE the
experiment dir, raw output committed under `logs/`.

Experiments may hack; nothing here is a production dependency. A script
that proves out gets promoted deliberately (spec + TDD) into
`src/archicad_builder/`.
