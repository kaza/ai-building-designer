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

# ── Garage storey — Option A (owner 2026-08-08): x4.5-9.5 × y0.6-8,
#    ~37m² / 2 cars, under the east block only. The old full-L basement was
#    an E050 workaround; E050 now understands partial basements (walls
#    outside the footprint stand on foundations). The garage perimeter sits
#    exactly under the GF bearing lines x=4.5 / x=9.5 / y=8, making x=4.5 a
#    real bearing line for the roof (load-takedown experiment 2026-08-08). ──
GAR = "Garage"
GH = 2.89  # clear 2.52 after 0.37 structure — exactly the W001 target
b.add_story(GAR, height=GH, elevation=-GH)


def gwall(name, start, end):
    # Stone rubble facade per the owner's maquette photo (facade-finishes.md)
    return b.add_wall(GAR, start, end, height=GH, thickness=EXT, name=name,
                      is_external=True, load_bearing=True,
                      finish="stone_rubble")


# Maquette photo #22: the garage south face is INSET 0.6m behind the GF edge
# (GF cantilevers over it, carport-style); the spiral-stair shaft pokes
# through the gap x6.1-7.6. Side walls keep their full length to the y=0
# corners — the stone reaches the front, only the door plane is recessed.
gwall("Garage South Wall", (4.5, 0.6), (6.1, 0.6))
gwall("Garage South Wall East", (7.6, 0.6), (9.5, 0.6))
gwall("Garage East Wall", (9.5, 0), (9.5, 8))
gwall("Garage North Wall", (9.5, 8), (4.5, 8))
gwall("Garage West Wall", (4.5, 8), (4.5, 0))

# vehicle door on the EAST wall (owner 2026-08-08) — the shrunk south face
# has only 1.6m/1.9m segments beside the stair shaft, a 2.4m door no longer
# fits there; driveway approaches from the east. NOTDEFINED = sectional.
b.add_door(GAR, "Garage East Wall", position=1.0, width=2.4, height=2.1,
           name="Garage Vehicle Door",
           operation_type=DoorOperationType.NOTDEFINED)
b.add_slab(GAR, [(4.5, 0.6), (9.5, 0.6), (9.5, 8), (4.5, 8)],
           thickness=0.25, name="Garage Slab")
# spiral stair shaft aligned with the ground-floor one (E051); straddles the
# south facade — the tower is half OUTSIDE the house (maquette photo #22)
b.add_staircase(GAR, [(6.1, -0.75), (7.6, -0.75), (7.6, 0.75), (6.1, 0.75)],
                width=0.7, stair_type=StaircaseType.SPIRAL_STAIR,
                name="Garage Stair Lower")

# ── Strip footings under the garage bearing grid (specs/foundations.md).
# 0.6 × 0.5 m rc strips, top flush with the garage floor; sized against the
# placeholder sigma_rd=200 kPa pending the real geotech report (spec.md).
for fname, fs, fe in [
    ("Footing Garage South", (4.5, 0.6), (6.1, 0.6)),
    ("Footing Garage South East", (7.6, 0.6), (9.5, 0.6)),
    ("Footing Garage East", (9.5, 0), (9.5, 8)),
    ("Footing Garage North", (9.5, 8), (4.5, 8)),
]:
    b.add_footing(GAR, fs, fe, width=0.6, height=0.5, name=fname)
# x=4.5 is the real bearing line for the roof (load-takedown 2026-08-08):
# 0.6 m bears 215 kPa > sigma_rd — E105 sized this one up to 0.8 m
b.add_footing(GAR, (4.5, 8), (4.5, 0), width=0.8, height=0.5,
              name="Footing Garage West")
# Arena 2026-08-13 (b-garage): strip under the GF Terrace Fin Wall
# (y=12, outside the garage box — bears on soil). Declared on the
# garage storey because footings live on the lowest storey (E104);
# the real construction depth is a frost-depth strip, engineer to set.
b.add_footing(GAR, (4.5, 12), (6.0, 12), width=0.6, height=0.5,
              name="Footing Terrace Fin")

b.add_story(GF, height=H, elevation=0.0)


def wall(name: str, start, end, thickness=INT):
    return b.add_wall(GF, start, end, height=H, thickness=thickness, name=name,
                      is_external=thickness == EXT, load_bearing=thickness == EXT)


