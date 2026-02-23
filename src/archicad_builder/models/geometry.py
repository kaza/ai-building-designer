"""Geometric primitives for building elements."""

from __future__ import annotations

import math

from pydantic import BaseModel, field_validator


class Point2D(BaseModel):
    """2D point in the XY plane (meters)."""

    x: float
    y: float

    def distance_to(self, other: Point2D) -> float:
        """Euclidean distance to another point."""
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Point2D):
            return NotImplemented
        return math.isclose(self.x, other.x, abs_tol=1e-6) and math.isclose(
            self.y, other.y, abs_tol=1e-6
        )

    def __hash__(self) -> int:
        return hash((round(self.x, 6), round(self.y, 6)))


class Point3D(BaseModel):
    """3D point (meters)."""

    x: float
    y: float
    z: float

    def distance_to(self, other: Point3D) -> float:
        """Euclidean distance to another point."""
        return math.sqrt(
            (self.x - other.x) ** 2
            + (self.y - other.y) ** 2
            + (self.z - other.z) ** 2
        )


class Polygon2D(BaseModel):
    """Closed polygon in the XY plane. Minimum 3 vertices. Auto-closes (no need to repeat first vertex)."""

    vertices: list[Point2D]

    @field_validator("vertices")
    @classmethod
    def at_least_3_vertices(cls, v: list[Point2D]) -> list[Point2D]:
        if len(v) < 3:
            raise ValueError("Polygon must have at least 3 vertices")
        return v

    @property
    def area(self) -> float:
        """Compute area using the shoelace formula. Returns absolute value."""
        n = len(self.vertices)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += self.vertices[i].x * self.vertices[j].y
            area -= self.vertices[j].x * self.vertices[i].y
        return abs(area) / 2.0

    @property
    def perimeter(self) -> float:
        """Total perimeter length."""
        n = len(self.vertices)
        return sum(
            self.vertices[i].distance_to(self.vertices[(i + 1) % n]) for i in range(n)
        )
