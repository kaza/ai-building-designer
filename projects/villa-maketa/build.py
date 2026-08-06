"""Villa Maketa v1 — build building.json from spec.md dimensions.

Run: .venv/bin/python projects/villa-maketa/build.py
Coordinates are wall centerlines. See spec.md for the layout diagram.
"""

from pathlib import Path

from archicad_builder.models import Building
from archicad_builder.models.elements import DoorOperationType, StaircaseType
from archicad_builder.models.geometry import Point2D, Polygon2D
from archicad_builder.models.spaces import Apartment, RoomType, Space

GF = "Ground Floor"
H = 3.0          # storey height (clear height must be >= 2.5 after 0.37 structure, E001)
EXT = 0.30       # exterior wall thickness
INT = 0.12       # interior wall thickness

b = Building(name="Villa Maketa", description="Villa from cardboard maquette: garage + ground floor")

# ── Garage storey (full L-footprint basement; E050 needs every GF
#    load-bearing wall aligned with one below) ─────────────────────────
GAR = "Garage"
GH = 2.89  # clear 2.52 after 0.37 structure — exactly the W001 target
b.add_story(GAR, height=GH, elevation=-GH)


def gwall(name, start, end):
    # Stone rubble facade per the owner's maquette photo (facade-finishes.md)
    return b.add_wall(GAR, start, end, height=GH, thickness=EXT, name=name,
                      is_external=True, load_bearing=True,
                      finish="stone_rubble")


gwall("Garage South Wall", (0, 0), (9.5, 0))
gwall("Garage East Wall", (9.5, 0), (9.5, 12))
gwall("Garage North Wall", (9.5, 12), (6.0, 12))
gwall("Garage West Wall Upper", (6.0, 12), (6.0, 8))
gwall("Garage North Wall West", (6.0, 8), (4.5, 8))
gwall("Garage Northwest Wall", (4.5, 8), (0, 8))
gwall("Garage West Wall", (0, 8), (0, 0))

# vehicle door on the south wall (driveway from the south)
b.add_door(GAR, "Garage South Wall", position=1.0, width=2.4, height=2.1,
           name="Garage Vehicle Door")
b.add_slab(GAR, [(0, 0), (9.5, 0), (9.5, 12), (6.0, 12), (6.0, 8), (0, 8)],
           thickness=0.25, name="Garage Slab")
# spiral stair shaft aligned with the ground-floor one (E051)
b.add_staircase(GAR, [(6.1, 0.2), (7.6, 0.2), (7.6, 1.7), (6.1, 1.7)],
                width=0.7, stair_type=StaircaseType.SPIRAL_STAIR,
                name="Garage Stair Lower")

b.add_story(GF, height=H, elevation=0.0)


def wall(name: str, start, end, thickness=INT):
    return b.add_wall(GF, start, end, height=H, thickness=thickness, name=name,
                      is_external=thickness == EXT, load_bearing=thickness == EXT)


# --- Exterior walls (counter-clockwise around the L footprint) ---
w_south = wall("South Wall", (0, 0), (9.5, 0), EXT)
w_east = wall("East Wall", (9.5, 0), (9.5, 12), EXT)
w_north = wall("North Wall", (9.5, 12), (6.0, 12), EXT)
w_r2_west = wall("Room 2 West Wall", (6.0, 12), (6.0, 8), EXT)
w_master_n = wall("Master North Wall", (6.0, 8), (4.5, 8), EXT)
w_nw = wall("Living North Wall", (4.5, 8), (0, 8), EXT)
w_west = wall("West Wall", (0, 8), (0, 0), EXT)

# --- Interior walls ---
# Naming matters: validators match corridor walls and doors by name
# (E022 wants "corridor" in a wall name; E070 wants "<apt> <room> Door").
w_divider = wall("Living East Wall", (4.5, 0), (4.5, 8))          # west column vs center
w_hall_w = wall("Corridor West Wall", (8, 2.5), (8, 8))           # hallway vs baths/master
w_bath_s = wall("Bath South Wall", (4.5, 2.5), (8, 2.5))          # passage vs baths
# Guest bathroom needs >= 1.30m CLEAR between W11 and W9 (owner requirement —
# the 0.8 x 1.3 shower spans the full width): 8.0 - 1.3 - 0.06 - 0.06 = 6.58
w_bath_mid = wall("Bath Divider Wall", (6.58, 2.5), (6.58, 4.5))  # bath 1 vs guest bath
w_master_s = wall("Master South Wall", (4.5, 4.5), (8, 4.5))      # baths vs master
w_r2_hall = wall("Room 2 South Wall East", (8, 8), (9.5, 8))      # room2 vs hallway
w_r2_master = wall("Room 2 South Wall West", (6.0, 8), (8, 8))    # room2 vs master

