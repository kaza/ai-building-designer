"""Facade finishes — optional per-element finish tag (specs/facade-finishes.md)."""

import json
import tempfile
from pathlib import Path

from archicad_builder.models import Building


def _building_with_finishes() -> Building:
    b = Building(name="Finish Test")
    b.add_story("GF", height=3.0, elevation=0.0)
    b.add_wall("GF", (0, 0), (6, 0), height=3.0, thickness=0.3,
               name="Stone Wall", is_external=True, finish="stone_rubble")
    b.add_wall("GF", (6, 0), (6, 4), height=3.0, thickness=0.3,
               name="Plain Wall", is_external=True)
    b.add_slab("GF", [(0, 0), (6, 0), (6, 4), (0, 4)], thickness=0.25,
               name="Deck Slab", finish="deck_wood")
    b.add_roof("GF", [(-0.6, -0.6), (6.6, -0.6), (6.6, 4.6), (-0.6, 4.6)],
               name="Main Roof", finish="roof_brown")
    return b


class TestFinishField:
    def test_add_wall_forwards_finish(self):
        b = _building_with_finishes()
        story = b.get_story("GF")
        assert story.walls[0].finish == "stone_rubble"

    def test_finish_defaults_to_none(self):
        b = _building_with_finishes()
        story = b.get_story("GF")
        assert story.walls[1].finish is None
        assert story.staircases == []  # unrelated elements untouched

    def test_add_slab_and_roof_forward_finish(self):
        b = _building_with_finishes()
        story = b.get_story("GF")
        assert story.slabs[0].finish == "deck_wood"
        assert story.roofs[0].finish == "roof_brown"

    def test_save_load_round_trip(self):
        b = _building_with_finishes()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "b.json"
            b.save(path)
            loaded = Building.load(path)
        story = loaded.get_story("GF")
        assert story.walls[0].finish == "stone_rubble"
        assert story.walls[1].finish is None
        assert story.slabs[0].finish == "deck_wood"
        assert story.roofs[0].finish == "roof_brown"

    def test_unfinished_elements_serialize_without_finish_key(self):
        """None finishes must not appear in JSON — old files stay identical."""
        b = _building_with_finishes()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "b.json"
            b.save(path)
            data = json.loads(path.read_text())
        walls = data["stories"][0]["walls"]
        assert walls[0]["finish"] == "stone_rubble"
        assert "finish" not in walls[1]

    def test_legacy_json_without_finish_loads(self):
        """Files written before the field existed load with finish=None."""
        b = _building_with_finishes()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "b.json"
            b.save(path)
            data = json.loads(path.read_text())
            del data["stories"][0]["walls"][0]["finish"]
            path.write_text(json.dumps(data))
            loaded = Building.load(path)
        assert loaded.get_story("GF").walls[0].finish is None
