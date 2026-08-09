# Feature: IFC import — collaboration with foreign models

## Status
implemented, delivery A (2026-08-09) — read-only import + patch-based update.
Merge into an existing project (delivery B) is deliberately out of scope; see
"Boundaries".

## Why this exists
ADR-001's reopen trigger fired: a partner (architect, engineer) works in
ArchiCAD/Revit and sends an IFC back. Until now the framework could only
*write* IFC; a foreign model had no way in, and our GlobalIds were useless to
reference against. With stable ids (ADR-005) the missing half is import.

## What it does

### `import-ifc <file> --project <name> [--strict]`
Creates a NEW project from a foreign IFC (`importers/ifc.py::import_ifc`):

- **GUIDs are preserved verbatim** for project, storeys, walls, slabs, roofs,
  doors, windows and spaces — the ENTITY's GlobalId, which wins over any stale
  copy inside a pset. A partner's GlobalId is how they reference the element.
- Scope, delivery A: our own exports import **losslessly** via their
  `AB_Parametric` psets (each entity carries its exact model JSON; the IFC
  geometry stays real BIM for CAD viewers). Foreign entities WITHOUT the pset
  — i.e. everything in a native ArchiCAD/Revit export — are `unmapped`:
  reported per entity, never guessed. Their geometry is not lost to the
  collaboration, because updates patch their original file. Recovering
  foreign geometry into our model (wall axes from extruded bodies, openings
  from void relations) is delivery B, to be built against real partner files.
- **Nothing is silently dropped.** Every entity that cannot be represented is
  recorded in `ImportResult.unmapped` (type + GlobalId + name) and printed;
  `--strict` exits non-zero — and refuses to write anything at all.
- Elements carry provenance: `source="imported"` plus the file's sha256 in the
  project record (`import-source.json`), never a machine path.
- The original file is copied to the project as **`import-source.ifc`** — it
  is the partner's artifact and the base for updates.

### `update-ifc <project>` — patch, don't regenerate (owner decision 2026-08-09)
A project with an import source never re-exports foreign geometry from our
lossy JSON. Instead the command opens `import-source.ifc` and surgically
updates it:

- entities whose GlobalId exists in our model AND is marked ours → replaced;
- our new elements → added to the correct storey;
- **everything else — the partner's geometry — is untouched.**

Re-serialization shifts bytes (entity numbering); attributes and GlobalIds
survive exactly. Semantically lossless is the contract; byte-stability is not.

## Boundaries & edge cases
- **Pset staleness**: import trusts `AB_Parametric` verbatim. If a partner
  moves OUR wall in CAD, the IFC geometry changes but the pset does not — the
  import reconstructs the pset version. Doors/windows get a drift warning
  (their `OverallWidth`/`OverallHeight` attributes are compared); walls/slabs
  do not — reconciling foreign geometry edits is delivery B.
- **Apartment grouping does not survive** the round trip: IFC has no
  apartment entity, so apartment spaces come back as storey-level spaces and
  the `Apartment` objects (with their ids) are gone.
- `update-ifc` refuses locally-EDITED imported elements (replacing foreign
  geometry is delivery B) and reports — but does not propagate — local
  deletions of imported elements. Locally-added spaces/virtual elements are
  refused loudly, never silently skipped.
- Our patched elements use absolute world placement; a foreign file whose
  site/storey placements carry transforms would show them misaligned. Fine
  for re-imports of our own exports; real foreign files need checking against
  delivery B.
- **No merge into an existing project (delivery B).** Merge-by-GUID without a
  base revision is a destructive two-way overwrite: it cannot distinguish
  "partner deleted X" from "we added X while they edited", and any partial or
  filtered export would read as mass deletion. Delivery A stores the parsed
  import as the base so a future delivery can be a true 3-way merge.
- Mesh-only geometry (`IfcFacetedBrep` etc. without an axis/extrusion) is
  `unmapped`, never guessed into walls.
- `import-ifc` refuses an existing project directory — no silent overwrite.
- Duplicate GlobalIds in the foreign file are an error (`ids` semantics).
- Fields our model cannot carry (materials, property sets beyond the ones we
  write, arbitrary placements) survive via the patch flow — they live in
  `import-source.ifc`, which we never regenerate.

## Related
[ADR-005](decisions/005-element-identity-and-reconciliation.md) — identity rules.
[ADR-001](decisions/001-json-as-single-source-of-truth.md) — the reopen trigger.
[ifc-identity.md](ifc-identity.md) — id validity and derivation.
