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


class ImportError_(Exception):
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
        raise ImportError_(
            f"expected exactly one IfcProject, found {len(projects)}")
    project = projects[0]
    payload = _parametric(model, project) or {}
    payload.setdefault("global_id", project.GlobalId)
    payload.setdefault("name", project.Name or path.stem)
    building = Building.model_validate(payload)
    imported_ids.add(building.global_id)

    # storeys, in elevation order
    storeys = sorted(model.by_type("IfcBuildingStorey"),
                     key=lambda s: s.Elevation or 0.0)
    storey_by_id: dict[str, Story] = {}
    for st in storeys:
        payload = _parametric(model, st) or {
            "name": st.Name or f"Storey {len(storey_by_id) + 1}",
            "elevation": float(st.Elevation or 0.0),
            "height": 3.0,
        }
        if _parametric(model, st) is None:
            result_warnings.append(
                f"storey {st.Name!r}: no AB_Parametric — height defaulted "
                "to 3.0")
        payload.setdefault("global_id", st.GlobalId)
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
            payload.setdefault("global_id", entity.GlobalId)
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
        payload.setdefault("global_id", entity.GlobalId)
        story.spaces.append(Space.model_validate(payload))
        imported_ids.add(entity.GlobalId)

    # our exporter derives extra products from elements (door handles);
    # their ids are reproducible, so "derived from something we imported"
    # is decidable — anything else is genuinely foreign and gets LISTED
    from archicad_builder.models.ifc_id import derived_ifc_id
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

    if any(len(model.by_type(t)) for t in ("IfcRelAggregates",)):
        pass    # relationship glue is expected; nothing to report

    dupes = _duplicate_ids(building)
    if dupes:
        raise ImportError_("duplicate GlobalIds in the file: "
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
        raise ImportError_(
            f"{project_dir} already exists — import creates a NEW project, "
            "it never overwrites one")
    result = import_ifc(ifc_path)
    if strict and result.unmapped:
        raise ImportError_(
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
        raise ImportError_(
            f"{project_dir} has no import source — update-ifc only applies "
            "to projects created by import-ifc")
    record = json.loads(record_path.read_text())
    theirs = set(record["imported_ids"])
    building = Building.load(project_dir / "building.json")

    patcher = IFCExporter.__new__(IFCExporter)
    patcher.building = building
    patcher.file = ifcopenshell.open(str(source))
    contexts = patcher.file.by_type("IfcGeometricRepresentationContext")
    body = next((c for c in patcher.file.by_type(
        "IfcGeometricRepresentationSubContext")
        if c.ContextIdentifier == "Body"), None)
    patcher._context = next(
        (c for c in contexts
         if not c.is_a("IfcGeometricRepresentationSubContext")), None)
    patcher._body_context = body or patcher._context
    if patcher._context is None:
        raise ImportError_("import-source.ifc has no geometric context")

    storey_entities = {s.GlobalId: s
                       for s in patcher.file.by_type("IfcBuildingStorey")}
    added: list[str] = []
    for story in building.stories:
        ifc_storey = storey_entities.get(story.global_id)
        if ifc_storey is None:
            raise ImportError_(
                f"storey {story.name!r} ({story.global_id}) is not in the "
                "source file — adding storeys is not supported yet")
        new_products = []
        for wall in story.walls:
            if wall.global_id in theirs:
                continue
            ifc_wall = patcher._create_wall(wall, story)
            patcher._attach_parametric(ifc_wall, wall.model_dump(
                mode="json", exclude_none=True))
            new_products.append(ifc_wall)
            added.append(f"wall {wall.name!r} {wall.global_id}")
        for slab in story.slabs:
            if slab.global_id in theirs:
                continue
            ifc_slab = patcher._create_slab(slab, story.elevation)
            patcher._attach_parametric(ifc_slab, slab.model_dump(
                mode="json", exclude_none=True))
            new_products.append(ifc_slab)
            added.append(f"slab {slab.name!r} {slab.global_id}")
        for beam in story.beams:
            if beam.global_id in theirs:
                continue
            ifc_beam = patcher._create_beam(beam, story.elevation)
            patcher._attach_parametric(ifc_beam, beam.model_dump(
                mode="json", exclude_none=True))
            new_products.append(ifc_beam)
            added.append(f"beam {beam.name!r} {beam.global_id}")
        if new_products:
            patcher.file.createIfcRelContainedInSpatialStructure(
                GlobalId=ifcopenshell.guid.new(),
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
