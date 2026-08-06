"""E052 — door/window opening must not clash with another storey's slab.

Spec: specs/storey-datum.md. Openings are 3D volumes (z-range × the
opening's 2D footprint of width × wall thickness); slabs hang below their
storey datum ([elevation − thickness, elevation]). Strict overlap in both
axes is an error; surface/edge contact is legal. Fixtures are test-owned
per specs/test-fixtures.md.
"""

from archicad_builder.models import (
    Building,
    Door,
    Point2D,
    Polygon2D,
    Slab,
    Story,
    Wall,
    Window,
)
from archicad_builder.validators.phases import validate_phase6_vertical


def _e052(building: Building) -> list:
    return [e for e in validate_phase6_vertical(building)
            if "E052" in e.message]


def _slab(vertices: list[tuple[float, float]], thickness: float = 0.3) -> Slab:
    return Slab(
        name="Slab",
        outline=Polygon2D(vertices=[Point2D(x=x, y=y) for x, y in vertices]),
        thickness=thickness,
    )


def _two_storey(
    door_height: float,
    upper_elevation: float,
    upper_slab: Slab,
) -> Building:
    """Ground storey with one south wall + door; upper storey with a slab
    hanging below its datum ([upper_elevation − t, upper_elevation])."""
    wall = Wall(
        name="South", start=Point2D(x=0, y=0), end=Point2D(x=6, y=0),
        height=3.0, thickness=0.25,
    )
    door = Door(
        name="Tall Door", wall_id=wall.global_id,
        position=2.5, width=0.9, height=door_height,
    )
    ground = Story(
        name="Ground", elevation=0.0, height=3.0,
        walls=[wall], doors=[door],
        slabs=[_slab([(0, -1), (6, -1), (6, 4), (0, 4)], thickness=0.25)],
    )
    upper = Story(
        name="Upper", elevation=upper_elevation, height=3.0,
        slabs=[upper_slab],
    )
    return Building(name="Fixture", stories=[ground, upper])


FULL_FOOTPRINT = [(0, -1), (6, -1), (6, 4), (0, 4)]


class TestE052Clash:
    def test_upper_slab_dipping_into_tall_door_errors(self):
        # Upper slab [2.2, 2.5] vs door [0, 2.8] → 0.3 m of penetration
        b = _two_storey(2.8, 2.5, _slab(FULL_FOOTPRINT, thickness=0.3))
        errors = _e052(b)
        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert errors[0].element_type == "Door"
        assert "Tall Door" in errors[0].message

    def test_window_dipping_into_upper_slab_errors(self):
        b = _two_storey(2.1, 2.5, _slab(FULL_FOOTPRINT, thickness=0.3))
        b.stories[0].windows.append(Window(
            name="Tall Window", wall_id=b.stories[0].walls[0].global_id,
            position=0.5, width=1.0, height=1.5, sill_height=0.9,
        ))  # window z [0.9, 2.4] vs slab [2.2, 2.5]
        errors = _e052(b)
        assert len(errors) == 1
        assert errors[0].element_type == "Window"

    def test_door_touching_slab_bottom_is_legal(self):
        # Door top 2.2 == slab bottom 2.2 — contact, not penetration
        b = _two_storey(2.2, 2.5, _slab(FULL_FOOTPRINT, thickness=0.3))
        assert _e052(b) == []

    def test_penetration_below_epsilon_is_legal(self):
        b = _two_storey(2.2 + 5e-7, 2.5, _slab(FULL_FOOTPRINT, thickness=0.3))
        assert _e052(b) == []

    def test_slab_footprint_missing_the_opening_is_legal(self):
        far = _slab([(10, -1), (16, -1), (16, 4), (10, 4)], thickness=0.3)
        b = _two_storey(2.8, 2.5, far)
        assert _e052(b) == []

    def test_slab_edge_flush_with_wall_face_is_contact_not_clash(self):
        # Slab starts exactly at the wall's inner face (y = 0.125):
        # footprints share an edge, zero area — legal.
        flush = _slab([(0, 0.125), (6, 0.125), (6, 4), (0, 4)], thickness=0.3)
        b = _two_storey(2.8, 2.5, flush)
        assert _e052(b) == []

    def test_slab_overlapping_half_the_wall_thickness_errors(self):
        # Slab reaches only to y = 0.05 — it never touches the wall
        # CENTERLINE (y = 0) but does cut the opening's inner half.
        # A centerline test would silently pass this (plan review).
        half = _slab([(0, 0.05), (6, 0.05), (6, 4), (0, 4)], thickness=0.3)
        b = _two_storey(2.8, 2.5, half)
        assert len(_e052(b)) == 1

    def test_diagonal_wall_opening_footprint(self):
        wall = Wall(
            name="Diagonal", start=Point2D(x=0, y=0), end=Point2D(x=4, y=3),
            height=3.0, thickness=0.25,
        )
        door = Door(
            name="Diag Door", wall_id=wall.global_id,
            position=1.0, width=1.0, height=2.8,
        )
        ground = Story(name="Ground", elevation=0.0, height=3.0,
                       walls=[wall], doors=[door])
        upper = Story(
            name="Upper", elevation=2.5, height=3.0,
            slabs=[_slab([(0.5, 0.0), (2.0, 0.0), (2.0, 2.0), (0.5, 2.0)],
                         thickness=0.3)],
        )
        b = Building(name="Fixture", stories=[ground, upper])
        assert len(_e052(b)) == 1

    def test_dangling_wall_id_is_skipped(self):
        b = _two_storey(2.8, 2.5, _slab(FULL_FOOTPRINT, thickness=0.3))
        b.stories[0].doors[0].wall_id = "NO-SUCH-WALL"
        # structural validation owns the dangling reference finding
        assert _e052(b) == []

    def test_self_intersecting_slab_outline_does_not_crash(self):
        # Polygon2D permits bowties; Shapely raises GEOSException on them
        # unless normalized (Codex review 2026-08-06). The bowtie's lobes
        # meet at (3, 1.5); its left lobe covers y=0 only for x < 1.2, so
        # the door moves there — the clash must still be found, not crash.
        bowtie = _slab([(0, -1), (6, 4), (6, -1), (0, 4)], thickness=0.3)
        b = _two_storey(2.8, 2.5, bowtie)
        b.stories[0].doors[0].position = 0.2
        assert len(_e052(b)) == 1

    def test_same_storey_slab_never_clashes(self):
        # All slabs top out at their own datum and sills are >= 0 —
        # same-storey contact is the CORRECT geometry.
        wall = Wall(name="S", start=Point2D(x=0, y=0), end=Point2D(x=6, y=0),
                    height=3.0, thickness=0.25)
        door = Door(name="D", wall_id=wall.global_id,
                    position=1.0, width=0.9, height=2.1)
        story = Story(name="Only", elevation=0.0, height=3.0,
                      walls=[wall], doors=[door],
                      slabs=[_slab(FULL_FOOTPRINT, thickness=0.25)])
        assert _e052(Building(name="Fixture", stories=[story])) == []
