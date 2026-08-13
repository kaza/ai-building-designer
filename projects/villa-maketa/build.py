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

# ── Garage storey — THE ARCHITECT'S GRID (owner + architect, decoded from
#    the maquette 2026-08-13, arena j-true-grid). The box moves from
#    x4.5-9.5 to A-B: west wall ON axis A (x=2.8), east wall ON axis B
#    (x=6.58 — the Bath Divider line above lands on it exactly), north
#    wall directly UNDER axis 2 (y=8, the kamin line). One-car box,
#    3.48 m clear. South face stays INSET at y=0.6 (maquette photo #22:
#    the GF volume floats over the door plane — console look). ──
GAR = "Garage"
GH = 2.89  # clear 2.52 after 0.37 structure — exactly the W001 target
A, B, C = 2.8, 6.58, 9.5   # letter axes (constant-x), owner 2026-08-13
b.add_story(GAR, height=GH, elevation=-GH)


def gwall(name, start, end):
    # Stone rubble facade per the owner's maquette photo (facade-finishes.md)
    return b.add_wall(GAR, start, end, height=GH, thickness=EXT, name=name,
                      is_external=True, load_bearing=True,
                      finish="stone_rubble")


# The spiral-stair shaft (x6.1-7.6, unchanged — it must keep landing
# beside B) straddles the new SE corner: the south wall stops at the
# shaft, the east wall starts north of it (a wall through the shaft
# would cut the spiral). The landing opens into the garage corner.
gwall("Garage South Wall", (A, 0.6), (6.1, 0.6))
gwall("Garage East Wall", (B, 0.75), (B, 8))
gwall("Garage North Wall", (B, 8), (A, 8))
gwall("Garage West Wall", (A, 8), (A, 0))

# vehicle entrance in the garage SOUTH wall (owner-confirmed 2026-08-13):
# the moved box faces the driveway again. NOTDEFINED = sectional.
b.add_door(GAR, "Garage South Wall", position=0.45, width=2.4, height=2.1,
           name="Garage Vehicle Door",
           operation_type=DoorOperationType.NOTDEFINED)
b.add_slab(GAR, [(A, 0.6), (B, 0.6), (B, 8), (A, 8)],
           thickness=0.25, name="Garage Slab")
# spiral stair shaft aligned with the ground-floor one (E051); straddles the
# south facade — the tower is half OUTSIDE the house (maquette photo #22)
b.add_staircase(GAR, [(6.1, -0.75), (7.6, -0.75), (7.6, 0.75), (6.1, 0.75)],
                width=0.7, stair_type=StaircaseType.SPIRAL_STAIR,
                name="Garage Stair Lower")

# ── Strip footings move WITH the box (specs/foundations.md). 0.6/0.8 ×
# 0.5 m rc strips, top flush with the garage floor; sized against the
# placeholder sigma_rd=200 kPa pending the real geotech report (spec.md).
# B carries the GF slab console reaction + the Bath Divider takedown →
# 0.8 m; A carries the slab + the kamin line edge → 0.8 m.
for fname, fs, fe, fw in [
    ("Footing Garage South", (A, 0.6), (6.1, 0.6), 0.6),
    ("Footing Garage East", (B, 0.75), (B, 8), 0.8),
    ("Footing Garage North", (B, 8), (A, 8), 0.8),
    ("Footing Garage West", (A, 8), (A, 0), 0.8),
]:
    b.add_footing(GAR, fs, fe, width=fw, height=0.5, name=fname)

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
# Axis 4 (y=0): thickened 0.30 -> 0.40 (arena j-true-grid) — the moved
# garage takes the old x=4.5 bearing line away from the x-direction
# shear ledger; the south stone band gives it back (+61 kN at ~EUR 800).
w_south = b.add_wall(GF, (0, 0), (6.1, 0), height=H, thickness=0.40,
                     name="South Wall", is_external=True,
                     load_bearing=True)  # white
