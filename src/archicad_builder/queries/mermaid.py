"""Mermaid diagram export for connectivity graphs.

Converts a ConnectivityGraph to Mermaid flowchart syntax.
The output is readable, useful for AI reasoning about building layout,
and can be rendered to SVG/PNG by any Mermaid-compatible tool.
"""

from __future__ import annotations

from archicad_builder.queries.connectivity import ConnectivityGraph


# Node shape by type
_NODE_SHAPES = {
    "exterior": ("([", "])"),     # stadium shape
    "corridor": ("[[", "]]"),     # subroutine shape
    "lobby": ("[[", "]]"),
    "vestibule": ("[[", "]]"),
    "elevator": ("[/", "/]"),     # parallelogram
    "staircase": ("[/", "/]"),
    "hallway": ("(", ")"),        # rounded
    "bathroom": ("(", ")"),
    "toilet": ("(", ")"),
    "kitchen": ("{", "}"),        # rhombus-ish
    "storage": ("(", ")"),
}
_DEFAULT_SHAPE = ("[", "]")  # rectangle for living, bedroom, etc.


def _sanitize_id(name: str) -> str:
    """Convert a space name to a valid Mermaid node ID."""
    return name.replace(" ", "_").replace("-", "_").replace(".", "_")


def graph_to_mermaid(
    graph: ConnectivityGraph,
    direction: str = "LR",
    show_area: bool = True,
) -> str:
    """Convert a connectivity graph to Mermaid flowchart syntax.

    Args:
        graph: The connectivity graph to export.
        direction: Flowchart direction (LR, TB, RL, BT).
        show_area: Include area in node labels.

    Returns:
        Mermaid flowchart string.
    """
    lines = [f"flowchart {direction}"]

    # Define nodes with appropriate shapes
    for name, node in sorted(graph.nodes.items()):
        node_id = _sanitize_id(name)
        label = name
        if show_area and node.area > 0:
            label += f"\\n{node.area:.1f}m²"

        left, right = _NODE_SHAPES.get(node.node_type, _DEFAULT_SHAPE)
        lines.append(f"    {node_id}{left}\"{label}\"{right}")

    # Define edges with door labels
    lines.append("")
    seen_edges: set[tuple[str, str]] = set()
    for edge in graph.edges:
        from_id = _sanitize_id(edge.from_node)
        to_id = _sanitize_id(edge.to_node)

        # Avoid duplicate edges
        edge_key = tuple(sorted((from_id, to_id)))
        if edge_key in seen_edges:
            # Still add if it's a different door
            pass
        seen_edges.add(edge_key)

        door_label = edge.door_name or "door"
        door_label += f" {edge.door_width:.1f}m"
        lines.append(f"    {from_id} -->|\"{door_label}\"| {to_id}")

    return "\n".join(lines)


def graph_to_mermaid_simple(graph: ConnectivityGraph) -> str:
    """Simplified one-line-per-path Mermaid representation.

    More compact, useful for quick AI reasoning.
    Example: Exterior -->|Building Main Entry 1.2m| Lobby -->|Core Entry 0.9m| Corridor
    """
    lines = [f"%% {graph.storey} — Room Connectivity"]
    lines.append("flowchart LR")

    for edge in graph.edges:
        from_id = _sanitize_id(edge.from_node)
        to_id = _sanitize_id(edge.to_node)
        door_label = f"{edge.door_name} {edge.door_width:.1f}m"
        lines.append(f"    {from_id} -->|\"{door_label}\"| {to_id}")

    return "\n".join(lines)
