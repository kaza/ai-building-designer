"""Tests for geometric primitives."""

import math

import pytest

from archicad_builder.models.geometry import Point2D, Point3D, Polygon2D


class TestPoint2D:
    def test_create(self):
        p = Point2D(x=1.0, y=2.0)
        assert p.x == 1.0
        assert p.y == 2.0

    def test_distance(self):
        p1 = Point2D(x=0.0, y=0.0)
        p2 = Point2D(x=3.0, y=4.0)
        assert math.isclose(p1.distance_to(p2), 5.0)

    def test_equality(self):
        p1 = Point2D(x=1.0, y=2.0)
        p2 = Point2D(x=1.0, y=2.0)
        assert p1 == p2

    def test_equality_tolerance(self):
        p1 = Point2D(x=1.0, y=2.0)
        p2 = Point2D(x=1.0000001, y=2.0000001)
        assert p1 == p2

    def test_inequality(self):
        p1 = Point2D(x=1.0, y=2.0)
        p2 = Point2D(x=1.0, y=3.0)
        assert p1 != p2

    def test_hash_equal_points(self):
        p1 = Point2D(x=1.0, y=2.0)
        p2 = Point2D(x=1.0, y=2.0)
        assert hash(p1) == hash(p2)
        assert len({p1, p2}) == 1


class TestPoint3D:
    def test_create(self):
        p = Point3D(x=1.0, y=2.0, z=3.0)
        assert p.z == 3.0

    def test_distance(self):
        p1 = Point3D(x=0.0, y=0.0, z=0.0)
        p2 = Point3D(x=1.0, y=2.0, z=2.0)
        assert math.isclose(p1.distance_to(p2), 3.0)


class TestPolygon2D:
    def test_triangle(self):
        poly = Polygon2D(
            vertices=[
                Point2D(x=0, y=0),
                Point2D(x=4, y=0),
                Point2D(x=0, y=3),
            ]
        )
        assert math.isclose(poly.area, 6.0)

    def test_rectangle(self):
        poly = Polygon2D(
            vertices=[
                Point2D(x=0, y=0),
                Point2D(x=10, y=0),
                Point2D(x=10, y=5),
                Point2D(x=0, y=5),
            ]
        )
        assert math.isclose(poly.area, 50.0)

    def test_perimeter(self):
        poly = Polygon2D(
            vertices=[
                Point2D(x=0, y=0),
                Point2D(x=10, y=0),
                Point2D(x=10, y=5),
                Point2D(x=0, y=5),
            ]
        )
        assert math.isclose(poly.perimeter, 30.0)

    def test_min_vertices(self):
        with pytest.raises(ValueError, match="at least 3"):
            Polygon2D(vertices=[Point2D(x=0, y=0), Point2D(x=1, y=0)])