# --- Doors ---
b.add_door(GF, "South Wall", position=8.5, width=1.0, height=2.1, name="Vila Entry Door")
b.add_door(GF, "Living East Wall", position=1.6, width=0.9, height=2.1, name="Vila Kitchen Door")
# Maquette close-up: Bath 1 is the master en-suite — entered from the bedroom,
# not from the passage. Guests use the hallway WC.
# Print (maquette-alignment.md D-3): x5.25-6.0, hinge west, opens SOUTH into bath
b.add_door(GF, "Master South Wall", position=0.75, width=0.75, height=2.1,
           name="Vila Bath 1 Door", swing_inward=False)
# Print (D-4, provisional): shifted south so the swing clears the north shower
b.add_door(GF, "Corridor West Wall", position=0.3, width=0.75, height=2.1,
           name="Vila Guest Bathroom Door")
# Print (D-2): hard against the SE corner, y4.6-5.5
b.add_door(GF, "Corridor West Wall", position=2.1, width=0.9, height=2.1,
           name="Vila Master Bedroom Door")
d_r2 = b.add_door(GF, "Room 2 South Wall East", position=0.3, width=0.9, height=2.1,
                  name="Vila Room 2 Door")
# Hinge on the east side: the open leaf rests against the east facade wall
d_r2.operation_type = DoorOperationType.SINGLE_SWING_RIGHT
# Maquette close-up: terrace door is in the NORTH wall near the west corner
# (opens onto the deck), not in the west wall.
# 1.4m double door to the pool deck (owner request 2026-08-04); W060 waived
# Opens OUTWARD onto the deck (terrace doors do) — keeps the 1.4m swing arc
# out of the bedroom (W100)
b.add_door(GF, "North Wall", position=2.0, width=1.4, height=2.1,
           name="Vila Room 2 Terrace Door", swing_inward=False)

# --- Windows ---
b.add_window(GF, "South Wall", position=1.5, width=1.5, height=1.4, name="Kitchen Window")
# West wall is the TV wall: clerestory windows only (sill 1.80, natural
# light from above)
b.add_window(GF, "West Wall", position=1.5, width=1.8, height=0.75,
             sill_height=1.8, name="Living Window W1")
b.add_window(GF, "West Wall", position=4.5, width=1.8, height=0.75,
             sill_height=1.8, name="Living Window W2")
b.add_window(GF, "Living North Wall", position=0.15, width=4.2, height=2.5,
             sill_height=0.15, name="Living Sliding Window")
# Maquette print (maquette-alignment.md D-1): asymmetric glass pair filling the
# approved 1.4 opening — 0.9 leaf hinge EAST (x5.95) + 0.5 leaf hinge WEST
# (x4.55), BOTH swinging south into the master. Wall runs (6,8)->(4.5,8), so
# door_start is the east side: large leaf = LEFT hinge at pos 0.05.
b.add_door(GF, "Master North Wall", position=0.05, width=0.9, height=2.1,
           name="Vila Master Bedroom Terrace Door",
           operation_type=DoorOperationType.SINGLE_SWING_LEFT)
d_terrace_small = b.add_door(GF, "Master North Wall", position=0.95, width=0.5,
                             height=2.1,
                             name="Vila Master Bedroom Terrace Door Small")
d_terrace_small.operation_type = DoorOperationType.SINGLE_SWING_RIGHT
# Room 2 north face is glass: sliding door floor-to-ceiling beside D7
b.add_window(GF, "North Wall", position=0.15, width=1.85, height=2.75,
             sill_height=0.05, name="Room 2 Sliding Door")
b.add_window(GF, "East Wall", position=6.3, width=1.0, height=1.4, name="Hallway Window")

