"""Tests for vision prompt builder."""

import pytest

from archicad_builder.models.building import Building
from archicad_builder.vision.prompt import build_comparison_prompt


@pytest.fixture
def simple_building() -> Building:
    b = Building(name="Test")
    b.add_story("GF", height=2.7)
    w = b.add_wall("GF", (0, 0), (6, 0), height=2.7, thickness=0.3, name="South")
    b.add_wall("GF", (6, 0), (6, 4), height=2.7, thickness=0.3, name="East")
    b.add_door("GF", "South", position=2.0, width=0.9, height=2.1, name="Front Door")
    b.add_window("GF", "East", position=1.0, width=1.2, height=1.5, name="East Window")
    return b


def test_prompt_contains_element_data(simple_building: Building):
    prompt = build_comparison_prompt(simple_building, "GF")
    assert "### Walls (2)" in prompt
    assert "### Doors (1)" in prompt
    assert "### Windows (1)" in prompt
    assert '"South"' in prompt
    assert '"Front Door"' in prompt
    assert '"East Window"' in prompt


def test_prompt_round_number(simple_building: Building):
    prompt = build_comparison_prompt(simple_building, "GF", round_num=3)
    assert "Round 3" in prompt


def test_prompt_includes_previous_rounds(simple_building: Building):
    prev = ["Fixed W1 thickness", "Added D2 kitchen door"]
    prompt = build_comparison_prompt(
        simple_building, "GF", round_num=3, previous_rounds=prev
    )
    assert "Round 1:" in prompt
    assert "Fixed W1 thickness" in prompt
    assert "Round 2:" in prompt
    assert "Added D2 kitchen door" in prompt
    assert "REMAINING discrepancies" in prompt


def test_prompt_no_previous_rounds(simple_building: Building):
    prompt = build_comparison_prompt(simple_building, "GF", round_num=1)
    assert "Previous Rounds" not in prompt


def test_prompt_invalid_story(simple_building: Building):
    with pytest.raises(ValueError, match="not found"):
        build_comparison_prompt(simple_building, "Nonexistent")


def test_prompt_wall_coordinates(simple_building: Building):
    prompt = build_comparison_prompt(simple_building, "GF")
    # Check wall coordinates are in prompt
    assert "(0.00,0.00)→(6.00,0.00)" in prompt
    assert "(6.00,0.00)→(6.00,4.00)" in prompt


def test_prompt_door_host_wall_tag(simple_building: Building):
    prompt = build_comparison_prompt(simple_building, "GF")
    # Door should reference host wall by tag
    assert "on W1" in prompt  # South wall is W1


def test_prompt_response_format_section(simple_building: Building):
    prompt = build_comparison_prompt(simple_building, "GF")
    assert '"assessment"' in prompt
    assert '"corrections"' in prompt
    assert '"perfect_match"' in prompt
    assert "needs_corrections" in prompt
