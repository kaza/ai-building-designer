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
  doors, windows and spaces. A partner's GlobalId is how they reference the
  element; it must survive the round trip unchanged.
- Scope v1 — geometry we can honestly recover: wall axis + thickness + height
  (from `IfcWallStandardCase`/`IfcWall` with extruded bodies), openings via
  `IfcRelVoidsElement`/`IfcRelFillsElement` → host wall + position along its
  axis, slabs/roofs from extruded profile footprints, spaces from boundary
  polygons.
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
