"""Top-level building model: Building and Story.

IDs use IFC-compatible GlobalIds (22-char compressed GUIDs).
Follows IFC conventions for spatial hierarchy and element naming.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from archicad_builder.models.elements import (
    Door,
    Roof,
    RoofType,
    Slab,
    Staircase,
    StaircaseType,
    VirtualElement,
    Wall,
    Window,
)
from archicad_builder.models.spaces import Apartment, RoomType, Space
from archicad_builder.models.geometry import Point2D, Polygon2D
from archicad_builder.models.ifc_id import generate_ifc_id


class Story(BaseModel):
    """A single story (floor level) of a building.

    Elevation is the absolute height of the story floor from ground (z=0),
    following IFC's IfcBuildingStorey convention.
    """

    global_id: str = Field(default_factory=generate_ifc_id, description="IFC GlobalId")
    name: str = Field(description="Story name, e.g. 'Ground Floor', 'First Floor'")
    description: str = ""
    elevation: float = Field(
        default=0.0, description="Absolute elevation of story floor in meters (IFC convention)"
    )
    height: float = Field(
        gt=0, description="Floor-to-floor height in meters (typically 2.7-3.5)"
    )
    walls: list[Wall] = Field(default_factory=list)
    slabs: list[Slab] = Field(default_factory=list)
    doors: list[Door] = Field(default_factory=list)
    windows: list[Window] = Field(default_factory=list)
    roofs: list[Roof] = Field(default_factory=list)
    staircases: list[Staircase] = Field(default_factory=list)
    virtual_elements: list[VirtualElement] = Field(default_factory=list)
    spaces: list[Space] = Field(default_factory=list)
    apartments: list[Apartment] = Field(default_factory=list)

    def get_wall(self, wall_id: str) -> Wall | None:
        """Find a wall by GlobalId."""
        return next((w for w in self.walls if w.global_id == wall_id), None)

    def get_wall_by_name(self, name: str) -> Wall | None:
        """Find a wall by name (case-insensitive)."""
        return next(
            (w for w in self.walls if w.name.lower() == name.lower()), None
        )

    def get_door_by_name(self, name: str) -> Door | None:
        """Find a door by name (case-insensitive)."""
        return next(
            (d for d in self.doors if d.name.lower() == name.lower()), None
        )

    def get_window_by_name(self, name: str) -> Window | None:
        """Find a window by name (case-insensitive)."""
        return next(
            (w for w in self.windows if w.name.lower() == name.lower()), None
        )

    def wall_ids(self) -> set[str]:
        """Set of all wall GlobalIds in this story."""
        return {w.global_id for w in self.walls}

    def ensure_tags(self) -> None:
        """Auto-generate tags for elements that don't have one.

        Assigns W1, W2... for walls, D1, D2... for doors, etc.
        Skips elements that already have a tag.
        """
        w_counter = 1
        for wall in self.walls:
            if not wall.tag:
                wall.tag = f"W{w_counter}"
            w_counter += 1
        d_counter = 1
        for door in self.doors:
            if not door.tag:
                door.tag = f"D{d_counter}"
            d_counter += 1
        win_counter = 1
        for window in self.windows:
            if not window.tag:
                window.tag = f"Win{win_counter}"
            win_counter += 1
        st_counter = 1
        for staircase in self.staircases:
            if not staircase.tag:
                staircase.tag = f"ST{st_counter}"
            st_counter += 1
        v_counter = 1
        for ve in self.virtual_elements:
            if not ve.tag:
                ve.tag = f"V{v_counter}"
            v_counter += 1
        r_counter = 1
        for space in self.spaces:
            if not space.tag:
                space.tag = f"R{r_counter}"
            r_counter += 1
        a_counter = 1
        for apt in self.apartments:
            if not apt.tag:
                apt.tag = f"A{a_counter}"
            a_counter += 1


class Building(BaseModel):
    """Top-level building model.

    Follows IFC hierarchy: Building contains Stories, which contain elements.
    """

    global_id: str = Field(default_factory=generate_ifc_id, description="IFC GlobalId")
    name: str = Field(default="Untitled Building", description="Building name")
    description: str = ""
    units: str = Field(
        default="meters",
        description="Coordinate unit system. Only 'meters' supported for now.",
    )
    stories: list[Story] = Field(default_factory=list)

    @field_validator("units")
    @classmethod
    def only_meters(cls, v: str) -> str:
        if v != "meters":
            raise ValueError("Only 'meters' unit system is currently supported")
        return v

    # ── File I/O ──────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: str | Path) -> Building:
        """Load a building from a JSON file."""
        path = Path(path)
        return cls.model_validate_json(path.read_text())

    def save(self, path: str | Path) -> Path:
        """Save the building to a JSON file. Creates parent dirs if needed."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2))
        return path

    # ── Lookups ───────────────────────────────────────────────────────

    def get_story(self, name: str) -> Story | None:
        """Find a story by name (case-insensitive)."""
        return next(
            (s for s in self.stories if s.name.lower() == name.lower()), None
        )

    def get_story_by_id(self, global_id: str) -> Story | None:
        """Find a story by GlobalId."""
        return next((s for s in self.stories if s.global_id == global_id), None)

    def _require_story(self, story_name: str) -> Story:
        """Get a story by name or raise ValueError."""
        story = self.get_story(story_name)
        if story is None:
            available = [s.name for s in self.stories]
            raise ValueError(
                f"Story '{story_name}' not found. Available: {available}"
            )
        return story

    def _top_elevation(self) -> float:
        """Calculate the elevation for the next story (top of current stack)."""
        if not self.stories:
            return 0.0
        top = self.stories[-1]  # stories are sorted by elevation
        return top.elevation + top.height

    # ── Add elements ──────────────────────────────────────────────────

    def add_story(
        self,
        name: str,
        height: float,
        elevation: float | None = None,
    ) -> Story:
        """Add a new story to the building.

        If elevation is not provided, it's calculated as the top of the
        current story stack (sum of elevations + heights below).
        If elevation is provided, it's used as-is (IFC absolute elevation).
        """
        if self.get_story(name) is not None:
            raise ValueError(f"Story '{name}' already exists")
        if elevation is None:
            elevation = self._top_elevation()
        story = Story(name=name, height=height, elevation=elevation)
        self.stories.append(story)
        # Keep stories sorted by elevation
        self.stories.sort(key=lambda s: s.elevation)
        return story

    def add_wall(
        self,
        story_name: str,
        start: tuple[float, float],
        end: tuple[float, float],
        height: float,
        thickness: float,
        name: str = "",
        description: str = "",
    ) -> Wall:
        """Add a wall to a story. Returns the created wall."""
        story = self._require_story(story_name)
        wall = Wall(
            name=name,
            description=description,
            start=Point2D(x=start[0], y=start[1]),
            end=Point2D(x=end[0], y=end[1]),
            height=height,
            thickness=thickness,
        )
        story.walls.append(wall)
        return wall

    def add_door(
        self,
        story_name: str,
        wall_name: str,
        position: float,
        width: float,
        height: float,
        name: str = "",
        description: str = "",
    ) -> Door:
        """Add a door to a wall (by wall name). Returns the created door."""
        story = self._require_story(story_name)
        wall = story.get_wall_by_name(wall_name)
        if wall is None:
            available = [w.name for w in story.walls if w.name]
            raise ValueError(
                f"Wall '{wall_name}' not found in '{story_name}'. Available: {available}"
            )
        door = Door(
            name=name,
            description=description,
            wall_id=wall.global_id,
            position=position,
            width=width,
            height=height,
        )
        story.doors.append(door)
        return door

    def add_window(
        self,
        story_name: str,
        wall_name: str,
        position: float,
        width: float,
        height: float,
        sill_height: float = 0.9,
        name: str = "",
        description: str = "",
    ) -> Window:
        """Add a window to a wall (by wall name). Returns the created window."""
        story = self._require_story(story_name)
        wall = story.get_wall_by_name(wall_name)
        if wall is None:
            available = [w.name for w in story.walls if w.name]
            raise ValueError(
                f"Wall '{wall_name}' not found in '{story_name}'. Available: {available}"
            )
        window = Window(
            name=name,
            description=description,
            wall_id=wall.global_id,
            position=position,
            width=width,
            height=height,
            sill_height=sill_height,
        )
        story.windows.append(window)
        return window

    def add_slab(
        self,
        story_name: str,
        vertices: list[tuple[float, float]],
        thickness: float = 0.25,
        is_floor: bool = True,
        name: str = "",
        description: str = "",
    ) -> Slab:
        """Add a slab to a story. Vertices as list of (x, y) tuples."""
        story = self._require_story(story_name)
        slab = Slab(
            name=name,
            description=description,
            outline=Polygon2D(
                vertices=[Point2D(x=v[0], y=v[1]) for v in vertices]
            ),
            thickness=thickness,
            is_floor=is_floor,
        )
        story.slabs.append(slab)
        return slab

    def add_staircase(
        self,
        story_name: str,
        vertices: list[tuple[float, float]],
        width: float = 1.2,
        riser_height: float = 0.175,
        tread_length: float = 0.28,
        stair_type: StaircaseType = StaircaseType.STRAIGHT_RUN_STAIR,
        name: str = "",
        description: str = "",
    ) -> Staircase:
        """Add a staircase to a story. Vertices as list of (x, y) tuples."""
        story = self._require_story(story_name)
        staircase = Staircase(
            name=name,
            description=description,
            outline=Polygon2D(
                vertices=[Point2D(x=v[0], y=v[1]) for v in vertices]
            ),
            width=width,
            riser_height=riser_height,
            tread_length=tread_length,
            stair_type=stair_type,
        )
        story.staircases.append(staircase)
        return staircase

    def add_roof(
        self,
        story_name: str,
        vertices: list[tuple[float, float]],
        roof_type: RoofType = RoofType.FLAT,
        pitch: float = 0.0,
        thickness: float = 0.3,
        name: str = "",
        description: str = "",
    ) -> Roof:
        """Add a roof to a story. Vertices as list of (x, y) tuples."""
        story = self._require_story(story_name)
        roof = Roof(
            name=name,
            description=description,
            outline=Polygon2D(
                vertices=[Point2D(x=v[0], y=v[1]) for v in vertices]
            ),
            roof_type=roof_type,
            pitch=pitch,
            thickness=thickness,
        )
        story.roofs.append(roof)
        return roof

    # ── Remove elements ───────────────────────────────────────────────

    def remove_story(self, name: str) -> None:
        """Remove a story by name."""
        story = self._require_story(name)
        self.stories.remove(story)

    def remove_wall(self, story_name: str, wall_name: str) -> None:
        """Remove a wall by name. Also removes doors/windows hosted on it."""
        story = self._require_story(story_name)
        wall = story.get_wall_by_name(wall_name)
        if wall is None:
            raise ValueError(f"Wall '{wall_name}' not found in '{story_name}'")
        # Remove hosted doors and windows
        story.doors = [d for d in story.doors if d.wall_id != wall.global_id]
        story.windows = [w for w in story.windows if w.wall_id != wall.global_id]
        story.walls.remove(wall)

    def remove_door(self, story_name: str, door_name: str) -> None:
        """Remove a door by name."""
        story = self._require_story(story_name)
        door = story.get_door_by_name(door_name)
        if door is None:
            raise ValueError(f"Door '{door_name}' not found in '{story_name}'")
        story.doors.remove(door)

    def remove_window(self, story_name: str, window_name: str) -> None:
        """Remove a window by name."""
        story = self._require_story(story_name)
        window = story.get_window_by_name(window_name)
        if window is None:
            raise ValueError(f"Window '{window_name}' not found in '{story_name}'")
        story.windows.remove(window)

    # ── Modify elements ───────────────────────────────────────────────

    def move_wall(
        self,
        story_name: str,
        wall_name: str,
        new_start: tuple[float, float] | None = None,
        new_end: tuple[float, float] | None = None,
    ) -> Wall:
        """Move a wall's start and/or end point.

        Automatically updates any space/apartment boundary vertices that
        lie on the old wall line — rooms resize with their walls.
        """
        story = self._require_story(story_name)
        wall = story.get_wall_by_name(wall_name)
        if wall is None:
            raise ValueError(f"Wall '{wall_name}' not found in '{story_name}'")

        # Record old wall line before moving
        old_start = (wall.start.x, wall.start.y)
        old_end = (wall.end.x, wall.end.y)
        eff_new_start = new_start if new_start is not None else old_start
        eff_new_end = new_end if new_end is not None else old_end

        # Move the wall
        idx = story.walls.index(wall)
        new_wall = wall.model_copy(
            update={
                k: Point2D(x=v[0], y=v[1])
                for k, v in [("start", new_start), ("end", new_end)]
                if v is not None
            }
        )
        story.walls[idx] = new_wall

        # Auto-update space and apartment boundaries that touch the old wall
        self._update_boundaries_for_wall_move(
            story, old_start, old_end, eff_new_start, eff_new_end
        )

        return new_wall

    @staticmethod
    def _update_boundaries_for_wall_move(
        story: "Story",
        old_start: tuple[float, float],
        old_end: tuple[float, float],
        new_start: tuple[float, float],
        new_end: tuple[float, float],
        tol: float = 0.02,
    ) -> None:
        """Update space/apartment boundary vertices that lie on the old wall line.

        For axis-aligned walls (vertical or horizontal), shifts boundary vertices
        from the old wall position to the new one. This ensures rooms resize
        automatically when their bounding walls move.
        """
        ox1, oy1 = old_start
        ox2, oy2 = old_end
        nx1, ny1 = new_start
        nx2, ny2 = new_end

        is_vertical = abs(ox1 - ox2) < tol
        is_horizontal = abs(oy1 - oy2) < tol

        if not is_vertical and not is_horizontal:
            return  # Only handle axis-aligned walls for now

        # Collect all boundaries to update (spaces + apartment boundaries)
        boundaries: list[Polygon2D] = []
        for apt in story.apartments:
            if apt.boundary:
                boundaries.append(apt.boundary)
            for space in apt.spaces:
                if space.boundary:
                    boundaries.append(space.boundary)

        for boundary in boundaries:
            updated = False
            new_vertices = []
            for v in boundary.vertices:
                vx, vy = v.x, v.y

                if is_vertical:
                    # Wall is vertical at x = ox1. Match vertices on this x
                    # within the wall's y-range.
                    y_min = min(oy1, oy2) - tol
                    y_max = max(oy1, oy2) + tol
                    if abs(vx - ox1) < tol and y_min <= vy <= y_max:
                        # Shift x from old to new wall position
                        vx = nx1
                        updated = True

                elif is_horizontal:
                    # Wall is horizontal at y = oy1. Match vertices on this y
                    # within the wall's x-range.
                    x_min = min(ox1, ox2) - tol
                    x_max = max(ox1, ox2) + tol
                    if abs(vy - oy1) < tol and x_min <= vx <= x_max:
                        # Shift y from old to new wall position
                        vy = ny1
                        updated = True

                new_vertices.append(Point2D(x=round(vx, 4), y=round(vy, 4)))

            if updated:
                boundary.vertices = new_vertices

    def resize_door(
        self,
        story_name: str,
        door_name: str,
        new_width: float,
    ) -> Door:
        """Change a door's width. Returns the updated door."""
        story = self._require_story(story_name)
        door = story.get_door_by_name(door_name)
        if door is None:
            available = [d.name for d in story.doors if d.name]
            raise ValueError(
                f"Door '{door_name}' not found in '{story_name}'. Available: {available}"
            )
        idx = story.doors.index(door)
        new_door = door.model_copy(update={"width": new_width})
        story.doors[idx] = new_door
        return new_door

    def resize_window(
        self,
        story_name: str,
        window_name: str,
        new_width: float | None = None,
        new_height: float | None = None,
    ) -> Window:
        """Change a window's dimensions. Returns the updated window."""
        story = self._require_story(story_name)
        window = story.get_window_by_name(window_name)
        if window is None:
            available = [w.name for w in story.windows if w.name]
            raise ValueError(
                f"Window '{window_name}' not found in '{story_name}'. Available: {available}"
            )
        idx = story.windows.index(window)
        updates = {}
        if new_width is not None:
            updates["width"] = new_width
        if new_height is not None:
            updates["height"] = new_height
        new_window = window.model_copy(update=updates)
        story.windows[idx] = new_window
        return new_window

    def rename_wall(
        self, story_name: str, old_name: str, new_name: str
    ) -> Wall:
        """Rename a wall. Returns the updated wall."""
        story = self._require_story(story_name)
        wall = story.get_wall_by_name(old_name)
        if wall is None:
            raise ValueError(f"Wall '{old_name}' not found in '{story_name}'")
        idx = story.walls.index(wall)
        new_wall = wall.model_copy(update={"name": new_name})
        story.walls[idx] = new_wall
        return new_wall

    # ── Export shortcuts ──────────────────────────────────────────────

    def export_ifc(self, path: str | Path) -> Path:
        """Export the building to IFC. Returns the output path."""
        from archicad_builder.export.ifc import IFCExporter

        exporter = IFCExporter(self)
        return exporter.export(path)

    def render_floorplan(
        self,
        story_name: str,
        path: str | Path,
        **kwargs,
    ) -> Path:
        """Render a 2D floor plan of a story. Returns the output path."""
        from archicad_builder.export.floorplan import render_floorplan

        story = self._require_story(story_name)
        return render_floorplan(story, path, **kwargs)

    def render_overview(self, path: str | Path, **kwargs) -> Path:
        """Render all floor plans in a grid layout. Returns the output path."""
        from archicad_builder.export.overview import render_overview

        return render_overview(self, path, **kwargs)

    def validate(self) -> list:
        """Run all validators across all stories. Returns list of errors."""
        from archicad_builder.validators.structural import validate_story
        from archicad_builder.validators.connectivity import validate_connectivity
        from archicad_builder.validators.building import validate_building

        errors = []
        # Per-story validators
        for story in self.stories:
            errors.extend(validate_story(story))
            errors.extend(validate_connectivity(story))
        # Building-level validators
        errors.extend(validate_building(self))
        return errors

    def snap_endpoints(
        self, story_name: str, tolerance: float = 0.02
    ) -> list:
        """Snap wall endpoints within tolerance. Returns list of SnapResults."""
        from archicad_builder.validators.snap import snap_endpoints

        story = self._require_story(story_name)
        return snap_endpoints(story, tolerance)

    # ── Query helpers ─────────────────────────────────────────────────

    def total_area(self) -> float:
        """Total floor area across all stories (sum of floor slab areas)."""
        return sum(
            slab.area
            for story in self.stories
            for slab in story.slabs
            if slab.is_floor
        )

    def story_count(self) -> int:
        """Number of stories."""
        return len(self.stories)

    def summary(self) -> str:
        """Human-readable summary of the building."""
        lines = [f"🏗️ {self.name}"]
        lines.append(f"   Stories: {self.story_count()}")
        lines.append(f"   Total floor area: {self.total_area():.1f} m²")
        total_apts = sum(len(s.apartments) for s in self.stories)
        if total_apts:
            lines.append(f"   Total apartments: {total_apts}")
        for story in self.stories:
            lines.append(f"   📐 {story.name} (elev {story.elevation}m, h={story.height}m)")
            parts = [
                f"Walls: {len(story.walls)}",
                f"Doors: {len(story.doors)}",
                f"Windows: {len(story.windows)}",
                f"Slabs: {len(story.slabs)}",
            ]
            if story.staircases:
                parts.append(f"Stairs: {len(story.staircases)}")
            if story.apartments:
                parts.append(f"Apts: {len(story.apartments)}")
            lines.append(f"      {', '.join(parts)}")
        return "\n".join(lines)
