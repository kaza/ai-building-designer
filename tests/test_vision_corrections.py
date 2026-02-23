"""Tests for vision correction parsing and application."""

import json

import pytest

from archicad_builder.models.building import Building
from archicad_builder.vision.corrections import (
    ComparisonResult,
    Correction,
    apply_corrections,
    parse_response,
    summarize_round,
)


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def apartment_building() -> Building:
    """A small apartment with tagged elements."""
    b = Building(name="Test Apartment")
    b.add_story("GF", height=2.7)
    w1 = b.add_wall("GF", (0, 0), (6, 0), height=2.7, thickness=0.3, name="South Exterior")
    w1.load_bearing = True
    w1.is_external = True

    w2 = b.add_wall("GF", (6, 0), (6, 8), height=2.7, thickness=0.3, name="East Exterior")
    w2.load_bearing = True
    w2.is_external = True

    w3 = b.add_wall("GF", (0, 0), (0, 8), height=2.7, thickness=0.3, name="West Exterior")
    w3.load_bearing = True
    w3.is_external = True

    w4 = b.add_wall("GF", (0, 8), (6, 8), height=2.7, thickness=0.3, name="North Exterior")
    w4.load_bearing = True
    w4.is_external = True

    w5 = b.add_wall("GF", (3, 0), (3, 8), height=2.7, thickness=0.1, name="Central Partition")
    w5.load_bearing = False

    b.add_door("GF", "Central Partition", position=3.0, width=0.8, height=2.0, name="Room Door")
    b.add_window("GF", "South Exterior", position=1.0, width=1.5, height=1.2, name="South Window")

    # Ensure tags are assigned
    story = b.stories[0]
    story.ensure_tags()
    return b


# ── parse_response tests ──────────────────────────────────────────


def test_parse_perfect_match():
    response = json.dumps({
        "assessment": "perfect_match",
        "confidence": 1.0,
        "corrections": [],
        "notes": "Model matches perfectly."
    })
    result = parse_response(response)
    assert result.is_perfect
    assert result.confidence == 1.0
    assert len(result.corrections) == 0


def test_parse_with_corrections():
    response = json.dumps({
        "assessment": "needs_corrections",
        "confidence": 0.95,
        "corrections": [
            {
                "element_tag": "W5",
                "action": "modify",
                "field": "load_bearing",
                "current_value": False,
                "corrected_value": True,
                "reason": "Wall has hatching in original"
            }
        ],
        "notes": "One structural fix needed."
    })
    result = parse_response(response)
    assert not result.is_perfect
    assert len(result.corrections) == 1
    assert result.corrections[0].element_tag == "W5"
    assert result.corrections[0].action == "modify"
    assert result.corrections[0].field == "load_bearing"


def test_parse_markdown_fenced_json():
    response = '```json\n{"assessment": "perfect_match", "confidence": 1.0, "corrections": [], "notes": ""}\n```'
    result = parse_response(response)
    assert result.is_perfect


def test_parse_add_correction():
    response = json.dumps({
        "assessment": "needs_corrections",
        "confidence": 0.9,
        "corrections": [
            {
                "element_tag": "W6",
                "action": "add",
                "element_type": "wall",
                "data": {
                    "name": "Corridor Wall",
                    "start": {"x": 3, "y": 4},
                    "end": {"x": 6, "y": 4},
                    "thickness": 0.1,
                    "height": 2.7,
                    "load_bearing": False,
                    "is_external": False
                },
                "reason": "Missing corridor divider"
            }
        ],
        "notes": ""
    })
    result = parse_response(response)
    assert result.corrections[0].action == "add"
    assert result.corrections[0].element_type == "wall"
    assert result.corrections[0].data["name"] == "Corridor Wall"


# ── apply_corrections tests ───────────────────────────────────────


def test_apply_modify_load_bearing(apartment_building: Building):
    result = ComparisonResult(
        assessment="needs_corrections",
        confidence=0.95,
        corrections=[
            Correction(
                element_tag="W5",
                action="modify",
                field="load_bearing",
                current_value=False,
                corrected_value=True,
                reason="Has hatching"
            )
        ],
    )
    changelog = apply_corrections(apartment_building, "GF", result)

    wall = apartment_building.stories[0].walls[4]  # Central Partition
    assert wall.load_bearing is True
    assert any("W5" in l and "load_bearing" in l for l in changelog)


def test_apply_modify_thickness(apartment_building: Building):
    result = ComparisonResult(
        assessment="needs_corrections",
        confidence=0.9,
        corrections=[
            Correction(
                element_tag="W5",
                action="modify",
                field="thickness",
                current_value=0.10,
                corrected_value=0.20,
                reason="Should be thicker"
            )
        ],
    )
    changelog = apply_corrections(apartment_building, "GF", result)

    wall = apartment_building.stories[0].walls[4]
    assert wall.thickness == 0.20
    assert any("thickness" in l for l in changelog)


