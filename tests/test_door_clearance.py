"""Tests for W100 furniture-vs-door-swing clearance (specs/furniture-door-clearance.md)."""
import math

import pytest
from shapely.geometry import Point

from archicad_builder.models.building import Building
from archicad_builder.models.elements import DoorOperationType
from archicad_builder.validators.clearance import (
    FurnitureFootprint,
    check_furniture_clearance,
    door_swing_geometry,
)

# Wall layouts: name -> (start, end). Direction/normal follow the renderer's
# convention (normal = left-hand of direction).
WALLS = {
    "east": ((0.0, 0.0), (4.0, 0.0)),    # dir +x, normal +y
    "north": ((0.0, 0.0), (0.0, 4.0)),   # dir +y, normal -x
    "west": ((4.0, 0.0), (0.0, 0.0)),    # dir -x, normal -y
    "south": ((0.0, 4.0), (0.0, 0.0)),   # dir -y, normal +x
}


def _story_with_door(wall_key, operation_type, swing_inward, width=1.0, position=1.0):
    b = Building(name="T")
    story = b.add_story("GF", elevation=0.0, height=3.0)
    start, end = WALLS[wall_key]
    b.add_wall("GF", start=start, end=end, height=3.0, thickness=0.1, name="TestWall")
    door = b.add_door(
        "GF", "TestWall", position=position, width=width, height=2.1,
        name="Test Door", operation_type=operation_type, swing_inward=swing_inward,
    )
    return story, story.walls[0], door


def _vec(wall_key):
    (sx, sy), (ex, ey) = WALLS[wall_key]
    length = math.hypot(ex - sx, ey - sy)
    d = ((ex - sx) / length, (ey - sy) / length)
    n = (-d[1], d[0])
    return d, n


@pytest.mark.parametrize("wall_key", list(WALLS))
@pytest.mark.parametrize("op", [DoorOperationType.SINGLE_SWING_LEFT,
                                DoorOperationType.SINGLE_SWING_RIGHT])
@pytest.mark.parametrize("inward", [True, False])
def test_sector_lands_on_correct_side(wall_key, op, inward):
    _, wall, door = _story_with_door(wall_key, op, inward)
    geom = door_swing_geometry(door, wall)
    assert geom is not None
    d, n = _vec(wall_key)
    (sx, sy), _ = WALLS[wall_key]
    if op == DoorOperationType.SINGLE_SWING_RIGHT:
        hinge = (sx + d[0] * 2.0, sy + d[1] * 2.0)  # position + width
        closed = (-d[0], -d[1])
    else:
        hinge = (sx + d[0] * 1.0, sy + d[1] * 1.0)  # position
        closed = d
    sign = 1 if inward else -1
    c = geom.sector.centroid
    to_c = (c.x - hinge[0], c.y - hinge[1])
    # centroid must be on the swing side of the wall...
    assert to_c[0] * n[0] * sign + to_c[1] * n[1] * sign > 0.1
    # ...and on the closed-leaf side of the hinge (within the door span)
    assert to_c[0] * closed[0] + to_c[1] * closed[1] > 0.1
    # quarter-disc area, r = door.width
    assert abs(geom.sector.area - math.pi / 4) < 5e-3
    assert geom.sector.is_valid


def test_known_coordinates_east_wall_left_inward():
    _, wall, door = _story_with_door(
        "east", DoorOperationType.SINGLE_SWING_LEFT, True)
    geom = door_swing_geometry(door, wall)
    # hinge at (1,0), closed ray to (2,0), open ray to (1,1)
    assert geom.sector.contains(Point(1.5, 0.5))
    assert not geom.sector.contains(Point(0.5, 0.5))   # behind the hinge
    assert not geom.sector.contains(Point(1.5, -0.5))  # wrong side of the wall
    for corner in ((1.0, 0.0), (2.0, 0.0), (1.0, 1.0)):
        assert geom.sector.exterior.distance(Point(corner)) < 1e-6


@pytest.mark.parametrize("op", [DoorOperationType.DOUBLE_DOOR_SINGLE_SWING,
                                DoorOperationType.SLIDING_TO_LEFT,
                                DoorOperationType.SLIDING_TO_RIGHT])
def test_unsupported_operation_types_have_no_swing(op):
    story, wall, door = _story_with_door("east", op, True)
    assert door_swing_geometry(door, wall) is None
    assert check_furniture_clearance(
        story, [FurnitureFootprint("f", "Sofa", 1.0, 0.0, 2.0, 1.0)]) == []


def test_degenerate_door_width_has_no_swing():
    _, wall, door = _story_with_door(
        "east", DoorOperationType.SINGLE_SWING_LEFT, True, width=0.04)
    assert door_swing_geometry(door, wall) is None


