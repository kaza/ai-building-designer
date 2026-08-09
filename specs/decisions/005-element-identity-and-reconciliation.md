# Decision 005: GlobalIds are minted on add and reconciled on rebuild

## Status
accepted

## Date
2026-08-09

## Context
`build.py` regenerates `building.json` from Python on every run, and every element
minted a fresh GlobalId on construction. So identical designs produced different
files: 64 ids churned per run, invalidating the whole downstream pipeline (~11 min)
and making the ids worthless for IFC collaboration — a partner cannot reference an
element whose id changes whenever we re-run a script. The owner's requirement:
*"we should generate GUIDs only on add, or import them if using an imported IFC."*

## Options considered

| Option | Pros | Cons |
|--------|------|------|
| A — delete `build.py`; `building.json` becomes the only authored form | ids trivially stable | loses parametric authoring (`H = 3.0`, bearing-line alignment); every future change is manual JSON coordinate surgery |
| B — deterministic ids derived from element content (name+coords) | no state needed | moving a wall changes its id — the opposite of identity; breaks partner references on any design change |
| C — keep `build.py`, reconcile ids against the previous file by (story, kind, name) | stable ids AND parametric authoring; same reconciler reusable for IFC import | names become load-bearing as merge keys; renaming in the script = new identity |

## Decision
**Option C.** `reconcile_ids(new, prev)` (framework, `models/reconcile.py`) copies
ids from the committed `building.json` onto the freshly built model by
`(story.name, kind, element.name)`; duplicate keys are a hard error. New elements
mint exactly one id; removals are reported. IFC-only entities (relationships,
openings, psets, hardware) get **derived** ids — `uuid5` over a versioned,
JSON-encoded seed naming every participant — so an unchanged model exports an
unchanged `.ifc`. Header pinned (`SOURCE_DATE_EPOCH` or a frozen constant).

Foreign IFCs keep their ids verbatim on import, and projects with an import source
are updated by **patching the original file** (`update-ifc`), never by regenerating
foreign geometry from our lossy model (owner decision 2026-08-09).

Option A was the original plan; pre-code review (Gemini) identified the false trade
and option C as strictly better. Option B misunderstands what a GUID is for.

## Consequences
**Easier:** rebuilds are no-ops when the design is unchanged (pipeline cache
actually works); partners can reference our elements across revisions; `.ifc`
diffs are meaningful.

**Harder:** element names within a storey+kind must stay unique (enforced, hard
error); a rename in the build script is a new identity (use `apply rename-*` to
keep the id); the derived-seed grammar and namespace are frozen — changing them
rewrites every exported relationship id, so golden-vector tests guard them.

## Applies to
`models/ifc_id.py`, `models/reconcile.py`, `models/building.py`, `export/ifc.py`,
project build scripts, the `ids` CLI command.

## Related
[ifc-identity.md](../ifc-identity.md) — the feature spec.
[ADR-001](001-json-as-single-source-of-truth.md) — amended reading: `build.py` is an
authoring tool that may never re-identify an existing element; `building.json`
remains the single source of truth.