def test_apply_modify_wall_endpoint(apartment_building: Building):
    result = ComparisonResult(
        assessment="needs_corrections",
        confidence=0.9,
        corrections=[
            Correction(
                element_tag="W5",
                action="modify",
                field="end",
                corrected_value={"x": 3.0, "y": 6.0},
                reason="Wall too long"
            )
        ],
    )
    changelog = apply_corrections(apartment_building, "GF", result)

    wall = apartment_building.stories[0].walls[4]
    assert wall.end.x == 3.0
    assert wall.end.y == 6.0


def test_apply_modify_door_position(apartment_building: Building):
    result = ComparisonResult(
        assessment="needs_corrections",
        confidence=0.9,
        corrections=[
            Correction(
                element_tag="D1",
                action="modify",
                field="position",
                current_value=3.0,
                corrected_value=2.5,
                reason="Door shifted"
            )
        ],
    )
    changelog = apply_corrections(apartment_building, "GF", result)

    door = apartment_building.stories[0].doors[0]
    assert door.position == 2.5


def test_apply_modify_door_width(apartment_building: Building):
    result = ComparisonResult(
        assessment="needs_corrections",
        confidence=0.9,
        corrections=[
            Correction(
                element_tag="D1",
                action="modify",
                field="width",
                current_value=0.8,
                corrected_value=0.9,
                reason="Wider door"
            )
        ],
    )
    changelog = apply_corrections(apartment_building, "GF", result)

    door = apartment_building.stories[0].doors[0]
    assert door.width == 0.9


def test_apply_modify_window_sill(apartment_building: Building):
    result = ComparisonResult(
        assessment="needs_corrections",
        confidence=0.9,
        corrections=[
            Correction(
                element_tag="Win1",
                action="modify",
                field="sill_height",
                current_value=0.9,
                corrected_value=0.0,
                reason="Floor-to-ceiling window"
            )
        ],
    )
    changelog = apply_corrections(apartment_building, "GF", result)

    window = apartment_building.stories[0].windows[0]
    assert window.sill_height == 0.0


def test_apply_modify_host_wall(apartment_building: Building):
    result = ComparisonResult(
        assessment="needs_corrections",
        confidence=0.9,
        corrections=[
            Correction(
                element_tag="D1",
                action="modify",
                field="host_wall_tag",
                current_value="W5",
                corrected_value="W2",
                reason="Door moved to East wall"
            )
        ],
    )
    changelog = apply_corrections(apartment_building, "GF", result)

    door = apartment_building.stories[0].doors[0]
    east_wall = apartment_building.stories[0].walls[1]
    assert door.wall_id == east_wall.global_id


def test_apply_add_wall(apartment_building: Building):
    result = ComparisonResult(
        assessment="needs_corrections",
        confidence=0.9,
        corrections=[
            Correction(
                element_tag="W6",
                action="add",
                element_type="wall",
                data={
                    "name": "Corridor Divider",
                    "start": {"x": 3, "y": 4},
                    "end": {"x": 6, "y": 4},
                    "thickness": 0.1,
                    "height": 2.7,
                    "load_bearing": False,
                    "is_external": False,
                },
                reason="Missing wall"
            )
        ],
    )
    initial_count = len(apartment_building.stories[0].walls)
    changelog = apply_corrections(apartment_building, "GF", result)

    assert len(apartment_building.stories[0].walls) == initial_count + 1
    new_wall = apartment_building.stories[0].walls[-1]
    assert new_wall.name == "Corridor Divider"
    assert new_wall.tag == "W6"
    assert new_wall.start.x == 3
    assert new_wall.end.x == 6


def test_apply_add_door(apartment_building: Building):
    result = ComparisonResult(
        assessment="needs_corrections",
        confidence=0.9,
        corrections=[
            Correction(
                element_tag="D2",
                action="add",
                element_type="door",
                data={
                    "name": "Kitchen Door",
                    "host_wall_tag": "W4",
                    "position": 2.0,
                    "width": 0.8,
                    "height": 2.0,
                },
                reason="Missing door"
            )
        ],
    )
    initial_count = len(apartment_building.stories[0].doors)
    changelog = apply_corrections(apartment_building, "GF", result)

    assert len(apartment_building.stories[0].doors) == initial_count + 1
    new_door = apartment_building.stories[0].doors[-1]
    assert new_door.name == "Kitchen Door"
    assert new_door.tag == "D2"


def test_apply_add_window(apartment_building: Building):
    result = ComparisonResult(
        assessment="needs_corrections",
        confidence=0.9,
        corrections=[
            Correction(
                element_tag="Win2",
                action="add",
                element_type="window",
                data={
                    "name": "North Window",
                    "host_wall_tag": "W4",
                    "position": 2.0,
                    "width": 2.0,
                    "height": 1.5,
                    "sill_height": 0.0,
                },
                reason="Missing window"
            )
        ],
    )
    initial_count = len(apartment_building.stories[0].windows)
    changelog = apply_corrections(apartment_building, "GF", result)

    assert len(apartment_building.stories[0].windows) == initial_count + 1
    new_win = apartment_building.stories[0].windows[-1]
    assert new_win.name == "North Window"
    assert new_win.sill_height == 0.0