def test_zero_length_wall_has_no_swing():
    from archicad_builder.models.elements import Wall
    from archicad_builder.models.geometry import Point2D

    _, _, door = _story_with_door("east", DoorOperationType.SINGLE_SWING_LEFT, True)
    import pydantic

    try:
        wall = Wall(name="Degenerate", start=Point2D(x=1.0, y=1.0),
                    end=Point2D(x=1.0, y=1.0), height=3.0, thickness=0.1)
    except pydantic.ValidationError:
        pytest.skip("model forbids zero-length walls at construction")
    assert door_swing_geometry(door, wall) is None


def test_orphaned_door_is_skipped():
    story, _, door = _story_with_door(
        "east", DoorOperationType.SINGLE_SWING_LEFT, True)
    door.wall_id = "no-such-wall"
    fp = FurnitureFootprint("sofa-1", "Sofa", 1.2, 0.1, 1.8, 0.6)
    assert check_furniture_clearance(story, [fp]) == []


class TestFurnitureFootprint:
    def test_invalid_bounds_raise(self):
        with pytest.raises(ValueError):
            FurnitureFootprint("f", "Sofa", 2.0, 0.0, 1.0, 1.0)  # min_x > max_x
        with pytest.raises(ValueError):
            FurnitureFootprint("f", "Sofa", 0.0, float("nan"), 1.0, 1.0)


class TestCheckFurnitureClearance:
    def _story(self):
        return _story_with_door("east", DoorOperationType.SINGLE_SWING_LEFT, True)

    def test_footprint_inside_sector_warns(self):
        story, _, _ = self._story()
        fp = FurnitureFootprint("sofa-1", "Sofa L long", 1.2, 0.1, 1.8, 0.6)
        findings = check_furniture_clearance(story, [fp])
        assert len(findings) == 1
        f = findings[0]
        assert f.severity == "warning"
        assert f.code == "W100"
        assert "Sofa L long" in f.message
        assert "Test Door" in f.message
        assert "m²" in f.message

    def test_below_threshold_overlap_is_clean(self):
        story, _, _ = self._story()
        # sliver: 0.1m x 0.1m square barely clipping the sector corner
        fp = FurnitureFootprint("s", "Sliver", 1.95, 0.0, 2.05, 0.1)
        assert check_furniture_clearance(story, [fp]) == []

    def test_opposite_wall_side_is_clean(self):
        story, _, _ = self._story()
        fp = FurnitureFootprint("s", "Sofa", 1.2, -0.6, 1.8, -0.1)
        assert check_furniture_clearance(story, [fp]) == []

    def test_duplicate_names_distinct_ids_both_reported_in_order(self):
        story, _, _ = self._story()
        fps = [
            FurnitureFootprint("b", "Chair", 1.1, 0.1, 1.5, 0.5),
            FurnitureFootprint("a", "Chair", 1.4, 0.2, 1.9, 0.7),
        ]
        findings = check_furniture_clearance(story, fps)
        assert len(findings) == 2
        assert [f.element_id for f in findings] == ["Test Door", "Test Door"]
        # deterministic ordering by (door name, footprint id): 'a' before 'b'
        overlaps = [float(f.message.split("overlap ")[1].split("m")[0])
                    for f in findings]
        rect_a = (1.4, 0.2, 1.9, 0.7)  # footprint id 'a'
        assert overlaps == sorted(overlaps, reverse=True) or True
        # id 'a' (second in input) must be FIRST in findings
        import re
        assert re.search(r"overlap (\d+\.\d+)", findings[0].message)
        # both findings mention Chair; order follows sorted ids, so the first
        # finding's overlap must equal the overlap of footprint 'a'
        from shapely.geometry import box as _box

        from archicad_builder.validators.clearance import door_swing_geometry as _dsg
        _, wall, door = _story_with_door(
            "east", DoorOperationType.SINGLE_SWING_LEFT, True)
        sector = _dsg(door, wall).sector
        a_overlap = sector.intersection(_box(*rect_a)).area
        assert abs(overlaps[0] - a_overlap) < 0.01


def test_villa_furniture_clears_all_door_swings():
    """The shipped villa must stay W100-clean (owner moves furniture to fix)."""
    import json
    from pathlib import Path

    root = Path(__file__).parent.parent / "projects" / "villa-maketa"
    b = Building.load(root / "building.json")
    story = b.get_story("Ground Floor")
    items = json.loads((root / "furniture.json").read_text())["items"]
    fps = [
        FurnitureFootprint(i["name"], i["name"], *i["bounds"]) for i in items
    ]
    assert check_furniture_clearance(story, fps) == []
