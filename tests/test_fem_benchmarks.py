"""FEM X-ray solver gates (specs/fem-xray.md, Acceptance).

Closed-form benchmarks against raw PyNite with the boundary-condition
recipe the fem package uses (in-plane DOFs fixed everywhere — quads have
no drilling stiffness — DZ pinned on support edges). If these fail, the
solver dependency or the recipe broke; nothing project-specific here.
Units: kN, m. Experiment origin: 2026-08-08_pynite-plate-oracle.
"""

import pytest
from Pynite import FEModel3D

from archicad_builder.fem import _principal

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


def test_membrane_shear_matches_parabolic_distribution():
    """Txy is a real in-plane shear stress in the quad's local frame.

    Slender cantilever wall-beam (L/h = 10) loaded by an end shear V:
    away from the load introduction, elementary beam theory gives a
    parabolic Txy over the depth with mid-depth 1.5*V/(t*h). The section
    integral must recover V first — if that fails, the component we are
    about to color walls by is not a shear stress at all.
    Plan review (Codex 2026-08-08): the original deep-beam version of
    this gate was wrong; 1.5V/A only holds for a slender member.
    """
    L, h, t, V = 10.0, 1.0, 0.20, 40.0
    m = FEModel3D()
    m.add_material("C25", E, G, NU, rho=0.0)
    m.add_rectangle_mesh("M", 0.1, L, h, t, "C25", plane="XY")
    m.meshes["M"].generate()
    for node in m.nodes.values():
        clamped = abs(node.X) < 1e-9
        m.def_support(node.name, clamped, clamped, True, True, True, clamped)
    tip = [n for n in m.nodes.values() if abs(n.X - L) < 1e-9]
    for n in tip:                     # end shear, spread over the depth
        m.add_node_load(n.name, "FY", -V / len(tip), case="Q")
    m.add_load_combo("C", {"Q": 1.0})
    m.analyze_linear(log=False, check_statics=False, sparse=True)

    # ONE column of quads at mid-span, away from clamp and load introduction.
    # The window must be narrower than the cell (0.1) or two adjacent columns
    # both qualify and the section integral comes out as 2V.
    station = L / 2 + 0.05            # a cell center, not a cell boundary
    col = [q for q in m.quads.values()
           if abs(sum(n.X for n in (q.i_node, q.j_node, q.m_node, q.n_node))
                  / 4 - station) < 0.02]
    assert len(col) >= 8, "need 8+ cells through the depth"
    total = 0.0
    for q in col:
        nds = (q.i_node, q.j_node, q.m_node, q.n_node)
        depth = max(n.Y for n in nds) - min(n.Y for n in nds)
        total += float(q.membrane(0, 0, combo_name="C")[2][0]) * t * depth
    assert abs(total) == pytest.approx(V, rel=0.10)   # section integral = V

    mid = min(col, key=lambda q: abs(
        sum(n.Y for n in (q.i_node, q.j_node, q.m_node, q.n_node)) / 4 - h / 2))
    tau_mid = abs(float(mid.membrane(0, 0, combo_name="C")[2][0]))
    assert tau_mid == pytest.approx(1.5 * V / (t * h), rel=0.15)


def test_twist_dominates_where_axis_moments_do_not():
    """Ignoring Mxy under-reports a real plate — the regression gate.

    Corner-supported square plate under uniform load: the classic case
    where twisting moments carry a large share of the load. If the
    principal moment is not materially larger than max(|Mx|, |My|)
    somewhere in this plate, the twist channel is not doing anything and
    the old axis-only reading was fine — which would make this whole
    feature theatre (Gemini review: the element-level test alone was a
    tautology).
    """
    import math
    S, t, q = 4.0, 0.20, 10.0
    m = _strip_model(S, S, t, q, 0.1)
    corners = [(0, 0), (S, 0), (0, S), (S, S)]
    for node in m.nodes.values():
        at_corner = any(abs(node.X - cx) < 1e-9 and abs(node.Y - cy) < 1e-9
                        for cx, cy in corners)
        m.def_support(node.name, True, True, at_corner, False, False, True)
    m.analyze_linear(log=False, check_statics=False, sparse=True)

    best = 0.0
    for quad in m.quads.values():
        mom = quad.moment(0, 0, combo_name="C")
        mx, my, mxy = (float(mom[0][0]), float(mom[1][0]), float(mom[2][0]))
        axis = max(abs(mx), abs(my))
        r = math.hypot((mx - my) / 2, mxy)
        principal = max(abs((mx + my) / 2 + r), abs((mx + my) / 2 - r))
        if axis > 1e-6:
            best = max(best, principal / axis)
    assert best > 1.2, (
        f"twist adds only {best:.2f}x over the axis moments — the "
        "principal-moment channel would be pointless")