def test_apply_remove_wall_cascades(apartment_building: Building):
    """Removing a wall should also remove its hosted doors."""
    result = ComparisonResult(
        assessment="needs_corrections",
        confidence=0.9,
        corrections=[
            Correction(
                element_tag="W5",
                action="remove",
                reason="Wall doesn't exist"
            )
        ],
    )
    changelog = apply_corrections(apartment_building, "GF", result)

    story = apartment_building.stories[0]
    assert not any(w.tag == "W5" for w in story.walls)
    # D1 was hosted on W5, should be removed
    assert not any(d.tag == "D1" for d in story.doors)
    assert any("cascaded" in l for l in changelog)


def test_apply_remove_door(apartment_building: Building):
    result = ComparisonResult(
        assessment="needs_corrections",
        confidence=0.9,
        corrections=[
            Correction(
                element_tag="D1",
                action="remove",
                reason="Door doesn't exist"
            )
        ],
    )
    changelog = apply_corrections(apartment_building, "GF", result)

    story = apartment_building.stories[0]
    assert not any(d.tag == "D1" for d in story.doors)


def test_apply_perfect_match(apartment_building: Building):
    result = ComparisonResult(
        assessment="perfect_match",
        confidence=1.0,
        corrections=[],
    )
    changelog = apply_corrections(apartment_building, "GF", result)

    assert any("Perfect match" in l for l in changelog)


def test_apply_unknown_tag_warns(apartment_building: Building):
    result = ComparisonResult(
        assessment="needs_corrections",
        confidence=0.9,
        corrections=[
            Correction(
                element_tag="W99",
                action="modify",
                field="thickness",
                corrected_value=0.5,
                reason="Test"
            )
        ],
    )
    changelog = apply_corrections(apartment_building, "GF", result)
    assert any("not found" in l for l in changelog)


def test_apply_add_wall_with_array_coordinates(apartment_building: Building):
    """Test that Gemini's [x,y] format works for add."""
    result = ComparisonResult(
        assessment="needs_corrections",
        confidence=0.9,
        corrections=[
            Correction(
                element_tag="W6",
                action="add",
                element_type="wall",
                data={
                    "name": "Test Wall",
                    "start": [1.0, 2.0],
                    "end": [3.0, 2.0],
                    "thickness": 0.1,
                },
                reason="Test"
            )
        ],
    )
    changelog = apply_corrections(apartment_building, "GF", result)
    new_wall = apartment_building.stories[0].walls[-1]
    assert new_wall.start.x == 1.0
    assert new_wall.start.y == 2.0


def test_apply_modify_with_alias_fields(apartment_building: Building):
    """Test shorthand field names like 'lb' and 't'."""
    result = ComparisonResult(
        assessment="needs_corrections",
        confidence=0.9,
        corrections=[
            Correction(
                element_tag="W5",
                action="modify",
                field="lb",
                corrected_value=True,
                reason="Load bearing"
            ),
            Correction(
                element_tag="W5",
                action="modify",
                field="t",
                corrected_value=0.20,
                reason="Thicker"
            ),
        ],
    )
    changelog = apply_corrections(apartment_building, "GF", result)

    wall = apartment_building.stories[0].walls[4]
    assert wall.load_bearing is True
    assert wall.thickness == 0.20


def test_apply_modify_wall_start_from_string(apartment_building: Building):
    """Test point parsing from string format."""
    result = ComparisonResult(
        assessment="needs_corrections",
        confidence=0.9,
        corrections=[
            Correction(
                element_tag="W5",
                action="modify",
                field="start",
                corrected_value="(3.5, 0.0)",
                reason="Shifted"
            )
        ],
    )
    changelog = apply_corrections(apartment_building, "GF", result)

    wall = apartment_building.stories[0].walls[4]
    assert wall.start.x == 3.5
    assert wall.start.y == 0.0


# ── summarize_round tests ────────────────────────────────────────


def test_summarize_round():
    changelog = [
        '✏️ W13.load_bearing: False→True',
        '✏️ W13.thickness: 0.1→0.2',
        '➕ W16 "Corridor Divider": (3.7,6.3)→(4.9,6.3)',
        '🗑️ D5 "Bad Door"',
    ]
    summary = summarize_round(changelog)
    assert "modified W13" in summary
    assert "added W16" in summary
    assert "removed D5" in summary


def test_summarize_empty():
    assert summarize_round([]) == "No corrections applied."
    assert summarize_round(["⚠️ some warning"]) == "No corrections applied."