w_east = wall("East Wall", (9.5, 0), (9.5, 12), EXT)
w_north = wall("North Wall", (9.5, 12), (6.0, 12), EXT)
w_r2_west = wall("Room 2 West Wall", (6.0, 12), (6.0, 8), EXT)
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
# ARENA j-true-grid (2026-08-13): the garage moved to A-B — x=4.5 has
# NOTHING below any more. Living East Wall is DEMOTED to a plain room
# partition (E050/E103 would rightly fail it as bearing); the takedown
# reorganizes onto the architect's axes A (x=2.8) / B (x=6.58) / C (9.5).
w_hall_w = wall("Corridor West Wall", (8, 2.5), (8, 8))           # hallway vs baths/master
w_bath_s = wall("Bath South Wall", (4.5, 2.5), (8, 2.5))          # passage vs baths
# Guest bathroom needs >= 1.30m CLEAR between W11 and W9 (owner requirement —
# the 0.8 x 1.3 shower spans the full width): 8.0 - 1.3 - 0.06 - 0.06 = 6.58
w_bath_mid = wall("Bath Divider Wall", (6.58, 2.5), (6.58, 4.5))  # bath 1 vs guest bath
# The Bath Divider sits ON axis B — the garage east wall is directly
# below after the move. It becomes the interior bearing line (the
# architect's grid made it "natural": B was aligned to it exactly).
w_bath_mid.load_bearing = True
w_bath_mid.material = "rc"
w_master_s = wall("Master South Wall", (4.5, 4.5), (8, 4.5))      # baths vs master
w_master_s.material = "rc"   # axis 3 ("stiffens the house") — data-only:
# no garage wall below its x4.5-6.58 stretch, so it cannot be bearing
w_bath_s.material = "rc"     # axis-3 family, declared intent (hatched)
w_r2_hall = wall("Room 2 South Wall East", (8, 8), (9.5, 8))      # room2 vs hallway
w_r2_master = wall("Room 2 South Wall West", (6.0, 8), (8, 8))    # room2 vs master
# Axis 2 (y=8, the kamin line) extends across x6-9.5 as rc BEARING walls
# (rebuilt 0.12 -> 0.25): east of B they stand on their own foundations
# (grade), west of x6.58 the garage north wall is below. This is the
# mid-support Roof East loses when x=4.5 dies, plus +x shear capacity.
for _w2 in (w_r2_hall, w_r2_master):
    _w2.load_bearing = True
    _w2.material = "rc"
    _w2.thickness = 0.25
w_south_e = wall("South Wall East", (7.6, 0), (9.5, 0), EXT)  # W15, D1, white
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
d_r2_terrace = b.add_door(GF, "North Wall", position=1.75, width=1.1,
                          height=2.8, name="Vila Room 2 Terrace Door",
                          swing_inward=False, pane_side="inner")
d_r2_terrace.operation_type = DoorOperationType.SLIDING_TO_LEFT

# --- Windows ---
# ALL villa glazing sits flush with the INNER wall face (maquette photo #28,
# owner 2026-08-06): the yellow volume and roof float over recessed glass.
# Framework default is outer-flush — every window here overrides it.
# The yellow L is part concrete part glass (owner 2026-08-06): the living
# stretch of the west wall (y 4.5-8) is floor-to-ceiling glazing; the
# concrete stretches carry a roof-to-1.80 band so the wall below stays
# usable and light falls from above.
b.add_window(GF, "South Wall", position=1.5, width=1.5, height=0.75,
             sill_height=2.05, name="Kitchen Window", pane_side="inner")
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
# ARENA j-true-grid: width 2.15 -> 1.60. The architect's 2A stub (60x20,
# hidden in the kamin/stone mass) stands at x=2.8 — the wall x2.9-2.35
# returns to solid masonry so the stub has mass to hide in. Living keeps
# 90.2% of baseline glazing (>= 90% gate).
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
b.add_window(GF, "North Wall", position=0.65, width=1.1, height=2.75,
             sill_height=0.05, name="Room 2 Sliding Door", pane_side="inner")
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
b.add_window(GF, "Living North Wall", position=2.15, width=2.35, height=0.75,
             sill_height=2.05, name="Living Band Window N", pane_side="inner")
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
# Arena j-true-grid: west edge +0.30 m — compensates the new wall
# footprints (South Wall +0.10, Room 2 south walls +0.13, wing wall, A1
# post pier: ~1.6 m2) so net slab-minus-walls floor area stays positive.
b.add_slab(
    GF,
    [(-0.3, 8), (6, 8), (6, 12), (9.5, 12), (9.5, 14), (-0.3, 14)],
    thickness=0.15,
    name="Deck",
)
b.add_slab(GF, [(0.5, 14), (9, 14), (9, 17.5), (0.5, 17.5)], thickness=0.15, name="Pool")
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