# --- Slab (full L footprint) ---
b.add_slab(
    GF,
    [(0, 0), (9.5, 0), (9.5, 12), (6.0, 12), (6.0, 8), (0, 8)],
    thickness=0.25,
    name="Ground Slab",
)

# --- Outdoor: deck, pool, lawn (render/IFC only — outside the apartment) ---
b.add_slab(
    GF,
    [(0, 8), (6, 8), (6, 12), (9.5, 12), (9.5, 14), (0, 14)],
    thickness=0.15,
    name="Deck",
)
b.add_slab(GF, [(0.5, 14), (9, 14), (9, 17.5), (0.5, 17.5)], thickness=0.15, name="Pool")
b.add_slab(GF, [(4.7, 8.3), (5.9, 8.3), (5.9, 10.8), (4.7, 10.8)], thickness=0.16, name="Lawn")

# --- Roof (maquette photo: flat slab, 0.6m overhang, brown fascia, and a
# skylight aperture over the deck). Two polygons frame the hole — a C-shaped
# west part and an east strip (facade-finishes.md). ---
b.add_roof(
    GF,
    [(-0.6, -0.6), (4.3, -0.6), (4.3, 9.2), (2.3, 9.2),
     (2.3, 11.2), (4.3, 11.2), (4.3, 12.6), (-0.6, 12.6)],
    thickness=0.25, name="Roof West", finish="roof_brown",
)
b.add_roof(
    GF,
    [(4.3, -0.6), (10.1, -0.6), (10.1, 12.6), (4.3, 12.6)],
    thickness=0.25, name="Roof East", finish="roof_brown",
)

# --- Spiral staircase down to garage (matches the maquette) ---
b.add_staircase(
    GF,
    [(6.1, 0.2), (7.6, 0.2), (7.6, 1.7), (6.1, 1.7)],
    width=0.7,
    stair_type=StaircaseType.SPIRAL_STAIR,
    name="Garage Stair",
)


def space(name: str, room_type: RoomType, verts) -> Space:
    return Space(
        name=name,
        room_type=room_type,
        boundary=Polygon2D(vertices=[Point2D(x=x, y=y) for x, y in verts]),
    )


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


hallway_verts = [
    (4.5, 0), (6.1, 0), (6.1, 1.7), (7.6, 1.7), (7.6, 0),
    (9.5, 0), (9.5, 8), (8, 8), (8, 2.5), (4.5, 2.5),
]

apartment = Apartment(
    name="Vila",
    tag="A1",
    boundary=Polygon2D(
        vertices=[
            Point2D(x=x, y=y)
            for x, y in [(0, 0), (9.5, 0), (9.5, 12), (6.0, 12), (6.0, 8), (0, 8)]
        ]
    ),
    spaces=[
        space("Kitchen", RoomType.KITCHEN, rect(0, 0, 4.5, 2.5)),
        space("Living", RoomType.LIVING, rect(0, 2.5, 4.5, 8)),
        space("Bath 1", RoomType.BATHROOM, rect(4.5, 2.5, 6.58, 4.5)),
        space("Guest Bathroom", RoomType.TOILET, rect(6.58, 2.5, 8, 4.5)),
        space("Master Bedroom", RoomType.BEDROOM, rect(4.5, 4.5, 8, 8)),
        space("Room 2", RoomType.BEDROOM, rect(6.0, 8, 9.5, 12)),
        space("Hallway", RoomType.HALLWAY, hallway_verts),
        space("Garage Stair", RoomType.STAIRCASE, rect(6.1, 0.2, 7.6, 1.7)),
    ],
)

story = b.get_story(GF)
assert story is not None
story.apartments.append(apartment)

garage_story = b.get_story(GAR)
assert garage_story is not None
garage_story.spaces.append(space(
    "Garage", RoomType.UTILITY,
    [(0, 0), (9.5, 0), (9.5, 12), (6.0, 12), (6.0, 8), (0, 8)],
))

out = Path(__file__).parent / "building.json"
b.save(out)
print(f"Saved {out}")
print(f"Walls: {len(story.walls)}, doors: {len(story.doors)}, windows: {len(story.windows)}")
print(f"Apartment area: {apartment.area:.1f} m2, rooms: {apartment.room_count}")
