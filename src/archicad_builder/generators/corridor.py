"""Corridor carving.

Creates a central corridor through the building from the vertical core
to the building edges, dividing the floor into apartment zones on
either side.

For a building with the core at the south-center:
```
+------------------+
|   Apt zone (N)   |
+---+---------+----+
|   | corridor|    |
+---+---------+----+
|   Apt zone (S)   |
+--+---+-------+---+
   |ELV|  ST   |
   +---+-------+
```

The corridor is defined by two parallel partition walls running
the full width (or depth) of the building.
"""

from __future__ import annotations

from archicad_builder.models.building import Building


def carve_corridor(
    building: Building,
    corridor_y: float,
    corridor_width: float = 1.5,
    wall_thickness: float = 0.15,
    wall_height: float | None = None,
    x_start: float = 0.0,
    x_end: float | None = None,
) -> None:
    """Carve a horizontal (east-west) corridor through all floors.

    Creates two parallel partition walls defining the corridor:
    - South corridor wall at y = corridor_y
    - North corridor wall at y = corridor_y + corridor_width

    Args:
        building: Building to modify (mutated in place).
        corridor_y: Y coordinate of corridor south edge.
        corridor_width: Corridor width in meters (1.2m min per Austrian code).
        x_start: X start of corridor (typically 0 = west exterior wall).
        x_end: X end of corridor (defaults to building width from east wall).
        wall_thickness: Corridor wall thickness.
        wall_height: Wall height (defaults to story height).
    """
    if x_end is None:
        # Auto-detect building width from first story's walls
        x_end = _detect_building_width(building)

    for story in building.stories:
        story_name = story.name
        wh = wall_height if wall_height is not None else story.height

        # South corridor wall
        wall_s = building.add_wall(
            story_name,
            start=(x_start, corridor_y),
            end=(x_end, corridor_y),
            height=wh,
            thickness=wall_thickness,
            name="Corridor South Wall",
        )
        wall_s.load_bearing = False
        wall_s.is_external = False

        # North corridor wall
        wall_n = building.add_wall(
            story_name,
            start=(x_start, corridor_y + corridor_width),
            end=(x_end, corridor_y + corridor_width),
            height=wh,
            thickness=wall_thickness,
            name="Corridor North Wall",
        )
        wall_n.load_bearing = False
        wall_n.is_external = False


def _detect_building_width(building: Building) -> float:
    """Detect building width from exterior walls (max X coordinate)."""
    max_x = 0.0
    if building.stories:
        for wall in building.stories[0].walls:
            max_x = max(max_x, wall.start.x, wall.end.x)
    return max_x