# ── Arena j-true-grid (2026-08-13): the two grid members standing free ──
# A1: the architect's post at (A, 12) — the roof/canopy support at the
# all-glass deck corner. Phase C1 does not mesh columns (specs/columns.md:
# a Column would be visual-only and the deck roof would stay red), so the
# post is modeled as a 0.50x0.30 rc PIER — a wall stub the FEM meshes.
# It earns NO confinement credit beyond its own tie; the engineer designs
# the actual member (steel HEA or rc 50x30) and its anchorage.
b.add_wall(GF, (A - 0.25, 12), (A + 0.25, 12), height=H, thickness=EXT,
           name="A1 Post", is_external=True, load_bearing=True,
           material="rc")
# Wing wall on the axis-2 line west of the facade (round-1 e-wildcard /
# round-2 f-grid proved the move): the kamin/stone line runs 1.2 m past
# the west glass — +x shear capacity outside the footprint, zero floor
# loss, and a real seat for the axis-2 ring beam's west end.
b.add_wall(GF, (0, 8), (-1.2, 8), height=H, thickness=EXT,
           name="Wing Wall 2W", is_external=True, load_bearing=True,
           finish="accent", material="rc")

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
roof_s = b.add_roof(
    GF,
    [(-0.15, -0.15), (9.65, -0.15), (9.65, 2.7), (-0.15, 2.7)],
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

# --- Ring beams (E062 / arena j-true-grid 2026-08-13) ---
# History: beams REMOVED 2026-08-08 (owner: "let's see how it looks
# without them, then we can check where and how we need to make
# Verstärkung"). The beam-less FEM answered; the architect's grid puts
# them back as CONTINUOUS ring beams hidden in the 0.45 m roof-fascia
# depth. Soffits sit ON the glazing heads (z 2.80) — the f-grid lane
# proved a 5 cm masonry sliver between head and soffit carries the roof
# edge in tension and stays red.
# Axis 2 (the kamin line), wing tip to the east overhang:
b.add_beam(GF, (-1.2, 8), (9.65, 8), width=0.30, depth=0.50,
           z_top=3.30, name="Ring Beam Axis 2")
# Axis 1 (y=12, guest-room north / deck edge):
b.add_beam(GF, (0.2, 12), (9.65, 12), width=0.30, depth=0.50,
           z_top=3.30, name="Ring Beam Axis 1")
# THE architect's beam ("iron or concrete" — concrete here, a steel beam
# would not be meshed): on the A line at roof level, from the 2A stub
# north to the A1 post, carrying the roof edge over the glass zone.
b.add_beam(GF, (A, 8), (A, 12.15), width=0.30, depth=0.50,
           z_top=3.30, name="Beam Axis A")
# Axis B roof-level tie: bridges the Bath Divider (B3) up to axis 2 —
# the roof seam field x4.3-6.58 lost its x=4.5 support when the garage
# moved; B is its new east seat.
b.add_beam(GF, (B, 2.35), (B, 8.15), width=0.30, depth=0.50,
           z_top=3.30, name="Ring Beam Axis B")
# West facade: soffit at 2.80 = the band-window head.
b.add_beam(GF, (0, 2.55), (0, 8.15), width=0.30, depth=0.50,
           z_top=3.30, name="Ring Beam West Facade")

# --- Tie-column grid (confined masonry evidence, EN 1998-1 §9.5.3) ---
# The architect's axes: A/B/C = x 2.8/6.58/9.5, 1/2/3/4 = y 12/8/4.5/0.
# Ties at every bearing-wall intersection, free end, jamb of openings
# > 1.5 m2, and <= 5 m spacing — output/seismic.json
# confinement_failures must be EMPTY (earns q = 2.0 fail-closed).
# The architect's hidden stub: 60x20 at 2A, long side along A (y) —
# hosted in the kamin wall, 20 cm along the wall, 60 cm across it.
b.add_column(GF, wall="Living North Wall", along=1.7, width=0.20,
             depth=0.60, material="rc", name="Stub 2A 60x20")
GF_TIES = [
    # (host wall, along, width, name)
    ("South Wall", 0.15, 0.25, "Tie 4-west corner"),
    ("South Wall", 3.05, 0.25, "Tie 4 mid (A4 zone)"),
    ("South Wall", 5.95, 0.25, "Tie 4 stair W"),
    ("South Wall East", 0.15, 0.25, "Tie 4 stair E"),
    ("South Wall East", 0.90, 0.25, "Tie 4 entry jamb"),
    ("South Wall East", 1.85, 0.25, "Tie C4"),
    ("East Wall", 2.70, 0.25, "Tie C hall jamb S"),
    ("East Wall", 5.35, 0.25, "Tie C mid"),
    ("East Wall", 8.00, 0.25, "Tie C2"),
    ("East Wall", 11.85, 0.25, "Tie C1"),
    ("North Wall", 0.65, 0.25, "Tie 1 win jamb E"),
    ("North Wall", 1.75, 0.25, "Tie 1 door jamb"),
    ("North Wall", 2.85, 0.25, "Tie 1 win jamb W"),
    ("Room 2 West Wall", 3.85, 0.25, "Tie 2 x6"),
    ("Master North Wall", 0.95, 0.25, "Tie 2 master jamb"),
    ("Living East Wall", 7.85, 0.25, "Tie 2 old-A line"),
    ("Living North Wall", 2.05, 0.25, "Tie 2 kamin E"),
    ("West Wall", 3.35, 0.25, "Tie W mullion"),
    ("West Wall", 5.25, 0.25, "Tie 3W joint"),
    ("Room 2 South Wall East", 0.15, 0.25, "Tie 2 corridor"),
    ("Room 2 South Wall East", 1.20, 0.25, "Tie 2 room2 jamb"),
    ("Bath Divider Wall", 0.15, 0.25, "Tie B3 south"),
    ("Bath Divider Wall", 1.85, 0.25, "Tie B3 north"),
    ("Wing Wall 2W", 0.05, 0.25, "Tie 2W corner"),
    ("Wing Wall 2W", 1.05, 0.25, "Tie 2W end"),
    ("A1 Post", 0.25, 0.25, "Tie A1"),
]
for _host, _along, _w, _name in GF_TIES:
    b.add_column(GF, wall=_host, along=_along, width=_w, depth=0.25,
                 material="rc", name=_name)
GAR_TIES = [
    ("Garage West Wall", 0.15, "GTie A2 corner"),
    ("Garage West Wall", 4.00, "GTie A mid"),
    ("Garage West Wall", 7.85, "GTie A4 corner"),
    ("Garage East Wall", 0.15, "GTie B stair corner"),
    ("Garage East Wall", 3.55, "GTie B mid"),
    ("Garage East Wall", 7.10, "GTie B2 corner"),
    ("Garage South Wall", 0.45, "GTie 4 door jamb W"),
    ("Garage South Wall", 3.05, "GTie 4 door jamb E"),
]
for _host, _along, _name in GAR_TIES:
    b.add_column(GAR, wall=_host, along=_along, width=0.25, depth=0.25,
                 material="rc", name=_name)

# --- Foundation piers under off-garage tie-columns (E108) ---
# GF ties standing over the garage box lines are supported by the walls
# below; the rest of the grid gets an rc pier to the garage founding
# level with its own pad — one founding depth for the whole house, no
# differential settlement against the box. (2.45,8) lands on the wide
# A footing, so it needs no pad of its own.
TIE_PIERS = [
    ((0.15, 0), "x"), ((3.05, 0), "x"), ((5.95, 0), "x"),
    ((7.75, 0), "x"), ((8.50, 0), "x"), ((9.45, 0), "x"),
    ((9.5, 2.7), "y"), ((9.5, 5.35), "y"), ((9.5, 8.0), "y"),
    ((9.5, 11.85), "y"),
    ((8.85, 12), "x"), ((7.75, 12), "x"), ((6.65, 12), "x"),
    ((2.45, 8), None),          # on the axis-A strip footing (w 0.8)
    ((-0.05, 8), "x"), ((-1.05, 8), "x"),
    ((0, 4.65), "y"), ((0, 2.75), "y"),
    ((8.15, 8), "x"), ((9.2, 8), "x"),
    ((2.8, 12), "x"),           # under the A1 post pier
]
for _i, ((_px, _py), _axis) in enumerate(TIE_PIERS, 1):
    b.add_column(GAR, at=(_px, _py), width=0.25, depth=0.25,
                 material="rc", name=f"Foundation Pier {_i}")
    if _axis == "x":
        _fs, _fe = (_px - 0.35, _py), (_px + 0.35, _py)
    elif _axis == "y":
        _fs, _fe = (_px, _py - 0.35), (_px, _py + 0.35)
    else:
        continue
    b.add_footing(GAR, _fs, _fe, width=0.7, height=0.5,
                  name=f"Pad Pier {_i}")

garage_story = b.get_story(GAR)
assert garage_story is not None
garage_story.spaces.append(space(
    "Garage", RoomType.UTILITY,
    [(A, 0.6), (B, 0.6), (B, 8), (A, 8)],
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
