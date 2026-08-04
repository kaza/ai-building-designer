"""Shared synthetic-building builders for framework tests.

Policy (specs/test-fixtures.md): exact assertions run against buildings
built here, never against mutable `projects/` data.
"""

from archicad_builder.models.building import Building
from archicad_builder.models.geometry import Point2D, Polygon2D
from archicad_builder.models.spaces import Apartment, RoomType, Space

GF = "Ground Floor"


def rect_space(name: str, room_type: RoomType,
               x0: float, y0: float, x1: float, y1: float) -> Space:
    """Axis-aligned rectangular Space."""
    return Space(name=name, room_type=room_type, boundary=Polygon2D(vertices=[
        Point2D(x=x0, y=y0), Point2D(x=x1, y=y0),
        Point2D(x=x1, y=y1), Point2D(x=x0, y=y1)]))


def rect_boundary(x0: float, y0: float, x1: float, y1: float) -> Polygon2D:
    return Polygon2D(vertices=[
        Point2D(x=x0, y=y0), Point2D(x=x1, y=y0),
        Point2D(x=x1, y=y1), Point2D(x=x0, y=y1)])


def make_defect_building() -> Building:
    """Synthetic single-storey building with deliberate defects.

    Apt A (west): reachable from corridor; Kitchen is open-plan (no door,
    E080); Bedroom reachable only through Living (Durchgangszimmer, W080).
    Apt B (east): internally connected but NO entry from the corridor (E082).
    """
    b = Building(name="Defect Fixture")
    b.add_story(GF, height=3.0)

    def wall(name, s_, e_, thickness=0.25, external=False):
        return b.add_wall(GF, s_, e_, height=3.0, thickness=thickness,
                          name=name, is_external=external, load_bearing=external)

    wall("South Wall", (0, 0), (12, 0), external=True)
    wall("East Wall", (12, 0), (12, 8), external=True)
    wall("North Wall", (12, 8), (0, 8), external=True)
    wall("West Wall", (0, 8), (0, 0), external=True)
    wall("Corridor South Wall", (0, 5.25), (12, 5.25))
    wall("Corridor North Wall", (0, 6.75), (12, 6.75))
    wall("Apt A Vorraum West Wall", (2, 3.25), (2, 5.25), 0.12)
    wall("Apt A Vorraum South Wall", (2, 3.25), (4, 3.25), 0.12)
    wall("Apt A Bedroom Wall", (4, 0), (4, 5.25), 0.12)
    wall("Apt Divider Wall", (6, 0), (6, 5.25), 0.12)
    wall("Apt B Vorraum West Wall", (8, 3.25), (8, 5.25), 0.12)
    wall("Apt B Vorraum South Wall", (8, 3.25), (10, 3.25), 0.12)

    b.add_door(GF, "Corridor South Wall", position=2.6, width=0.9, height=2.1,
               name="Apt A Entry")
    b.add_door(GF, "Apt A Vorraum South Wall", position=0.55, width=0.9,
               height=2.1, name="Apt A Living Door")
    b.add_door(GF, "Apt A Bedroom Wall", position=1.3, width=0.8, height=2.1,
               name="Apt A Bedroom Door")
    # Apt B: internal door only — deliberately NO entry from the corridor
    b.add_door(GF, "Apt B Vorraum South Wall", position=0.55, width=0.9,
               height=2.1, name="Apt B Living Door")

    b.add_window(GF, "South Wall", position=4.5, width=1.2, height=1.4,
                 name="Apt A Bedroom Window")

    story = b.get_story(GF)
    story.apartments.append(Apartment(
        name="Apt A",
        boundary=rect_boundary(0, 0, 6, 5.25),
        spaces=[
            rect_space("Apt A Kitchen", RoomType.KITCHEN, 0, 0, 2, 3.25),
            rect_space("Apt A Living", RoomType.LIVING, 2, 0, 4, 3.25),
            rect_space("Apt A Vorraum", RoomType.HALLWAY, 2, 3.25, 4, 5.25),
            rect_space("Apt A Bedroom", RoomType.BEDROOM, 4, 0, 6, 5.25),
        ],
    ))
    story.apartments.append(Apartment(
        name="Apt B",
        boundary=rect_boundary(6, 0, 12, 5.25),
        spaces=[
            # Living spans the full south band so the vorraum door (center
            # x=9) actually lands in it — vorraum <-> living edge exists.
            rect_space("Apt B Living", RoomType.LIVING, 6, 0, 12, 3.25),
            rect_space("Apt B Vorraum", RoomType.HALLWAY, 8, 3.25, 10, 5.25),
        ],
    ))
    return b
