"""FEM X-ray solver gates (specs/fem-xray.md, Acceptance).

Closed-form benchmarks against raw PyNite with the boundary-condition
recipe the fem package uses (in-plane DOFs fixed everywhere — quads have
no drilling stiffness — DZ pinned on support edges). If these fail, the
solver dependency or the recipe broke; nothing project-specific here.
Units: kN, m. Experiment origin: 2026-08-08_pynite-plate-oracle.
"""

import pytest
from Pynite import FEModel3D

E = 31e6
NU = 0.2
G = E / (2 * (1 + NU))


def _strip_model(length, width, t, q, mesh):
    m = FEModel3D()
    m.add_material("C25", E, G, NU, rho=0.0)
    m.add_rectangle_mesh("M", mesh, length, width, t, "C25", plane="XY")
    m.meshes["M"].generate()
    for qname in m.quads:
        m.add_quad_surface_pressure(qname, q, case="Q")
    m.add_load_combo("C", {"Q": 1.0})
    return m


def test_simply_supported_strip_matches_closed_form():
    L, W, t, q = 4.0, 1.0, 0.20, 10.0
    m = _strip_model(L, W, t, q, 0.125)
    for node in m.nodes.values():
        pinned = abs(node.X) < 1e-9 or abs(node.X - L) < 1e-9
        m.def_support(node.name, True, True, pinned, False, False, True)
    m.analyze_linear()

    mid = next(n for n in m.nodes.values()
               if abs(n.X - L / 2) < 1e-6 and abs(n.Y - W / 2) < 1e-6)
    mx = max(abs(quad.moment(0, 0, combo_name="C")[0][0])
             for quad in m.quads.values())
    I = t**3 / 12
    assert mx == pytest.approx(q * L**2 / 8, rel=0.10)
    assert abs(mid.DZ["C"]) == pytest.approx(5 * q * L**4 / (384 * E * I), rel=0.10)
    rz = sum(n.RxnFZ["C"] for n in m.nodes.values() if n.support_DZ)
    assert abs(rz) == pytest.approx(q * L * W, rel=0.01)


def test_cantilever_strip_matches_closed_form():
    L, W, t, q = 2.0, 1.0, 0.20, 10.0
    m = _strip_model(L, W, t, q, 0.10)
    for node in m.nodes.values():
        if abs(node.X) < 1e-9:
            m.def_support(node.name, True, True, True, True, True, True)
        else:
            m.def_support(node.name, True, True, False, False, False, True)
    m.analyze_linear()

    tip = next(n for n in m.nodes.values()
               if abs(n.X - L) < 1e-6 and abs(n.Y - W / 2) < 1e-6)
    root = max(abs(quad.moment(-1, 0, combo_name="C")[0][0])
               for quad in m.quads.values()
               if min(n.X for n in (quad.i_node, quad.j_node,
                                    quad.m_node, quad.n_node)) < 1e-9)
    I = t**3 / 12
    assert root == pytest.approx(q * L**2 / 2, rel=0.10)
    assert abs(tip.DZ["C"]) == pytest.approx(q * L**4 / (8 * E * I), rel=0.10)


