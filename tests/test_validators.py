"""Tests for structural validation."""

from archicad_builder.models import Door, Point2D, Story, Wall, Window, generate_ifc_id
from archicad_builder.validators.structural import validate_story


class TestDoorValidation:
    def test_door_orphan_wall(self):
        """Door referencing non-existent wall → error."""
        story = Story(
            name="GF",
            height=3.0,
            doors=[Door(wall_id=generate_ifc_id(), position=0, width=0.9, height=2.1)],
        )
        errors = validate_story(story)
        assert len(errors) == 1
        assert "non-existent wall" in errors[0].message

    def test_door_exceeds_wall_length(self):
        """Door positioned past wall end → error."""
        wall = Wall(
            start=Point2D(x=0, y=0),
            end=Point2D(x=3, y=0),
            height=3.0,
            thickness=0.2,
        )
        story = Story(
            name="GF",
            height=3.0,
            walls=[wall],
            doors=[Door(wall_id=wall.global_id, position=2.5, width=0.9, height=2.1)],
        )
        errors = validate_story(story)
        assert len(errors) == 1
        assert "extends past wall end" in errors[0].message

    def test_door_exceeds_wall_height(self):
        """Door taller than wall → error."""
        wall = Wall(
            start=Point2D(x=0, y=0),
            end=Point2D(x=5, y=0),
            height=2.0,
            thickness=0.2,
        )
        story = Story(
            name="GF",
            height=3.0,
            walls=[wall],
            doors=[Door(wall_id=wall.global_id, position=0, width=0.9, height=2.5)],
        )
        errors = validate_story(story)
        assert len(errors) == 1
        assert "exceeds wall height" in errors[0].message

    def test_valid_door(self):
        """Properly placed door → no errors."""
        wall = Wall(
            start=Point2D(x=0, y=0),
            end=Point2D(x=5, y=0),
            height=3.0,
            thickness=0.2,
        )
        story = Story(
            name="GF",
            height=3.0,
            walls=[wall],
            doors=[Door(wall_id=wall.global_id, position=1.0, width=0.9, height=2.1)],
        )
        errors = validate_story(story)
        assert len(errors) == 0


    def test_overlapping_doors_on_same_wall(self):
        """Two doors overlapping on the same wall → error."""
        wall = Wall(
            start=Point2D(x=0, y=0),
            end=Point2D(x=5, y=0),
            height=3.0,
            thickness=0.2,
        )
        story = Story(
            name="GF",
            height=3.0,
            walls=[wall],
            doors=[
                Door(
                    wall_id=wall.global_id,
                    position=0.3,
                    width=0.8,
                    height=2.1,
                    name="Door A",
                ),
                Door(
                    wall_id=wall.global_id,
                    position=0.5,
                    width=0.8,
                    height=2.1,
                    name="Door B",
                ),
            ],
        )
        errors = validate_story(story)
        overlap_errors = [e for e in errors if "overlaps with" in e.message]
        assert len(overlap_errors) == 1
        assert "0.60m" in overlap_errors[0].message

    def test_non_overlapping_doors_on_same_wall(self):
        """Two doors side by side on the same wall → no overlap error."""
        wall = Wall(
            start=Point2D(x=0, y=0),
            end=Point2D(x=5, y=0),
            height=3.0,
            thickness=0.2,
        )
        story = Story(
            name="GF",
            height=3.0,
            walls=[wall],
            doors=[
                Door(
                    wall_id=wall.global_id,
                    position=0.3,
                    width=0.8,
                    height=2.1,
                    name="Door A",
                ),
                Door(
                    wall_id=wall.global_id,
                    position=1.5,
                    width=0.8,
                    height=2.1,
                    name="Door B",
                ),
            ],
        )
        errors = validate_story(story)
        overlap_errors = [e for e in errors if "overlaps with" in e.message]
        assert len(overlap_errors) == 0

    def test_door_window_overlap_on_same_wall(self):
        """Door overlapping with window on same wall → error."""
        wall = Wall(
            start=Point2D(x=0, y=0),
            end=Point2D(x=5, y=0),
            height=3.0,
            thickness=0.2,
        )
        story = Story(
            name="GF",
            height=3.0,
            walls=[wall],
            doors=[
                Door(
                    wall_id=wall.global_id,
                    position=1.0,
                    width=0.9,
                    height=2.1,
                    name="Front Door",
                )
            ],
            windows=[
                Window(
                    wall_id=wall.global_id,
                    position=1.5,
                    width=1.2,
                    height=1.5,
                    name="Side Window",
                )
            ],
        )
        errors = validate_story(story)
        overlap_errors = [e for e in errors if "overlaps with window" in e.message]
        assert len(overlap_errors) == 1


    def test_door_crosses_perpendicular_wall(self):
        """Door opening that crosses through another wall → error."""
        # Horizontal wall
        h_wall = Wall(
            start=Point2D(x=0, y=5),
            end=Point2D(x=10, y=5),
            height=3.0,
            thickness=0.2,
            name="Horizontal Wall",
        )
        # Vertical wall starting at (4, 5) going north
        v_wall = Wall(
            start=Point2D(x=4, y=5),
            end=Point2D(x=4, y=10),
            height=3.0,
            thickness=0.1,
            name="Perpendicular Wall",
        )
        # Door at position 3.5, width 1.0 → spans x=3.5 to x=4.5 → crosses v_wall at x=4
        story = Story(
            name="GF",
            height=3.0,
            walls=[h_wall, v_wall],
            doors=[
                Door(
                    wall_id=h_wall.global_id,
                    position=3.5,
                    width=1.0,
                    height=2.1,
                    name="Bad Door",
                )
            ],
        )
        errors = validate_story(story)
        cross_errors = [e for e in errors if "crosses wall" in e.message]
        assert len(cross_errors) == 1
        assert "Perpendicular Wall" in cross_errors[0].message

    def test_door_does_not_cross_distant_wall(self):
        """Door opening that doesn't cross any wall → no error."""
        h_wall = Wall(
            start=Point2D(x=0, y=5),
            end=Point2D(x=10, y=5),
            height=3.0,
            thickness=0.2,
            name="Horizontal Wall",
        )
        v_wall = Wall(
            start=Point2D(x=8, y=5),
            end=Point2D(x=8, y=10),
            height=3.0,
            thickness=0.1,
            name="Far Wall",
        )
        # Door at position 1.0, width 0.9 → spans x=1.0 to x=1.9 → far from v_wall
        story = Story(
            name="GF",
            height=3.0,
            walls=[h_wall, v_wall],
            doors=[
                Door(
                    wall_id=h_wall.global_id,
                    position=1.0,
                    width=0.9,
                    height=2.1,
                    name="Good Door",
                )
            ],
        )
        errors = validate_story(story)
        cross_errors = [e for e in errors if "crosses wall" in e.message]
        assert len(cross_errors) == 0


    def test_wall_crosses_through_staircase(self):
        """Wall passing through staircase area → error."""
        # Staircase walls define the zone
        stair_south = Wall(
            start=Point2D(x=5, y=5),
            end=Point2D(x=8, y=5),
            height=3.0, thickness=0.2, name="Staircase South Wall",
        )
        stair_north = Wall(
            start=Point2D(x=5, y=8),
            end=Point2D(x=8, y=8),
            height=3.0, thickness=0.2, name="Staircase North Wall",
        )
        stair_west = Wall(
            start=Point2D(x=5, y=5),
            end=Point2D(x=5, y=8),
            height=3.0, thickness=0.2, name="Staircase West Wall",
        )
        stair_east = Wall(
            start=Point2D(x=8, y=5),
            end=Point2D(x=8, y=8),
            height=3.0, thickness=0.2, name="Staircase East Wall",
        )
        # Apartment partition wall crossing through staircase
        partition = Wall(
            start=Point2D(x=6.5, y=0),
            end=Point2D(x=6.5, y=10),
            height=3.0, thickness=0.1, name="Apt Partition",
        )
        story = Story(
            name="GF", height=3.0,
            walls=[stair_south, stair_north, stair_west, stair_east, partition],
        )
        errors = validate_story(story)
        cross_errors = [e for e in errors if "crosses through" in e.message]
        assert len(cross_errors) >= 1
        assert "staircase" in cross_errors[0].message.lower()


