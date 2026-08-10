# Feature: Engineer handoff report

## Status

Spec'd 2026-08-10 (S4 of the seismic commission).

## Why this exists

Mission statement (README): the product of this tool is
**building-ready subject to civil-engineer validation**. That promise
is only real if the engineer receives ONE document with every number,
assumption and gap — otherwise "verification" means re-modeling the
building, and the mission collapses to "nice walkthrough." The report
is the artifact the engineer marks up and signs against.

## What it does

1. **CLI `report <project>`** → `output/engineer-report.html`
   (self-contained, no external assets), plus a `[[step]]` in the
   project pipeline. Optional publish alongside walkthrough/X-ray.
2. **Contents, in order**:
   - Mission banner: "Generated design — requires verification and
     signature by a licensed civil engineer. This report exists to
     make that verification complete and fast."
   - Project identity: name, building digest, generation date, storey
     table (elevation, height, floor area).
   - Site & design basis: `[site]` values, full `DesignBasis` +
     `SeismicBasis` dumps with units and sources (which numbers are
     EC-recommended vs NA-overridden vs assumed).
   - Gravity: strip-engine summary (worst utilizations per element
     kind, load balance), FEM design values (element `u` + `u_peak`,
     governing combo), link to the X-ray.
   - Seismic: per-storey mass table, `T1`, `Sd(T1)`, `Fb`, storey
     force table, per-direction wall shear capacity vs demand,
     wall-density table, eccentricity/torsional radii per storey,
     continuity findings. Cantilever inventory with the standing
     "vertical seismic component to be verified" flag.
   - Foundations: footing schedule (dimensions, worst bearing
     pressure vs `sigma_rd`), sliding and overturning ratios, the
     EC7-lite exclusion list, tie-beam standing note.
   - Validation: every finding (active, waived — with the waiver's
     mandatory reason — and unresolved) grouped by code, so a waiver
     is a documented engineering conversation, not a buried flag.
   - `not_modelled`: the merged honest-gaps list from every engine,
     verbatim. The report NEVER omits an exclusion a component
     publishes.
3. **Data sources**: `building.json`, `output/loads.json`,
   `output/fem-loads.json`, seismic/foundation results,
   `validation.json`. Missing inputs render as "NOT RUN" sections in
   red — a partial report must look partial (fail loud, on paper).

## Boundaries

- A report, not a calculation package: it presents results computed
  elsewhere; it computes nothing new.
- Not a drawing set: plans/IFC stay separate exports; the report
  links, it does not embed geometry beyond small summary tables.
- No PDF generation — HTML prints fine; a PDF pipeline is YAGNI.
- English only for now (the engineer audience for BA/DE/AT reads it;
  localization when a real engineer asks).

## Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-08-10 | Single self-contained HTML | same contract as xray.html; an engineer gets one file by email, no server |
| 2026-08-10 | Missing inputs render red "NOT RUN", never omitted | an incomplete report that looks complete is the exact lie the mission forbids |
| 2026-08-10 | Waivers surface with their reasons in the report | the waiver reason field was mandatory from day one precisely so it could face an engineer |

## Acceptance

- Unit tests: report builds from synthetic fixtures; missing
  loads.json produces the red NOT RUN section, not an exception;
  waived findings appear with reasons.
- villa-maketa: `report` runs in the pipeline, output opens in a
  browser, every section populated.

## Related

[seismic-lateral.md](seismic-lateral.md) ·
[foundations.md](foundations.md) ·
[structural-plausibility.md](structural-plausibility.md) ·
[fem-xray.md](fem-xray.md) ·
[validation-waivers.md](validation-waivers.md) ·
[web-deployment.md](web-deployment.md) (publish contract).
