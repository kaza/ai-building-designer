"""Reachability validator using the connectivity graph.

Validates that all rooms are reachable from the building entrance
and flags rooms that are only reachable through other habitable rooms
(Durchgangszimmer — walk-through rooms).

Error codes:
    E080: Room is completely unreachable (no doors at all) → ERROR
    E081: No path from building entrance to staircase → ERROR
    E082: No path from corridor to apartment → ERROR
    W080: Room only reachable through another habitable room → WARNING
"""

from __future__ import annotations

from archicad_builder.models.building import Building
from archicad_builder.queries.connectivity import (
    ConnectivityGraph,
    build_connectivity_graph,
)
from archicad_builder.validators.structural import ValidationError


# Room types that are "habitable" (can't be walk-through rooms)
_HABITABLE_TYPES = {"living", "bedroom", "kitchen", "office"}


def validate_reachability(
    building: Building,
    storey_name: str,
    graph: ConnectivityGraph | None = None,
) -> list[ValidationError]:
    """Run all reachability validators for one storey.

    Args:
        building: The building model.
        storey_name: Storey to validate.
        graph: Pre-built connectivity graph (built if not provided).

    Returns:
        List of validation errors/warnings.
    """
    if graph is None:
        graph = build_connectivity_graph(building, storey_name)

    errors: list[ValidationError] = []
    errors.extend(_validate_unreachable_rooms(graph))
    errors.extend(_validate_entrance_to_staircase(graph))
    errors.extend(_validate_corridor_to_apartments(building, storey_name, graph))
    errors.extend(_validate_walk_through_rooms(graph))
    return errors


def _validate_unreachable_rooms(graph: ConnectivityGraph) -> list[ValidationError]:
    """E080: Room has no doors at all (isolated)."""
    errors: list[ValidationError] = []

    # Nodes that appear in no edges
    connected_nodes = set()
    for edge in graph.edges:
        connected_nodes.add(edge.from_node)
        connected_nodes.add(edge.to_node)

    for name, node in graph.nodes.items():
        if name == "Exterior":
            continue  # Exterior is always "connected"
        if name not in connected_nodes:
            errors.append(ValidationError(
                severity="error",
                element_type="Space",
                element_id="",
                message=(
                    f"E080: Room '{name}' ({node.node_type}) on "
                    f"'{graph.storey}' is completely unreachable — "
                    f"no doors connect to it."
                ),
            ))

    return errors


def _validate_entrance_to_staircase(graph: ConnectivityGraph) -> list[ValidationError]:
    """E081: No path from building entrance/corridor to staircase.

    On ground floor: checks path from building entrance (Exterior/Lobby).
    On upper floors: checks path from corridor (main access point).
    """
    errors: list[ValidationError] = []

    # Find access point nodes
    access_nodes = set()

    # Ground floor: entrance-based
    if "Exterior" in graph.nodes:
        access_nodes.add("Exterior")
        for neighbor, _ in graph.neighbors("Exterior"):
            access_nodes.add(neighbor)

    # All floors: corridor-based
    for name, node in graph.nodes.items():
        if node.node_type in ("corridor", "lobby"):
            access_nodes.add(name)

    if not access_nodes:
        return errors  # No access points, other validators handle this

    # Find staircase nodes
    staircase_nodes = [
        name for name, node in graph.nodes.items()
        if node.node_type == "staircase"
    ]

    if not staircase_nodes:
        return errors  # No staircase, Phase 2 validator handles this

    # Check path from any access point to any staircase
    for stair in staircase_nodes:
        reachable = False
        for access in access_nodes:
            if graph.has_path(access, stair):
                reachable = True
                break
        if not reachable:
            errors.append(ValidationError(
                severity="error",
                element_type="Staircase",
                element_id="",
                message=(
                    f"E081: No path from corridor/entrance to staircase "
                    f"'{stair}' on '{graph.storey}'. The staircase must "
                    f"be reachable from the building circulation."
                ),
            ))

    return errors


def _validate_corridor_to_apartments(
    building: Building,
    storey_name: str,
    graph: ConnectivityGraph,
) -> list[ValidationError]:
    """E082: No path from corridor to apartment."""
    errors: list[ValidationError] = []

    story = building._require_story(storey_name)

    # Find corridor node
    corridor_nodes = [
        name for name, node in graph.nodes.items()
        if node.node_type == "corridor"
    ]

    if not corridor_nodes:
        return errors  # No corridor, Phase 3 validators handle this

    corridor = corridor_nodes[0]

    # For each apartment, check that at least one of its rooms
    # is reachable from the corridor
    for apt in story.apartments:
        apt_space_names = {space.name for space in apt.spaces}
        reachable = graph.reachable_from(corridor)
        apt_reachable = apt_space_names & reachable

        if not apt_reachable:
            errors.append(ValidationError(
                severity="error",
                element_type="Apartment",
                element_id=apt.global_id,
                message=(
                    f"E082: No path from corridor to apartment "
                    f"'{apt.name}' on '{storey_name}'. "
                    f"Apartment rooms: {sorted(apt_space_names)}."
                ),
            ))

    return errors


def _validate_walk_through_rooms(graph: ConnectivityGraph) -> list[ValidationError]:
    """W080: Room only reachable through another habitable room (Durchgangszimmer).

    A bedroom should not be the only path to reach another bedroom.
    Checks if removing any habitable room from the graph disconnects
    other habitable rooms from the corridor/entrance.
    """
    errors: list[ValidationError] = []

    # Find the "entry point" — corridor or exterior
    entry_node = None
    for name, node in graph.nodes.items():
        if node.node_type in ("corridor", "lobby"):
            entry_node = name
            break
    if entry_node is None and "Exterior" in graph.nodes:
        entry_node = "Exterior"
    if entry_node is None:
        return errors

    # Get all habitable rooms
    habitable = {
        name for name, node in graph.nodes.items()
        if node.node_type in _HABITABLE_TYPES
    }

    # For each habitable room, check if it's only reachable via
    # another habitable room (excluding hallway, corridor, vestibule)
    for room_name in habitable:
        if room_name == entry_node:
            continue

        # Find all paths from entry to this room
        # Check if any path avoids other habitable rooms
        reachable_avoiding = _reachable_avoiding_types(
            graph, entry_node, _HABITABLE_TYPES - {room_name}
        )

        if room_name not in reachable_avoiding:
            # Room is only reachable through other habitable rooms
            node = graph.nodes[room_name]
            errors.append(ValidationError(
                severity="warning",
                element_type="Space",
                element_id="",
                message=(
                    f"W080: Room '{room_name}' ({node.node_type}) on "
                    f"'{graph.storey}' is only reachable through another "
                    f"habitable room (Durchgangszimmer). Consider adding "
                    f"a hallway or separate access."
                ),
            ))

    return errors


def _reachable_avoiding_types(
    graph: ConnectivityGraph,
    start: str,
    avoid_types: set[str],
) -> set[str]:
    """BFS reachability, avoiding nodes of certain types (except start/end)."""
    visited = {start}
    queue = [start]
    while queue:
        current = queue.pop(0)
        for neighbor, _ in graph.neighbors(current):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            node = graph.nodes.get(neighbor)
            # Can traverse through this node if it's not an avoided type
            if node and node.node_type not in avoid_types:
                queue.append(neighbor)
            # If it IS an avoided type, we still "reach" it but don't
            # traverse through it
    return visited
