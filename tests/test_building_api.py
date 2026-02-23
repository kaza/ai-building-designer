"""Tests for Building convenience API (high-level methods)."""

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from archicad_builder.models import Building, Story, Wall, Door, Window, Point2D, generate_ifc_id


class TestFileIO:
    def test_save_and_load(self, tmp_path):
        """Building round-trips through JSON file."""
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        b.add_wall("GF", (0, 0), (5, 0), height=3.0, thickness=0.2, name="W1")

        json_path = tmp_path / "building.json"
        b.save(json_path)

        loaded = Building.load(json_path)
        assert loaded.name == "Test"
        assert loaded.story_count() == 1
        assert len(loaded.stories[0].walls) == 1

    def test_save_creates_dirs(self, tmp_path):
        """Save creates parent directories if they don't exist."""
        b = Building(name="Test")
        deep_path = tmp_path / "a" / "b" / "c" / "building.json"
        b.save(deep_path)
        assert deep_path.exists()

    def test_load_nonexistent_raises(self):
        """Loading a nonexistent file raises an error."""
        with pytest.raises(FileNotFoundError):
            Building.load("/tmp/nonexistent_building_12345.json")


class TestAddStory:
    def test_add_story(self):
        b = Building(name="Test")
        story = b.add_story("Ground Floor", height=3.0, elevation=0.0)
        assert story.name == "Ground Floor"
        assert b.story_count() == 1

    def test_add_story_auto_elevation(self):
        """When elevation is omitted, it's calculated from the stack."""
        b = Building(name="Test")
        gf = b.add_story("Ground Floor", height=3.0)
        ff = b.add_story("First Floor", height=3.0)
        sf = b.add_story("Second Floor", height=2.8)
        assert gf.elevation == 0.0
        assert ff.elevation == 3.0
        assert sf.elevation == 6.0

    def test_add_story_explicit_elevation(self):
        """When elevation is provided, it's used as-is."""
        b = Building(name="Test")
        b.add_story("Basement", height=2.5, elevation=-2.5)
        b.add_story("Ground Floor", height=3.0, elevation=0.0)
        assert b.stories[0].name == "Basement"
        assert b.stories[0].elevation == -2.5

    def test_add_story_sorted_by_elevation(self):
        b = Building(name="Test")
        b.add_story("Second Floor", height=3.0, elevation=6.0)
        b.add_story("Ground Floor", height=3.0, elevation=0.0)
        b.add_story("First Floor", height=3.0, elevation=3.0)
        assert [s.name for s in b.stories] == [
            "Ground Floor", "First Floor", "Second Floor"
        ]

    def test_add_duplicate_story_raises(self):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        with pytest.raises(ValueError, match="already exists"):
            b.add_story("GF", height=3.0)


class TestAddWall:
    def test_add_wall(self):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        wall = b.add_wall("GF", (0, 0), (5, 0), height=3.0, thickness=0.2, name="South")
        assert wall.name == "South"
        assert wall.length == 5.0
        assert len(b.stories[0].walls) == 1

    def test_add_wall_bad_story(self):
        b = Building(name="Test")
        with pytest.raises(ValueError, match="not found"):
            b.add_wall("Nonexistent", (0, 0), (5, 0), height=3.0, thickness=0.2)


class TestAddDoor:
    def test_add_door_by_wall_name(self):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        b.add_wall("GF", (0, 0), (5, 0), height=3.0, thickness=0.2, name="South")
        door = b.add_door("GF", "South", position=1.0, width=0.9, height=2.1, name="Front Door")
        assert door.name == "Front Door"
        assert door.wall_id == b.stories[0].walls[0].global_id

    def test_add_door_bad_wall(self):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        with pytest.raises(ValueError, match="Wall.*not found"):
            b.add_door("GF", "Nonexistent", position=0, width=0.9, height=2.1)


