"""Space models: rooms, apartments, and spatial relationships.

IFC alignment:
- Space maps to IfcSpace — a bounded area within a building
- SpaceType maps to IfcSpaceTypeEnum (SPACE for rooms, PARKING for garage, etc.)
- Apartment is a collection of Spaces forming a dwelling unit

Spaces are defined by their boundary polygon. They don't replace walls —
walls are the physical elements, spaces are the logical/spatial overlay.
A space's boundary should align with wall centerlines or virtual elements.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator

from archicad_builder.models.geometry import Point2D, Polygon2D
from archicad_builder.models.ifc_id import generate_ifc_id


class RoomType(str, Enum):
    """Room type classification for residential buildings.

    Maps to IfcSpace.LongName or custom property sets.
    """

    LIVING = "living"
    BEDROOM = "bedroom"
    KITCHEN = "kitchen"
    BATHROOM = "bathroom"
    TOILET = "toilet"  # separate WC
    HALLWAY = "hallway"
    STORAGE = "storage"
    BALCONY = "balcony"
    CORRIDOR = "corridor"  # building-level corridor
    STAIRCASE = "staircase"
    ELEVATOR = "elevator"
    UTILITY = "utility"
    OFFICE = "office"
    NOTDEFINED = "notdefined"


# Minimum room areas by type (m²) — Austrian residential norms as baseline
MIN_ROOM_AREAS: dict[RoomType, float] = {
    RoomType.LIVING: 14.0,
    RoomType.BEDROOM: 10.0,
    RoomType.KITCHEN: 6.0,
    RoomType.BATHROOM: 4.0,
    RoomType.TOILET: 1.5,
    RoomType.HALLWAY: 3.0,
    RoomType.STORAGE: 1.0,
}


class Space(BaseModel):
    """A bounded area within a building (maps to IfcSpace).

    Represents a room, corridor, or other defined area.
    The boundary polygon should align with wall centerlines.
    """

    global_id: str = Field(default_factory=generate_ifc_id, description="IFC GlobalId")
    name: str = ""
    tag: str = Field(default="", description="Short label for drawings, e.g. 'R1'")
    description: str = ""
    room_type: RoomType = Field(
        default=RoomType.NOTDEFINED,
        description="Room function classification",
    )
    boundary: Polygon2D = Field(description="Room boundary polygon (wall centerlines)")

    @property
    def area(self) -> float:
        """Room area from boundary polygon (m²)."""
        return self.boundary.area

    @property
    def perimeter(self) -> float:
        """Room perimeter length (m)."""
        return self.boundary.perimeter


class Apartment(BaseModel):
    """A dwelling unit composed of multiple spaces/rooms.

    Not a direct IFC type — represents a logical grouping of IfcSpaces
    that form one apartment. In IFC, this could be modeled as an IfcZone
    or property set grouping.
    """

    global_id: str = Field(default_factory=generate_ifc_id, description="IFC GlobalId")
    name: str = ""
    tag: str = Field(default="", description="Short label, e.g. 'A1'")
    description: str = ""
    boundary: Polygon2D = Field(description="Apartment outer boundary polygon")
    spaces: list[Space] = Field(default_factory=list)

    @property
    def area(self) -> float:
        """Total apartment area from boundary polygon (m²)."""
        return self.boundary.area

    @property
    def room_count(self) -> int:
        """Number of rooms (excluding hallway/corridor)."""
        return sum(
            1 for s in self.spaces
            if s.room_type not in (RoomType.HALLWAY, RoomType.CORRIDOR)
        )

    def get_space_by_type(self, room_type: RoomType) -> list[Space]:
        """Get all spaces of a given type."""
        return [s for s in self.spaces if s.room_type == room_type]

    def has_bathroom(self) -> bool:
        """Check if apartment has at least one bathroom or toilet."""
        return any(
            s.room_type in (RoomType.BATHROOM, RoomType.TOILET)
            for s in self.spaces
        )

    def has_kitchen(self) -> bool:
        """Check if apartment has a kitchen."""
        return any(s.room_type == RoomType.KITCHEN for s in self.spaces)
