"""IFC → Building import (specs/ifc-import.md, delivery A).

Two classes of file:
- OUR exports carry an ``AB_Parametric`` pset per entity (the element's
  exact model JSON) — those import losslessly, ids verbatim.
- Foreign entities without it are recorded in ``unmapped`` — reported,
  never guessed. Their geometry still survives collaboration because
  updates PATCH the original file (`update_ifc`) instead of regenerating
  it from our lossy model (owner decision 2026-08-09).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from archicad_builder.models.building import Building, Story
from archicad_builder.models.ifc_id import derived_ifc_id
from archicad_builder.models.elements import (
    Beam,
    Door,
    Roof,
    Slab,
    Staircase,
    VirtualElement,
    Wall,
    Window,
)
from archicad_builder.models.spaces import Space

# IFC entity type -> (model class, Story collection name)
_KIND_MAP = {
    "IfcWall": (Wall, "walls"),
    "IfcWallStandardCase": (Wall, "walls"),
    "IfcSlab": (Slab, "slabs"),
    "IfcDoor": (Door, "doors"),
    "IfcWindow": (Window, "windows"),
    "IfcRoof": (Roof, "roofs"),
    "IfcStair": (Staircase, "staircases"),
    "IfcBeam": (Beam, "beams"),
    "IfcVirtualElement": (VirtualElement, "virtual_elements"),
}

# infrastructure entities that are structural glue, never "unmapped"
_GLUE = {
    "IfcProject", "IfcSite", "IfcBuilding", "IfcBuildingStorey",
    "IfcOpeningElement", "IfcSpace",
}


class IfcImportError(Exception):
    """The file cannot be imported; the message says why."""


@dataclass
class ImportResult:
    building: Building
    unmapped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    imported_ids: set[str] = field(default_factory=set)


def _parametric(model, entity) -> dict | None:
    """The AB_Parametric JSON of an entity, or None."""
    for rel in model.get_inverse(entity):
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        pset = rel.RelatingPropertyDefinition
        if not pset.is_a("IfcPropertySet") or pset.Name != "AB_Parametric":
            continue
        for prop in pset.HasProperties:
            if prop.Name == "json" and prop.NominalValue is not None:
                return json.loads(prop.NominalValue.wrappedValue)
    return None


def _storey_of(entity) -> object | None:
    """The IfcBuildingStorey containing/aggregating this entity.

    IfcSpace is a spatial element: it has no ContainedInStructure inverse,
    only Decomposes — hence the getattr."""
    for rel in getattr(entity, "ContainedInStructure", None) or []:
        if rel.RelatingStructure.is_a("IfcBuildingStorey"):
            return rel.RelatingStructure
    for rel in getattr(entity, "Decomposes", None) or []:
        if rel.RelatingObject.is_a("IfcBuildingStorey"):
            return rel.RelatingObject
    return None


def import_ifc(path: Path) -> ImportResult:
    """Parse an IFC into a Building. GUIDs verbatim; nothing silently
    dropped — see ImportResult.unmapped."""
    import ifcopenshell

    model = ifcopenshell.open(str(path))
    result_warnings: list[str] = []
    unmapped: list[str] = []
    imported_ids: set[str] = set()

    projects = model.by_type("IfcProject")
    if len(projects) != 1:
        raise IfcImportError(
            f"expected exactly one IfcProject, found {len(projects)}")
    project = projects[0]
    payload = _parametric(model, project) or {}
    # the ENTITY GlobalId is authoritative — a partner can regenerate ids
    # without rewriting our pset, and "verbatim" means theirs, not our
    # stale copy (Codex 2026-08-09)
    payload["global_id"] = project.GlobalId
    payload.setdefault("name", project.Name or path.stem)
    building = Building.model_validate(payload)
    imported_ids.add(building.global_id)

    # storeys, in elevation order
    storeys = sorted(model.by_type("IfcBuildingStorey"),
                     key=lambda s: s.Elevation or 0.0)
    storey_by_id: dict[str, Story] = {}
    for st in storeys:
        payload = _parametric(model, st)
        if payload is None:
            payload = {
                "name": st.Name or f"Storey {len(storey_by_id) + 1}",
                "elevation": float(st.Elevation or 0.0),
                "height": 3.0,
            }
            result_warnings.append(
                f"storey {st.Name!r}: no AB_Parametric — height defaulted "
                "to 3.0")
        payload["global_id"] = st.GlobalId       # entity id wins
        story = Story.model_validate(payload)
        building.stories.append(story)
        storey_by_id[st.GlobalId] = story
        imported_ids.add(story.global_id)

    # elements
    seen: set[int] = set()
    for ifc_type, (cls, collection) in _KIND_MAP.items():
        for entity in model.by_type(ifc_type):
            if entity.id() in seen:
                continue        # IfcWallStandardCase is also an IfcWall
            seen.add(entity.id())
            payload = _parametric(model, entity)
            if payload is None:
                unmapped.append(
                    f"{entity.is_a()} {entity.GlobalId} {entity.Name!r}")
                continue
            payload["global_id"] = entity.GlobalId   # entity id wins
            el = cls.model_validate(payload)
            st = _storey_of(entity)
            story = storey_by_id.get(st.GlobalId) if st else None
            if story is None:
                unmapped.append(
                    f"{entity.is_a()} {entity.GlobalId} {entity.Name!r} "
                    "(no containing storey)")
                continue
            getattr(story, collection).append(el)
            imported_ids.add(el.global_id)

    # spaces (apartment structure does not exist in IFC — they come back
    # as storey-level spaces; reported, not hidden)
    for entity in model.by_type("IfcSpace"):
        payload = _parametric(model, entity)
        st = _storey_of(entity)
        story = storey_by_id.get(st.GlobalId) if st else None
        if payload is None or story is None:
            unmapped.append(
                f"IfcSpace {entity.GlobalId} {entity.Name!r}")
            continue
        payload["global_id"] = entity.GlobalId       # entity id wins
        story.spaces.append(Space.model_validate(payload))
        imported_ids.add(entity.GlobalId)

    # doors/windows referencing a wall that did not import (partner
    # deleted it but kept our opening) would silently vanish at the next
    # export — surface it (CodeRabbit 2026-08-09). Ditto a partner who
    # resized our door in CAD: the IFC attributes move, our pset does not.
    wall_ids = {w.global_id for st_ in building.stories
                for w in st_.walls}
    for st_ in building.stories:
        for el in (*st_.doors, *st_.windows):
            if el.wall_id not in wall_ids:
                result_warnings.append(
                    f"{el.name!r} references wall {el.wall_id}, which is "
                    "not in the file — it will not survive a re-export")
    for entity in (*model.by_type("IfcDoor"), *model.by_type("IfcWindow")):
        payload = _parametric(model, entity)
        if payload is None:
            continue
        for attr, key in (("OverallWidth", "width"),
                          ("OverallHeight", "height")):
            ifc_val = getattr(entity, attr, None)
            if ifc_val is not None and key in payload and \
                    abs(float(ifc_val) - float(payload[key])) > 1e-6:
                result_warnings.append(
                    f"{entity.Name!r}: IFC {attr}={ifc_val} disagrees with "
                    f"its AB_Parametric {key}={payload[key]} — the partner "
                    "edited it in CAD; the pset wins on import, review "
                    "manually")

    # our exporter derives extra products from elements (door handles);
    # their ids are reproducible, so "derived from something we imported"
    # is decidable — anything else is genuinely foreign and gets LISTED
    derived: set[str] = set()
    for story in building.stories:
        for door in story.doors:
            derived |= {derived_ifc_id("handle", door.global_id, index=n)
                        for n in range(16)}
    for entity in model.by_type("IfcProduct"):
        if entity.id() in seen or entity.is_a() in _GLUE:
            continue
        if entity.is_a("IfcSpace") or entity.GlobalId in derived:
            continue
        unmapped.append(f"{entity.is_a()} {entity.GlobalId} {entity.Name!r}")

    all_ids: dict[str, int] = {}
    for entity in model.by_type("IfcRoot"):
        all_ids[entity.GlobalId] = all_ids.get(entity.GlobalId, 0) + 1
    dupes = [gid for gid, n in all_ids.items() if n > 1]
    if dupes:
        raise IfcImportError("duplicate GlobalIds in the file: "
                             + ", ".join(dupes))
    return ImportResult(building=building, unmapped=unmapped,
                        warnings=result_warnings,
                        imported_ids=imported_ids)


def _duplicate_ids(building: Building) -> list[str]:
    seen: set[str] = set()
    dupes: list[str] = []
    def visit(gid: str) -> None:
        if gid in seen:
            dupes.append(gid)
        seen.add(gid)
    visit(building.global_id)
    for s in building.stories:
        visit(s.global_id)
        for kind in ("walls", "slabs", "doors", "windows", "roofs",
                     "staircases", "beams", "virtual_elements", "spaces"):
            for el in getattr(s, kind):
                visit(el.global_id)
    return dupes


def import_project(ifc_path: Path, project_dir: Path, *,
                   strict: bool = False) -> ImportResult:
    """Create a NEW project from a foreign IFC: building.json +
    import-source.ifc (the partner's pristine file) + import-source.json
    (provenance + which ids are theirs)."""
    ifc_path = Path(ifc_path)
    project_dir = Path(project_dir)
    if project_dir.exists():
        raise IfcImportError(
            f"{project_dir} already exists — import creates a NEW project, "
            "it never overwrites one")
    result = import_ifc(ifc_path)
    if strict and result.unmapped:
        raise IfcImportError(
            "unmapped entities (nothing was written):\n  "
            + "\n  ".join(result.unmapped))
    project_dir.mkdir(parents=True)
    result.building.save(project_dir / "building.json")
    shutil.copy2(ifc_path, project_dir / "import-source.ifc")
    (project_dir / "import-source.json").write_text(json.dumps({
        "source_file": ifc_path.name,
        "source_sha256": hashlib.sha256(
            ifc_path.read_bytes()).hexdigest(),
        "imported_ids": sorted(result.imported_ids),
        "unmapped": result.unmapped,
        "warnings": result.warnings,
    }, indent=2))
    return result


def update_ifc(project_dir: Path, out_path: Path | None = None) -> Path:
    """Patch, don't regenerate: open the partner's import-source.ifc and
    add OUR elements (ids not in imported_ids). Foreign entities are
    untouched; changed foreign elements stay theirs. Writes
    output/updated.ifc — the base file stays pristine."""
    import ifcopenshell

    from archicad_builder.export.ifc import IFCExporter

    project_dir = Path(project_dir)
    source = project_dir / "import-source.ifc"
    record_path = project_dir / "import-source.json"
    if not source.is_file() or not record_path.is_file():
        raise IfcImportError(
            f"{project_dir} has no import source — update-ifc only applies "
            "to projects created by import-ifc")
    record = json.loads(record_path.read_text())
    theirs = set(record["imported_ids"])
    building = Building.load(project_dir / "building.json")

    # The output is regenerated from the PRISTINE source, so an imported
    # element we edited in building.json — or deleted — would silently
    # come back as the partner's version. That contradicts the spec's
    # fail-loud rule (CodeRabbit 2026-08-09): compare every in-`theirs`
    # element against the source psets and refuse on drift; report
    # deletions. Replacing foreign geometry is delivery B.
    src_model = None
    import ifcopenshell as _ios
    src_model = _ios.open(str(source))
    src_payloads: dict[str, dict] = {}
    for entity in src_model.by_type("IfcRoot"):
        payload = _parametric(src_model, entity)
        if payload is not None:
            src_payloads[entity.GlobalId] = payload
    present_ids: set[str] = set()
    edited: list[str] = []
    for st_ in building.stories:
        for kind in ("walls", "slabs", "doors", "windows", "roofs",
                     "staircases", "beams", "virtual_elements", "spaces"):
            for el in getattr(st_, kind):
                present_ids.add(el.global_id)
                if el.global_id in theirs and el.global_id in src_payloads:
                    ours = el.model_dump(mode="json", exclude_none=True)
                    if ours != src_payloads[el.global_id]:
                        edited.append(f"{el.name!r} ({el.global_id})")
    if edited:
        raise IfcImportError(
            "these IMPORTED elements were edited locally, and update-ifc "
            "cannot yet replace foreign geometry (delivery B): "
            + ", ".join(edited))
    deleted = sorted(gid for gid in theirs
                     if gid in src_payloads and gid not in present_ids)
    if deleted:
        print(f"note: {len(deleted)} imported element(s) deleted locally "
              "stay in the partner file (deletion propagation is "
              "delivery B): " + ", ".join(deleted))

    patcher = IFCExporter.__new__(IFCExporter)
    patcher.building = building
    patcher.file = ifcopenshell.open(str(source))
    contexts = patcher.file.by_type("IfcGeometricRepresentationContext")
    body = next((c for c in patcher.file.by_type(
        "IfcGeometricRepresentationSubContext")
        if c.ContextIdentifier == "Body"), None)
    top = [c for c in contexts
           if not c.is_a("IfcGeometricRepresentationSubContext")]
    # foreign files carry Model AND Plan contexts; file order must not
    # decide where our geometry lands (CodeRabbit 2026-08-09)
    patcher._context = (next((c for c in top
                              if c.ContextType == "Model"), None)
                        or (top[0] if top else None))
    patcher._body_context = body or patcher._context
    if patcher._context is None:
        raise IfcImportError("import-source.ifc has no geometric context")
    # our create-helpers emit metre-valued absolute placements; patching a
    # millimetre file would produce 6 mm walls (Codex 2026-08-09) — refuse
    # anything but a plain metre unit until delivery B handles conversion
    for ua in patcher.file.by_type("IfcUnitAssignment"):
        for unit in ua.Units:
            if getattr(unit, "UnitType", None) == "LENGTHUNIT":
                prefix = getattr(unit, "Prefix", None)
                name = getattr(unit, "Name", None)
                if prefix is not None or name != "METRE":
                    raise IfcImportError(
                        f"source file length unit is {prefix or ''}"
                        f"{name!r}; patching supports plain METRE only "
                        "(unit conversion is delivery B)")

    storey_entities = {s.GlobalId: s
                       for s in patcher.file.by_type("IfcBuildingStorey")}
    added: list[str] = []
    for story in building.stories:
        ifc_storey = storey_entities.get(story.global_id)
        if ifc_storey is None:
            raise IfcImportError(
                f"storey {story.name!r} ({story.global_id}) is not in the "
                "source file — adding storeys is not supported yet")
        # host walls for OUR doors/windows may be THEIRS — look every wall
        # up in the patched file, whether we just created it or not
        wall_map: dict[str, object] = {
            w.GlobalId: w
            for w in (*patcher.file.by_type("IfcWall"),
                      *patcher.file.by_type("IfcWallStandardCase"))}
        new_products = []

        def _add(entity, el, label: str) -> None:
            patcher._attach_parametric(entity, el.model_dump(
                mode="json", exclude_none=True))
            new_products.append(entity)
            added.append(f"{label} {el.name!r} {el.global_id}")

        for wall in story.walls:
            if wall.global_id in theirs:
                continue
            ifc_wall = patcher._create_wall(wall, story)
            wall_map[wall.global_id] = ifc_wall
            _add(ifc_wall, wall, "wall")
        for slab in story.slabs:
            if slab.global_id not in theirs:
                _add(patcher._create_slab(slab, story.elevation),
                     slab, "slab")
        for beam in story.beams:
            if beam.global_id not in theirs:
                _add(patcher._create_beam(beam, story.elevation),
                     beam, "beam")
        for roof in story.roofs:
            if roof.global_id not in theirs:
                _add(patcher._create_roof(
                    roof, story.elevation + story.height), roof, "roof")
        for stair in story.staircases:
            if stair.global_id not in theirs:
                _add(patcher._create_staircase(stair, story.elevation),
                     stair, "staircase")
        for door in story.doors:
            if door.global_id in theirs:
                continue
            wall = story.get_wall(door.wall_id)
            host = wall_map.get(door.wall_id)
            if wall is None or host is None:
                raise IfcImportError(
                    f"door {door.name!r} references wall {door.wall_id}, "
                    "which is neither ours nor in the source file")
            ifc_door = patcher._create_door(door, wall, story)
            opening = patcher._create_opening(
                door, wall, story, is_door=True,
                guid=derived_ifc_id("opening", wall.global_id,
                                    door.global_id))
            patcher.file.createIfcRelVoidsElement(
                GlobalId=derived_ifc_id("rel-voids", wall.global_id,
                                        opening.GlobalId),
                RelatingBuildingElement=host,
                RelatedOpeningElement=opening)
            patcher.file.createIfcRelFillsElement(
                GlobalId=derived_ifc_id("rel-fills", opening.GlobalId,
                                        door.global_id),
                RelatingOpeningElement=opening,
                RelatedBuildingElement=ifc_door)
            _add(ifc_door, door, "door")
            # "a door must read as a door in every output" (owner
            # 2026-08-06) — patched doors get handles like exported ones
            new_products.extend(
                patcher._create_door_handles(door, wall, story))
        for window in story.windows:
            if window.global_id in theirs:
                continue
            wall = story.get_wall(window.wall_id)
            host = wall_map.get(window.wall_id)
            if wall is None or host is None:
                raise IfcImportError(
                    f"window {window.name!r} references wall "
                    f"{window.wall_id}, which is neither ours nor in the "
                    "source file")
            ifc_window = patcher._create_window(window, wall, story)
            opening = patcher._create_opening_for_window(
                window, wall, story,
                guid=derived_ifc_id("opening", wall.global_id,
                                    window.global_id))
            patcher.file.createIfcRelVoidsElement(
                GlobalId=derived_ifc_id("rel-voids", wall.global_id,
                                        opening.GlobalId),
                RelatingBuildingElement=host,
                RelatedOpeningElement=opening)
            patcher.file.createIfcRelFillsElement(
                GlobalId=derived_ifc_id("rel-fills", opening.GlobalId,
                                        window.global_id),
                RelatingOpeningElement=opening,
                RelatedBuildingElement=ifc_window)
            _add(ifc_window, window, "window")
        # anything else we cannot patch in must FAIL, not vanish
        for kind in ("virtual_elements", "spaces"):
            leftovers = [el for el in getattr(story, kind)
                         if el.global_id not in theirs]
            if leftovers:
                raise IfcImportError(
                    f"cannot add {kind} to a foreign IFC yet: "
                    + ", ".join(el.name for el in leftovers))
        apt_leftovers = [sp.name for apt in story.apartments
                         for sp in apt.spaces
                         if sp.global_id not in theirs]
        if apt_leftovers:
            raise IfcImportError(
                "cannot add apartment spaces to a foreign IFC yet: "
                + ", ".join(apt_leftovers))
        if new_products:
            patcher.file.createIfcRelContainedInSpatialStructure(
                # derived, not random: the output is regenerated from the
                # pristine source each run, so same adds -> same file
                GlobalId=derived_ifc_id("rel-contained-update",
                                        story.global_id),
                RelatingStructure=ifc_storey,
                RelatedElements=new_products,
            )
    out = out_path or (project_dir / "output" / "updated.ifc")
    out.parent.mkdir(parents=True, exist_ok=True)
    patcher.file.write(str(out))
    print(f"updated IFC: {len(added)} element(s) added, foreign geometry "
          f"untouched -> {out}")
    for line in added:
        print(f"  + {line}")
    return out
