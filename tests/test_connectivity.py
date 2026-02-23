"""Tests for wall connectivity validation and endpoint snapping."""

import pytest

from archicad_builder.models.building import Building
from archicad_builder.validators.connectivity import (
    find_connections,
    validate_connectivity,
)
from archicad_builder.validators.snap import snap_endpoints


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def connected_box() -> Building:
    """4 walls forming a perfect box — all connected."""
    b = Building(name="Box")
    b.add_story("GF", height=2.7)
    b.add_wall("GF", (0, 0), (6, 0), height=2.7, thickness=0.3, name="South")
    b.add_wall("GF", (6, 0), (6, 4), height=2.7, thickness=0.3, name="East")
    b.add_wall("GF", (6, 4), (0, 4), height=2.7, thickness=0.3, name="North")
    b.add_wall("GF", (0, 4), (0, 0), height=2.7, thickness=0.3, name="West")
    return b


@pytest.fixture
def gapped_box() -> Building:
    """4 walls with small gaps (Gemini-style coordinate drift)."""
    b = Building(name="Gapped Box")
    b.add_story("GF", height=2.7)
    b.add_wall("GF", (0, 0), (6, 0), height=2.7, thickness=0.3, name="South")
    b.add_wall("GF", (6.01, 0.01), (6, 4), height=2.7, thickness=0.3, name="East")  # small gap
    b.add_wall("GF", (6, 4.015), (0, 4), height=2.7, thickness=0.3, name="North")  # small gap
    b.add_wall("GF", (0, 4), (0.005, 0.005), height=2.7, thickness=0.3, name="West")  # small gap
    return b


@pytest.fixture
def t_junction() -> Building:
    """Walls with a T-junction (interior wall meets exterior)."""
    b = Building(name="T-Junction")
    b.add_story("GF", height=2.7)
    b.add_wall("GF", (0, 0), (10, 0), height=2.7, thickness=0.3, name="Bottom")
    b.add_wall("GF", (5, 0), (5, 5), height=2.7, thickness=0.1, name="Interior")  # T-junction at (5,0)
    return b


@pytest.fixture
def disconnected_wall() -> Building:
    """A wall floating in space with a big gap."""
    b = Building(name="Disconnected")
    b.add_story("GF", height=2.7)
    b.add_wall("GF", (0, 0), (6, 0), height=2.7, thickness=0.3, name="South")
    b.add_wall("GF", (0, 0), (0, 4), height=2.7, thickness=0.3, name="West")
    b.add_wall("GF", (10, 10), (15, 10), height=2.7, thickness=0.1, name="Floating")  # disconnected
    return b


# ── Connectivity validation tests ─────────────────────────────────


def test_connected_box_no_errors(connected_box: Building):
    """Perfect box should have zero connectivity errors."""
    errors = validate_connectivity(connected_box.stories[0])
    assert len(errors) == 0


def test_gapped_box_has_warnings(gapped_box: Building):
    """Gapped box should detect gaps as warnings."""
    errors = validate_connectivity(gapped_box.stories[0], tolerance=0.001)
    # With very tight tolerance, gaps should be flagged
    assert len(errors) > 0
    assert all(e.severity == "warning" for e in errors)


def test_gapped_box_ok_with_tolerance(gapped_box: Building):
    """Gapped box within tolerance should pass."""
    errors = validate_connectivity(gapped_box.stories[0], tolerance=0.02)
    assert len(errors) == 0


def test_t_junction_detected(t_junction: Building):
    """T-junction should be found as a valid connection."""
    connections, errors = find_connections(t_junction.stories[0])
    # Interior wall start at (5,0) connects to Bottom wall's body (T-junction)
    body_connections = [c for c in connections if c.wall2_end == "body"]
    assert len(body_connections) > 0
    # The open endpoints (W1 start/end, W2 end) correctly produce warnings
    assert len(errors) == 3  # 3 open endpoints in a 2-wall T-junction


def test_disconnected_wall_flagged(disconnected_wall: Building):
    """Floating wall should produce connectivity warnings."""
    errors = validate_connectivity(disconnected_wall.stories[0], tolerance=0.1)
    # "Floating" wall's both endpoints are far from everything
    floating_errors = [e for e in errors if "Floating" in e.message or "W3" in e.message]
    assert len(floating_errors) > 0


def test_find_connections_corner_junctions(connected_box: Building):
    """Perfect box should find 8 connections (2 per wall, 4 walls)."""
    connections, errors = find_connections(connected_box.stories[0])
    assert len(errors) == 0
    # Each wall has 2 endpoints, each connecting to an adjacent wall
    assert len(connections) == 8


# ── Snap tests ────────────────────────────────────────────────────


def test_snap_fixes_gaps(gapped_box: Building):
    """Snapping should fix small gaps."""
    story = gapped_box.stories[0]

    # Before snap: should have gaps
    errors_before = validate_connectivity(story, tolerance=0.001)
    assert len(errors_before) > 0

    # Snap
    snaps = snap_endpoints(story, tolerance=0.02)
    assert len(snaps) > 0

    # After snap: should be clean
    errors_after = validate_connectivity(story, tolerance=0.001)
    assert len(errors_after) == 0


def test_snap_doesnt_change_connected(connected_box: Building):
    """Snapping a perfect box should change nothing."""
    story = connected_box.stories[0]
    snaps = snap_endpoints(story, tolerance=0.02)
    assert len(snaps) == 0


def test_snap_respects_tolerance():
    """Snap should not merge points beyond tolerance."""
    b = Building(name="Far")
    b.add_story("GF", height=2.7)
    b.add_wall("GF", (0, 0), (6, 0), height=2.7, thickness=0.3, name="A")
    b.add_wall("GF", (6.1, 0), (6.1, 4), height=2.7, thickness=0.3, name="B")

    story = b.stories[0]
    snaps = snap_endpoints(story, tolerance=0.02)
    # 0.1m gap is beyond 0.02m tolerance — should NOT snap
    assert len(snaps) == 0


def test_snap_result_fields(gapped_box: Building):
    """Snap results should have correct field values."""
    story = gapped_box.stories[0]
    snaps = snap_endpoints(story, tolerance=0.02)

    for snap in snaps:
        assert snap.wall_tag  # has a tag
        assert snap.end in ("start", "end")
        assert snap.old != snap.new  # actually moved
        assert snap.snapped_to_wall  # target wall


# ── Building.snap_endpoints integration ───────────────────────────


def test_building_snap_method(gapped_box: Building):
    """Building.snap_endpoints() should work as a convenience method."""
    snaps = gapped_box.snap_endpoints("GF", tolerance=0.02)
    assert len(snaps) > 0

    # Validate should now pass
    errors = gapped_box.validate()
    connectivity_errors = [e for e in errors if "no connection" in str(e)]
    assert len(connectivity_errors) == 0


# ── Building.validate integration ─────────────────────────────────


def test_validate_includes_connectivity(disconnected_wall: Building):
    """Building.validate() should include connectivity checks."""
    errors = disconnected_wall.validate()
    # Should have connectivity warnings for the floating wall
    connectivity_errors = [e for e in errors if "no connection" in str(e.message)]
    assert len(connectivity_errors) > 0


def test_validate_connected_box_clean(connected_box: Building):
    """Building.validate() on a perfect box should have no structural/connectivity errors."""
    errors = connected_box.validate()
    # Filter out building-level errors (slab completeness, staircase) — this test
    # is specifically about wall connectivity
    connectivity_errors = [
        e for e in errors
        if e.element_type == "Wall" or "connectivity" in e.message.lower()
    ]
    assert len(connectivity_errors) == 0
