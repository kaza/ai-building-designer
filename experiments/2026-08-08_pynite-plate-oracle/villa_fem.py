"""PyNite plate model of villa-maketa (AGENTS.md success criteria 2-3).

Idealization (every choice logged in the audit log):
- Bearing walls -> vertical quad plates on the wall axis, openings cut out.
- Roofs (t capped at 0.25, DesignBasis.cap_thickness) and the Ground Slab
  -> horizontal quad plates; Deck/Pool/Lawn + Garage Slab are on grade ->
  excluded (soil), matching structural.py.
- One global control grid (wall axes, endpoints, jambs, outline vertices;
  story-global z lines incl. all sills/heads) subdivided to <=MESH so all
  meshes share nodes exactly - no hanging nodes.
- Supports: garage wall bases clamped; GF wall bases clamped where NOT
  over the garage void; Ground Slab nodes outside the void get soil DZ.
- Loads: DesignBasis ULS area loads as surface pressures (down = -Z),
  wall self-weight (x gamma_g) as node loads, non-bearing partitions as
  line loads at z=0. Single pre-factored case "U", combo "ULS".
- Per-node drilling DOF restrained when all attached plates are coplanar.

Units: kN, m.  Run: ../../.venv/bin/python villa_fem.py [--mesh 0.25]
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from shapely.geometry import Point, Polygon

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from archicad_builder.structural import DesignBasis  # noqa: E402
from Pynite import FEModel3D  # noqa: E402

E = 31e6
NU = 0.2
G = E / (2 * (1 + NU))
TOL = 1e-6
KEY = 3          # mm rounding for node identity
WALL_STRESS_CAP = None   # filled from DesignBasis below


def k(v):
    return round(v, KEY)


def subdivide(controls, step):
    """Sorted control values + equal subdivision of each gap to <= step."""
    pts = sorted(set(k(c) for c in controls))
    out = []
    for a, b in zip(pts, pts[1:]):
        n = max(1, round((b - a) / step + 0.499))
        out.extend(k(a + (b - a) * i / n) for i in range(n))
    out.append(pts[-1])
    return out


class Mesher:
    def __init__(self, mesh):
        self.model = FEModel3D()
        self.model.add_material("C25", E, G, NU, rho=0.0)
        self.mesh = mesh
        self.nodes = {}                       # (x,y,z) -> name
        self.node_planes = defaultdict(set)   # name -> {'X','Y','Z'} normals
        self.quad_elem = {}                   # quad name -> (kind, elem name)
        self.qn = 0

    def node(self, x, y, z):
        key = (k(x), k(y), k(z))
        if key not in self.nodes:
            name = f"N{len(self.nodes)}"
            self.model.add_node(name, *key)
            self.nodes[key] = name
        return self.nodes[key]

    def quad(self, corners, t, normal, kind, elem):
        """corners: 4 (x,y,z) counter-clockwise."""
        names = [self.node(*c) for c in corners]
        self.qn += 1
        qname = f"Q{self.qn}"
        self.model.add_quad(qname, *names, t, "C25")
        for n in names:
            self.node_planes[n].add(normal)
        self.quad_elem[qname] = (kind, elem)
        return qname


def opening_rects(story, wall):
    """[(a0, a1, z0, z1)] along-axis / absolute-z rects for a wall."""
    rects = []
    sx, sy = wall["start"]["x"], wall["start"]["y"]
    ex, ey = wall["end"]["x"], wall["end"]["y"]
    length = abs(ex - sx) + abs(ey - sy)
    for op in story["doors"] + story["windows"]:
        if op["wall_id"] != wall["global_id"]:
            continue
        sill = op.get("sill_height") or 0.0
        a0 = op["position"]
        rects.append((a0, min(a0 + op["width"], length),
                      story["elevation"] + sill,
                      story["elevation"] + sill + op["height"]))
    return rects


def build(mesh_size):
    db = DesignBasis()
    building = json.load(open(REPO / "projects/villa-maketa/building.json"))
    stories = {s["name"]: s for s in building["stories"]}
    gar, gf = stories["Garage"], stories["Ground Floor"]

    garage_void = Polygon([(v["x"], v["y"]) for v in
                           gar["slabs"][0]["outline"]["vertices"]]).buffer(0.16)

    # ---- global control lines ----
    xs, ys = set(), set()
    zs = set()
    for s in (gar, gf):
        zs.update((s["elevation"], s["elevation"] + s["height"]))
        for w in s["walls"]:
            xs.update((w["start"]["x"], w["end"]["x"]))
            ys.update((w["start"]["y"], w["end"]["y"]))
            for a0, a1, z0, z1 in opening_rects(s, w):
                zs.update((z0, z1))
                horiz = abs(w["end"]["y"] - w["start"]["y"]) < TOL
                base = w["start"]["x" if horiz else "y"]
                sign = 1 if (w["end"]["x" if horiz else "y"] > base) else -1
                (xs if horiz else ys).update((base + sign * a0, base + sign * a1))
        for coll in ("slabs", "roofs"):
            for sl in s.get(coll, []):
                for v in sl["outline"]["vertices"]:
                    xs.add(v["x"]); ys.add(v["y"])
    gx, gy = subdivide(xs, mesh_size), subdivide(ys, mesh_size)
    gz = subdivide(zs, mesh_size)

    m = Mesher(mesh_size)

    # ---- walls (bearing only) ----
    wall_meta = {}
    for s in (gar, gf):
        z_lo, z_hi = s["elevation"], s["elevation"] + s["height"]
        for w in s["walls"]:
            if not w["load_bearing"]:
                continue
            horiz = abs(w["end"]["y"] - w["start"]["y"]) < TOL
            assert horiz or abs(w["end"]["x"] - w["start"]["x"]) < TOL, w["name"]
            rects = opening_rects(s, w)
            const = w["start"]["y"] if horiz else w["start"]["x"]
            a_start = w["start"]["x" if horiz else "y"]
            a_end = w["end"]["x" if horiz else "y"]
            a0g, a1g = min(a_start, a_end), max(a_start, a_end)
            grid_a = [a for a in (gx if horiz else gy) if a0g - TOL <= a <= a1g + TOL]
            grid_z = [z for z in gz if z_lo - TOL <= z <= min(z_hi, z_lo + w["height"]) + TOL]
            for a, a2 in zip(grid_a, grid_a[1:]):
                for z, z2 in zip(grid_z, grid_z[1:]):
                    ac, zc = (a + a2) / 2, (z + z2) / 2
                    arel = abs(ac - a_start)
                    if any(r[0] < arel < r[1] and r[2] < zc < r[3] for r in rects):
                        continue
                    if horiz:
                        c = [(a, const, z), (a2, const, z), (a2, const, z2), (a, const, z2)]
                        m.quad(c, w["thickness"], "Y", "wall", w["name"])
                    else:
                        c = [(const, a, z), (const, a2, z), (const, a2, z2), (const, a, z2)]
                        m.quad(c, w["thickness"], "X", "wall", w["name"])
            wall_meta[w["name"]] = dict(story=s["name"], t=w["thickness"],
                                        z_lo=z_lo, horiz=horiz,
                                        a=(w["start"]["x"], w["start"]["y"]),
                                        b=(w["end"]["x"], w["end"]["y"]))

    # ---- horizontal plates: roofs + Ground Slab ----
    panels = []
    for r in gf["roofs"]:
        panels.append((r["name"], "roof", gf["elevation"] + gf["height"],
                       min(r["thickness"], db.cap_thickness),
                       Polygon([(v["x"], v["y"]) for v in r["outline"]["vertices"]]),
                       db.roof_area_load(r["thickness"])))
    gslab = next(sl for sl in gf["slabs"] if sl["name"] == "Ground Slab")
    panels.append((gslab["name"], "slab", gf["elevation"],
                   min(gslab["thickness"], db.cap_thickness),
                   Polygon([(v["x"], v["y"]) for v in gslab["outline"]["vertices"]]),
                   db.floor_area_load(gslab["thickness"])))

    for name, kind, z, t, poly, q in panels:
        for x, x2 in zip(gx, gx[1:]):
            for y, y2 in zip(gy, gy[1:]):
                if not poly.contains(Point((x + x2) / 2, (y + y2) / 2)):
                    continue
                qname = m.quad([(x, y, z), (x2, y, z), (x2, y2, z), (x, y2, z)],
                               t, "Z", kind, name)
                m.model.add_quad_surface_pressure(qname, -q, case="U")

    # ---- wall self-weight (factored) as node loads ----
    for qname, (kind, elem) in m.quad_elem.items():
        if kind != "wall":
            continue
        quad = m.model.quads[qname]
        nds = (quad.i_node, quad.j_node, quad.m_node, quad.n_node)
        xs_ = [n.X for n in nds]; ys_ = [n.Y for n in nds]; zs_ = [n.Z for n in nds]
        area = (max(xs_) - min(xs_) + max(ys_) - min(ys_)) * (max(zs_) - min(zs_))
        f = area * wall_meta[elem]["t"] * db.rc_density * db.gamma_g / 4
        for n in nds:
            m.model.add_node_load(n.name, "FZ", -f, case="U")

    # ---- non-bearing partition weight -> line loads at their base ----
    for s in (gar, gf):
        for w in s["walls"]:
            if w["load_bearing"]:
                continue
            horiz = abs(w["end"]["y"] - w["start"]["y"]) < TOL
            const = w["start"]["y"] if horiz else w["start"]["x"]
            a_lo = min(w["start"]["x" if horiz else "y"], w["end"]["x" if horiz else "y"])
            a_hi = max(w["start"]["x" if horiz else "y"], w["end"]["x" if horiz else "y"])
            grid_a = [a for a in (gx if horiz else gy) if a_lo - TOL <= a <= a_hi + TOL]
            qline = w["thickness"] * w["height"] * db.rc_density * db.gamma_g
            for i, a in enumerate(grid_a):
                trib = ((grid_a[min(i + 1, len(grid_a) - 1)] -
                         grid_a[max(i - 1, 0)]) / 2)
                key = ((k(a), k(const)) if horiz else (k(const), k(a)))
                nkey = (key[0], key[1], k(s["elevation"]))
                if nkey in m.nodes:
                    m.model.add_node_load(m.nodes[nkey], "FZ", -qline * trib, case="U")

    # ---- supports ----
    clamped = soil = 0
    for (x, y, z), name in m.nodes.items():
        planes = m.node_planes[name]
        clamp = False
        if abs(z - gar["elevation"]) < TOL and ("X" in planes or "Y" in planes):
            clamp = True                                    # garage wall base
        elif abs(z - gf["elevation"]) < TOL and ("X" in planes or "Y" in planes) \
                and not garage_void.contains(Point(x, y)):
            clamp = True                                    # GF wall base on footing
        if clamp:
            m.model.def_support(name, True, True, True, True, True, True)
            clamped += 1
            continue
        if abs(z - gf["elevation"]) < TOL and "Z" in planes \
                and not garage_void.contains(Point(x, y)):
            # soil DZ; drilling RZ too if the node is slab-only
            m.model.def_support(name, False, False, True, False, False,
                                planes == {"Z"})
            soil += 1
            continue
        if planes == {"Z"}:
            m.model.def_support(name, False, False, False, False, False, True)
        elif planes == {"Y"}:
            m.model.def_support(name, False, False, False, False, True, False)
        elif planes == {"X"}:
            m.model.def_support(name, False, False, False, True, False, False)
    return m, db, wall_meta, panels, clamped, soil


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", type=float, default=0.25)
    args = ap.parse_args()

    t0 = time.time()
    m, db, wall_meta, panels, clamped, soil = build(args.mesh)
    print(f"mesh {args.mesh}: {len(m.model.nodes)} nodes, {m.qn} quads, "
          f"{clamped} clamped, {soil} soil-DZ  (built {time.time()-t0:.1f}s)")

    applied = sum(
        load[1] for node in m.model.nodes.values()
        for load in node.NodeLoads if load[0] == "FZ")
    for qname in m.model.quads:
        pass  # surface pressures live on the quads; PyNite sums them itself

    m.model.add_load_combo("ULS", {"U": 1.0})
    t1 = time.time()
    m.model.analyze_linear(log=False, check_statics=False, sparse=True)
    print(f"solved in {time.time()-t1:.1f}s")

    # ---- harvest ----
    results = {}
    by_elem = defaultdict(list)
    for qname, tag in m.quad_elem.items():
        by_elem[tag].append(m.model.quads[qname])

    def centers(q):
        nds = (q.i_node, q.j_node, q.m_node, q.n_node)
        return (sum(n.X for n in nds) / 4, sum(n.Y for n in nds) / 4,
                sum(n.Z for n in nds) / 4)

    def strip_avg(samples, band=1.0):
        """samples: [(across_coord, value)] -> max |1m-moving-average|."""
        best = 0.0
        for c0, _ in samples:
            win = [v for c, v in samples if abs(c - c0) <= band / 2]
            best = max(best, abs(sum(win) / len(win)))
        return best

    for (kind, elem), quads in sorted(by_elem.items()):
        if kind == "wall":
            base_z = min(centers(q)[2] for q in quads)
            stations = []
            for q in quads:
                xc, yc, zc = centers(q)
                if abs(zc - base_z) > 0.05:
                    continue                     # lowest existing row
                s = q.membrane(0, -0.9, combo_name="ULS")
                along = xc if wall_meta[elem]["horiz"] else yc
                stations.append((along, float(s[1][0])))
            peak = max(abs(v) for _, v in stations)
            avg = strip_avg(stations, band=0.5)
            cap = db.wall_phi * db.wall_fd
            meta = wall_meta[elem]
            lo = min(meta["a"][0 if meta["horiz"] else 1],
                     meta["b"][0 if meta["horiz"] else 1])
            length = abs(meta["b"][0] - meta["a"][0]) + abs(meta["b"][1] - meta["a"][1])
            profile = []
            for i in range(8):
                c0, c1 = lo + length * i / 8, lo + length * (i + 1) / 8
                vals = [abs(v) for c, v in stations if c0 - 0.05 <= c <= c1 + 0.05]
                profile.append(round((sum(vals) / len(vals)) / cap, 3) if vals else 0.0)
            results[f"wall {elem}"] = dict(
                kind=kind, sigma=avg, sigma_peak=peak, base_z=base_z,
                u=avg / cap, profile=profile)
        else:
            t = quads[0].t
            cap = db.strip_moment_capacity(t)
            mx_by_x, my_by_y, mx_all, my_all = defaultdict(list), defaultdict(list), [], []
            for q in quads:
                xc, yc, _ = centers(q)
                mom = q.moment(0, 0, combo_name="ULS")
                mx, my = float(mom[0][0]), float(mom[1][0])
                mx_all.append(mx); my_all.append(my)
                mx_by_x[round(xc, 2)].append((yc, mx))
                my_by_y[round(yc, 2)].append((xc, my))
            # design moment: max over sections of the 1m strip average
            mx_design = max(strip_avg(sams) for sams in mx_by_x.values())
            my_design = max(strip_avg(sams) for sams in my_by_y.values())
            results[f"{kind} {elem}"] = dict(
                kind=kind, mx_design=mx_design, my_design=my_design,
                mx_peak=max(map(abs, mx_all)), my_peak=max(map(abs, my_all)),
                cap=cap, u=max(mx_design, my_design) / cap)

    total_rz = sum(n.RxnFZ["ULS"] for n in m.model.nodes.values()
                   if n.support_DZ)
    total_applied = -applied
    for name, node in m.model.nodes.items():
        pass
    press = 0.0
    for pname, (kind, elem) in m.quad_elem.items():
        quad = m.model.quads[pname]
        for p in quad.pressures:
            xs_ = [n.X for n in (quad.i_node, quad.j_node, quad.m_node, quad.n_node)]
            ys_ = [n.Y for n in (quad.i_node, quad.j_node, quad.m_node, quad.n_node)]
            press += -p[0] * (max(xs_) - min(xs_)) * (max(ys_) - min(ys_))
    total_applied += press

    print(f"\napplied ULS vertical load {total_applied:.1f} kN, "
          f"reactions {total_rz:.1f} kN, balance {total_rz/total_applied:.4f}")

    print(f"\n{'element':42s} {'u':>6s}  detail")
    for name, r in sorted(results.items(), key=lambda kv: -kv[1]["u"]):
        if r["kind"] == "wall":
            print(f"{name:42s} {r['u']:6.2f}  sigma {r['sigma']:8.1f} "
                  f"(peak {r['sigma_peak']:8.1f}) kN/m2  base z {r['base_z']:.2f}")
        else:
            print(f"{name:42s} {r['u']:6.2f}  Mx {r['mx_design']:6.1f} "
                  f"(peak {r['mx_peak']:6.1f})  My {r['my_design']:6.1f} "
                  f"(peak {r['my_peak']:6.1f})  cap {r['cap']:.1f}")

    out = dict(mesh=args.mesh, nodes=len(m.model.nodes), quads=m.qn,
               applied=total_applied, reactions=total_rz, results=results)
    Path("logs").mkdir(exist_ok=True)
    Path(f"logs/villa-fem-mesh{args.mesh}.json").write_text(json.dumps(out, indent=1))

    # walkthrough Loads-view payload (same schema as output/loads.json)
    fem = {}
    for name, r in results.items():
        kind, elem = name.split(" ", 1)
        slug = elem.replace(" ", "_")
        if kind == "wall":
            meta = wall_meta[elem]
            fem[f"IfcWallStandardCase_{slug}"] = dict(
                kind="wall", u=round(r["u"], 3), profile=r["profile"],
                q=round(r["sigma"] * meta["t"], 1),
                a=list(meta["a"]), b=list(meta["b"]))
        else:
            ifc = "IfcSlab_" + slug
            fem[ifc] = dict(kind="slab", u=round(r["u"], 3),
                            M=round(max(r["mx_design"], r["my_design"]), 1),
                            balance=1.0)
    # per-quad field for the X-ray fragment view
    field = []
    wall_cap = db.wall_phi * db.wall_fd
    for qname, (kind, elem) in m.quad_elem.items():
        q = m.model.quads[qname]
        nds = (q.i_node, q.j_node, q.m_node, q.n_node)
        if kind == "wall":
            u = abs(float(q.membrane(0, 0, combo_name="ULS")[1][0])) / wall_cap
        else:
            mom = q.moment(0, 0, combo_name="ULS")
            u = max(abs(float(mom[0][0])), abs(float(mom[1][0]))) / db.strip_moment_capacity(q.t)
        field.append(dict(k=kind, e=elem, u=round(u, 3),
                          c=[[round(n.X, 3), round(n.Y, 3), round(n.Z, 3)] for n in nds]))
    Path(f"logs/fem-field-mesh{args.mesh}.json").write_text(json.dumps(field))
    print(f"field: {len(field)} quads -> logs/fem-field-mesh{args.mesh}.json")

    fem["_assumptions"] = [
        f"PyNite {__import__('importlib.metadata', fromlist=['version']).version('PyNiteFEA')} plate FEM, mesh {args.mesh} m, quads: {m.qn}",
        "same DesignBasis as the strip engine (ULS 1.35G+1.5Q, snow 1.32)",
        "design values: 1 m strip-averaged plate moments / 0.5 m averaged wall base stress",
        f"load balance {total_rz/total_applied:.4f}",
    ]
    Path(f"logs/fem-loads-mesh{args.mesh}.json").write_text(json.dumps(fem, indent=1))
    print(f"\nwritten logs/villa-fem-mesh{args.mesh}.json + fem-loads-mesh{args.mesh}.json")


if __name__ == "__main__":
    main()
