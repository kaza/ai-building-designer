"""Closed-form benchmarks for PyNite plate models (AGENTS.md success
criterion 1). Units: kN, m. Each case prints computed vs expected and a
PASS/FAIL verdict at +-10%.

Run: ../../.venv/bin/python benchmarks.py [case ...]
"""

import sys

from Pynite import FEModel3D

E = 31e6      # kN/m2 (C25/30, ~31 GPa)
NU = 0.2
G = E / (2 * (1 + NU))
TOL = 0.10


def _concrete(model):
    model.add_material("C25", E, G, NU, rho=0.0)  # rho 0: loads applied explicitly


def _report(name, rows):
    print(f"\n== {name} ==")
    ok = True
    for label, computed, expected in rows:
        ratio = computed / expected if expected else float("inf")
        verdict = "PASS" if abs(ratio - 1.0) <= TOL else "FAIL"
        ok &= verdict == "PASS"
        print(f"  {label:34s} computed {computed:10.4f}  expected {expected:10.4f}"
              f"  ratio {ratio:6.3f}  {verdict}")
    print(f"  => {'PASS' if ok else 'FAIL'}")
    return ok


def _plate_bending_supports(model, span, axis="x"):
    """Fix in-plane DOFs everywhere (no drilling stiffness in quads);
    pin out-of-plane (DZ) along the two support edges."""
    for node in model.nodes.values():
        model.def_support(node.name, True, True, False, False, False, True)
        coord = node.X if axis == "x" else node.Y
        if abs(coord) < 1e-9 or abs(coord - span) < 1e-9:
            model.def_support(node.name, True, True, True, False, False, True)


def _pressure_all(model, q, case="Q"):
    for qname in model.quads:
        model.add_quad_surface_pressure(qname, q, case=case)


def _sum_rz(model, combo="C"):
    return sum(n.RxnFZ[combo] for n in model.nodes.values() if n.support_DZ)


def _node_at(model, x, y):
    for n in model.nodes.values():
        if abs(n.X - x) < 1e-6 and abs(n.Y - y) < 1e-6:
            return n
    raise LookupError(f"no node at ({x},{y})")


def case_ss_strip():
    """Simply supported one-way strip: L=4 m span (X), 1 m wide, t=0.20,
    q=10 kN/m2. Beam theory: M=qL2/8, w=5qL4/384EI (I=t3/12 per m)."""
    L, W, t, q = 4.0, 1.0, 0.20, 10.0
    model = FEModel3D()
    _concrete(model)
    model.add_rectangle_mesh("M", 0.125, L, W, t, "C25", plane="XY")
    model.meshes["M"].generate()
    _plate_bending_supports(model, L, axis="x")
    _pressure_all(model, q)
    model.add_load_combo("C", {"Q": 1.0})
    model.analyze_linear()

    mid = _node_at(model, L / 2, W / 2)
    w_mid = abs(mid.DZ["C"])
    # midspan Mx per unit width: average the four quads touching midspan
    mids = []
    for quad in model.quads.values():
        xs = [n.X for n in (quad.i_node, quad.j_node, quad.m_node, quad.n_node)]
        ys = [n.Y for n in (quad.i_node, quad.j_node, quad.m_node, quad.n_node)]
        if min(xs) < L / 2 < max(xs) or abs(sum(xs) / 4 - L / 2) < 0.07:
            mids.append(abs(quad.moment(0, 0, combo_name="C")[0][0]))
    mx = max(mids)

    I = t**3 / 12
    return _report("ss_strip (1-way, L=4, q=10)", [
        ("midspan Mx [kNm/m]", mx, q * L**2 / 8),
        ("midspan deflection [m]", w_mid, 5 * q * L**4 / (384 * E * I)),
        ("sum reactions Rz [kN]", abs(_sum_rz(model)), q * L * W),
    ])


def case_cantilever():
    """Cantilever strip: L=2 m (X, fixed at x=0), 1 m wide, t=0.20,
    q=10 kN/m2. M_root=qL2/2, w_tip=qL4/8EI."""
    L, W, t, q = 2.0, 1.0, 0.20, 10.0
    model = FEModel3D()
    _concrete(model)
    model.add_rectangle_mesh("M", 0.10, L, W, t, "C25", plane="XY")
    model.meshes["M"].generate()
    for node in model.nodes.values():
        if abs(node.X) < 1e-9:
            model.def_support(node.name, True, True, True, True, True, True)
        else:
            model.def_support(node.name, True, True, False, False, False, True)
    _pressure_all(model, q)
    model.add_load_combo("C", {"Q": 1.0})
    model.analyze_linear()

    tip = _node_at(model, L, W / 2)
    roots = []
    for quad in model.quads.values():
        xs = [n.X for n in (quad.i_node, quad.j_node, quad.m_node, quad.n_node)]
        if min(xs) < 1e-9:
            roots.append(abs(quad.moment(-1, 0, combo_name="C")[0][0]))
    I = t**3 / 12
    return _report("cantilever (L=2, q=10)", [
        ("root Mx [kNm/m]", max(roots), q * L**2 / 2),
        ("tip deflection [m]", abs(tip.DZ["C"]), q * L**4 / (8 * E * I)),
        ("sum reactions Rz [kN]", abs(_sum_rz(model)), q * L * W),
    ])