# --- Exterior walls (counter-clockwise around the L footprint) ---
# The SW corner L (South + West walls) is YELLOW outside (owner 2026-08-06 —
# supersedes the misread "accent volume"); high window band gives light from
# above and keeps the wall below usable (TV wall).
# South facade splits around the stair tower (x6.1-7.6, photo #22); the
# east segment is appended after all other walls so W1-W14 stay stable.
# White south-band walls rise past the brown roof as a parapet (photo #24:
# "the wall should go to that height" — there is NO thick white roof)
# Arena 2026-08-13 (b-garage): the south band and the Room 2 north wall
# thicken OUTWARD (centerline shifts, inner face stays put — room areas
# untouched): South/South East 0.30→0.45, North 0.30→0.60. Extra shear
# area for E100 x lands where the walls are already mostly solid.
T_SOUTH = 0.45   # centerline y = -0.075, inner face stays at +0.15
T_NORTH = 0.60   # centerline y = 12.15, inner face stays at 11.85
w_south = wall("South Wall", (-0.15, -0.075), (6.1, -0.075), T_SOUTH)  # white
w_south.is_external = True
w_south.load_bearing = True
w_east = wall("East Wall", (9.5, 0), (9.5, 12.15), EXT)  # meets thick N wall
w_north = wall("North Wall", (9.65, 12.15), (6.0, 12.15), T_NORTH)
w_north.is_external = True
w_north.load_bearing = True
w_r2_west = wall("Room 2 West Wall", (6.0, 12.15), (6.0, 8), EXT)
w_master_n = wall("Master North Wall", (6.0, 8), (4.5, 8), EXT)
# W6: east (door-side) half is one floor-to-roof window; west half is solid
# yellow concrete carrying the TV, wrapping the corner into W7 (owner 2026-08-06)
w_nw = wall("Living North Wall", (4.5, 8), (0, 8), EXT)
w_nw.finish = "accent"
# Photo #21: the west facade's southern ~third is WHITE — the wall splits
# so the finish can differ (yellow north, plain south).
w_west = wall("West Wall", (0, 8), (0, 2.7), EXT)
w_west.finish = "accent"

# --- Interior walls ---
# Naming matters: validators match corridor walls and doors by name
# (E022 wants "corridor" in a wall name; E070 wants "<apt> <room> Door").
w_divider = wall("Living East Wall", (4.5, 0), (4.5, 8))          # west column vs center
# The x=4.5 line is the interior BEARING line (garage west wall directly
# below): halves the roof spans so the band-window facades stop carrying
# the whole roof (load-takedown experiment 2026-08-08). Kept at INT
# thickness — a 12cm RC bearing wall; sizing is the future E06x feature.
w_divider.load_bearing = True
w_hall_w = wall("Corridor West Wall", (8, 2.5), (8, 8))           # hallway vs baths/master
w_bath_s = wall("Bath South Wall", (4.5, 2.5), (8, 2.5))          # passage vs baths
# Guest bathroom needs >= 1.30m CLEAR between W11 and W9 (owner requirement —
# the 0.8 x 1.3 shower spans the full width): 8.0 - 1.3 - 0.06 - 0.06 = 6.58
w_bath_mid = wall("Bath Divider Wall", (6.58, 2.5), (6.58, 4.5))  # bath 1 vs guest bath
w_master_s = wall("Master South Wall", (4.5, 4.5), (8, 4.5))      # baths vs master
w_r2_hall = wall("Room 2 South Wall East", (8, 8), (9.5, 8))      # room2 vs hallway
w_r2_master = wall("Room 2 South Wall West", (6.0, 8), (8, 8))    # room2 vs master
# Arena 2026-08-13 (b-garage): the y=8 line is the garage north wall's
# centerline — these two partitions stand ON it (E050/E103 continuous).
# Re-anchored as bearing: the garage box becomes the spine of the
# northern x-direction shear line (E100 x / E102 x fix).
w_r2_hall.load_bearing = True
w_r2_master.load_bearing = True
w_south_e = wall("South Wall East", (7.6, -0.075), (9.65, -0.075), T_SOUTH)  # W15, D1, white
w_south_e.is_external = True
w_south_e.load_bearing = True
w_west_s = wall("West Wall South", (0, 2.7), (0, 0), EXT)        # W16, white

