"""IFC export via ifcopenshell.

Converts Pydantic building models to IFC 2x3 format for ArchiCAD import.
Focuses on correct geometry and proper IFC hierarchy.
"""

from __future__ import annotations

import math
import time
import uuid
from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid
import numpy as np

from archicad_builder.models.building import Building, Story
from archicad_builder.models.elements import Door, Slab, SlabType, Staircase, Wall, Window, Roof, RoofType
from archicad_builder.models.spaces import Space
from archicad_builder.models.geometry import Point2D
from archicad_builder.models.ifc_id import generate_ifc_id


def _new_guid() -> str:
    """Generate a new IFC GlobalId for IFC-only entities (relationships, openings)."""
    return generate_ifc_id()


def _wall_direction(wall: Wall) -> tuple[float, float]:
    """Unit direction vector of a wall."""
    dx = wall.end.x - wall.start.x
    dy = wall.end.y - wall.start.y
    length = wall.length
    return (dx / length, dy / length)


def _wall_normal(wall: Wall) -> tuple[float, float]:
    """Left-hand normal of wall direction (for thickness offset)."""
    dx, dy = _wall_direction(wall)
    return (-dy, dx)


class IFCExporter:
    """Export a Building model to IFC file."""

    def __init__(self, building: Building):
        self.building = building
        self.file = ifcopenshell.file(schema="IFC2X3")
        self._setup_header()
        self._context: ifcopenshell.entity_instance | None = None
        self._body_context: ifcopenshell.entity_instance | None = None

    def _setup_header(self) -> None:
        """Set IFC file header metadata."""
        header = self.file.wrapped_data.header()
        file_name = header.file_name_py()
        file_name.name = f"{self.building.name}.ifc"
        file_name.author = ("ArchiCAD Builder",)
        file_name.organization = ("",)

    def export(self, output_path: str | Path) -> Path:
        """Export the building to an IFC file. Returns the output path."""
        output_path = Path(output_path)

        # Create geometric contexts
        self._create_contexts()

        # IFC hierarchy: Project → Site → Building → Stories
        ifc_project = self._create_project()
        ifc_site = self._create_site(ifc_project)
        ifc_building = self._create_building(ifc_site)

        for story in self.building.stories:
            self._export_story(story, ifc_building)

        self.file.write(str(output_path))
        return output_path

    def _create_contexts(self) -> None:
        """Create geometric representation contexts."""
        # 3D context
        self._context = self.file.createIfcGeometricRepresentationContext(
            ContextIdentifier="3D",
            ContextType="Model",
            CoordinateSpaceDimension=3,
            Precision=1e-5,
            WorldCoordinateSystem=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            TrueNorth=self.file.createIfcDirection((0.0, 1.0)),
        )

        # Body sub-context for geometry
        self._body_context = self.file.createIfcGeometricRepresentationSubContext(
            ContextIdentifier="Body",
            ContextType="Model",
            ParentContext=self._context,
            TargetView="MODEL_VIEW",
        )

    def _create_project(self) -> ifcopenshell.entity_instance:
        """Create IfcProject with units."""
        # Length unit: meters
        length_unit = self.file.createIfcSIUnit(
            UnitType="LENGTHUNIT",
            Name="METRE",
        )
        area_unit = self.file.createIfcSIUnit(
            UnitType="AREAUNIT",
            Name="SQUARE_METRE",
        )
        volume_unit = self.file.createIfcSIUnit(
            UnitType="VOLUMEUNIT",
            Name="CUBIC_METRE",
        )
        # Angle unit: radians
        angle_unit = self.file.createIfcSIUnit(
            UnitType="PLANEANGLEUNIT",
            Name="RADIAN",
        )
        unit_assignment = self.file.createIfcUnitAssignment(
            Units=[length_unit, area_unit, volume_unit, angle_unit],
        )

        project = self.file.createIfcProject(
            GlobalId=self.building.global_id,
            Name=self.building.name,
            UnitsInContext=unit_assignment,
            RepresentationContexts=[self._context],
        )
        return project

    def _create_site(
        self, project: ifcopenshell.entity_instance
    ) -> ifcopenshell.entity_instance:
        """Create IfcSite and attach to project."""
        site = self.file.createIfcSite(
            GlobalId=_new_guid(),
            Name="Default Site",
            CompositionType="ELEMENT",
        )
        self.file.createIfcRelAggregates(
            GlobalId=_new_guid(),
            RelatingObject=project,
            RelatedObjects=[site],
        )
        return site

    def _create_building(
        self, site: ifcopenshell.entity_instance
    ) -> ifcopenshell.entity_instance:
        """Create IfcBuilding and attach to site."""
        ifc_building = self.file.createIfcBuilding(
            GlobalId=_new_guid(),
            Name=self.building.name,
            CompositionType="ELEMENT",
        )
        self.file.createIfcRelAggregates(
            GlobalId=_new_guid(),
            RelatingObject=site,
            RelatedObjects=[ifc_building],
        )
        return ifc_building

    def _export_story(
        self,
        story: Story,
        ifc_building: ifcopenshell.entity_instance,
    ) -> None:
        """Export a single story with all its elements."""
        ifc_storey = self.file.createIfcBuildingStorey(
            GlobalId=story.global_id,
            Name=story.name,
            CompositionType="ELEMENT",
            Elevation=story.elevation,
        )
        self.file.createIfcRelAggregates(
            GlobalId=_new_guid(),
            RelatingObject=ifc_building,
            RelatedObjects=[ifc_storey],
        )

        products: list[ifcopenshell.entity_instance] = []

        # Export walls
        wall_map: dict[str, ifcopenshell.entity_instance] = {}
        for wall in story.walls:
            ifc_wall = self._create_wall(wall, story.elevation)
            wall_map[wall.global_id] = ifc_wall
            products.append(ifc_wall)

        # Export virtual elements (IfcVirtualElement — room boundaries)
        for ve in story.virtual_elements:
            ifc_ve = self._create_virtual_element(ve, story.elevation)
            products.append(ifc_ve)

        # Export slabs
        for slab in story.slabs:
            ifc_slab = self._create_slab(slab, story.elevation)
            products.append(ifc_slab)

        # Export staircases
        for staircase in story.staircases:
            ifc_stair = self._create_staircase(staircase, story.elevation)
            products.append(ifc_stair)

        # Export roofs
        for roof in story.roofs:
            ifc_roof = self._create_roof(roof, story.elevation + story.height)
            products.append(ifc_roof)

        # Export doors (with wall openings)
        # Note: IfcOpeningElements are NOT added to spatial containment —
        # they're linked to their host wall via IfcRelVoidsElement only.
        for door in story.doors:
            wall = story.get_wall(door.wall_id)
            if wall:
                ifc_door = self._create_door(door, wall, story.elevation)
                ifc_wall_host = wall_map.get(door.wall_id)
                if ifc_wall_host:
                    opening = self._create_opening(door, wall, story.elevation, is_door=True)
                    self.file.createIfcRelVoidsElement(
                        GlobalId=_new_guid(),
                        RelatingBuildingElement=ifc_wall_host,
                        RelatedOpeningElement=opening,
                    )
                    self.file.createIfcRelFillsElement(
                        GlobalId=_new_guid(),
                        RelatingOpeningElement=opening,
                        RelatedBuildingElement=ifc_door,
                    )
                products.append(ifc_door)

        # Export windows (with wall openings)
        for window in story.windows:
            wall = story.get_wall(window.wall_id)
            if wall:
                ifc_window = self._create_window(window, wall, story.elevation)
                ifc_wall_host = wall_map.get(window.wall_id)
                if ifc_wall_host:
                    opening = self._create_opening_for_window(
                        window, wall, story.elevation
                    )
                    self.file.createIfcRelVoidsElement(
                        GlobalId=_new_guid(),
                        RelatingBuildingElement=ifc_wall_host,
                        RelatedOpeningElement=opening,
                    )
                    self.file.createIfcRelFillsElement(
                        GlobalId=_new_guid(),
                        RelatingOpeningElement=opening,
                        RelatedBuildingElement=ifc_window,
                    )
                products.append(ifc_window)

        # Contain all products in the storey
        if products:
            self.file.createIfcRelContainedInSpatialStructure(
                GlobalId=_new_guid(),
                RelatingStructure=ifc_storey,
                RelatedElements=products,
            )

        # Export spaces (IfcSpace) — these aggregate under the storey
        all_spaces = list(story.spaces)
        for apt in story.apartments:
            all_spaces.extend(apt.spaces)
        if all_spaces:
            ifc_spaces = []
            for space in all_spaces:
                ifc_space = self._create_space(space, story.elevation)
                ifc_spaces.append(ifc_space)
            self.file.createIfcRelAggregates(
                GlobalId=_new_guid(),
                RelatingObject=ifc_storey,
                RelatedObjects=ifc_spaces,
            )

    def _create_wall(
        self, wall: Wall, elevation: float
    ) -> ifcopenshell.entity_instance:
        """Create an IfcWallStandardCase with extruded geometry."""
        dx, dy = _wall_direction(wall)
        nx, ny = _wall_normal(wall)

        # Wall placement at start point, offset by half thickness along normal
        ox = wall.start.x - nx * wall.thickness / 2
        oy = wall.start.y - ny * wall.thickness / 2

        placement = self._create_local_placement(
            origin=(ox, oy, elevation),
            z_dir=(0.0, 0.0, 1.0),
            x_dir=(dx, dy, 0.0),
        )

        # Profile: rectangle (length x thickness)
        profile = self.file.createIfcRectangleProfileDef(
            ProfileType="AREA",
            XDim=wall.length,
            YDim=wall.thickness,
            Position=self.file.createIfcAxis2Placement2D(
                Location=self.file.createIfcCartesianPoint(
                    (wall.length / 2, wall.thickness / 2)
                ),
            ),
        )

        # Extrude upward
        solid = self.file.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=self.file.createIfcDirection((0.0, 0.0, 1.0)),
            Depth=wall.height,
        )

        shape = self.file.createIfcShapeRepresentation(
            ContextOfItems=self._body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

        product_shape = self.file.createIfcProductDefinitionShape(
            Representations=[shape],
        )

        ifc_wall = self.file.createIfcWallStandardCase(
            GlobalId=wall.global_id,
            Name=wall.name or "Wall",
            Description=wall.description or None,
            ObjectPlacement=placement,
            Representation=product_shape,
        )

        # Pset_WallCommon — IFC standard property set
        props = [
            self.file.createIfcPropertySingleValue(
                Name="LoadBearing",
                NominalValue=self.file.create_entity("IfcBoolean", wall.load_bearing),
            ),
            self.file.createIfcPropertySingleValue(
                Name="IsExternal",
                NominalValue=self.file.create_entity("IfcBoolean", wall.is_external),
            ),
        ]
        pset = self.file.createIfcPropertySet(
            GlobalId=_new_guid(),
            Name="Pset_WallCommon",
            HasProperties=props,
        )
        self.file.createIfcRelDefinesByProperties(
            GlobalId=_new_guid(),
            RelatedObjects=[ifc_wall],
            RelatingPropertyDefinition=pset,
        )

        return ifc_wall

    def _create_virtual_element(
        self, ve: "VirtualElement", elevation: float
    ) -> ifcopenshell.entity_instance:
        """Create an IfcVirtualElement — a zero-thickness boundary line."""
        from archicad_builder.models.elements import VirtualElement as VE

        dx = ve.end.x - ve.start.x
        dy = ve.end.y - ve.start.y
        length = ve.length

        placement = self._create_local_placement(
            origin=(ve.start.x, ve.start.y, elevation),
            z_dir=(0.0, 0.0, 1.0),
            x_dir=(dx / length, dy / length, 0.0),
        )

        ifc_ve = self.file.createIfcVirtualElement(
            GlobalId=ve.global_id,
            Name=ve.name or "VirtualElement",
            Description=ve.description or None,
            ObjectPlacement=placement,
        )
        return ifc_ve

    def _create_slab(
        self, slab: Slab, elevation: float
    ) -> ifcopenshell.entity_instance:
        """Create an IfcSlab with extruded polygon geometry."""
        vertices = slab.outline.vertices

        # Create polyline profile from polygon vertices
        ifc_points = [
            self.file.createIfcCartesianPoint((v.x, v.y)) for v in vertices
        ]
        # Close the loop
        ifc_points.append(ifc_points[0])

        polyline = self.file.createIfcPolyline(Points=ifc_points)
        profile = self.file.createIfcArbitraryClosedProfileDef(
            ProfileType="AREA",
            OuterCurve=polyline,
        )

        # Slab z position: floor slabs at elevation, ceiling at elevation - thickness
        z = elevation if slab.is_floor else elevation - slab.thickness

        placement = self._create_local_placement(
            origin=(0.0, 0.0, z),
        )

        solid = self.file.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=self.file.createIfcDirection((0.0, 0.0, 1.0)),
            Depth=slab.thickness,
        )

        shape = self.file.createIfcShapeRepresentation(
            ContextOfItems=self._body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

        product_shape = self.file.createIfcProductDefinitionShape(
            Representations=[shape],
        )

        ifc_slab = self.file.createIfcSlab(
            GlobalId=slab.global_id,
            Name=slab.name or "Slab",
            ObjectPlacement=placement,
            Representation=product_shape,
            PredefinedType=slab.slab_type.value,
        )
        return ifc_slab

    def _create_roof(
        self, roof: Roof, elevation: float
    ) -> ifcopenshell.entity_instance:
        """Create an IfcSlab with ROOF type (flat roof as slab)."""
        vertices = roof.outline.vertices
        ifc_points = [
            self.file.createIfcCartesianPoint((v.x, v.y)) for v in vertices
        ]
        ifc_points.append(ifc_points[0])

        polyline = self.file.createIfcPolyline(Points=ifc_points)
        profile = self.file.createIfcArbitraryClosedProfileDef(
            ProfileType="AREA",
            OuterCurve=polyline,
        )

        placement = self._create_local_placement(
            origin=(0.0, 0.0, elevation),
        )

        solid = self.file.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=self.file.createIfcDirection((0.0, 0.0, 1.0)),
            Depth=roof.thickness,
        )

        shape = self.file.createIfcShapeRepresentation(
            ContextOfItems=self._body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

        product_shape = self.file.createIfcProductDefinitionShape(
            Representations=[shape],
        )

        ifc_roof = self.file.createIfcSlab(
            GlobalId=roof.global_id,
            Name=roof.name or "Roof",
            ObjectPlacement=placement,
            Representation=product_shape,
            PredefinedType="ROOF",
        )
        return ifc_roof

    def _create_staircase(
        self, staircase: Staircase, elevation: float
    ) -> ifcopenshell.entity_instance:
        """Create an IfcStair with extruded polygon geometry.

        In IFC 2x3, IfcStair uses ShapeType attribute for the staircase type.
        The geometry is a simple extrusion of the footprint outline — detailed
        flights/landings can be added later as IfcStairFlight components.
        """
        vertices = staircase.outline.vertices

        ifc_points = [
            self.file.createIfcCartesianPoint((v.x, v.y)) for v in vertices
        ]
        ifc_points.append(ifc_points[0])

        polyline = self.file.createIfcPolyline(Points=ifc_points)
        profile = self.file.createIfcArbitraryClosedProfileDef(
            ProfileType="AREA",
            OuterCurve=polyline,
        )

        placement = self._create_local_placement(
            origin=(0.0, 0.0, elevation),
        )

        # Extrude to a reasonable height (story height approximation)
        # Using width as a proxy for stair height per flight
        stair_height = staircase.riser_height * 17  # ~17 risers per flight typical

        solid = self.file.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=self.file.createIfcDirection((0.0, 0.0, 1.0)),
            Depth=stair_height,
        )

        shape = self.file.createIfcShapeRepresentation(
            ContextOfItems=self._body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

        product_shape = self.file.createIfcProductDefinitionShape(
            Representations=[shape],
        )

        ifc_stair = self.file.createIfcStair(
            GlobalId=staircase.global_id,
            Name=staircase.name or "Staircase",
            ObjectPlacement=placement,
            Representation=product_shape,
            ShapeType=staircase.stair_type.value,
        )
        return ifc_stair

    def _create_space(
        self, space: Space, elevation: float
    ) -> ifcopenshell.entity_instance:
        """Create an IfcSpace with extruded polygon geometry.

        IfcSpace represents a bounded area within the building — rooms,
        corridors, etc. In IFC 2x3, uses CompositionType and InternalOrExternal.
        """
        vertices = space.boundary.vertices

        ifc_points = [
            self.file.createIfcCartesianPoint((v.x, v.y)) for v in vertices
        ]
        ifc_points.append(ifc_points[0])

        polyline = self.file.createIfcPolyline(Points=ifc_points)
        profile = self.file.createIfcArbitraryClosedProfileDef(
            ProfileType="AREA",
            OuterCurve=polyline,
        )

        placement = self._create_local_placement(
            origin=(0.0, 0.0, elevation),
        )

        # Extrude to standard room height (2.7m typical)
        room_height = 2.7

        solid = self.file.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=self.file.createIfcDirection((0.0, 0.0, 1.0)),
            Depth=room_height,
        )

        shape = self.file.createIfcShapeRepresentation(
            ContextOfItems=self._body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

        product_shape = self.file.createIfcProductDefinitionShape(
            Representations=[shape],
        )

        ifc_space = self.file.createIfcSpace(
            GlobalId=space.global_id,
            Name=space.name or "Space",
            Description=space.description or None,
            ObjectPlacement=placement,
            Representation=product_shape,
            CompositionType="ELEMENT",
            InteriorOrExteriorSpace="INTERNAL",
        )

        # Add room type as property
        if space.room_type.value != "notdefined":
            props = [
                self.file.createIfcPropertySingleValue(
                    Name="RoomType",
                    NominalValue=self.file.create_entity(
                        "IfcLabel", space.room_type.value
                    ),
                ),
            ]
            pset = self.file.createIfcPropertySet(
                GlobalId=_new_guid(),
                Name="Pset_SpaceCommon",
                HasProperties=props,
            )
            self.file.createIfcRelDefinesByProperties(
                GlobalId=_new_guid(),
                RelatedObjects=[ifc_space],
                RelatingPropertyDefinition=pset,
            )

        return ifc_space

    def _create_door(
        self, door: Door, wall: Wall, elevation: float
    ) -> ifcopenshell.entity_instance:
        """Create an IfcDoor with geometry placed in the host wall."""
        dx, dy = _wall_direction(wall)
        nx, ny = _wall_normal(wall)

        # Door origin: wall start + offset along wall direction
        ox = wall.start.x + dx * door.position - nx * wall.thickness / 2
        oy = wall.start.y + dy * door.position - ny * wall.thickness / 2

        placement = self._create_local_placement(
            origin=(ox, oy, elevation),
            z_dir=(0.0, 0.0, 1.0),
            x_dir=(dx, dy, 0.0),
        )

        # Door geometry: simple box
        profile = self.file.createIfcRectangleProfileDef(
            ProfileType="AREA",
            XDim=door.width,
            YDim=wall.thickness,
            Position=self.file.createIfcAxis2Placement2D(
                Location=self.file.createIfcCartesianPoint(
                    (door.width / 2, wall.thickness / 2)
                ),
            ),
        )

        solid = self.file.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=self.file.createIfcDirection((0.0, 0.0, 1.0)),
            Depth=door.height,
        )

        shape = self.file.createIfcShapeRepresentation(
            ContextOfItems=self._body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

        product_shape = self.file.createIfcProductDefinitionShape(
            Representations=[shape],
        )

        ifc_door = self.file.createIfcDoor(
            GlobalId=door.global_id,
            Name=door.name or "Door",
            ObjectPlacement=placement,
            Representation=product_shape,
            OverallHeight=door.height,
            OverallWidth=door.width,
        )
        return ifc_door

    def _create_window(
        self, window: Window, wall: Wall, elevation: float
    ) -> ifcopenshell.entity_instance:
        """Create an IfcWindow with geometry placed in the host wall."""
        dx, dy = _wall_direction(wall)
        nx, ny = _wall_normal(wall)

        # Window origin: wall start + offset, elevated by sill height
        ox = wall.start.x + dx * window.position - nx * wall.thickness / 2
        oy = wall.start.y + dy * window.position - ny * wall.thickness / 2

        placement = self._create_local_placement(
            origin=(ox, oy, elevation + window.sill_height),
            z_dir=(0.0, 0.0, 1.0),
            x_dir=(dx, dy, 0.0),
        )

        profile = self.file.createIfcRectangleProfileDef(
            ProfileType="AREA",
            XDim=window.width,
            YDim=wall.thickness,
            Position=self.file.createIfcAxis2Placement2D(
                Location=self.file.createIfcCartesianPoint(
                    (window.width / 2, wall.thickness / 2)
                ),
            ),
        )

        solid = self.file.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=self.file.createIfcDirection((0.0, 0.0, 1.0)),
            Depth=window.height,
        )

        shape = self.file.createIfcShapeRepresentation(
            ContextOfItems=self._body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

        product_shape = self.file.createIfcProductDefinitionShape(
            Representations=[shape],
        )

        ifc_window = self.file.createIfcWindow(
            GlobalId=window.global_id,
            Name=window.name or "Window",
            ObjectPlacement=placement,
            Representation=product_shape,
            OverallHeight=window.height,
            OverallWidth=window.width,
        )
        return ifc_window

    def _create_opening(
        self,
        door: Door,
        wall: Wall,
        elevation: float,
        is_door: bool = True,
    ) -> ifcopenshell.entity_instance:
        """Create an IfcOpeningElement for a door in a wall."""
        dx, dy = _wall_direction(wall)
        nx, ny = _wall_normal(wall)

        ox = wall.start.x + dx * door.position - nx * wall.thickness / 2
        oy = wall.start.y + dy * door.position - ny * wall.thickness / 2

        placement = self._create_local_placement(
            origin=(ox, oy, elevation),
            z_dir=(0.0, 0.0, 1.0),
            x_dir=(dx, dy, 0.0),
        )

        # Opening is slightly larger than the door for clean boolean
        profile = self.file.createIfcRectangleProfileDef(
            ProfileType="AREA",
            XDim=door.width,
            YDim=wall.thickness + 0.01,  # slightly thicker for clean cut
            Position=self.file.createIfcAxis2Placement2D(
                Location=self.file.createIfcCartesianPoint(
                    (door.width / 2, (wall.thickness + 0.01) / 2)
                ),
            ),
        )

        solid = self.file.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=self.file.createIfcDirection((0.0, 0.0, 1.0)),
            Depth=door.height,
        )

        shape = self.file.createIfcShapeRepresentation(
            ContextOfItems=self._body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

        product_shape = self.file.createIfcProductDefinitionShape(
            Representations=[shape],
        )

        opening = self.file.createIfcOpeningElement(
            GlobalId=_new_guid(),
            Name="Door Opening" if is_door else "Window Opening",
            ObjectPlacement=placement,
            Representation=product_shape,
        )
        return opening

    def _create_opening_for_window(
        self,
        window: Window,
        wall: Wall,
        elevation: float,
    ) -> ifcopenshell.entity_instance:
        """Create an IfcOpeningElement for a window in a wall."""
        dx, dy = _wall_direction(wall)
        nx, ny = _wall_normal(wall)

        ox = wall.start.x + dx * window.position - nx * wall.thickness / 2
        oy = wall.start.y + dy * window.position - ny * wall.thickness / 2

        placement = self._create_local_placement(
            origin=(ox, oy, elevation + window.sill_height),
            z_dir=(0.0, 0.0, 1.0),
            x_dir=(dx, dy, 0.0),
        )

        profile = self.file.createIfcRectangleProfileDef(
            ProfileType="AREA",
            XDim=window.width,
            YDim=wall.thickness + 0.01,
            Position=self.file.createIfcAxis2Placement2D(
                Location=self.file.createIfcCartesianPoint(
                    (window.width / 2, (wall.thickness + 0.01) / 2)
                ),
            ),
        )

        solid = self.file.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=self.file.createIfcAxis2Placement3D(
                Location=self.file.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=self.file.createIfcDirection((0.0, 0.0, 1.0)),
            Depth=window.height,
        )

        shape = self.file.createIfcShapeRepresentation(
            ContextOfItems=self._body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

        product_shape = self.file.createIfcProductDefinitionShape(
            Representations=[shape],
        )

        opening = self.file.createIfcOpeningElement(
            GlobalId=_new_guid(),
            Name="Window Opening",
            ObjectPlacement=placement,
            Representation=product_shape,
        )
        return opening

    def _create_local_placement(
        self,
        origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
        z_dir: tuple[float, float, float] = (0.0, 0.0, 1.0),
        x_dir: tuple[float, float, float] = (1.0, 0.0, 0.0),
    ) -> ifcopenshell.entity_instance:
        """Create an IfcLocalPlacement."""
        axis2 = self.file.createIfcAxis2Placement3D(
            Location=self.file.createIfcCartesianPoint(origin),
            Axis=self.file.createIfcDirection(z_dir),
            RefDirection=self.file.createIfcDirection(x_dir),
        )
        return self.file.createIfcLocalPlacement(
            RelativePlacement=axis2,
        )
