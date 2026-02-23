"""Vertical core placement.

Places elevator shaft and staircase through all floors of a building.
The core is positioned at a given (x, y) origin and creates:
- Elevator shaft walls (structural, forming a rectangular enclosure)
- Staircase element (with footprint)
- Doors from corridor side on each floor

The elevator + staircase together form the "vertical core" that
repeats identically on every floor.
"""

from __future__ import annotations

from archicad_builder.models.building import Building
from archicad_builder.models.elements import StaircaseType
from archicad_builder.models.geometry import Point2D, Polygon2D


def place_vertical_core(
    building: Building,
    core_x: float,
    core_y: float,
    elevator_width: float = 2.0,
    elevator_depth: float = 2.0,
    stair_width: float = 2.5,
    stair_depth: float = 5.0,
    wall_thickness: float = 0.20,
    wall_height: float | None = None,
    corridor_side: str = "south",
) -> None:
    """Place a vertical core (elevator + staircase) through all floors.

    Layout (corridor_side="south"):
    ```
    +---+-------+
    | E |       |
    | L |  ST   |
    | V |       |
    +---+-------+
       corridor →
    ```

    The elevator is placed to the west, staircase to the east.
    A door is placed on each floor facing the corridor side.

    Args:
        building: Building to modify (mutated in place).
        core_x: X position of core's bottom-left corner.
        core_y: Y position of core's bottom-left corner.
        elevator_width: Elevator shaft width (X direction).
        elevator_depth: Elevator shaft depth (Y direction).
        stair_width: Staircase width (X direction).
        stair_depth: Staircase depth (Y direction).
        wall_thickness: Core wall thickness.
        wall_height: Wall height (defaults to story height).
        corridor_side: Which side faces the corridor ("south", "north", "east", "west").
    """
    # Core total dimensions
    core_width = elevator_width + stair_width
    core_depth = max(elevator_depth, stair_depth)

    # Elevator shaft corners (left portion of core)
    elev_x0 = core_x
    elev_y0 = core_y
    elev_x1 = core_x + elevator_width
    elev_y1 = core_y + elevator_depth

    # Staircase corners (right portion of core)
    stair_x0 = core_x + elevator_width
    stair_y0 = core_y
    stair_x1 = core_x + core_width
    stair_y1 = core_y + stair_depth

    for story in building.stories:
        story_name = story.name
        wh = wall_height if wall_height is not None else story.height

        # --- Elevator shaft walls ---
        # We create 3 walls for the elevator (the 4th side is shared with staircase
        # or open to corridor depending on layout)

        # West wall of elevator
        _add_core_wall(building, story_name,
                       (elev_x0, elev_y0), (elev_x0, elev_y1),
                       wh, wall_thickness, "Elevator West Wall")

        # North wall of elevator
        _add_core_wall(building, story_name,
                       (elev_x0, elev_y1), (elev_x1, elev_y1),
                       wh, wall_thickness, "Elevator North Wall")

        # South wall of elevator (with door opening on corridor side)
        if corridor_side == "south":
            # South wall gets a door
            elev_south = _add_core_wall(
                building, story_name,
                (elev_x0, elev_y0), (elev_x1, elev_y0),
                wh, wall_thickness, "Elevator South Wall")
            building.add_door(
                story_name,
                wall_name="Elevator South Wall",
                position=0.3,
                width=0.9,
                height=2.1,
                name="Elevator Door",
            )
        else:
            _add_core_wall(building, story_name,
                           (elev_x0, elev_y0), (elev_x1, elev_y0),
                           wh, wall_thickness, "Elevator South Wall")

        # Dividing wall between elevator and staircase
        _add_core_wall(building, story_name,
                       (elev_x1, elev_y0), (elev_x1, elev_y1),
                       wh, wall_thickness, "Core Divider Wall")

        # --- Staircase walls ---
        # East wall
        _add_core_wall(building, story_name,
                       (stair_x1, stair_y0), (stair_x1, stair_y1),
                       wh, wall_thickness, "Staircase East Wall")

        # North wall
        _add_core_wall(building, story_name,
                       (stair_x0, stair_y1), (stair_x1, stair_y1),
                       wh, wall_thickness, "Staircase North Wall")

        # South wall (with door to corridor)
        if corridor_side == "south":
            _add_core_wall(building, story_name,
                           (stair_x0, stair_y0), (stair_x1, stair_y0),
                           wh, wall_thickness, "Staircase South Wall")
            building.add_door(
                story_name,
                wall_name="Staircase South Wall",
                position=0.3,
                width=1.0,
                height=2.1,
                name="Staircase Door",
            )
        else:
            _add_core_wall(building, story_name,
                           (stair_x0, stair_y0), (stair_x1, stair_y0),
                           wh, wall_thickness, "Staircase South Wall")

        # --- Staircase element ---
        stair_outline = [
            (stair_x0, stair_y0),
            (stair_x1, stair_y0),
            (stair_x1, stair_y1),
            (stair_x0, stair_y1),
        ]
        building.add_staircase(
            story_name,
            vertices=stair_outline,
            width=stair_width,
            name="Main Staircase",
        )


def _add_core_wall(
    building: Building,
    story_name: str,
    start: tuple[float, float],
    end: tuple[float, float],
    height: float,
    thickness: float,
    name: str,
) -> None:
    """Add a load-bearing core wall."""
    wall = building.add_wall(
        story_name, start=start, end=end,
        height=height, thickness=thickness, name=name,
    )
    wall.load_bearing = True
    wall.is_external = False
