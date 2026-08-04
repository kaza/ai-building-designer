"""Spatial query tools.

Context-pulling tools for the validate → fix loop:
- neighbors: what's adjacent to an element
- above_below: vertically aligned elements across floors
- floor_context: extract relevant building state slice
- connectivity: room connectivity graph
- mermaid: Mermaid diagram export
- wall_rooms: wall-room relationship queries
- slice: apartment data extraction
"""

from archicad_builder.queries.connectivity import (
    ConnectivityGraph,
    GraphEdge,
    GraphNode,
    build_connectivity_graph,
)
from archicad_builder.queries.mermaid import (
    graph_to_mermaid,
    graph_to_mermaid_simple,
)
from archicad_builder.queries.slice import (
    ApartmentSlice,
    extract_apartment,
)
from archicad_builder.queries.spatial import (
    extract_floor_context,
    find_above_below,
    find_neighbors,
)
from archicad_builder.queries.wall_rooms import (
    get_room_exterior_walls,
    get_room_walls,
    get_room_windows,
    get_wall_rooms,
)

__all__ = [
    "ApartmentSlice",
    "ConnectivityGraph",
    "GraphEdge",
    "GraphNode",
    "build_connectivity_graph",
    "extract_apartment",
    "extract_floor_context",
    "find_above_below",
    "find_neighbors",
    "get_room_exterior_walls",
    "get_room_walls",
    "get_room_windows",
    "get_wall_rooms",
    "graph_to_mermaid",
    "graph_to_mermaid_simple",
]
