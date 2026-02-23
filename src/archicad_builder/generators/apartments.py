"""Apartment subdivision generator.

Divides the usable floor area (minus corridor and core) into apartments.
Creates apartment boundaries, partition walls between apartments,
and basic room subdivision within each apartment.

Strategy:
1. Identify usable zones (north side and south side of corridor)
2. Divide each zone into apartment-width strips
3. Create partition walls between apartments
4. Subdivide each apartment into rooms
5. Place doors (apartment entry from corridor, internal between rooms)
"""

from __future__ import annotations

import math

from archicad_builder.models.building import Building, Story
from archicad_builder.models.geometry import Point2D, Polygon2D
from archicad_builder.models.spaces import Apartment, RoomType, Space
from archicad_builder.models.ifc_id import generate_ifc_id


def subdivide_apartments(
    building: Building,
    story_name: str,
    corridor_y: float,
    corridor_width: float = 1.5,
    building_width: float | None = None,
    building_depth: float | None = None,
    apartments_per_side: int = 2,
    wall_thickness: float = 0.15,
    wall_height: float | None = None,
) -> list[Apartment]:
    """Subdivide a floor into apartments on both sides of the corridor.

    Creates apartments as equal-width strips running perpendicular to
    the corridor, on both the north and south sides.

    Layout (apartments_per_side=2):
    ```
    +--------+--------+
    |  A3    |  A4    |   North zone
    +--------+--------+
    |     corridor     |
    +--------+--------+
    |  A1    |  A2    |   South zone
    +--------+--------+
    ```

    Args:
        building: Building to modify.
        story_name: Story to subdivide.
        corridor_y: Y coordinate of corridor south edge.
        corridor_width: Corridor width.
        building_width: Building X extent (auto-detected if None).
        building_depth: Building Y extent (auto-detected if None).
        apartments_per_side: Number of apartments on each side of corridor.
        wall_thickness: Partition wall thickness between apartments.
        wall_height: Wall height (defaults to story height).

    Returns:
        List of created Apartment objects.
    """
    story = building._require_story(story_name)
    wh = wall_height if wall_height is not None else story.height

    if building_width is None:
        building_width = _detect_extent(story, "x")
    if building_depth is None:
        building_depth = _detect_extent(story, "y")

    corridor_north_y = corridor_y + corridor_width
    apt_width = building_width / apartments_per_side

    all_apartments: list[Apartment] = []

    # --- South zone: y=0 to corridor_y ---
    for i in range(apartments_per_side):
        x0 = i * apt_width
        x1 = (i + 1) * apt_width
        y0 = 0.0
        y1 = corridor_y

        apt = _create_apartment(
            building, story_name,
            x0, y0, x1, y1,
            name=f"Apt {len(all_apartments) + 1}",
            wh=wh,
        )
        story.apartments.append(apt)
        all_apartments.append(apt)

        # Add partition wall between apartments (not at building edge)
        if i > 0:
            wall = building.add_wall(
                story_name,
                start=(x0, y0), end=(x0, y1),
                height=wh, thickness=wall_thickness,
                name=f"Apt Partition S-{i}",
            )
            wall.load_bearing = False
            wall.is_external = False

    # --- North zone: corridor_north_y to building_depth ---
    for i in range(apartments_per_side):
        x0 = i * apt_width
        x1 = (i + 1) * apt_width
        y0 = corridor_north_y
        y1 = building_depth

        apt = _create_apartment(
            building, story_name,
            x0, y0, x1, y1,
            name=f"Apt {len(all_apartments) + 1}",
            wh=wh,
        )
        story.apartments.append(apt)
        all_apartments.append(apt)

        # Partition wall
        if i > 0:
            wall = building.add_wall(
                story_name,
                start=(x0, y0), end=(x0, y1),
                height=wh, thickness=wall_thickness,
                name=f"Apt Partition N-{i}",
            )
            wall.load_bearing = False
            wall.is_external = False

    # --- Add apartment entry doors from corridor ---
    for apt in all_apartments:
        _add_entry_door(building, story_name, apt, corridor_y, corridor_north_y)

    return all_apartments


def _create_apartment(
    building: Building,
    story_name: str,
    x0: float, y0: float,
    x1: float, y1: float,
    name: str,
    wh: float,
) -> Apartment:
    """Create an apartment with boundary and basic room subdivision."""
    boundary = Polygon2D(vertices=[
        Point2D(x=x0, y=y0),
        Point2D(x=x1, y=y0),
        Point2D(x=x1, y=y1),
        Point2D(x=x0, y=y1),
    ])

    # Basic room subdivision
    spaces = _subdivide_rooms(x0, y0, x1, y1, name)

    return Apartment(
        name=name,
        boundary=boundary,
        spaces=spaces,
    )


