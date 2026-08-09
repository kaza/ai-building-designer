# Feature: Element identity — GUIDs that survive rebuilds

## Status
implemented (2026-08-09)

## Why this exists
Every element carries an IFC GlobalId (`global_id`, 22-char compressed UUID) so the
same identifier appears in `building.json`, the exported `.ifc`, the FEM report and
the walkthrough. That only has value if the id is **stable**: a partner referencing
`1a2B3c...` in ArchiCAD must find the same wall under the same id after we rebuild.

Before this feature, ids were minted on *construction* (`default_factory`), so every
`build.py` run re-identified the entire building: 64 ids churned, `building.json`'s
hash changed, and ~11 minutes of pipeline (IFC → OBJ → blend → GLB → FEM) rebuilt
for zero semantic change. IFC-internal entities (relationships, openings, psets) got
fresh random ids on every export, so even an unchanged model produced a different
`.ifc` each time.

## What it does

### The identity rule
**A GlobalId is minted exactly once — when the element is added — and never again.**

| Situation | GlobalId behaviour |
|---|---|
| Element loaded from `building.json` | kept verbatim |
| Element imported from a foreign IFC | kept verbatim (theirs) |
| New element (CLI `apply`, generator, build script) | minted once, persisted |
| Element rebuilt by a project build script | **reconciled** — see below |
| Element renamed via `apply rename-*` | kept (same object mutated) |
| Element removed and re-added | new id (a new lifetime) |

### Reconciliation (`archicad_builder.models.reconcile`)
`reconcile_ids(new, prev) -> ReconcileReport` copies ids from a previous model onto a
freshly constructed one. Match key: `(story.name, element kind, element.name)` —
name is the identity carrier for scripted builds. Duplicate keys in either model are
a hard error (`ReconcileError`), because a merge over ambiguous names would guess.

Project build scripts (e.g. `projects/villa-maketa/build.py`) call it before saving:
an unchanged design produces a byte-identical `building.json`; a new element mints
exactly one id; a removed element is reported (`removed: <name> <id>`). Renaming an
element *in the build script* is remove + add — the report says so; if the id must
survive, use `apply rename-*` or edit the JSON.

### Derived ids for IFC-only entities (`models/ifc_id.py::derived_ifc_id`)
Relationships, openings, property sets and door hardware exist only in the `.ifc`,
but must be stable across exports or the file churns. They get **derived** ids:

```
seed = json.dumps([SEED_VERSION, kind, [parts...], index], separators=(",", ":"))
id   = compress(uuid5(AB_NAMESPACE, seed))
```

- `AB_NAMESPACE` and `SEED_VERSION` are frozen constants. Changing either rewrites
  every derived id in every export — the golden-vector tests exist to make that a
  deliberate act, not an accident.
- JSON-array encoding is injective — no delimiter ambiguity if a part contains `|`.
- `parts` must contain **every identity-defining participant** (e.g. a void relation
  seeds on host wall id AND filler id), and `index` disambiguates genuine one-to-many
  cases (a window cutting corner openings in two walls; multiple handles per door).
- Placements and other non-IfcRoot entities have no GlobalId at all.

Before writing, the exporter asserts all GlobalIds in the file are unique —
ArchiCAD silently drops colliding entities, so we fail loudly instead.

### Deterministic export
The IFC header is pinned: fixed author/organization, `time_stamp` from
`SOURCE_DATE_EPOCH` when set, else a frozen constant (declared as `env` on the `ifc`
pipeline step so the freshness digest covers it). Under a pinned IfcOpenShell build,
exporting the same building twice yields byte-identical files. Byte identity is NOT
promised across IfcOpenShell versions (the header embeds its version string);
semantic identity (GUID sets, entity counts) is.

### Load / save semantics
- `Building.load()` never writes. An element arriving without a `global_id` gets one
  minted **in memory** (pydantic default) — persisted only by explicit repair.
- `Building.save()` is canonical and idempotent: `save(load(save(x))) == save(x)`.
  Byte-round-trip of arbitrary hand-written JSON is *not* an invariant (key order,
  int→float, dropped nulls are normalized on first save).

### `ids` CLI
`python -m archicad_builder ids <project>` reports, per element: duplicate ids,
invalid ids (see below), and ids minted at load (missing in the file).
`--strict` exits non-zero on any finding; `--repair` persists minted ids.

`is_valid_ifc_id`: exactly 22 chars from the IFC base64 alphabet
(`0-9 A-Z a-z _ $`), first char `0-3` (the leading 2 bits of a 128-bit value).

## Boundaries & edge cases
- Reconciliation is by name, not geometry: moving a wall keeps its id (correct — the
  id is the wall's identity, not its position). Swapping two elements' names swaps
  their ids — names ARE the key; the report shows both as kept.
- Storey names fold case (matching `Building.get_story`); duplicate storey names are
  a `ReconcileError`.
- If the *previous* file lacks an id for an element, the build script's save persists
  a freshly minted one — that is mint-on-add for an element that never had identity,
  equivalent to `ids --repair`, and is deliberate (review discussion 2026-08-09).
- `reconcile_ids` only fills ids for *matching* keys; it never deletes and never
  writes files — the caller decides what to do with the report.
- Two exports in the same second could mask a broken timestamp pin; the header test
  asserts the exact expected timestamp string, not just equality of two files.

## Lessons learned
- `_setup_header()` had silently never worked: `file_name_py()` returns a detached
  wrapper, so assignments went nowhere and every export shipped blank author + wall
  clock. Write through `self.file.header.file_name` instead.
- Pre-code review (Gemini) killed the v1 plan to delete `build.py` for id stability:
  reconciliation-by-name keeps parametric authoring AND stable ids. Verified
  precondition: villa element names are unique per storey+kind.
- Pre-code review (Codex): seeding derived ids on the parent id alone collides (4×
  IfcRelVoidsElement per wall is real in the villa); placements need no GlobalId;
  `"|".join` is not injective.

## Related
[ADR-005](decisions/005-element-identity-and-reconciliation.md) — the decision record.
[ADR-001](decisions/001-json-as-single-source-of-truth.md) — building.json as source of truth.
[project-pipeline.md](project-pipeline.md) — why id churn cost 11 minutes per rebuild.