class TestAddWindow:
    def test_add_window_by_wall_name(self):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        b.add_wall("GF", (0, 0), (5, 0), height=3.0, thickness=0.2, name="East")
        window = b.add_window(
            "GF", "East", position=1.0, width=1.2, height=1.5,
            sill_height=0.9, name="East Window",
        )
        assert window.name == "East Window"
        assert window.sill_height == 0.9

    def test_add_window_default_sill(self):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        b.add_wall("GF", (0, 0), (5, 0), height=3.0, thickness=0.2, name="W")
        window = b.add_window("GF", "W", position=1.0, width=1.0, height=1.0)
        assert window.sill_height == 0.9


class TestAddSlab:
    def test_add_slab(self):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        slab = b.add_slab(
            "GF",
            vertices=[(0, 0), (5, 0), (5, 4), (0, 4)],
            thickness=0.25,
            name="Floor",
        )
        assert slab.area == 20.0
        assert slab.is_floor is True


class TestRemoveElements:
    def _make_building(self) -> Building:
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        b.add_wall("GF", (0, 0), (5, 0), height=3.0, thickness=0.2, name="South")
        b.add_wall("GF", (5, 0), (5, 4), height=3.0, thickness=0.2, name="East")
        b.add_door("GF", "South", position=1.0, width=0.9, height=2.1, name="Door1")
        b.add_window("GF", "East", position=1.0, width=1.2, height=1.5, name="Win1")
        return b

    def test_remove_wall_cascades(self):
        """Removing a wall also removes its hosted doors and windows."""
        b = self._make_building()
        assert len(b.stories[0].doors) == 1
        b.remove_wall("GF", "South")
        assert len(b.stories[0].walls) == 1
        assert len(b.stories[0].doors) == 0  # door was on South wall

    def test_remove_wall_keeps_others(self):
        """Removing a wall doesn't affect elements on other walls."""
        b = self._make_building()
        b.remove_wall("GF", "South")
        assert len(b.stories[0].windows) == 1  # window was on East wall

    def test_remove_door(self):
        b = self._make_building()
        b.remove_door("GF", "Door1")
        assert len(b.stories[0].doors) == 0

    def test_remove_window(self):
        b = self._make_building()
        b.remove_window("GF", "Win1")
        assert len(b.stories[0].windows) == 0

    def test_remove_story(self):
        b = self._make_building()
        b.remove_story("GF")
        assert b.story_count() == 0

    def test_remove_nonexistent_raises(self):
        b = self._make_building()
        with pytest.raises(ValueError):
            b.remove_wall("GF", "Nonexistent")
        with pytest.raises(ValueError):
            b.remove_door("GF", "Nonexistent")
        with pytest.raises(ValueError):
            b.remove_window("GF", "Nonexistent")


class TestMoveWall:
    def test_move_start(self):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        b.add_wall("GF", (0, 0), (5, 0), height=3.0, thickness=0.2, name="W")
        updated = b.move_wall("GF", "W", new_start=(1, 0))
        assert updated.start.x == 1.0
        assert updated.end.x == 5.0  # unchanged

    def test_move_end(self):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        b.add_wall("GF", (0, 0), (5, 0), height=3.0, thickness=0.2, name="W")
        updated = b.move_wall("GF", "W", new_end=(6, 0))
        assert updated.start.x == 0.0  # unchanged
        assert updated.end.x == 6.0

    def test_move_both(self):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        b.add_wall("GF", (0, 0), (5, 0), height=3.0, thickness=0.2, name="W")
        updated = b.move_wall("GF", "W", new_start=(1, 1), new_end=(6, 1))
        assert updated.start.x == 1.0
        assert updated.start.y == 1.0
        assert updated.end.x == 6.0

    def test_move_nonexistent_raises(self):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        with pytest.raises(ValueError, match="not found"):
            b.move_wall("GF", "Nope", new_start=(0, 0))


class TestRenameWall:
    def test_rename(self):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        b.add_wall("GF", (0, 0), (5, 0), height=3.0, thickness=0.2, name="Old")
        updated = b.rename_wall("GF", "Old", "New")
        assert updated.name == "New"
        assert b.stories[0].get_wall_by_name("New") is not None
        assert b.stories[0].get_wall_by_name("Old") is None


