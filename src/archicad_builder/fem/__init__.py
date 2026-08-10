"""FEM X-ray core — plate finite-element oracle (specs/fem-xray.md).

Meshes a Building's bearing walls, ring beams, slabs and roofs as
conforming quad plates on one global snapped control grid, solves ULS
gravity via PyNite, and returns per-element design utilizations (keyed
by global_id) plus a per-quad field for the X-ray view.

Grounding contract (plan review 2026-08-08): only stories at elevation
<= GROUND_EPS may ground (wall-base clamps, slab soil support), and only
where no story below covers the point; an elevated story must sit on a
vertically adjacent story or preflight fails loudly. Load accounting:
intended vs attached vs reacted; dropping > 1% of intended load is a
typed error, smaller drops become `unresolved` entries.

Promoted from experiments/2026-08-08_pynite-plate-oracle (benchmarks:
tests/test_fem_benchmarks.py).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field as dc_field

from shapely.geometry import LineString
from shapely.geometry import Point as ShPoint
from shapely.geometry import Polygon
from shapely.ops import unary_union

from archicad_builder.models import Building
from archicad_builder.structural import DesignBasis

E = 31e6          # kN/m2, C25/30
NU = 0.2
G = E / (2 * (1 + NU))
TOL = 1e-6
GROUND_EPS = 0.01
VOID_BUFFER = 0.16    # outer face of a 0.3 wall on the story below
KEY = 3               # node identity rounding (mm)


class FemError(Exception):
    """Base for all FEM X-ray errors."""


class FemPreflightError(FemError):
    """The building cannot be honestly meshed — never approximated."""


class FemSizeError(FemError):
    """Estimated quad count exceeds the configured ceiling."""


class FemLoadDropError(FemError):
    """More than 1% of intended load could not be attached to the model."""


@dataclass
class FemResult:
    elements: dict[str, dict]
    field: dict
    intended: float
    attached: float
    reactions: float
    unresolved: list[str] = dc_field(default_factory=list)
    assumptions: list[str] = dc_field(default_factory=list)
    not_modelled: list[str] = dc_field(default_factory=list)
    combos: list[str] = dc_field(default_factory=lambda: ["ULS"])
    # per-case equilibrium ledgers: gravity cases carry intended/attached/
    # reacted (vertical), lateral cases applied/reacted (horizontal) — a
    # single scalar balance can hide one case over-reacting while another
    # under-reacts (Codex plan review 2026-08-10)
    case_balance: dict = dc_field(default_factory=dict)

    @property
    def balance(self) -> float:
        return self.reactions / self.attached if self.attached else 0.0

    def find(self, name: str) -> dict:
        hits = [e for e in self.elements.values() if e["name"] == name]
        if len(hits) != 1:
            raise LookupError(f"{len(hits)} elements named {name!r}")
        return hits[0]


def _k(v: float) -> float:
    return round(v, KEY)


def _subdivide(controls, step):
    pts = sorted(set(_k(c) for c in controls))
    out = []
    for a, b in zip(pts, pts[1:]):
        n = max(1, round((b - a) / step + 0.499))
        out.extend(_k(a + (b - a) * i / n) for i in range(n))
    out.append(pts[-1])
    return out


def _axis(elem, kind, problems):
    """(horiz, const, a_lo, a_hi) for an axis-aligned wall/beam."""
    sx, sy = elem.start.x, elem.start.y
    ex, ey = elem.end.x, elem.end.y
    if abs(ey - sy) < TOL:
        return True, sy, min(sx, ex), max(sx, ex)
    if abs(ex - sx) < TOL:
        return False, sx, min(sy, ey), max(sy, ey)
    problems.append(f"{kind} '{elem.name}' is not axis-aligned "
                    f"(({sx},{sy})->({ex},{ey}))")
    return None


def _poly(outline) -> Polygon:
    return Polygon([(v.x, v.y) for v in outline.vertices])


def _opening_rects(story, wall):
    rects = []
    length = abs(wall.end.x - wall.start.x) + abs(wall.end.y - wall.start.y)
    for op in list(story.doors) + list(story.windows):
        if op.wall_id != wall.global_id:
            continue
        sill = getattr(op, "sill_height", None) or 0.0
        rects.append((op.position, min(op.position + op.width, length),
                      story.elevation + sill,
                      story.elevation + sill + op.height))
    return rects


class _Mesher:
    def __init__(self):
        from Pynite import FEModel3D
        self.model = FEModel3D()
        self.model.add_material("C25", E, G, NU, rho=0.0)
        self.nodes: dict[tuple, str] = {}
        self.node_planes: dict[str, set] = defaultdict(set)
        self.quad_meta: dict[str, tuple] = {}     # qname -> (kind, gid)
        self.qn = 0

    def node(self, x, y, z):
        key = (_k(x), _k(y), _k(z))
        if key not in self.nodes:
            name = f"N{len(self.nodes)}"
            self.model.add_node(name, *key)
            self.nodes[key] = name
        return self.nodes[key]

    def quad(self, corners, t, normal, kind, gid):
        names = [self.node(*c) for c in corners]
        self.qn += 1
        qname = f"Q{self.qn}"
        self.model.add_quad(qname, *names, t, "C25")
        for n in names:
            self.node_planes[n].add(normal)
        self.quad_meta[qname] = (kind, gid)
        return qname


def _principal(sx: float, sy: float, txy: float) -> tuple[float, float, float]:
    """Mohr's circle: (max principal, min principal, angle of max in deg).

    Concrete cracks on the maximum PRINCIPAL tension, whichever way it
    points — a panel in pure shear has sx = sy = 0 and cracks diagonally
    at |txy|. Checking only the axis-aligned components (what this engine
    did until 2026-08-08) reports that panel as calm.

    Both principal values are eigenvalues of [[sx, txy], [txy, sy]], so
    the MAGNITUDES survive a sign flip of txy (the only real ambiguity in
    the wall path, where the local y direction follows the plate normal).
    They do NOT survive a sign flip of one diagonal term, which is what
    PyNite's source comment claims its local moments carry — that claim
    is false and is pinned down by a symmetric-plate gate in
    tests/test_fem_benchmarks.py. A swap of sx/sy also preserves the
    magnitudes but would transpose the horizontal/vertical LABELS, so do
    not lean on it (CodeRabbit review 2026-08-09).

    The angle is measured from the local x axis and is degenerate when
    the circle collapses (r = 0, equal principals); 0 is returned there.
    Works for moments too — [[mx, mxy], [mxy, my]] has the same algebra.
    """
    c = (sx + sy) / 2.0
    r = math.hypot((sx - sy) / 2.0, txy)
    # RELATIVE degeneracy test: stresses here run to 1e4 kN/m2, so an
    # absolute epsilon let a hydrostatic quad (no principal direction at
    # all) be labelled "diagonal tension" off the last bits of the solve
    # (CodeRabbit review 2026-08-09).
    tiny = 1e-9 * max(abs(sx), abs(sy), abs(txy), 1.0)
    theta = 0.0 if r <= tiny else math.degrees(
        0.5 * math.atan2(2.0 * txy, sx - sy))
    return c + r, c - r, theta


def _tension_component(theta: float) -> int:
    """Governing-component code for a principal tension at angle theta."""
    a = abs(theta)
    if a <= 22.5:
        return 1        # horizontal tension (along the wall)
    if a >= 67.5:
        return 2        # vertical tension
    return 4            # diagonal tension — in-plane shear cracking


def _wavg(samples, center, band):
    """Tributary-weighted average of (coord, value, weight) in a window.

    Each cell contributes only the part of its tributary width that
    actually OVERLAPS the window. Counting a cell's whole width whenever
    its center fell inside made a nominal 1 m window physically 0.8-1.2 m
    wide depending on where the mesh lines landed, and design values
    drifted up to 29% between meshes — past the ~10% convergence this
    engine promises (Codex review 2026-08-09).
    """
    lo, hi = center - band / 2, center + band / 2
    num = den = 0.0
    for c, v, w in samples:
        if w <= 0:
            continue
        overlap = min(hi, c + w / 2) - max(lo, c - w / 2)
        if overlap <= 0:
            continue
        num += v * overlap
        den += overlap
    return num / den if den else 0.0


def _band_max(samples, band):
    return max((abs(_wavg(samples, c, band)) for c, _, _ in samples),
               default=0.0)


def compute_fem(building: Building, mesh: float = 0.25,
                max_quads: int = 60_000, site=None,
                seismic_basis=None) -> FemResult:
    """site: project [site] config — adds EQX/EQY lateral cases scaled to
    the ELF storey forces and four seismic combos (specs/seismic-lateral.md
    S2). None keeps the gravity-only ULS behavior bit-identical."""
    db = DesignBasis()
    stories = sorted(building.stories, key=lambda s: s.elevation)
    problems: list[str] = []
    unresolved: list[str] = []

    elf = None
    sbasis = None
    if site is not None:
        from archicad_builder.seismic import SeismicBasis, compute_seismic
        sbasis = seismic_basis or SeismicBasis()
        elf = compute_seismic(building, site, sbasis)
        if "elf" in elf["_unresolved"]:
            raise FemPreflightError(
                "seismic requested but " + elf["_unresolved"]["elf"])

    # ---------- preflight ----------
    meta = {}      # story name -> per-story derived data
    for s in stories:
        for w in s.walls:
            if w.load_bearing and _axis(w, "wall", problems) is None:
                pass
        for bm in s.beams:
            if _axis(bm, "beam", problems) is None:
                pass
        for coll, kindname in ((s.roofs, "roof"), (s.slabs, "slab")):
            for panel in coll:
                vs = [(v.x, v.y) for v in panel.outline.vertices]
                for (x0, y0), (x1, y1) in zip(vs, vs[1:] + vs[:1]):
                    if abs(x1 - x0) > TOL and abs(y1 - y0) > TOL:
                        problems.append(
                            f"{kindname} '{panel.name}' outline edge "
                            f"({x0},{y0})->({x1},{y1}) is not axis-aligned")
                        break
        if s.elevation > GROUND_EPS:
            below = [lo for lo in stories
                     if abs(lo.elevation + lo.height - s.elevation) < 0.02]
            support = None
            if below:
                polys = []
                for lo in below:
                    polys += [_poly(sl.outline) for sl in lo.slabs]
                    polys += [_poly(r.outline) for r in lo.roofs]
                    for w in lo.walls:
                        polys.append(LineString(
                            [(w.start.x, w.start.y), (w.end.x, w.end.y)]
                        ).buffer(max(w.thickness, 0.1)))
                support = unary_union(polys).buffer(0.2)
            bearing = [w for w in s.walls if w.load_bearing]
            unsupported = [
                w.name for w in bearing
                if support is None or not (
                    support.intersects(LineString(
                        [(w.start.x, w.start.y), (w.end.x, w.end.y)])))]
            if bearing and (not below or unsupported):
                names = ", ".join(f"'{n}'" for n in (
                    unsupported or [w.name for w in bearing]))
                problems.append(
                    f"story '{s.name}' at elevation {s.elevation} has no "
                    f"vertically adjacent support below {names}")
    if problems:
        raise FemPreflightError("; ".join(problems))

    def below_footprint(story):
        polys = []
        for lo in stories:
            if lo.elevation < story.elevation - GROUND_EPS:
                polys += [_poly(sl.outline) for sl in lo.slabs]
                polys += [_poly(r.outline) for r in lo.roofs]
        return unary_union(polys).buffer(VOID_BUFFER) if polys else None

    # ---------- global control grid ----------
    xs, ys, zs = set(), set(), set()
    panels = []       # (gid, kind, name, story, z, t, poly, pressure)
    for s in stories:
        zs.update((s.elevation, s.elevation + s.height))
        for w in s.walls:
            xs.update((w.start.x, w.end.x))
            ys.update((w.start.y, w.end.y))
            zs.add(s.elevation + w.height)   # short walls keep their top row
            if w.load_bearing:
                for a0, a1, z0, z1 in _opening_rects(s, w):
                    zs.update((z0, z1))
                    horiz, const, lo, _hi = _axis(w, "wall", [])
                    base = w.start.x if horiz else w.start.y
                    sign = 1 if ((w.end.x if horiz else w.end.y) > base) else -1
                    (xs if horiz else ys).update((base + sign * a0,
                                                  base + sign * a1))
        for bm in s.beams:
            xs.update((bm.start.x, bm.end.x))
            ys.update((bm.start.y, bm.end.y))
            zs.update((s.elevation + bm.z_top - bm.depth,
                       s.elevation + bm.z_top))
        for r in s.roofs:
            if getattr(r, "pitch", 0) or 0:
                unresolved.append(f"roof '{r.name}': pitched roofs are not "
                                  "meshed (flat plates only)")
                continue
            p = _poly(r.outline)
            xs.update(c[0] for c in p.exterior.coords)
            ys.update(c[1] for c in p.exterior.coords)
            panels.append((r.global_id, "roof", r.name, s,
                           s.elevation + s.height,
                           min(r.thickness, db.cap_thickness), p,
                           db.roof_dead(r.thickness), db.snow))
        for sl in s.slabs:
            p = _poly(sl.outline)
            xs.update(c[0] for c in p.exterior.coords)
            ys.update(c[1] for c in p.exterior.coords)
            panels.append((sl.global_id, "slab", sl.name, s, s.elevation,
                           min(sl.thickness, db.cap_thickness), p,
                           db.floor_dead(sl.thickness), db.floor_live))
    gx, gy, gz = _subdivide(xs, mesh), _subdivide(ys, mesh), _subdivide(zs, mesh)

    # ---------- size estimate ----------
    def _count(lo, hi, grid):
        return max(0, len([g for g in grid if lo - TOL <= g <= hi + TOL]) - 1)

    est = 0
    for s in stories:
        for w in s.walls:
            if not w.load_bearing:
                continue
            horiz, _c, lo, hi = _axis(w, "wall", [])
            est += (_count(lo, hi, gx if horiz else gy)
                    * _count(s.elevation, s.elevation + w.height, gz))
    for _gid, _kind, _n, _s, _z, _t, poly, _qd, _ql in panels:
        bx = poly.bounds
        est += _count(bx[0], bx[2], gx) * _count(bx[1], bx[3], gy)
    if est > max_quads:
        raise FemSizeError(
            f"estimated {est} quads exceeds max_quads={max_quads}; "
            f"raise mesh (current {mesh}) or max_quads")

    m = _Mesher()

    # ---------- beams (walls skip their boxes) ----------
    beam_meta = {}
    for s in stories:
        for bm in s.beams:
            if bm.material != "rc":
                unresolved.append(
                    f"beam '{bm.name}': material '{bm.material}' is not "
                    "modeled — the wall band is meshed instead (conservative)")
                continue
            horiz, const, lo, hi = _axis(bm, "beam", [])
            beam_meta[bm.global_id] = dict(
                name=bm.name, story=s.name, horiz=horiz, const=const,
                a_lo=lo, a_hi=hi, width=bm.width, depth=bm.depth,
                z_lo=s.elevation + bm.z_top - bm.depth,
                z_hi=s.elevation + bm.z_top)

    def in_beam(horiz, const, ac, zc):
        return any(b["horiz"] == horiz and abs(b["const"] - const) < 0.05
                   and b["a_lo"] - TOL < ac < b["a_hi"] + TOL
                   and b["z_lo"] - TOL < zc < b["z_hi"] + TOL
                   for b in beam_meta.values())

    # ---------- walls ----------
    wall_meta = {}
    for s in stories:
        for w in s.walls:
            if not w.load_bearing:
                continue
            horiz, const, a_lo, a_hi = _axis(w, "wall", [])
            rects = _opening_rects(s, w)
            a_start = w.start.x if horiz else w.start.y
            z_lo, z_hi = s.elevation, s.elevation + w.height
            grid_a = [a for a in (gx if horiz else gy)
                      if a_lo - TOL <= a <= a_hi + TOL]
            grid_z = [z for z in gz if z_lo - TOL <= z <= z_hi + TOL]
            for a, a2 in zip(grid_a, grid_a[1:]):
                for z, z2 in zip(grid_z, grid_z[1:]):
                    ac, zc = (a + a2) / 2, (z + z2) / 2
                    arel = abs(ac - a_start)
                    if any(r[0] < arel < r[1] and r[2] < zc < r[3]
                           for r in rects):
                        continue
                    if in_beam(horiz, const, ac, zc):
                        continue
                    if horiz:
                        c = [(a, const, z), (a2, const, z),
                             (a2, const, z2), (a, const, z2)]
                    else:
                        c = [(const, a, z), (const, a2, z),
                             (const, a2, z2), (const, a, z2)]
                    m.quad(c, w.thickness, "Y" if horiz else "X",
                           "wall", w.global_id)
            wall_meta[w.global_id] = dict(
                name=w.name, story=s.name, t=w.thickness, z_lo=z_lo,
                horiz=horiz, a=(w.start.x, w.start.y),
                b=(w.end.x, w.end.y))

    for gid, b in beam_meta.items():
        grid_a = [a for a in (gx if b["horiz"] else gy)
                  if b["a_lo"] - TOL <= a <= b["a_hi"] + TOL]
        grid_z = [z for z in gz if b["z_lo"] - TOL <= z <= b["z_hi"] + TOL]
        for a, a2 in zip(grid_a, grid_a[1:]):
            for z, z2 in zip(grid_z, grid_z[1:]):
                if b["horiz"]:
                    c = [(a, b["const"], z), (a2, b["const"], z),
                         (a2, b["const"], z2), (a, b["const"], z2)]
                else:
                    c = [(b["const"], a, z), (b["const"], a2, z),
                         (b["const"], a2, z2), (b["const"], a, z2)]
                m.quad(c, b["width"], "Y" if b["horiz"] else "X",
                       "beam", gid)

    # ---------- horizontal panels + pressures ----------
    # unfactored cases G (dead) and Q (live); QE is the storey-weighted
    # seismic live (phi * psi2 — a flat 0.3Q would overstate lower-storey
    # live mass, Codex plan review). Ledgers are per case.
    intended: dict[str, float] = defaultdict(float)
    attached: dict[str, float] = defaultdict(float)
    # lateral mass ledger: diaphragm z -> node name -> tributary weight
    lateral_ledger: dict[float, dict[str, float]] = defaultdict(
        lambda: defaultdict(float))
    top_z = max(s.elevation + s.height for s in stories)
    seismic_base = elf["base"] if elf is not None else 0.0
    for gid, kind, name, s, z, t, poly, q_dead, q_live in panels:
        # intended is the panel's TRUE load (q x area); attached only what
        # meshed cells carry — a non-rectilinear outline whose boundary
        # cells fall outside must show up as a drop, never as balance 1.0
        intended["G"] += q_dead * poly.area
        intended["Q"] += q_live * poly.area
        qe_f = 0.0
        elevated = z > seismic_base + GROUND_EPS
        if elf is not None and kind == "slab" and elevated:
            phi = (sbasis.phi_top if abs(z - top_z) < 0.02
                   else sbasis.phi_other)
            qe_f = phi * sbasis.psi2      # roofs: psi2(snow)=0, dead only
            intended["QE"] += qe_f * q_live * poly.area
        made = False
        for x, x2 in zip(gx, gx[1:]):
            for y, y2 in zip(gy, gy[1:]):
                if not poly.contains(ShPoint((x + x2) / 2, (y + y2) / 2)):
                    continue
                qn = m.quad([(x, y, z), (x2, y, z), (x2, y2, z), (x, y2, z)],
                            t, "Z", kind, gid)
                cell = (x2 - x) * (y2 - y)
                m.model.add_quad_surface_pressure(qn, -q_dead, case="G")
                attached["G"] += q_dead * cell
                if q_live:
                    m.model.add_quad_surface_pressure(qn, -q_live, case="Q")
                    attached["Q"] += q_live * cell
                if qe_f:
                    m.model.add_quad_surface_pressure(
                        qn, -qe_f * q_live, case="QE")
                    attached["QE"] += qe_f * q_live * cell
                if elf is not None and elevated:
                    w_cell = (q_dead + qe_f * q_live) * cell
                    for cx, cy in ((x, y), (x2, y), (x2, y2), (x, y2)):
                        nname = m.nodes[(_k(cx), _k(cy), _k(z))]
                        lateral_ledger[_k(z)][nname] += w_cell / 4
                made = True
        if not made:
            unresolved.append(f"{kind} '{name}': no mesh cell fits inside "
                              "its outline")

    # ---------- self-weight + partitions ----------
    # wall/beam mass lumps at its storey's diaphragm BUCKET; the force
    # lands on the highest node of each plan column at or below that
    # diaphragm — a short wall's inertia genuinely acts at its own top,
    # so it is not hoisted to a level it never reaches (declared in
    # _assumptions; Codex code review 2026-08-10)
    dia_by_gid: dict[str, float] = {}
    for s in stories:
        for w in s.walls:
            dia_by_gid[w.global_id] = s.elevation + s.height
        for bm in s.beams:
            dia_by_gid[bm.global_id] = s.elevation + s.height
    plan_zs: dict[tuple, list] = defaultdict(list)
    for (nx, ny, nz), nname in m.nodes.items():
        plan_zs[(nx, ny)].append((nz, nname))
    for v in plan_zs.values():
        v.sort()

    def _top_node(nx, ny, dia):
        cands = [nn for nz, nn in plan_zs[(_k(nx), _k(ny))]
                 if nz <= dia + 0.02]
        return cands[-1] if cands else None

    for qname, (kind, gid) in m.quad_meta.items():
        if kind not in ("wall", "beam"):
            continue
        quad = m.model.quads[qname]
        nds = (quad.i_node, quad.j_node, quad.m_node, quad.n_node)
        xs_ = [n.X for n in nds]; ys_ = [n.Y for n in nds]
        zs_ = [n.Z for n in nds]
        area = ((max(xs_) - min(xs_)) + (max(ys_) - min(ys_))) \
            * (max(zs_) - min(zs_))
        f = area * quad.t * db.rc_density
        intended["G"] += f
        attached["G"] += f
        for n in nds:
            m.model.add_node_load(n.name, "FZ", -f / 4, case="G")
        if elf is not None:
            dia = dia_by_gid.get(gid)
            if dia is not None and dia > seismic_base + GROUND_EPS:
                plan = {(n.X, n.Y) for n in nds}
                for px, py in plan:
                    nn = _top_node(px, py, dia)
                    if nn is not None:
                        lateral_ledger[_k(dia)][nn] += f / len(plan)

    for s in stories:
        for w in s.walls:
            if w.load_bearing:
                continue
            ax = _axis(w, "wall", [])
            if ax is None:
                continue          # non-bearing diagonals carry no load path
            horiz, const, a_lo, a_hi = ax
            grid_a = [a for a in (gx if horiz else gy)
                      if a_lo - TOL <= a <= a_hi + TOL]
            qline = w.thickness * w.height * db.rc_density
            intended["G"] += qline * max(0.0, a_hi - a_lo)
            dropped = 0.0
            for i, a in enumerate(grid_a):
                trib = (grid_a[min(i + 1, len(grid_a) - 1)]
                        - grid_a[max(i - 1, 0)]) / 2
                key = ((_k(a), _k(const)) if horiz else (_k(const), _k(a)))
                nkey = (key[0], key[1], _k(s.elevation))
                if nkey in m.nodes:
                    m.model.add_node_load(m.nodes[nkey], "FZ",
                                          -qline * trib, case="G")
                    attached["G"] += qline * trib
                    # partition mass buckets at its storey's CEILING —
                    # the same convention the ELF uses, so the two
                    # engines shake the same masses (Codex code review
                    # 2026-08-10: floor-bucketing dropped ground-storey
                    # partitions and skewed the plan distribution)
                    if elf is not None:
                        dia = s.elevation + s.height
                        if dia > seismic_base + GROUND_EPS:
                            nn = (_top_node(key[0], key[1], dia)
                                  or m.nodes[nkey])
                            lateral_ledger[_k(dia)][nn] += qline * trib
                else:
                    dropped += qline * trib
            if dropped > TOL:
                unresolved.append(
                    f"partition '{w.name}': {dropped:.1f} kN had no node "
                    "to land on and was dropped")
    tot_intended = db.gamma_g * intended["G"] + db.gamma_q * intended["Q"]
    tot_attached = db.gamma_g * attached["G"] + db.gamma_q * attached["Q"]
    if tot_intended and (tot_intended - tot_attached) / tot_intended > 0.01:
        raise FemLoadDropError(
            f"{tot_intended - tot_attached:.1f} kN of {tot_intended:.1f} kN "
            f"intended load could not be attached (> 1%)")

    # ---------- lateral storey forces (ELF) ----------
    applied_lat: dict[str, float] = defaultdict(float)
    if elf is not None:
        for frc in elf["forces"]:
            if frc["F"] <= 0:
                continue
            bucket = lateral_ledger.get(_k(frc["z"]))
            if not bucket:
                raise FemPreflightError(
                    f"no FEM mass at diaphragm z={frc['z']} for storey "
                    f"'{frc['story']}' — cannot apply its seismic force")
            wsum = sum(bucket.values())
            for nname, wgt in bucket.items():
                m.model.add_node_load(nname, "FX", frc["F"] * wgt / wsum,
                                      case="EQX")
                m.model.add_node_load(nname, "FY", frc["F"] * wgt / wsum,
                                      case="EQY")
            applied_lat["EQX"] += frc["F"]
            applied_lat["EQY"] += frc["F"]

    # ---------- supports ----------
    voids = {s.name: below_footprint(s) for s in stories}
    grounded = {s.name: s.elevation <= GROUND_EPS for s in stories}
    base_z = {s.name: s.elevation for s in stories}
    for (x, y, z), name in m.nodes.items():
        planes = m.node_planes[name]
        clamped = False
        for s in stories:
            if not grounded[s.name] or abs(z - base_z[s.name]) > TOL:
                continue
            void = voids[s.name]
            on_ground = void is None or not void.contains(ShPoint(x, y))
            if on_ground and ("X" in planes or "Y" in planes):
                m.model.def_support(name, True, True, True, True, True, True)
                clamped = True
            elif on_ground and planes == {"Z"}:
                m.model.def_support(name, False, False, True,
                                    False, False, True)
                clamped = True
            break
        if clamped:
            continue
        if planes == {"Z"}:
            m.model.def_support(name, False, False, False, False, False, True)
        elif planes == {"Y"}:
            m.model.def_support(name, False, False, False, False, True, False)
        elif planes == {"X"}:
            m.model.def_support(name, False, False, False, True, False, False)

    # ---------- solve ----------
    m.model.add_load_combo("ULS", {"G": db.gamma_g, "Q": db.gamma_q})
    display_combos = ["ULS"]
    if elf is not None:
        for cname, fac in (
                ("SEIS_X+", {"G": 1.0, "QE": 1.0, "EQX": 1.0}),
                ("SEIS_X-", {"G": 1.0, "QE": 1.0, "EQX": -1.0}),
                ("SEIS_Y+", {"G": 1.0, "QE": 1.0, "EQY": 1.0}),
                ("SEIS_Y-", {"G": 1.0, "QE": 1.0, "EQY": -1.0})):
            m.model.add_load_combo(cname, fac)
            display_combos.append(cname)
    audit_cases = ["G", "Q"] + (["QE", "EQX", "EQY"]
                                if elf is not None else [])
    for case in audit_cases:
        m.model.add_load_combo(f"_{case}", {case: 1.0})
    m.model.analyze_linear(log=False, check_statics=False, sparse=True)

    # ---------- harvest ----------
    def centers(q):
        nds = (q.i_node, q.j_node, q.m_node, q.n_node)
        return (sum(n.X for n in nds) / 4, sum(n.Y for n in nds) / 4,
                sum(n.Z for n in nds) / 4)

    by_elem = defaultdict(list)
    for qname, tag in m.quad_meta.items():
        by_elem[tag].append(m.model.quads[qname])

    wall_cap = db.wall_phi * db.wall_fd
    panel_by_gid = {p[0]: p for p in panels}

    def _harvest(combo: str):
        """Design values + per-quad field for ONE combination. The
        envelope over combos is built by the caller — element numbers
        and fragments must come from the same combination or they would
        contradict each other."""
        elements: dict[str, dict] = {}
        quad_u: dict[str, float] = {}
        quad_g: dict[str, int] = {}    # 0 vert compression, 1 horiz tension,
        quad_s: dict[str, float] = {}  # 2 vert tension, 3 plate bending
        _harvest_body(combo, elements, quad_u, quad_g, quad_s)
        return elements, quad_u, quad_g, quad_s

    def _harvest_body(combo, elements, quad_u, quad_g, quad_s):
        for (kind, gid), quads in sorted(by_elem.items()):
            if kind == "beam":
                b = beam_meta[gid]
                z_mid = (b["z_lo"] + b["z_hi"]) / 2
                stations = defaultdict(list)
                for q in quads:
                    xc, yc, zc = centers(q)
                    nds = (q.i_node, q.j_node, q.m_node, q.n_node)
                    h = max(n.Z for n in nds) - min(n.Z for n in nds)
                    sx = float(q.membrane(0, 0, combo_name=combo)[0][0])
                    stations[round(xc if b["horiz"] else yc, 3)].append(
                        (q, sx, zc, h))
                cap = db.beam_moment_capacity(b["width"], b["depth"])
                m_best = 0.0
                for sams in stations.values():
                    mom = sum(sx * b["width"] * h * (zc - z_mid)
                              for _, sx, zc, h in sams)
                    m_best = max(m_best, abs(mom))
                    for q, *_ in sams:
                        quad_u[q.name] = abs(mom) / cap
                elements[gid] = dict(kind="beam", name=b["name"],
                                     story=b["story"], M=m_best, cap=cap,
                                     u=m_best / cap,
                                     # beams carry bending only here; shear,
                                     # torsion and axial are in not_modelled
                                     parts=[["bending",
                                             f"{m_best / cap * 100:.0f}%"]])
            elif kind == "wall":
                w = wall_meta[gid]
                bz = min(centers(q)[2] for q in quads)
                stations = []
                tension_rows = defaultdict(list)   # z row -> (along, s1_tension, width)
                shear_rows = defaultdict(list)     # z row -> (along, |txy|, width)
                for q in quads:
                    xc, yc, zc = centers(q)
                    nds = (q.i_node, q.j_node, q.m_node, q.n_node)
                    width = (max(n.X for n in nds) - min(n.X for n in nds)
                             + max(n.Y for n in nds) - min(n.Y for n in nds))
                    along = xc if w["horiz"] else yc
                    if abs(zc - bz) <= 0.05:
                        sig = float(q.membrane(0, -0.9, combo_name=combo)[1][0])
                        stations.append((along, sig, width))
                    s_ = q.membrane(0, 0, combo_name=combo)
                    sx, sy = float(s_[0][0]), float(s_[1][0])
                    txy = float(s_[2][0])
                    s1, _s2, theta = _principal(sx, sy, txy)
                    # design values average the per-quad PRINCIPAL tension, not
                    # the components: averaging sx/sy/txy first lets a rotating
                    # shear field cancel itself and report false calm, which is
                    # the exact failure this channel exists to catch (Codex plan
                    # review; Gemini argued the other way — correct for a section
                    # resultant, wrong for a crack screen).
                    tension_rows[round(zc, 3)].append(
                        (along, max(0.0, s1), width))
                    shear_rows[round(zc, 3)].append((along, abs(txy), width))
                    # per-quad governing: vertical compression vs axial cap, or
                    # principal tension vs fctd (concrete cracks long before it
                    # crushes). Compression stays axis-aligned on purpose — the
                    # wall capacity carries a slenderness factor for VERTICAL
                    # load and means nothing applied to a diagonal strut.
                    u_c = max(0.0, -sy) / wall_cap
                    u_t = max(0.0, s1) / db.fctd
                    if u_t >= u_c:
                        quad_u[q.name] = u_t
                        quad_g[q.name] = _tension_component(theta)
                        quad_s[q.name] = s1
                    else:
                        quad_u[q.name] = u_c
                        quad_g[q.name] = 0
                        quad_s[q.name] = sy
                avg = _band_max(stations, 0.5)
                u_tension = max(
                    (_band_max(row, 0.5) / db.fctd
                     for row in tension_rows.values()), default=0.0)
                # reported as a STRESS, not a utilization: |txy| over fctd would
                # read alarmingly high on a wall in heavy compression whose
                # cracks are held shut, while the principal tension — the thing
                # that actually governs — is zero (Gemini review).
                tau_max = max(
                    (_band_max(row, 0.5) for row in shear_rows.values()),
                    default=0.0)
                lo = min(w["a"][0 if w["horiz"] else 1],
                         w["b"][0 if w["horiz"] else 1])
                length = (abs(w["b"][0] - w["a"][0])
                          + abs(w["b"][1] - w["a"][1]))
                profile = []
                for i in range(8):
                    cmid = lo + length * (i + 0.5) / 8
                    profile.append(round(abs(_wavg(stations, cmid,
                                                   length / 8 + 0.1))
                                         / wall_cap, 3))
                u_axial = avg / wall_cap
                elements[gid] = dict(
                    kind="wall", name=w["name"], story=w["story"],
                    sigma=avg, u=max(u_axial, u_tension), u_axial=u_axial,
                    u_tension=u_tension, tau_max=tau_max, profile=profile,
                    # every channel we compute, not just whichever one governs.
                    # (label, value) pairs, not sentences — the viewer lays
                    # them out in aligned columns and owns the layout; the
                    # engine owns the units.
                    parts=[["axial", f"{u_axial * 100:.0f}%"],
                           ["tension", f"{u_tension * 100:.0f}%"],
                           ["shear", f"{tau_max / 1000:.2f} MPa"]],
                    q=round(avg * w["t"], 1), a=list(w["a"]), b=list(w["b"]))
            else:
                _gid, pkind, pname, ps, _z, t, _ppoly, _qd, _ql = \
                panel_by_gid[gid]
                cap = db.strip_moment_capacity(t)
                mx_by_x, my_by_y = defaultdict(list), defaultdict(list)
                mp_by_x, mp_by_y = defaultdict(list), defaultdict(list)
                for q in quads:
                    xc, yc, _zc = centers(q)
                    nds = (q.i_node, q.j_node, q.m_node, q.n_node)
                    wx = max(n.X for n in nds) - min(n.X for n in nds)
                    wy = max(n.Y for n in nds) - min(n.Y for n in nds)
                    mom = q.moment(0, 0, combo_name=combo)
                    mx, my = float(mom[0][0]), float(mom[1][0])
                    mxy = float(mom[2][0])
                    # twist counts: a plate region in pure twist (mx = my = 0,
                    # mxy != 0) bends at 45 deg and used to paint 0%. The strip
                    # capacity is isotropic here, so the principal moment — not
                    # Wood-Armer, which sizes an orthogonal rebar grid — is the
                    # honest measure (both plan reviews agreed).
                    m1, m2, _th = _principal(mx, my, mxy)
                    m_princ = max(abs(m1), abs(m2))
                    quad_u[q.name] = m_princ / cap
                    mx_by_x[round(xc, 2)].append((yc, mx, wy))
                    my_by_y[round(yc, 2)].append((xc, my, wx))
                    mp_by_x[round(xc, 2)].append((yc, m_princ, wy))
                    mp_by_y[round(yc, 2)].append((xc, m_princ, wx))
                mxd = max((_band_max(s_, 1.0) for s_ in mx_by_x.values()),
                          default=0.0)
                myd = max((_band_max(s_, 1.0) for s_ in my_by_y.values()),
                          default=0.0)
                # the element value must see what the fragments see: a
                # twisting panel would otherwise paint hot while its number
                # stayed at the strip value. Averaged along BOTH strip
                # directions — a one-direction average can land below the
                # other direction's design moment, which would let the element
                # number under-report its own strips.
                mpd = max((_band_max(s_, 1.0)
                           for s_ in (*mp_by_x.values(), *mp_by_y.values())),
                          default=0.0)
                gov = max(mxd, myd, mpd)
                elements[gid] = dict(
                    kind=pkind, name=pname, story=ps.name,
                    mx_design=mxd, my_design=myd, m_principal_design=mpd,
                    cap=cap, M=gov, u=gov / cap,
                    parts=[["Mx", f"{mxd / cap * 100:.0f}%"],
                           ["My", f"{myd / cap * 100:.0f}%"],
                           ["principal", f"{mpd / cap * 100:.0f}%"]])

    # ---------- combination envelope ----------
    # element numbers and fragments always come from the same combo; the
    # ENVELOPE stores the worst combo per element/fragment plus per-combo
    # element values so an engineer can isolate what drives a number
    # (Gemini plan review: enveloping must not destroy diagnostics)
    elements: dict[str, dict] = {}
    quad_u: dict[str, float] = {}
    quad_g: dict[str, int] = {}
    quad_s: dict[str, float] = {}
    quad_cmb: dict[str, int] = {}
    per_combo_qu: list[dict[str, float]] = []   # V-key views, schema 3
    for ci, cname in enumerate(display_combos):
        els, qu, qg, qs = _harvest(cname)
        per_combo_qu.append(qu)
        for gid, e in els.items():
            if gid not in elements:
                elements[gid] = {**e, "combo": cname,
                                 "combos": {cname: round(e["u"], 4)}}
            else:
                rec = elements[gid]
                rec["combos"][cname] = round(e["u"], 4)
                if e["u"] > rec["u"]:
                    combos_map = rec["combos"]
                    elements[gid] = {**e, "combo": cname,
                                     "combos": combos_map}
        for qn, uv in qu.items():
            if uv > quad_u.get(qn, -1.0):
                quad_u[qn] = uv
                quad_g[qn] = qg.get(qn, 3)
                quad_s[qn] = qs.get(qn, 0.0)
                quad_cmb[qn] = ci

    # A fragment legitimately reads higher than its element: the element
    # number is a window-averaged DESIGN value, the fragment is a raw
    # local one that spikes at re-entrant corners and supports. Publishing
    # the peak alongside it makes that difference auditable instead of
    # looking like a contradiction (Codex review 2026-08-09).
    for qname, (_kind, gid) in m.quad_meta.items():
        if gid in elements:
            elements[gid]["u_peak"] = max(elements[gid].get("u_peak", 0.0),
                                          quad_u.get(qname, 0.0))

    reactions = sum(n.RxnFZ["ULS"] for n in m.model.nodes.values()
                    if n.support_DZ)
    case_balance: dict[str, dict] = {}
    for case in ("G", "Q") + (("QE",) if elf is not None else ()):
        reacted = sum(n.RxnFZ[f"_{case}"] for n in m.model.nodes.values()
                      if n.support_DZ)
        case_balance[case] = dict(
            intended=round(intended[case], 1),
            attached=round(attached[case], 1),
            reacted=round(float(abs(reacted)), 1))
    if elf is not None:
        for case, comp, flag in (("EQX", "RxnFX", "support_DX"),
                                 ("EQY", "RxnFY", "support_DY")):
            reacted = sum(getattr(n, comp)[f"_{case}"]
                          for n in m.model.nodes.values()
                          if getattr(n, flag))
            case_balance[case] = dict(applied=round(applied_lat[case], 1),
                                      reacted=round(float(abs(reacted)), 1))

    quads_out = []
    for qname, (kind, gid) in m.quad_meta.items():
        q = m.model.quads[qname]
        nds = (q.i_node, q.j_node, q.m_node, q.n_node)
        quads_out.append(dict(
            e=gid, k=kind, u=round(quad_u.get(qname, 0.0), 3),
            g=quad_g.get(qname, 3), s=round(quad_s.get(qname, 0.0)),
            cmb=quad_cmb.get(qname, 0),
            uc=[round(qu.get(qname, 0.0), 3) for qu in per_combo_qu],
            c=[[round(n.X, 3), round(n.Y, 3), round(n.Z, 3)] for n in nds]))

    assumptions = [
        f"PyNite plate FEM, mesh {mesh} m, {m.qn} quads",
        "loads/capacities: shared DesignBasis (ULS "
        f"{db.gamma_g}G+{db.gamma_q}Q, snow {db.snow})",
        ("combinations enveloped: " + ", ".join(display_combos)
         + " — SEIS = G + phi*psi2*Q +/- ELF storey forces "
         "(specs/seismic-lateral.md)" if elf is not None
         else "gravity only: ULS = "
         f"{db.gamma_g}G + {db.gamma_q}Q"),
        "design values: 1 m strip-averaged plate moments, 0.5 m averaged "
        "wall stress — overlap-weighted over the window, and the plate "
        "value averages |principal moment|, so hogging never cancels "
        "sagging inside a window (conservative)",
        "element numbers are DESIGN values; a single fragment peaks "
        "higher at corners and supports (u_peak), where the value is a "
        "mesh-dependent singularity rather than something to build for",
        f"wall coloring: governing of vertical compression (cap "
        f"{db.wall_phi * db.wall_fd:.0f}) and MAX PRINCIPAL tension (fctd "
        f"{db.fctd:.0f} kN/m2) — cracking follows the principal direction, "
        "so in-plane shear shows up as diagonal tension",
        "plate coloring: max principal moment (twist included) against an "
        "isotropic strip capacity — reinforcement is treated as "
        "direction-independent, thickness capped at 0.25 m",
    ]
    if elf is not None:
        assumptions.append(
            "EQ nodal forces: mass buckets per storey diaphragm scaled "
            "to the ELF storey force; applied at the highest node of "
            "each plan column at or below the diaphragm (a short wall "
            "pushes at its own top, not a level it never reaches)")
    # The honest answer to "what is missing" — printed on the X-ray page so
    # nobody mistakes a calm color for a safe building (owner 2026-08-08).
    not_modelled = [
        ("wind and wind-governed lateral stability" if elf is not None
         else "wind, seismic, lateral stability and diaphragm action"),
        "buckling, second-order effects and slender-wall behaviour",
        "punching and one-way (transverse) shear, local bearing",
        "foundations, soil bearing, settlement, uplift and sliding",
        "SLS deflection, crack width, creep, shrinkage and temperature",
        "reinforcement layout, anchorage and connection detailing",
        "beam axial force, shear and torsion (bending only)",
        "slab/roof in-plane (membrane) forces",
        "out-of-plane wall bending: the model has no eccentric or lateral "
        "wall load, so any moment there would be a support artefact",
        "non-bearing walls: self-weight only, no stiffness or load path",
    ]
    if elf is not None:
        not_modelled += [
            "accidental torsional eccentricity (+/-0.05L): inherent "
            "torsion only — the per-node delta amplification breaks "
            "force equilibrium (plan review); engineer applies EC8 "
            "accidental torsion in design",
            "vertical seismic component (cantilevers flagged in the "
            "handoff report instead)",
            "masonry stiffness: walls are meshed at C25 concrete "
            "stiffness while the ELF capacity ruler assumes URM — "
            "demand DISTRIBUTION is approximate where masonry is the "
            "real material",
            "behavior factor q applies to forces only; no ductility "
            "or capacity design checks",
        ]
    return FemResult(
        elements=elements,
        field=dict(schema=3, coords="building-z-up", mesh=mesh,
                   combos=display_combos, quads=quads_out),
        intended=tot_intended, attached=tot_attached,
        reactions=abs(reactions),
        unresolved=unresolved, assumptions=assumptions,
        not_modelled=not_modelled,
        combos=display_combos, case_balance=case_balance)
