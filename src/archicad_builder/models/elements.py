"""Building elements: walls, slabs, doors, windows, roofs.

Element IDs use IFC-compatible GlobalIds (22-char compressed GUIDs)
so the same ID appears in our JSON model and the exported IFC file.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from archicad_builder.models.geometry import Point2D, Polygon2D
from archicad_builder.models.ifc_id import generate_ifc_id


class Wall(BaseModel):
    """A wall defined by start/end points, height, and thickness.

    Walls are the primary structural elements. Doors and windows
    reference their host wall by GlobalId.
    """

    global_id: str = Field(default_factory=generate_ifc_id, description="IFC GlobalId")
    name: str = ""
    tag: str = Field(default="", description="Short label for drawings, e.g. 'W1' (IfcElement.Tag)")
    description: str = ""
    start: Point2D
    end: Point2D
    height: float = Field(gt=0, description="Wall height in meters")
    thickness: float = Field(gt=0, description="Wall thickness in meters")
    load_bearing: bool = Field(default=False, description="Pset_WallCommon.LoadBearing")
    is_external: bool = Field(default=False, description="Pset_WallCommon.IsExternal")
    finish: str | None = Field(
        default=None,
        description="Renderer finish tag (specs/facade-finishes.md); None = default",
    )

    @property
    def length(self) -> float:
        """Wall length (centerline)."""
        return self.start.distance_to(self.end)

    @model_validator(mode="after")
    def start_and_end_differ(self) -> Wall:
        if self.start == self.end:
            raise ValueError("Wall start and end points must be different")
        return self


class SlabType(str, Enum):
    """Slab predefined type, aligned with IFC IfcSlabTypeEnum.

    FLOOR: standard floor slab
    ROOF: roof slab (topmost)
    BASESLAB: foundation/ground slab (bottommost)
    LANDING: staircase landing slab
    NOTDEFINED: unspecified
    """

    FLOOR = "FLOOR"
    ROOF = "ROOF"
    BASESLAB = "BASESLAB"
    LANDING = "LANDING"
    NOTDEFINED = "NOTDEFINED"


class Slab(BaseModel):
    """A horizontal slab (floor or ceiling) defined by a polygon outline."""

    global_id: str = Field(default_factory=generate_ifc_id, description="IFC GlobalId")
    name: str = ""
    description: str = ""
    outline: Polygon2D
    thickness: float = Field(gt=0, description="Slab thickness in meters")
    is_floor: bool = Field(default=True, description="True=floor slab, False=ceiling")
    slab_type: SlabType = Field(
        default=SlabType.FLOOR,
        description="IFC IfcSlabTypeEnum — slab function",
    )
    finish: str | None = Field(
        default=None,
        description="Renderer finish tag (specs/facade-finishes.md); None = default",
    )
    span_direction: Literal["x", "y"] | None = Field(
        default=None,
        description="Structural one-way span axis (specs/structural-plausibility.md"
                    " Phase B); None = structural analysis reports 'unresolved'",
    )

    @property
    def area(self) -> float:
        """Slab area from outline polygon."""
        return self.outline.area


class DoorOperationType(str, Enum):
    """Door operation type, aligned with IFC IfcDoorStyleOperationEnum.

    Subset of the full IFC enum covering common residential door types.
    Left/right is relative to the wall's normal direction (looking from
    the wall's positive normal side toward the wall).
    """

    SINGLE_SWING_LEFT = "SINGLE_SWING_LEFT"
    SINGLE_SWING_RIGHT = "SINGLE_SWING_RIGHT"
    DOUBLE_DOOR_SINGLE_SWING = "DOUBLE_DOOR_SINGLE_SWING"
    SLIDING_TO_LEFT = "SLIDING_TO_LEFT"
    SLIDING_TO_RIGHT = "SLIDING_TO_RIGHT"
    NOTDEFINED = "NOTDEFINED"


class Door(BaseModel):
    """A door hosted in a wall.

    Position is measured as offset along the wall from the start point.

    Operation type follows IFC IfcDoorStyleOperationEnum:
    - SINGLE_SWING_LEFT: hinges on the left (viewed from normal side)
    - SINGLE_SWING_RIGHT: hinges on the right (viewed from normal side)
    - swing_inward: True = swings toward wall normal side (into room),
      False = swings away from normal side (out of room).
    """

    global_id: str = Field(default_factory=generate_ifc_id, description="IFC GlobalId")
    name: str = ""
    tag: str = Field(default="", description="Short label for drawings, e.g. 'D1' (IfcElement.Tag)")
    description: str = ""
    wall_id: str = Field(description="GlobalId of the host wall")
    position: float = Field(ge=0, description="Offset from wall start point in meters")
    width: float = Field(gt=0, description="Door width in meters")
    height: float = Field(gt=0, description="Door height in meters")
    operation_type: DoorOperationType = Field(
        default=DoorOperationType.SINGLE_SWING_LEFT,
        description="IFC IfcDoorStyleOperationEnum — hinge side and mechanism",
    )
    swing_inward: bool = Field(
        default=True,
        description="True = swings toward wall normal side, False = swings away",
    )
    pane_side: Literal["outer", "inner"] | None = Field(
        default=None,
        description="None = full-thickness leaf (legacy); 'outer'/'inner' = "
        "thin pane flush with that wall face — for glass doors "
        "(specs/window-glazing-placement.md)",
    )

    @field_validator("width")
    @classmethod
    def reasonable_width(cls, v: float) -> float:
        if v > 5.0:
            raise ValueError(f"Door width {v}m seems unreasonable (max 5m)")
        return v

    @field_validator("height")
    @classmethod
    def reasonable_height(cls, v: float) -> float:
        if v > 4.0:
            raise ValueError(f"Door height {v}m seems unreasonable (max 4m)")
        return v


class Window(BaseModel):
    """A window hosted in a wall.

    Position is offset along the wall from start point.
    Sill height is the distance from story floor to bottom of window.
    """

    global_id: str = Field(default_factory=generate_ifc_id, description="IFC GlobalId")
    name: str = ""
    tag: str = Field(default="", description="Short label for drawings, e.g. 'Win1' (IfcElement.Tag)")
    description: str = ""
    wall_id: str = Field(description="GlobalId of the host wall")
    position: float = Field(ge=0, description="Offset from wall start point in meters")
    width: float = Field(gt=0, description="Window width in meters")
    height: float = Field(gt=0, description="Window height in meters")
    sill_height: float = Field(
        default=0.9, ge=0, description="Height from floor to window bottom in meters"
    )
    pane_side: Literal["outer", "inner"] = Field(
        default="outer",
        description="Which wall face the thin glazing pane sits flush with "
        "(specs/window-glazing-placement.md)",
    )

    @field_validator("width")
    @classmethod
    def reasonable_width(cls, v: float) -> float:
        if v > 6.0:
            raise ValueError(f"Window width {v}m seems unreasonable (max 6m)")
        return v


class Beam(BaseModel):
    """A horizontal structural member (ring beam / lintel segment).

    Centerline start→end, rectangular section width × depth. z_top is
    meters above the storey datum; the beam occupies [z_top − depth,
    z_top] and MAY rise above the storey height (upstand hidden in the
    roof-edge zone — how band-window facades carry a roof).
    Spec: specs/structural-plausibility.md.
    """

    global_id: str = Field(default_factory=generate_ifc_id, description="IFC GlobalId")
    name: str = ""
    description: str = ""
    start: Point2D
    end: Point2D
    width: float = Field(gt=0, description="Horizontal width ⊥ to the axis (m)")
    depth: float = Field(gt=0, description="Vertical depth (m)")
    z_top: float = Field(description="Top of beam above storey datum (m)")
    material: Literal["rc", "steel", "timber"] = "rc"

    @model_validator(mode="after")
    def _non_degenerate(self) -> Beam:
        if (abs(self.end.x - self.start.x) < 1e-6
                and abs(self.end.y - self.start.y) < 1e-6):
            raise ValueError("beam start and end coincide (zero length)")
        return self


class StripFooting(BaseModel):
    """A strip footing under a bearing wall (specs/foundations.md).

    Centerline start→end like Wall; rectangular section width (horizontal,
    ⊥ axis) × height (vertical), top at the storey elevation, extending
    down. Lowest storey only (validator-enforced, not schema). rc.
    """

    global_id: str = Field(default_factory=generate_ifc_id, description="IFC GlobalId")
    name: str = ""
    description: str = ""
    start: Point2D
    end: Point2D
    width: float = Field(gt=0, description="Horizontal width ⊥ to the axis (m)")
    height: float = Field(gt=0, description="Vertical height (m), extends below storey elevation")

    @model_validator(mode="after")
    def _non_degenerate(self) -> StripFooting:
        if (abs(self.end.x - self.start.x) < 1e-6
                and abs(self.end.y - self.start.y) < 1e-6):
            raise ValueError("footing start and end coincide (zero length)")
        return self


class RoofType(str, Enum):
    """Supported roof types."""

    FLAT = "flat"
    GABLE = "gable"
    HIP = "hip"
    SHED = "shed"


class Roof(BaseModel):
    """A roof element."""

    global_id: str = Field(default_factory=generate_ifc_id, description="IFC GlobalId")
    name: str = ""
    description: str = ""
    outline: Polygon2D
    roof_type: RoofType = RoofType.FLAT
    span_direction: Literal["x", "y"] | None = Field(
        default=None,
        description="Structural one-way span axis (Phase B); None = unresolved",
    )
    pitch: float = Field(default=0.0, ge=0, le=89, description="Roof pitch in degrees")
    thickness: float = Field(default=0.3, gt=0, description="Roof thickness in meters")
    finish: str | None = Field(
        default=None,
        description="Renderer finish tag (specs/facade-finishes.md); None = default",
    )

    @model_validator(mode="after")
    def flat_roof_zero_pitch(self) -> Roof:
        if self.roof_type == RoofType.FLAT and self.pitch != 0:
            raise ValueError("Flat roof must have pitch=0")
        if self.roof_type != RoofType.FLAT and self.pitch == 0:
            raise ValueError(f"{self.roof_type.value} roof must have pitch > 0")
        return self


class StaircaseType(str, Enum):
    """Staircase shape type, aligned with IFC IfcStairTypeEnum (IFC2x3: ShapeType).

    Subset of the IFC enum covering common residential types.
    """

    STRAIGHT_RUN_STAIR = "STRAIGHT_RUN_STAIR"
    TWO_QUARTER_TURN_STAIR = "TWO_QUARTER_TURN_STAIR"
    QUARTER_TURN_STAIR = "QUARTER_TURN_STAIR"
    HALF_TURN_STAIR = "HALF_TURN_STAIR"
    SPIRAL_STAIR = "SPIRAL_STAIR"
    NOTDEFINED = "NOTDEFINED"


class Staircase(BaseModel):
    """A staircase element, IFC-aligned (maps to IfcStair).

    Represented by its footprint outline on the floor plan.
    Contains flight parameters for code compliance validation.
    In a multi-storey building, a staircase appears on each floor
    at the same XY position (vertical alignment enforced by validators).
    """

    global_id: str = Field(default_factory=generate_ifc_id, description="IFC GlobalId")
    name: str = ""
    tag: str = Field(default="", description="Short label for drawings, e.g. 'ST1'")
    description: str = ""
    outline: Polygon2D
    stair_type: StaircaseType = Field(
        default=StaircaseType.STRAIGHT_RUN_STAIR,
        description="IFC IfcStairTypeEnum — staircase shape",
    )
    width: float = Field(gt=0, default=1.2, description="Clear width of stair flight in meters")
    riser_height: float = Field(
        default=0.175, gt=0, le=0.21,
        description="Height of each riser in meters (Austrian code: max 0.20m residential)",
    )
    tread_length: float = Field(
        default=0.28, gt=0, ge=0.23,
        description="Depth of each tread in meters (Austrian code: min 0.23m)",
    )

    @property
    def area(self) -> float:
        """Staircase footprint area."""
        return self.outline.area


class VirtualElement(BaseModel):
    """An imaginary boundary between spaces — no physical properties.

    Maps to IfcVirtualElement in IFC. Used to separate rooms in
    open-plan areas (e.g., kitchen-living boundary) without a real wall.
    Same geometry interface as Wall (start/end) but no thickness, material,
    or structural properties.
    """

    global_id: str = Field(default_factory=generate_ifc_id, description="IFC GlobalId")
    name: str = ""
    tag: str = Field(default="", description="Short label for drawings, e.g. 'V1' (IfcElement.Tag)")
    description: str = ""
    start: Point2D
    end: Point2D

    @property
    def length(self) -> float:
        """Boundary length."""
        return self.start.distance_to(self.end)

    @model_validator(mode="after")
    def start_and_end_differ(self) -> VirtualElement:
        if self.start == self.end:
            raise ValueError("VirtualElement start and end points must be different")
        return self