def _subdivide_rooms(
    x0: float, y0: float,
    x1: float, y1: float,
    apt_name: str,
) -> list[Space]:
    """Subdivide an apartment rectangle into basic rooms.

    Layout strategy (simple partition):
    ```
    +----------+------+
    |          | bath |
    |  living  +------+
    |          | hall |
    +----------+------+
    |  bedroom        |
    +-----------------+
    ```

    The living room gets the larger portion, bathroom and hallway
    are in the corner near the entry, bedroom along one side.
    """
    w = x1 - x0
    h = y1 - y0
    area = w * h

    spaces = []

    if area < 20:
        # Studio: just one room
        spaces.append(Space(
            name=f"{apt_name} Studio",
            room_type=RoomType.LIVING,
            boundary=Polygon2D(vertices=[
                Point2D(x=x0, y=y0), Point2D(x=x1, y=y0),
                Point2D(x=x1, y=y1), Point2D(x=x0, y=y1),
            ]),
        ))
        return spaces

    # Split into upper and lower zones
    # Upper zone: living + bathroom + hallway
    # Lower zone: bedroom(s)
    split_y = y0 + h * 0.45  # 45% for bedroom, 55% for living area

    # Bedroom (lower zone)
    spaces.append(Space(
        name=f"{apt_name} Bedroom",
        room_type=RoomType.BEDROOM,
        boundary=Polygon2D(vertices=[
            Point2D(x=x0, y=y0), Point2D(x=x1, y=y0),
            Point2D(x=x1, y=split_y), Point2D(x=x0, y=split_y),
        ]),
    ))

    # Upper zone split: living (left 70%) + bathroom/hallway (right 30%)
    bath_x = x0 + w * 0.70
    bath_split_y = split_y + (y1 - split_y) * 0.55

    # Living room
    spaces.append(Space(
        name=f"{apt_name} Living",
        room_type=RoomType.LIVING,
        boundary=Polygon2D(vertices=[
            Point2D(x=x0, y=split_y), Point2D(x=bath_x, y=split_y),
            Point2D(x=bath_x, y=y1), Point2D(x=x0, y=y1),
        ]),
    ))

    # Hallway (entry area)
    spaces.append(Space(
        name=f"{apt_name} Hallway",
        room_type=RoomType.HALLWAY,
        boundary=Polygon2D(vertices=[
            Point2D(x=bath_x, y=split_y), Point2D(x=x1, y=split_y),
            Point2D(x=x1, y=bath_split_y), Point2D(x=bath_x, y=bath_split_y),
        ]),
    ))

    # Bathroom
    spaces.append(Space(
        name=f"{apt_name} Bathroom",
        room_type=RoomType.BATHROOM,
        boundary=Polygon2D(vertices=[
            Point2D(x=bath_x, y=bath_split_y), Point2D(x=x1, y=bath_split_y),
            Point2D(x=x1, y=y1), Point2D(x=bath_x, y=y1),
        ]),
    ))

    return spaces


def _add_entry_door(
    building: Building,
    story_name: str,
    apt: Apartment,
    corridor_y: float,
    corridor_north_y: float,
) -> None:
    """Add an apartment entry door facing the corridor.

    Finds the corridor-facing wall and places a door on it.
    """
    story = building._require_story(story_name)
    verts = apt.boundary.vertices

    # Determine which side faces the corridor
    min_y = min(v.y for v in verts)
    max_y = max(v.y for v in verts)
    min_x = min(v.x for v in verts)
    max_x = max(v.x for v in verts)

    # Find the corridor wall this apartment faces
    if abs(max_y - corridor_y) < 0.01:
        # South apartment: door on the north side (y=corridor_y)
        target_wall_y = corridor_y
        wall_name = "Corridor South Wall"
    elif abs(min_y - corridor_north_y) < 0.01:
        # North apartment: door on the south side (y=corridor_north_y)
        target_wall_y = corridor_north_y
        wall_name = "Corridor North Wall"
    else:
        return  # Can't determine corridor side

    # Find the matching corridor wall
    corridor_wall = story.get_wall_by_name(wall_name)
    if corridor_wall is None:
        return

    # Place door in the middle of the apartment's corridor-facing edge
    apt_center_x = (min_x + max_x) / 2
    wall_start_x = min(corridor_wall.start.x, corridor_wall.end.x)
    door_position = apt_center_x - wall_start_x - 0.45  # center the 0.9m door

    if door_position < 0:
        door_position = 0.1

    building.add_door(
        story_name,
        wall_name=wall_name,
        position=door_position,
        width=0.9,
        height=2.1,
        name=f"{apt.name} Entry",
    )


def _detect_extent(story: Story, axis: str) -> float:
    """Detect building extent from walls."""
    values = []
    for wall in story.walls:
        if axis == "x":
            values.extend([wall.start.x, wall.end.x])
        else:
            values.extend([wall.start.y, wall.end.y])
    return max(values) if values else 0.0