def test_plate_moment_components_share_one_frame():
    """moment(local=True) really is [Mx, My, Mxy] in ONE tensor frame.

    PyNite's own comment says the gauss vector is [-My, Mx, Mxy] and its
    (broken) local=False branch negates My. If either were true of the
    local path, _principal(mx, my, mxy) would eigen-decompose the wrong
    tensor — a sign flip on a DIAGONAL term is not one of the invariances
    that make the principal magnitudes safe. A square plate is the
    cheapest decisive gate: at the centre Mx and My must be equal and
    both sagging (CodeRabbit review 2026-08-09).
    """
    S, t, q = 4.0, 0.20, 10.0
    m = _strip_model(S, S, t, q, 0.5)
    for n in m.nodes.values():
        edge = (abs(n.X) < 1e-9 or abs(n.X - S) < 1e-9
                or abs(n.Y) < 1e-9 or abs(n.Y - S) < 1e-9)
        m.def_support(n.name, True, True, edge, False, False, True)
    m.analyze_linear(log=False, check_statics=False, sparse=True)

    def ctr(qd):
        nds = (qd.i_node, qd.j_node, qd.m_node, qd.n_node)
        return sum(n.X for n in nds) / 4, sum(n.Y for n in nds) / 4

    mid = min(m.quads.values(), key=lambda qd:
              (ctr(qd)[0] - S / 2) ** 2 + (ctr(qd)[1] - S / 2) ** 2)
    mom = mid.moment(0, 0, combo_name="C")
    mx, my, mxy = float(mom[0][0]), float(mom[1][0]), float(mom[2][0])
    assert mx > 0 and my > 0                    # SAME sign — the gate
    assert my == pytest.approx(mx, rel=0.02)    # square-plate symmetry
    assert mx == pytest.approx(0.0442 * q * S**2, rel=0.15)   # nu = 0.2
    assert abs(mxy) < 0.05 * mx                 # no twist at the centre


def test_pure_twist_patch_matches_closed_form():
    """Constant-twist patch — pins the SCALE of Mxy, not just a ratio.

    Square plate held in Z at three corners with a point load at the
    fourth: equilibrium forces the alternating +P/-P corner set, a state
    of uniform twist with Mx = My = 0 and |Mxy| = P/2 everywhere. A
    solver returning 2*Mxy (a real convention split — some formulations
    carry 2*kappa_xy in the curvature vector) would double every plate
    utilization and still sail through a ratio-only test (CodeRabbit).
    """
    a, t, P = 4.0, 0.20, 20.0
    m = FEModel3D()
    m.add_material("C25", E, G, NU, rho=0.0)
    m.add_rectangle_mesh("M", 0.5, a, a, t, "C25", plane="XY")
    m.meshes["M"].generate()
    corner = {}
    for n in m.nodes.values():
        for cx, cy in ((0.0, 0.0), (a, 0.0), (0.0, a), (a, a)):
            if abs(n.X - cx) < 1e-9 and abs(n.Y - cy) < 1e-9:
                corner[(cx, cy)] = n.name
    held = {corner[(0.0, 0.0)], corner[(a, 0.0)], corner[(0.0, a)]}
    for n in m.nodes.values():
        m.def_support(n.name, True, True, n.name in held, False, False, True)
    m.add_node_load(corner[(a, a)], "FZ", -P, case="Q")
    m.add_load_combo("C", {"Q": 1.0})
    m.analyze_linear(log=False, check_statics=False, sparse=True)

    for qd in m.quads.values():
        mom = qd.moment(0, 0, combo_name="C")
        mx, my, mxy = float(mom[0][0]), float(mom[1][0]), float(mom[2][0])
        assert abs(mxy) == pytest.approx(P / 2, rel=0.10)
        assert max(abs(mx), abs(my)) < 0.05 * abs(mxy)   # axis-only reads ~0
        s1, s2, _th = _principal(mx, my, mxy)
        assert max(abs(s1), abs(s2)) == pytest.approx(P / 2, rel=0.10)