class TestWindowValidation:
    def test_window_orphan_wall(self):
        """Window referencing non-existent wall → error."""
        story = Story(
            name="GF",
            height=3.0,
            windows=[
                Window(wall_id=generate_ifc_id(), position=0, width=1.2, height=1.5)
            ],
        )
        errors = validate_story(story)
        assert len(errors) == 1
        assert "non-existent wall" in errors[0].message

    def test_window_top_exceeds_wall(self):
        """Window sill + height > wall height → error."""
        wall = Wall(
            start=Point2D(x=0, y=0),
            end=Point2D(x=5, y=0),
            height=2.5,
            thickness=0.2,
        )
        story = Story(
            name="GF",
            height=3.0,
            walls=[wall],
            windows=[
                Window(
                    wall_id=wall.global_id,
                    position=1.0,
                    width=1.2,
                    height=1.5,
                    sill_height=1.5,
                )
            ],
        )
        errors = validate_story(story)
        assert len(errors) == 1
        assert "exceeds wall height" in errors[0].message

    def test_valid_window(self):
        """Properly placed window → no errors."""
        wall = Wall(
            start=Point2D(x=0, y=0),
            end=Point2D(x=5, y=0),
            height=3.0,
            thickness=0.2,
        )
        story = Story(
            name="GF",
            height=3.0,
            walls=[wall],
            windows=[
                Window(
                    wall_id=wall.global_id,
                    position=1.0,
                    width=1.2,
                    height=1.5,
                    sill_height=0.9,
                )
            ],
        )
        errors = validate_story(story)
        assert len(errors) == 0
