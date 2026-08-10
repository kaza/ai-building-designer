"""Copy GlobalIds from a previous model onto a freshly built one.

The problem this solves (specs/ifc-identity.md, ADR-005): project build
scripts reconstruct the whole building from Python, and construction mints
ids. Without reconciliation every rebuild re-identifies every element,
churning building.json and invalidating the entire derived pipeline.

Match key: (story name, element kind, element name). Names are the identity
carrier for scripted builds — duplicate keys are a hard error, because a
merge over ambiguous names would guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from archicad_builder.models.building import Building, Story
from archicad_builder.models.ifc_id import is_valid_ifc_id

# every flat Story collection whose members carry a global_id; spaces and
# apartments are handled separately because apartment spaces are nested
KINDS = ("walls", "slabs", "doors", "windows", "roofs", "staircases",
         "beams", "footings", "virtual_elements")

Key = tuple[str, str, str]          # (story, kind, name)


class ReconcileError(Exception):
    """Ambiguous identity — reconciliation refuses to guess."""


@dataclass
class ReconcileReport:
    kept: list[tuple[Key, str]] = field(default_factory=list)
    added: list[tuple[Key, str]] = field(default_factory=list)
    removed: list[tuple[Key, str]] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"{len(self.kept)} kept, {len(self.added)} added, "
                 f"{len(self.removed)} removed"]
        for key, gid in self.added:
            parts.append(f"  added:   {'/'.join(key)}  {gid}")
        for key, gid in self.removed:
            parts.append(f"  removed: {'/'.join(key)}  {gid}")
        return "\n".join(parts)


def _index(building: Building) -> dict[Key, object]:
    seen: dict[Key, object] = {}

    def put(story_name: str, kind: str, el) -> None:
        key = (story_name, kind, el.name)
        if key in seen:
            raise ReconcileError(
                f"two elements share the identity key {'/'.join(key)!r} — "
                "names are the merge key, so they must be unique per story "
                "and kind")
        seen[key] = el

    # storey names fold case, matching Building.get_story — a case-only
    # rename must not re-identify every element in the storey (Codex
    # review 2026-08-09). Duplicate storey names (any casing) are fatal:
    # empty duplicates would otherwise merge silently.
    story_names: set[str] = set()
    for story in building.stories:
        folded = story.name.lower()
        if folded in story_names:
            raise ReconcileError(
                f"two storeys share the name {story.name!r} (case-folded) — "
                "storey names are the merge key")
        story_names.add(folded)
        for kind in KINDS:
            for el in getattr(story, kind):
                put(folded, kind, el)
        for sp in story.spaces:
            put(folded, "spaces", sp)
        for apt in story.apartments:
            put(folded, "apartments", apt)
            for sp in apt.spaces:                 # nested — key by apartment
                put(folded, f"apartments/{apt.name}/spaces", sp)
    return seen


def reconcile_ids(new: Building, prev: Building) -> ReconcileReport:
    """Mutate `new` in place: matching elements take `prev`'s ids; doors' and
    windows' wall references are remapped accordingly. Never writes files —
    the caller decides what to do with the report."""
    new_els = _index(new)
    prev_els = _index(prev)
    # a hand-edited prev with duplicate/invalid ids would reconcile cleanly
    # and only blow up at export — fail here, where the cause is visible
    # (CodeRabbit 2026-08-09)
    prev_ids: dict[str, Key] = {}
    for key, el in prev_els.items():
        if not is_valid_ifc_id(el.global_id):
            raise ReconcileError(
                f"previous model has an invalid GlobalId on {'/'.join(key)}: "
                f"{el.global_id!r} — run `ids --repair` first")
        if el.global_id in prev_ids:
            raise ReconcileError(
                f"previous model has a duplicate GlobalId {el.global_id} on "
                f"{'/'.join(key)} and {'/'.join(prev_ids[el.global_id])} — "
                "resolve before reconciling")
        prev_ids[el.global_id] = key
    report = ReconcileReport()

    id_map: dict[str, str] = {}          # new (random) id -> prev id
    for key, el in new_els.items():
        prev_el = prev_els.get(key)
        if prev_el is None:
            report.added.append((key, el.global_id))
            continue
        id_map[el.global_id] = prev_el.global_id
        el.global_id = prev_el.global_id
        report.kept.append((key, el.global_id))
    for key, el in prev_els.items():
        if key not in new_els:
            report.removed.append((key, el.global_id))

    # cross-references: a door/window points at its host wall by id
    for story in new.stories:
        for el in (*story.doors, *story.windows):
            el.wall_id = id_map.get(el.wall_id, el.wall_id)

    new.global_id = prev.global_id
    prev_stories: dict[str, Story] = {s.name.lower(): s
                                      for s in prev.stories}
    for story in new.stories:
        if story.name.lower() in prev_stories:
            story.global_id = prev_stories[story.name.lower()].global_id
    return report
