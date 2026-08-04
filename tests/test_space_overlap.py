"""Tests for E090 space-overlap validation (specs/space-overlap.md)."""
from archicad_builder.models.building import Building
from archicad_builder.models.spaces import Apartment, RoomType
from archicad_builder.validators.spaces import validate_space_overlaps

from .factories import GF, make_defect_building, rect_boundary, rect_space


def _building_with(spaces_a, spaces_b=None) -> Building:
    b = Building(name="Overlap Fixture")
    b.add_story(GF, height=3.0)
    story = b.get_story(GF)
    story.apartments.append(Apartment(
        name="Apt A", boundary=rect_boundary(0, 0, 6, 6), spaces=spaces_a))
    if spaces_b is not None:
        story.apartments.append(Apartment(
            name="Apt B", boundary=rect_boundary(6, 0, 12, 6), spaces=spaces_b))
    return b


class TestE090:
    def test_overlapping_spaces_flagged_with_area(self):
        b = _building_with([
            rect_space("Kitchen", RoomType.KITCHEN, 0, 0, 3.5, 3),
            rect_space("Bedroom", RoomType.BEDROOM, 3, 0, 6, 3),  # 0.5m overlap
        ])
        errors = validate_space_overlaps(b)
        assert len(errors) == 1
        e = errors[0]
        assert e.severity == "error"
        assert e.message.startswith("E090:")
        assert "Kitchen" in e.message and "Bedroom" in e.message
        assert "1.5" in e.message  # 0.5 x 3.0 m

    def test_touching_spaces_clean(self):
        b = _building_with([
            rect_space("Kitchen", RoomType.KITCHEN, 0, 0, 3, 3),
            rect_space("Bedroom", RoomType.BEDROOM, 3, 0, 6, 3),  # shared edge
        ])
        assert validate_space_overlaps(b) == []

    def test_cross_apartment_overlap_flagged(self):
        b = _building_with(
            [rect_space("A Living", RoomType.LIVING, 0, 0, 6.5, 6)],
            [rect_space("B Living", RoomType.LIVING, 6, 0, 12, 6)],
        )
        errors = validate_space_overlaps(b)
        assert len(errors) == 1
        assert "A Living" in errors[0].message
        assert "B Living" in errors[0].message

    def test_sliver_below_tolerance_ignored(self):
        b = _building_with([
            rect_space("Kitchen", RoomType.KITCHEN, 0, 0, 3.01, 3),  # 0.03 m2
            rect_space("Bedroom", RoomType.BEDROOM, 3, 0, 6, 3),
        ])
        assert validate_space_overlaps(b) == []

    def test_defect_fixture_is_overlap_clean(self):
        assert validate_space_overlaps(make_defect_building()) == []

    def test_bowtie_polygon_still_detected(self):
        """Self-intersecting (bow-tie) ring is repaired by make_valid and
        both lobes still participate in overlap detection — buffer(0)
        used to silently drop one lobe."""
        from archicad_builder.models.geometry import Point2D, Polygon2D
        from archicad_builder.models.spaces import Space
        bowtie = Space(name="Bowtie", room_type=RoomType.LIVING,
                       boundary=Polygon2D(vertices=[
                           Point2D(x=0, y=0), Point2D(x=4, y=4),
                           Point2D(x=4, y=0), Point2D(x=0, y=4)]))
        b = _building_with([
            bowtie,
            rect_space("Bedroom", RoomType.BEDROOM, 2.5, 0, 6, 4),
        ])
        errors = validate_space_overlaps(b)
        assert len(errors) == 1
        assert "Bowtie" in errors[0].message


class TestE090RealProjects:
    def test_villa_is_overlap_clean(self):
        from pathlib import Path
        b = Building.load(Path(__file__).parent.parent / "projects"
                          / "villa-maketa" / "building.json")
        assert validate_space_overlaps(b) == []

    def test_generator_produces_overlap_free_buildings(self):
        from archicad_builder.generators.building_4apt import generate_building_4apt
        assert validate_space_overlaps(generate_building_4apt()) == []