# --- Doors ---
b.add_door(GF, "South Wall East", position=0.9, width=1.0, height=2.1,
           name="Vila Entry Door")  # same absolute spot x8.5-9.5; still D1
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
# Maquette photo #31 (owner 2026-08-07): Room 2's north face is a CENTERED
# 2-pane glass slider (~2.2m) with solid wall stubs ~0.65m on BOTH sides —
# not edge-to-edge glass. D7 = the operable 1.1m sliding pane (glass,
# inner-flush like all villa glazing), Win5 = the fixed 1.1m pane beside
# it; exact adjacency at position 1.75 (Gemini plan review: zero-overlap
# adjacency is legal, sliding op skips W100 swing checks, 1.1m > egress).
d_r2_terrace = b.add_door(GF, "North Wall", position=1.9, width=1.1,
                          height=2.8, name="Vila Room 2 Terrace Door",
                          swing_inward=False, pane_side="inner")
# (position 1.9 from the extended wall start x=9.65 = same absolute
# x6.65-7.75 opening as before the thickening)
d_r2_terrace.operation_type = DoorOperationType.SLIDING_TO_LEFT

# --- Windows ---
# ALL villa glazing sits flush with the INNER wall face (maquette photo #28,
# owner 2026-08-06): the yellow volume and roof float over recessed glass.
# Framework default is outer-flush — every window here overrides it.
# The yellow L is part concrete part glass (owner 2026-08-06): the living
# stretch of the west wall (y 4.5-8) is floor-to-ceiling glazing; the
# concrete stretches carry a roof-to-1.80 band so the wall below stays
# usable and light falls from above.
# Arena 2026-08-13 (b-garage): kitchen band consolidated to a taller,
# narrower pane — same 1.125 m² of glass, +0.6 m of shear wall (E100 x).
b.add_window(GF, "South Wall", position=1.95, width=0.9, height=1.25,
             sill_height=1.55, name="Kitchen Window", pane_side="inner")
# (position 1.95 from the extended wall start x=-0.15 = same absolute
# x1.8-2.7 spot as before the thickening)
# Win2 slot reused in place (tags are insertion-ordered — owner talks in ids).
# Owner 2026-08-06: Win2 runs from just below the roof (2.90) down to 1.80.
# Feedback #001: position 0 = flush with the W6 corner -> corner glazing,
# the band meets Win7 glass-to-glass around the corner (no yellow post).
b.add_window(GF, "West Wall", position=0, width=3.35, height=0.75,
             sill_height=2.05, name="Living Band Window", pane_side="inner")
# Win3: full-height glazing from Win2's end to the white south third
# (photo #21). Feedback #001: abuts Win2 directly — no mullion between.
b.add_window(GF, "West Wall", position=3.35, width=1.9, height=2.75,
             sill_height=0.05, name="Living Glass W2", pane_side="inner")
# Feedback #003: flush at the wall start (x=4.5) — glazing runs through the
# W8 end cap and touches the D8/D9 glass on the master side.
# Arena 2026-08-13 (b-garage): 2.15→1.60 — the freed 0.55 m becomes a
# masonry pier on the garage-anchored y=8 shear line (Living stays ≥90%
# glazed: 13.93 of 15.41 m²).
b.add_window(GF, "Living North Wall", position=0, width=1.60, height=2.75,
             sill_height=0.05, name="Living Sliding Window", pane_side="inner")
# Maquette print (maquette-alignment.md D-1): asymmetric glass pair filling the
# approved 1.4 opening — 0.9 leaf hinge EAST (x5.95) + 0.5 leaf hinge WEST
# (x4.55), BOTH swinging south into the master. Wall runs (6,8)->(4.5,8), so
# door_start is the east side: large leaf = LEFT hinge at pos 0.05.
# D8/D9 are glass — thin pane like the windows. Feedback #003/#005: head at
# 2.80 (same as Win4) and edge-to-edge — the whole master north wall is
# glass; flush ends run through both corner joints (Room 2 west wall at
# x=6, W8 end cap at x=4.5). Feedback #020: INNER-flush like Win4 (was
# outer) — the 0.18m plane offset between the door glass and the window
# glass read as "a weird gap" across the W8 joint; inner/inner pairs get
# the exact pass/butt corner join, so the panes now physically touch.
b.add_door(GF, "Master North Wall", position=0, width=0.95, height=2.8,
           name="Vila Master Bedroom Terrace Door",
           operation_type=DoorOperationType.SINGLE_SWING_LEFT,
           pane_side="inner")
