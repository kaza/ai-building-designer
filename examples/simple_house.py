"""Simple single-room house — proof of concept.

One room: 6m x 4m, 3m high
- 4 walls (0.25m thick)
- 1 door (south wall, 0.9m wide, 2.1m high)
- 3 windows (east, west, north walls, 1.2m wide, 1.5m high, 0.9m sill)
- 1 floor slab (0.25m thick)
- 1 flat roof (0.3m thick)

   N
   ↑
   |
   +--- E

Layout (top view):
   (0,4) -------- (6,4)
     |              |
  W  |    room      |  E
     |              |
   (0,0) -------- (6,0)
           S (door here)
"""

from pathlib import Path

from archicad_builder.models import (
    Building,
    Door,
    Point2D,
    Polygon2D,
    Roof,
    RoofType,
    Slab,
    Story,
    Wall,
    Window,
)
from archicad_builder.export.ifc import IFCExporter
from archicad_builder.validators.structural import validate_story

# Room dimensions
WIDTH = 6.0   # x-axis
DEPTH = 4.0   # y-axis
HEIGHT = 3.0  # wall height
WALL_T = 0.25  # wall thickness

# --- Walls ---
wall_south = Wall(
    name="South Wall",
    start=Point2D(x=0, y=0),
    end=Point2D(x=WIDTH, y=0),
    height=HEIGHT,
    thickness=WALL_T,
)

wall_east = Wall(
    name="East Wall",
    start=Point2D(x=WIDTH, y=0),
    end=Point2D(x=WIDTH, y=DEPTH),
    height=HEIGHT,
    thickness=WALL_T,
)

wall_north = Wall(
    name="North Wall",
    start=Point2D(x=WIDTH, y=DEPTH),
    end=Point2D(x=0, y=DEPTH),
    height=HEIGHT,
    thickness=WALL_T,
)

wall_west = Wall(
    name="West Wall",
    start=Point2D(x=0, y=DEPTH),
    end=Point2D(x=0, y=0),
    height=HEIGHT,
    thickness=WALL_T,
)

# --- Door (south wall, centered-ish) ---
door = Door(
    name="Front Door",
    wall_id=wall_south.global_id,
    position=2.5,   # 2.5m from left edge
    width=0.9,
    height=2.1,
)

# --- Windows ---
window_east = Window(
    name="East Window",
    wall_id=wall_east.global_id,
    position=1.2,    # 1.2m from south-east corner
    width=1.2,
    height=1.5,
    sill_height=0.9,
)

window_west = Window(
    name="West Window",
    wall_id=wall_west.global_id,
    position=1.2,    # 1.2m from north-west corner
    width=1.2,
    height=1.5,
    sill_height=0.9,
)

window_north = Window(
    name="North Window",
    wall_id=wall_north.global_id,
    position=2.4,    # centered on north wall (6.0 - 1.2) / 2
    width=1.2,
    height=1.5,
    sill_height=0.9,
)

# --- Floor slab ---
floor_slab = Slab(
    name="Ground Floor",
    outline=Polygon2D(
        vertices=[
            Point2D(x=0, y=0),
            Point2D(x=WIDTH, y=0),
            Point2D(x=WIDTH, y=DEPTH),
            Point2D(x=0, y=DEPTH),
        ]
    ),
    thickness=0.25,
    is_floor=True,
)

# --- Flat roof ---
roof = Roof(
    name="Flat Roof",
    outline=Polygon2D(
        vertices=[
            Point2D(x=-0.3, y=-0.3),      # slight overhang
            Point2D(x=WIDTH + 0.3, y=-0.3),
            Point2D(x=WIDTH + 0.3, y=DEPTH + 0.3),
            Point2D(x=-0.3, y=DEPTH + 0.3),
        ]
    ),
    roof_type=RoofType.FLAT,
    pitch=0,
    thickness=0.3,
)

# --- Assemble ---
ground_floor = Story(
    name="Ground Floor",
    elevation=0.0,
    height=HEIGHT,
    walls=[wall_south, wall_east, wall_north, wall_west],
    slabs=[floor_slab],
    doors=[door],
    windows=[window_east, window_west, window_north],
    roofs=[roof],
)

building = Building(
    name="Simple House",
    stories=[ground_floor],
)

# --- Validate ---
errors = validate_story(ground_floor)
if errors:
    print("⚠️  Validation errors:")
    for e in errors:
        print(f"  [{e.severity}] {e.element_type}: {e.message}")
else:
    print("✅ Validation passed")

# --- Export ---
output = Path(__file__).parent / "output"
output.mkdir(exist_ok=True)
output_file = output / "simple_house.ifc"

exporter = IFCExporter(building)
result = exporter.export(output_file)
print(f"📁 Exported to: {result}")
print(f"   Stories: {building.story_count()}")
print(f"   Floor area: {building.total_area():.1f} m²")
print(f"   Walls: {len(ground_floor.walls)}")
print(f"   Doors: {len(ground_floor.doors)}")
print(f"   Windows: {len(ground_floor.windows)}")
