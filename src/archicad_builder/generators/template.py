"""Floor template stamping.

Design a floor layout once (the "template" story), then replicate it
to other stories. This is the key efficiency tool for multi-storey
buildings where typical floors share the same layout.

The template is a story — all its walls, doors, windows, slabs,
staircases, and virtual elements are deep-copied to target stories.
GlobalIds are regenerated to ensure uniqueness. Wall references
(door.wall_id, window.wall_id) are remapped to the new wall IDs.
"""

from __future__ import annotations

from archicad_builder.models.building import Building, Story
from archicad_builder.models.elements import (
    Door,
    Roof,
    Slab,
    Staircase,
    VirtualElement,
    Wall,
    Window,
)
from archicad_builder.models.spaces import Apartment, Space
from archicad_builder.models.ifc_id import generate_ifc_id


def stamp_floor_template(
    building: Building,
    template_story_name: str,
    target_story_names: list[str],
    include_roofs: bool = False,
) -> None:
    """Copy all elements from a template story to target stories.

    Target stories must already exist in the building (with correct
    elevations). Their existing elements are cleared and replaced
    with copies from the template.

    Args:
        building: Building to modify (mutated in place).
        template_story_name: Name of the story to copy from.
        target_story_names: Names of stories to copy to.
        include_roofs: Whether to copy roof elements (usually False).
    """
    template = building._require_story(template_story_name)

    for target_name in target_story_names:
        target = building._require_story(target_name)
        _copy_story_elements(template, target, include_roofs)


def _copy_story_elements(
    source: Story,
    target: Story,
    include_roofs: bool = False,
) -> None:
    """Deep-copy all elements from source to target story.

    Generates new GlobalIds and remaps wall references for doors/windows.
    """
    # Build wall ID mapping: old_id → new_id
    wall_id_map: dict[str, str] = {}

    # Clear target
    target.walls = []
    target.slabs = []
    target.doors = []
    target.windows = []
    target.staircases = []
    target.virtual_elements = []
    target.spaces = []
    target.apartments = []
    if include_roofs:
        target.roofs = []

    # Copy walls
    for wall in source.walls:
        new_id = generate_ifc_id()
        wall_id_map[wall.global_id] = new_id
        new_wall = wall.model_copy(update={"global_id": new_id})
        target.walls.append(new_wall)

    # Copy doors (remap wall_id)
    for door in source.doors:
        new_wall_id = wall_id_map.get(door.wall_id, door.wall_id)
        new_door = door.model_copy(update={
            "global_id": generate_ifc_id(),
            "wall_id": new_wall_id,
        })
        target.doors.append(new_door)

    # Copy windows (remap wall_id)
    for window in source.windows:
        new_wall_id = wall_id_map.get(window.wall_id, window.wall_id)
        new_window = window.model_copy(update={
            "global_id": generate_ifc_id(),
            "wall_id": new_wall_id,
        })
        target.windows.append(new_window)

    # Copy slabs
    for slab in source.slabs:
        new_slab = slab.model_copy(update={"global_id": generate_ifc_id()})
        target.slabs.append(new_slab)

    # Copy staircases
    for staircase in source.staircases:
        new_staircase = staircase.model_copy(update={"global_id": generate_ifc_id()})
        target.staircases.append(new_staircase)

    # Copy virtual elements
    for ve in source.virtual_elements:
        new_ve = ve.model_copy(update={"global_id": generate_ifc_id()})
        target.virtual_elements.append(new_ve)

    # Copy spaces
    for space in source.spaces:
        new_space = space.model_copy(update={"global_id": generate_ifc_id()})
        target.spaces.append(new_space)

    # Copy apartments (with deep-copied spaces)
    for apt in source.apartments:
        new_spaces = [
            s.model_copy(update={"global_id": generate_ifc_id()})
            for s in apt.spaces
        ]
        new_apt = apt.model_copy(update={
            "global_id": generate_ifc_id(),
            "spaces": new_spaces,
        })
        target.apartments.append(new_apt)

    # Copy roofs if requested
    if include_roofs:
        for roof in source.roofs:
            new_roof = roof.model_copy(update={"global_id": generate_ifc_id()})
            target.roofs.append(new_roof)
