"""Tests for the CLI interface."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

CLI = [sys.executable, "-m", "archicad_builder"]
ROOT = Path(__file__).parent.parent


def run_cli(*args: str) -> dict:
    """Run CLI command and return parsed JSON output."""
    result = subprocess.run(
        [*CLI, *args],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert result.returncode == 0, f"CLI failed: {result.stderr}\n{result.stdout}"
    return json.loads(result.stdout)


def run_cli_expect_fail(*args: str) -> dict:
    """Run CLI command expecting failure, return parsed JSON output."""
    result = subprocess.run(
        [*CLI, *args],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert result.returncode != 0
    return json.loads(result.stdout)


class TestValidate:
    def test_validate_3apt(self):
        data = run_cli("validate", "3apt-corner-core")
        assert data["ok"] is True
        assert "validation" in data
        assert data["validation"]["errors"] == 0

    def test_validate_4apt(self):
        data = run_cli("validate", "4apt-centered-core")
        assert data["ok"] is True
        # 4apt has 2 known E032 šupaks (dead zone east of corridor close)
        # on both GF and 1F — real findings, not false positives
        assert data["validation"]["errors"] == 2
        e032 = [d for d in data["validation"]["details"]
                if "E032" in d["message"]]
        assert len(e032) == 2

    def test_validate_nonexistent_project(self):
        data = run_cli_expect_fail("validate", "nonexistent-project")
        assert data["ok"] is False


class TestList:
    def test_list_stories(self):
        data = run_cli("list", "3apt-corner-core", "stories")
        assert data["ok"] is True
        assert len(data["stories"]) == 2
        names = [s["name"] for s in data["stories"]]
        assert "Ground Floor" in names
        assert "1st Floor" in names

    def test_list_apartments(self):
        data = run_cli("list", "3apt-corner-core", "apartments")
        assert data["ok"] is True
        assert len(data["apartments"]) >= 4  # 2 GF + 3 1F (or 2)

    def test_list_apartments_by_story(self):
        data = run_cli("list", "3apt-corner-core", "apartments", "--story", "Ground Floor")
        assert data["ok"] is True
        for apt in data["apartments"]:
            assert apt["story"] == "Ground Floor"

    def test_list_rooms(self):
        data = run_cli("list", "3apt-corner-core", "rooms", "--apartment", "Apt S1", "--story", "Ground Floor")
        assert data["ok"] is True
        assert len(data["rooms"]) >= 3
        types = {r["type"] for r in data["rooms"]}
        assert "living" in types

    def test_list_rooms_requires_apartment(self):
        data = run_cli_expect_fail("list", "3apt-corner-core", "rooms")
        assert data["ok"] is False

    def test_list_walls(self):
        data = run_cli("list", "3apt-corner-core", "walls", "--story", "Ground Floor")
        assert data["ok"] is True
        assert len(data["walls"]) > 0
        # Each wall has required fields
        for w in data["walls"]:
            assert "name" in w
            assert "start" in w
            assert "end" in w


class TestAssess:
    def test_assess_3apt(self):
        data = run_cli("assess", "3apt-corner-core")
        assert data["ok"] is True
        assert data["building"] is not None
        assert len(data["stories"]) == 2
        assert "validation" in data
        # Check apartments have spaces
        for story in data["stories"]:
            for apt in story["apartments"]:
                assert len(apt["spaces"]) > 0
                assert apt["total_area_m2"] > 0


class TestApply:
    def test_apply_rename_wall_roundtrip(self):
        """Rename a wall and rename it back — verify no side effects."""
        # Rename
        data = run_cli(
            "apply", "4apt-centered-core",
            json.dumps([
                {"action": "rename-wall", "story": "Ground Floor",
                 "wall": "South Wall", "new_name": "Test Wall"},
            ]),
        )
        assert data["ok"] is True
        assert data["actions_applied"] == 1

        # Verify it's renamed
        walls = run_cli("list", "4apt-centered-core", "walls", "--story", "Ground Floor")
        names = [w["name"] for w in walls["walls"]]
        assert "Test Wall" in names
        assert "South Wall" not in names

        # Rename back
        data = run_cli(
            "apply", "4apt-centered-core",
            json.dumps([
                {"action": "rename-wall", "story": "Ground Floor",
                 "wall": "Test Wall", "new_name": "South Wall"},
            ]),
        )
        assert data["ok"] is True

    def test_apply_single_action_without_array(self):
        """Single action dict (not wrapped in array) should work."""
        data = run_cli(
            "apply", "4apt-centered-core", "--no-validate",
            json.dumps(
                {"action": "rename-wall", "story": "Ground Floor",
                 "wall": "South Wall", "new_name": "South Wall"},  # no-op rename
            ),
        )
        assert data["ok"] is True
        assert data["actions_applied"] == 1

    def test_apply_unknown_action_fails(self):
        data = run_cli_expect_fail(
            "apply", "4apt-centered-core",
            json.dumps([{"action": "fly-to-moon"}]),
        )
        assert data["ok"] is False

    def test_apply_invalid_json_fails(self):
        result = subprocess.run(
            [*CLI, "apply", "4apt-centered-core", "not json"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert result.returncode != 0

    def test_apply_with_validation(self):
        """Apply with validation enabled (default)."""
        data = run_cli(
            "apply", "4apt-centered-core",
            json.dumps([
                {"action": "rename-wall", "story": "Ground Floor",
                 "wall": "South Wall", "new_name": "South Wall"},
            ]),
        )
        assert data["ok"] is True
        assert "validation" in data
        assert "errors" in data["validation"]

    def test_apply_no_validate_flag(self):
        """Apply with --no-validate skips validation."""
        data = run_cli(
            "apply", "4apt-centered-core", "--no-validate",
            json.dumps([
                {"action": "rename-wall", "story": "Ground Floor",
                 "wall": "South Wall", "new_name": "South Wall"},
            ]),
        )
        assert data["ok"] is True
        assert "validation" not in data


class TestRender:
    def test_render_specific_story(self, tmp_path):
        data = run_cli(
            "render", "3apt-corner-core",
            "--story", "Ground Floor",
            "--output", str(tmp_path),
        )
        assert data["ok"] is True
        assert len(data["rendered"]) == 1
        assert data["rendered"][0]["story"] == "Ground Floor"
        assert Path(data["rendered"][0]["path"]).exists()

    def test_render_all_stories(self, tmp_path):
        data = run_cli(
            "render", "3apt-corner-core",
            "--output", str(tmp_path),
        )
        assert data["ok"] is True
        assert len(data["rendered"]) == 2