def case_two_span():
    """Two equal spans 2x4 m continuous over a center line support:
    M_support=qL2/8, center reaction line = 1.25qL, end 0.375qL."""
    L, W, t, q = 4.0, 1.0, 0.20, 10.0
    model = FEModel3D()
    _concrete(model)
    model.add_rectangle_mesh("M", 0.125, 2 * L, W, t, "C25", plane="XY",
                             x_control=[L])
    model.meshes["M"].generate()
    for node in model.nodes.values():
        model.def_support(node.name, True, True, False, False, False, True)
        if any(abs(node.X - x0) < 1e-9 for x0 in (0.0, L, 2 * L)):
            model.def_support(node.name, True, True, True, False, False, True)
    _pressure_all(model, q)
    model.add_load_combo("C", {"Q": 1.0})
    model.analyze_linear()

    hog = []
    for quad in model.quads.values():
        xs = [n.X for n in (quad.i_node, quad.j_node, quad.m_node, quad.n_node)]
        if abs(sum(xs) / 4 - L) < 0.07:
            hog.append(abs(quad.moment(0, 0, combo_name="C")[0][0]))
    center_r = sum(n.RxnFZ["C"] for n in model.nodes.values()
                   if abs(n.X - L) < 1e-9 and n.support_DZ)
    end_r = sum(n.RxnFZ["C"] for n in model.nodes.values()
                if abs(n.X) < 1e-9 and n.support_DZ)
    return _report("two_span (2x4 m continuous)", [
        ("support Mx [kNm/m]", max(hog), q * L**2 / 8),
        ("center reaction [kN]", abs(center_r), 1.25 * q * L * W),
        ("end reaction [kN]", abs(end_r), 0.375 * q * L * W),
        ("sum reactions Rz [kN]", abs(_sum_rz(model)), q * 2 * L * W),
    ])


def case_wall_axial():
    """Wall panel loaded in-plane: 3 m tall x 4 m long x t=0.30, top edge
    line load 100 kN/m downward. Base reaction = 400 kN; mid-height
    axial stress = N/A = 100/0.3 kN/m2 per unit length (membrane)."""
    H, Lw, t, p = 3.0, 4.0, 0.30, 100.0
    model = FEModel3D()
    _concrete(model)
    # wall in XZ? plane option: 'XY','YZ','XZ' — build in XY then treat
    # Y as height; in-plane load = node loads along -Y on the top edge.
    model.add_rectangle_mesh("M", 0.25, Lw, H, t, "C25", plane="XY")
    model.meshes["M"].generate()
    top_nodes = [n for n in model.nodes.values() if abs(n.Y - H) < 1e-9]
    top_nodes.sort(key=lambda n: n.X)
    for i, node in enumerate(top_nodes):
        trib = 0.25 if 0 < i < len(top_nodes) - 1 else 0.125
        model.add_node_load(node.name, "FY", -p * trib, case="Q")
    for node in model.nodes.values():
        if abs(node.Y) < 1e-9:
            model.def_support(node.name, True, True, True, True, True, True)
        else:
            model.def_support(node.name, False, False, True, True, True, False)
    model.add_load_combo("C", {"Q": 1.0})
    model.analyze_linear()

    base_r = sum(n.RxnFY["C"] for n in model.nodes.values() if n.support_DY)
    membranes = []
    for quad in model.quads.values():
        ys = [n.Y for n in (quad.i_node, quad.j_node, quad.m_node, quad.n_node)]
        if abs(sum(ys) / 4 - H / 2) < 0.2:
            membranes.append(abs(quad.membrane(0, 0, combo_name="C")[1][0]))
    # membrane() returns stresses [sx, sy, txy] in kN/m2; sy = p/t
    return _report("wall_axial (3x4 m, 100 kN/m top)", [
        ("base reaction [kN]", abs(base_r), p * Lw),
        ("mid-height sigma_y [kN/m2]", max(membranes), p / t),
    ])


CASES = {f.__name__.removeprefix("case_"): f
         for f in (case_ss_strip, case_cantilever, case_two_span, case_wall_axial)}

if __name__ == "__main__":
    wanted = sys.argv[1:] or list(CASES)
    results = {name: CASES[name]() for name in wanted}
    print("\n==== SUMMARY ====")
    for name, ok in results.items():
        print(f"  {name:12s} {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if all(results.values()) else 1)