class TestExportShortcuts:
    def test_export_ifc(self, tmp_path):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        b.add_wall("GF", (0, 0), (5, 0), height=3.0, thickness=0.2, name="W")
        result = b.export_ifc(tmp_path / "test.ifc")
        assert result.exists()

    def test_render_floorplan(self, tmp_path):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        b.add_wall("GF", (0, 0), (5, 0), height=3.0, thickness=0.2, name="W")
        result = b.render_floorplan("GF", tmp_path / "test.png")
        assert result.exists()

    def test_validate(self):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        wall = b.add_wall("GF", (0, 0), (3, 0), height=3.0, thickness=0.2, name="W")
        # Add a door that extends past wall end
        b.stories[0].doors.append(
            Door(name="Bad", wall_id=wall.global_id, position=2.5, width=0.9, height=2.1)
        )
        errors = b.validate()
        # Filter to structural errors only (building-level validators may add more)
        structural_errors = [e for e in errors if "extends past wall end" in e.message]
        assert len(structural_errors) == 1


class TestSummary:
    def test_summary(self):
        b = Building(name="My House")
        b.add_story("GF", height=3.0)
        b.add_wall("GF", (0, 0), (5, 0), height=3.0, thickness=0.2, name="W")
        s = b.summary()
        assert "My House" in s
        assert "Walls: 1" in s


class TestIfcGlobalIds:
    def test_elements_have_22_char_ids(self):
        b = Building(name="Test")
        assert len(b.global_id) == 22
        s = b.add_story("GF", height=3.0)
        assert len(s.global_id) == 22
        w = b.add_wall("GF", (0, 0), (5, 0), height=3.0, thickness=0.2, name="W")
        assert len(w.global_id) == 22

    def test_ids_unique(self):
        b = Building(name="Test")
        s = b.add_story("GF", height=3.0)
        w1 = b.add_wall("GF", (0, 0), (5, 0), height=3.0, thickness=0.2, name="W1")
        w2 = b.add_wall("GF", (5, 0), (5, 4), height=3.0, thickness=0.2, name="W2")
        ids = {b.global_id, s.global_id, w1.global_id, w2.global_id}
        assert len(ids) == 4

    def test_ids_preserved_through_json(self, tmp_path):
        b = Building(name="Test")
        b.add_story("GF", height=3.0)
        wall = b.add_wall("GF", (0, 0), (5, 0), height=3.0, thickness=0.2, name="W")
        original_ids = (b.global_id, b.stories[0].global_id, wall.global_id)

        b.save(tmp_path / "test.json")
        loaded = Building.load(tmp_path / "test.json")

        assert loaded.global_id == original_ids[0]
        assert loaded.stories[0].global_id == original_ids[1]
        assert loaded.stories[0].walls[0].global_id == original_ids[2]


class TestFullWorkflow:
    def test_build_save_load_export(self, tmp_path):
        """Full workflow: build → save → load → validate → export."""
        # Build
        b = Building(name="Workflow Test")
        b.add_story("GF", height=3.0)
        b.add_wall("GF", (0, 0), (6, 0), height=3.0, thickness=0.25, name="South")
        b.add_wall("GF", (6, 0), (6, 4), height=3.0, thickness=0.25, name="East")
        b.add_wall("GF", (6, 4), (0, 4), height=3.0, thickness=0.25, name="North")
        b.add_wall("GF", (0, 4), (0, 0), height=3.0, thickness=0.25, name="West")
        b.add_door("GF", "South", position=2.5, width=0.9, height=2.1, name="Door")
        b.add_window("GF", "East", position=1.2, width=1.2, height=1.5, name="Window")
        b.add_slab("GF", [(0, 0), (6, 0), (6, 4), (0, 4)], name="Floor")

        # Save
        json_path = tmp_path / "building.json"
        b.save(json_path)

        # Load
        loaded = Building.load(json_path)
        assert loaded.name == "Workflow Test"

        # Validate
        errors = loaded.validate()
        assert len(errors) == 0

        # Export
        ifc_path = loaded.export_ifc(tmp_path / "test.ifc")
        assert ifc_path.exists()
        assert ifc_path.stat().st_size > 0
