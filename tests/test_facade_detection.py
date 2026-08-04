"""Tests for facade detection (specs/facade-detection.md).

E044 must judge facade access by boundary edges lying on is_external walls,
not by bounding-box y-extremes. W046 fires when no walls are flagged.
"""
from pathlib import Path

from archicad_builder.models import Building
from archicad_builder.models.geometry import Point2D, Polygon2D
from archicad_builder.models.spaces import Apartment, RoomType, Space
from archicad_builder.validators.phases import validate_all_phases

GF = "Ground Floor"
PROJECTS = Path(__file__).parent.parent / "projects"


def _codes(errors, code):
    return [e for e in errors if e.message.startswith(f"{code}:")]


def _space(name, room_type, x0, y0, x1, y1):
    return Space(
        name=name,
        room_type=room_type,
        boundary=Polygon2D(vertices=[
            Point2D(x=x0, y=y0), Point2D(x=x1, y=y0),
            Point2D(x=x1, y=y1), Point2D(x=x0, y=y1),
        ]),
    )


def _base_building(*, external: bool) -> Building:
    """10x8 building, one apartment: living W, bedroom center, kitchen S.

    Bedroom (3-7, 3-6) touches no exterior edge -> E044 candidate.
    Living (0-3, 0-8) lies on the west facade. Kitchen (3-10, 0-3) on south.
    """
    b = Building(name="Facade Test")
    b.add_story(GF, height=3.0)

    def wall(name, s, e, thickness=0.3):
        w = b.add_wall(GF, s, e, height=3.0, thickness=thickness, name=name)
        w.is_external = external and thickness == 0.3
        return w

    wall("South", (0, 0), (10, 0))
    wall("East", (10, 0), (10, 8))
    wall("North", (10, 8), (0, 8))
    wall("West", (0, 8), (0, 0))
    wall("Living East", (3, 0), (3, 8), thickness=0.12)
    wall("Bedroom South", (3, 3), (10, 3), thickness=0.12)
    wall("Bedroom North", (3, 6), (10, 6), thickness=0.12)

    apt = Apartment(
        name="A1",
        boundary=Polygon2D(vertices=[
            Point2D(x=0, y=0), Point2D(x=10, y=0),
            Point2D(x=10, y=8), Point2D(x=0, y=8),
        ]),
        spaces=[
            _space("Living", RoomType.LIVING, 0, 0, 3, 8),
            _space("Bedroom", RoomType.BEDROOM, 3, 3, 7, 6),
            _space("Kitchen", RoomType.KITCHEN, 3, 0, 10, 3),
            _space("Bath", RoomType.BATHROOM, 7, 3, 10, 6),
            _space("Hall", RoomType.HALLWAY, 3, 6, 10, 8),
        ],
    )
    story = b.get_story(GF)
    story.apartments.append(apt)
    return b


class TestAddWallFlags:
    def test_add_wall_sets_is_external_and_load_bearing(self):
        b = Building(name="T")
        b.add_story(GF, height=3.0)
        w = b.add_wall(GF, (0, 0), (5, 0), height=3.0, thickness=0.3,
                       name="W", is_external=True, load_bearing=True)
        assert w.is_external is True
        assert w.load_bearing is True

    def test_add_wall_defaults_unchanged(self):
        b = Building(name="T")
        b.add_story(GF, height=3.0)
        w = b.add_wall(GF, (0, 0), (5, 0), height=3.0, thickness=0.3, name="W")
        assert w.is_external is False
        assert w.load_bearing is False


class TestE044EdgeBased:
    def test_west_facade_room_passes(self):
        errors = validate_all_phases(_base_building(external=True))
        assert not [e for e in _codes(errors, "E044") if "Living" in e.message]

    def test_south_facade_room_passes(self):
        errors = validate_all_phases(_base_building(external=True))
        assert not [e for e in _codes(errors, "E044") if "Kitchen" in e.message]

    def test_interior_room_fails(self):
        errors = validate_all_phases(_base_building(external=True))
        assert [e for e in _codes(errors, "E044") if "Bedroom" in e.message]

    def test_service_rooms_never_flagged(self):
        errors = validate_all_phases(_base_building(external=True))
        e044 = _codes(errors, "E044")
        assert not [e for e in e044 if "Bath" in e.message or "Hall" in e.message]

    def test_l_footprint_notch_edge_passes(self):
        """Room whose ONLY exterior contact is a notch segment (villa master)."""
        b = _base_building(external=True)
        # Carve an L: notch wall segment along bedroom north edge, external
        b.add_wall(GF, (3, 6), (7, 6), height=3.0, thickness=0.3, name="Notch",
                   is_external=True)
        errors = validate_all_phases(b)
        assert not [e for e in _codes(errors, "E044") if "Bedroom" in e.message]

    def test_no_external_walls_emits_single_w046(self):
        errors = validate_all_phases(_base_building(external=False))
        w046 = _codes(errors, "W046")
        assert len(w046) == 1
        assert w046[0].severity == "warning"
        assert not _codes(errors, "E044")


class TestRegressionRealProjects:
    def test_block_projects_have_no_facade_errors(self):
        """The E044 rewrite must not flag any block-project room.

        (Blocks do carry waived E090 data findings — see their
        validation.json — so this asserts specifically on E044.)
        """
        for name in ("3apt-corner-core", "4apt-centered-core"):
            b = Building.load(PROJECTS / name / "building.json")
            e044 = [e for e in validate_all_phases(b)
                    if e.message.startswith("E044:")]
            assert e044 == [], f"{name}: {[e.message for e in e044]}"

    def test_villa_has_no_e044_false_positives(self):
        b = Building.load(PROJECTS / "villa-maketa" / "building.json")
        errors = validate_all_phases(b)
        assert not _codes(errors, "E044")