def test_deep_plate_beam_station_moment_matches_closed_form():
    """The beam-extraction path (gate 5, Codex plan review): a beam
    modeled as a deep plate strip, loaded in-plane, its section moment
    recovered by integrating horizontal membrane stress over the depth
    — the same math archicad_builder.fem uses for ring beams."""
    L, d, t, q = 3.0, 0.5, 0.30, 40.0     # kN/m line load on top edge
    m = FEModel3D()
    m.add_material("C25", E, G, NU, rho=0.0)
    m.add_rectangle_mesh("M", 0.0625, L, d, t, "C25", plane="XY")
    m.meshes["M"].generate()
    top = sorted((n for n in m.nodes.values() if abs(n.Y - d) < 1e-9),
                 key=lambda n: n.X)
    for i, node in enumerate(top):
        trib = (top[min(i + 1, len(top) - 1)].X - top[max(i - 1, 0)].X) / 2
        m.add_node_load(node.name, "FY", -q * trib, case="Q")
    for node in m.nodes.values():
        end = abs(node.X) < 1e-9 or abs(node.X - L) < 1e-9
        bottom = abs(node.Y) < 1e-9
        m.def_support(node.name, end and bottom and node.X < 1e-9,
                      end and bottom, True, True, True, False)
    m.add_load_combo("C", {"Q": 1.0})
    m.analyze_linear()

    z_mid = d / 2
    stations = {}
    for quad in m.quads.values():
        nds = (quad.i_node, quad.j_node, quad.m_node, quad.n_node)
        xc = sum(n.X for n in nds) / 4
        yc = sum(n.Y for n in nds) / 4
        h = max(n.Y for n in nds) - min(n.Y for n in nds)
        sx = float(quad.membrane(0, 0, combo_name="C")[0][0])
        stations.setdefault(round(xc, 4), []).append((sx, yc, h))
    moments = {x: sum(sx * t * h * (yc - z_mid) for sx, yc, h in sams)
               for x, sams in stations.items()}
    m_mid = max(abs(v) for x, v in moments.items() if abs(x - L / 2) < 0.2)
    assert m_mid == pytest.approx(q * L**2 / 8, rel=0.10)


def test_two_span_continuous_matches_closed_form():
    L, W, t, q = 4.0, 1.0, 0.20, 10.0
    m = _strip_model(2 * L, W, t, q, 0.125)
    for node in m.nodes.values():
        pinned = any(abs(node.X - x0) < 1e-9 for x0 in (0.0, L, 2 * L))
        m.def_support(node.name, True, True, pinned, False, False, True)
    m.analyze_linear()
    hog = max(abs(quad.moment(0, 0, combo_name="C")[0][0])
              for quad in m.quads.values()
              if abs(sum(n.X for n in (quad.i_node, quad.j_node, quad.m_node,
                                       quad.n_node)) / 4 - L) < 0.07)
    center_r = sum(n.RxnFZ["C"] for n in m.nodes.values()
                   if abs(n.X - L) < 1e-9 and n.support_DZ)
    assert hog == pytest.approx(q * L**2 / 8, rel=0.10)
    assert abs(center_r) == pytest.approx(1.25 * q * L * W, rel=0.05)


def test_wall_inplane_axial_matches_closed_form():
    H, Lw, t, p_line = 3.0, 4.0, 0.30, 100.0
    m = FEModel3D()
    m.add_material("C25", E, G, NU, rho=0.0)
    m.add_rectangle_mesh("M", 0.25, Lw, H, t, "C25", plane="XY")
    m.meshes["M"].generate()
    top = sorted((n for n in m.nodes.values() if abs(n.Y - H) < 1e-9),
                 key=lambda n: n.X)
    for i, node in enumerate(top):
        trib = (top[min(i + 1, len(top) - 1)].X - top[max(i - 1, 0)].X) / 2
        m.add_node_load(node.name, "FY", -p_line * trib, case="Q")
    for node in m.nodes.values():
        if abs(node.Y) < 1e-9:
            m.def_support(node.name, True, True, True, True, True, True)
        else:
            m.def_support(node.name, False, False, True, True, True, False)
    m.add_load_combo("C", {"Q": 1.0})
    m.analyze_linear()
    base_r = sum(n.RxnFY["C"] for n in m.nodes.values() if n.support_DY)
    sig = max(abs(quad.membrane(0, 0, combo_name="C")[1][0])
              for quad in m.quads.values()
              if abs(sum(n.Y for n in (quad.i_node, quad.j_node, quad.m_node,
                                       quad.n_node)) / 4 - H / 2) < 0.2)
    assert abs(base_r) == pytest.approx(p_line * Lw, rel=0.01)
    assert sig == pytest.approx(p_line / t, rel=0.10)
