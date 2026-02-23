"""Building shell generator.

Given a rectangular footprint and floor count, generates:
- Stories with correct elevations
- Exterior walls (load-bearing, is_external) per floor
- Floor slabs per floor

This is the first step in top-down generation: create the building envelope.
"""

from __future__ import annotations

from archicad_builder.models.building import Building
from archicad_builder.models.geometry import Point2D, Polygon2D


def generate_shell(
    name: str = "Building",
    width: float = 16.0,
    depth: float = 12.0,
    num_floors: int = 4,
    floor_height: float = 3.0,
    wall_thickness: float = 0.30,
    wall_height: float | None = None,
    slab_thickness: float = 0.25,
    ground_floor_name: str = "Ground Floor",
) -> Building:
    """Generate a rectangular building shell.

    Creates a Building with:
    - N stories at correct elevations
    - 4 exterior walls per story (load-bearing, is_external)
    - 1 floor slab per story

    Args:
        name: Building name.
        width: Building width in X direction (meters).
        depth: Building depth in Y direction (meters).
        num_floors: Number of stories.
        floor_height: Floor-to-floor height (meters).
        wall_thickness: Exterior wall thickness (meters).
        wall_height: Wall height (defaults to floor_height).
        slab_thickness: Floor slab thickness (meters).
        ground_floor_name: Name for the ground floor story.

    Returns:
        Building with shell elements.
    """
    if wall_height is None:
        wall_height = floor_height

    building = Building(name=name)

    # Corner points of the rectangular footprint
    corners = [
        (0.0, 0.0),
        (width, 0.0),
        (width, depth),
        (0.0, depth),
    ]

    # Wall segments: (start, end, name_suffix)
    wall_segments = [
        (corners[0], corners[1], "South"),
        (corners[1], corners[2], "East"),
        (corners[2], corners[3], "North"),
        (corners[3], corners[0], "West"),
    ]

    for floor_idx in range(num_floors):
        if floor_idx == 0:
            story_name = ground_floor_name
        else:
            story_name = _ordinal_floor_name(floor_idx)

        story = building.add_story(story_name, height=floor_height)

        # Exterior walls
        for start, end, direction in wall_segments:
            wall = building.add_wall(
                story_name,
                start=start,
                end=end,
                height=wall_height,
                thickness=wall_thickness,
                name=f"{direction} Wall",
            )
            # Mark as external load-bearing
            wall.load_bearing = True
            wall.is_external = True

        # Floor slab
        building.add_slab(
            story_name,
            vertices=corners,
            thickness=slab_thickness,
            is_floor=True,
            name=f"Floor Slab",
        )

    return building


def _ordinal_floor_name(floor_idx: int) -> str:
    """Generate floor name: 1st Floor, 2nd Floor, etc."""
    suffixes = {1: "st", 2: "nd", 3: "rd"}
    suffix = suffixes.get(floor_idx, "th")
    return f"{floor_idx}{suffix} Floor"