d_terrace_small = b.add_door(GF, "Master North Wall", position=0.95, width=0.55,
                             height=2.8,
                             name="Vila Master Bedroom Terrace Door Small",
                             pane_side="inner")
d_terrace_small.operation_type = DoorOperationType.SINGLE_SWING_RIGHT
# The fixed pane of the Room 2 slider (photo #31) — abuts D7 at 1.75,
# same 2.80 head, slot reused in place so tags stay stable
# Arena 2026-08-13 (b-garage): fixed pane 1.1→0.9 (Room 2 keeps 91% of
# its glazing); exact adjacency to D7 at position 1.75 preserved.
b.add_window(GF, "North Wall", position=1.0, width=0.9, height=2.75,
             sill_height=0.05, name="Room 2 Sliding Door", pane_side="inner")
# (position 1.0 from the extended wall start x=9.65 = absolute x7.75-8.65,
# exact adjacency to D7 at x=7.75 preserved)
# Feedback #024: the east facade under Roof East (y 2.7-12.6) carries a
# clerestory band, not a lone porthole — same 2.05-2.80 language as
# Win2/Win7. Two windows because the Room 2 partition (y=8) must land on
# wall, not glass: Win6 = hallway stretch, Win8 (appended last, after
# Win7) = Room 2 stretch, stopping 0.15 short of the north corner like
# Win5 does.
b.add_window(GF, "East Wall", position=2.7, width=5.3, height=0.75,
             sill_height=2.05, name="Hallway Window", pane_side="inner")
# Band window over the TV wall (W6 solid half) — appended last => tag Win7.
# Feedback #001: reaches the wall end (corner with W7) -> corner glazing,
# meets Win2 glass-to-glass. Feedback #019: starts at Win4's edge (2.15) so
# the band glass touches the sliding window's glass — no yellow strip.
# Arena 2026-08-13 (b-garage): the 2.35 m band becomes a 0.65 m
# FULL-HEIGHT slot hard against the NW corner (same glass area, 1.79 vs
# 1.76 m²; echoes Win3's vertical language on the west facade). The
# corner joint with Win2 keeps glass meeting glass over the 2.05-2.80
# band strip; 1.70 m of yellow masonry pier lands mid-wall on the y=8
# shear line.
b.add_window(GF, "Living North Wall", position=3.85, width=0.65, height=2.75,
             sill_height=0.05, name="Living Band Window N", pane_side="inner")
# Win8 (Room 2's east clerestory, feedback #024) REMOVED 2026-08-08 on owner
# order ("remove win8 and make it wall") — the load-takedown experiment
# showed its 3.85m band was one of the worst structural offenders (79x).

# --- Slab (full L footprint) ---
gslab = b.add_slab(
    GF,
    [(0, 0), (9.5, 0), (9.5, 12), (6.0, 12), (6.0, 8), (0, 8)],
    thickness=0.25,
    name="Ground Slab",
)
gslab.span_direction = "x"  # over the garage: x=4.5 -> x=9.5 bearing lines

# --- Outdoor: deck, pool, lawn (render/IFC only — outside the apartment) ---
b.add_slab(
    GF,
    [(0, 8), (6, 8), (6, 12), (9.5, 12), (9.5, 14), (0, 14)],
    thickness=0.15,
    name="Deck",
)
b.add_slab(GF, [(0.5, 14), (9, 14), (9, 17.5), (0.5, 17.5)], thickness=0.15, name="Pool")
# Arena 2026-08-13 (b-garage): terrace fin — extends the North Wall line
# (axis 4) westward from the Room 2 corner, under the Roof East / Roof
# West north edge. Carries the roof corner over the covered terrace AND
# anchors the northern x-direction shear line far from the stiff south
# band (E100 x + E102 x). Full storey height, bearing, on its own strip
# footing (soil under — outside the garage box).
w_fin = b.add_wall(GF, (6.0, 12), (4.5, 12), height=H, thickness=EXT,
                   name="Terrace Fin Wall", is_external=True,
                   load_bearing=True)
# Deck windscreen on the west edge (feedback #004 + maquette photo #29):
# stone-clad near the house, glass panel running to the pool. Height 1.25
# above the deck top (deck slab tops out at the storey datum since the
# slab flip, specs/storey-datum.md) — balustrade height, owner gave the
# look, not a number (decided, not asked). Appended last => tags W17/W18.
b.add_wall(GF, (0, 8), (0, 10.5), height=1.25, thickness=0.12,
           name="Deck Screen Stone", finish="stone_rubble")
b.add_wall(GF, (0, 10.5), (0, 14), height=1.25, thickness=0.12,
           name="Deck Screen Glass", finish="glass")
# Feedback #032: the screen line ended at (0,14) but the deck edge runs on
# to the pool's west corner (0.5,14) — 0.5m of unguarded drop at the NW
# corner. Solid return at the same balustrade height closes the line.
b.add_wall(GF, (0, 14), (0.5, 14), height=1.25, thickness=0.12,
           name="Deck Screen Return N", finish="stone_rubble")
b.add_slab(GF, [(4.7, 8.3), (5.9, 8.3), (5.9, 10.8), (4.7, 10.8)], thickness=0.16, name="Lawn")

# --- Roof (maquette photo: flat slab, 0.6m overhang, brown fascia, and a
# skylight aperture over the deck). Two polygons frame the hole — a C-shaped
# west part and an east strip (facade-finishes.md). ---
roof_w = b.add_roof(
    GF,
    [(-0.6, 2.7), (4.3, 2.7), (4.3, 9.2), (2.3, 9.2),
     (2.3, 11.2), (4.3, 11.2), (4.3, 12.6), (-0.6, 12.6)],
    thickness=0.45, name="Roof West", finish="roof_brown",
)
# Structural span direction (Phase B, specs/structural-plausibility.md):
# all roofs span E-W onto the x=0 / x=4.5 / x=9.5 bearing lines.
roof_w.span_direction = "x"
roof_e = b.add_roof(
    GF,
    [(4.3, 2.7), (10.1, 2.7), (10.1, 12.6), (4.3, 12.6)],
    thickness=0.45, name="Roof East", finish="roof_brown",
)
roof_e.span_direction = "x"
# The roof splits into TWO clean rectangles (owner, P-shot 2026-08-06):
# white south band + brown rest, tops flush at 3.45. The white part has NO
# overhang — flush with the wall outer faces, "wall goes up then flat".
# Arena 2026-08-13 (b-garage): south edge -0.15→-0.3 — stays flush with
# the outer face of the thickened (0.45) south band walls.
roof_s = b.add_roof(
    GF,
    [(-0.15, -0.3), (9.65, -0.3), (9.65, 2.7), (-0.15, 2.7)],
    thickness=0.45, name="Roof South White",
)
roof_s.span_direction = "x"

# --- Spiral staircase down to garage (matches the maquette) ---
b.add_staircase(
    GF,
    [(6.1, -0.75), (7.6, -0.75), (7.6, 0.75), (6.1, 0.75)],
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
    (4.5, 0), (6.1, 0), (6.1, 0.75), (7.6, 0.75), (7.6, 0),
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
        space("Garage Stair", RoomType.STAIRCASE, rect(6.1, -0.75, 7.6, 0.75)),
    ],
)

story = b.get_story(GF)
assert story is not None
story.apartments.append(apartment)

# --- Ring beams over every wide opening on a bearing wall (E062) ---
# Ring beams REMOVED deliberately (owner 2026-08-08 evening): "remove
# them, let's see how it looks without them, then we can check where and
# how we need to make Verstärkung." The FEM X-ray on the beam-less model
# shows where reinforcement actually belongs; E062 findings are waived
# with this reason (validation.json). History: the load-takedown
# experiment proved the 0.20m bands fail 6-144x unreinforced; the beam
# sizes that worked are in git history (commit dd9ee6a and earlier).

garage_story = b.get_story(GAR)
assert garage_story is not None
garage_story.spaces.append(space(
    "Garage", RoomType.UTILITY,
    [(4.5, 0.6), (9.5, 0.6), (9.5, 8), (4.5, 8)],
))

out = Path(__file__).parent / "building.json"
# Identity: construction minted fresh GUIDs for everything above. Reconcile
# against the committed file so an unchanged design is a byte-identical save
# and only genuinely NEW elements keep their new ids (specs/ifc-identity.md).
if out.is_file():
    from archicad_builder.models.reconcile import reconcile_ids
    report = reconcile_ids(b, Building.load(out))
    print(report.summary())
b.save(out)
print(f"Saved {out}")
print(f"Walls: {len(story.walls)}, doors: {len(story.doors)}, windows: {len(story.windows)}")
print(f"Apartment area: {apartment.area:.1f} m2, rooms: {apartment.room_count}")
