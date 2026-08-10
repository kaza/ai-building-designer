"""Phase B structural load analysis — one typed load path, stated assumptions.

Spec: specs/structural-plausibility.md. This is a PLAUSIBILITY analysis
(design-basis constants below), not Eurocode compliance: it follows one
explicit load path — roof/floor strips (declared one-way span direction)
→ support reactions → bearing walls and beams → storeys below — and
asserts load conservation per panel. Elements the model cannot resolve
(no span direction, non-RC beams) are reported as `unresolved` with a
reason instead of guessed at (Codex review 2026-08-08).

Sign conventions: model plan coordinates (x, y); strips run along the
declared span axis, stations step along the other axis.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from shapely.geometry import LineString
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.validation import make_valid

from archicad_builder.models import Building

STATION_STEP = 0.2   # m between analysis strips across a panel
SUPPORT_TOL = 0.15   # m — how close a bearing wall must be to cut a strip


@dataclass
class DesignBasis:
    """Every number the analysis assumes, in one visible place."""

    snow: float = 1.32                # kN/m2 (sk 1.65 × μ1 0.8, Austria)
    roof_finishes: float = 2.0        # kN/m2 dead on top of structure
    floor_finishes: float = 1.5      # kN/m2
    floor_live: float = 2.0           # kN/m2 residential
    gamma_g: float = 1.35
    gamma_q: float = 1.5
    rc_density: float = 25.0          # kN/m3
    cap_thickness: float = 0.25       # m — modeled slabs above this are visual
    wall_fd: float = 3000.0           # kN/m2 design compressive strength
    wall_phi: float = 0.6             # slenderness reduction
    fctd: float = 1000.0              # kN/m2 design tensile strength —
                                      # C25/30 conservative-plain, the same
                                      # ruler the load-takedown bands used
    rho: float = 0.005                # RC bending reinforcement assumption
    fyd: float = 435000.0             # kN/m2 B500 design yield
    span_over_depth_limit: float = 30.0    # deflection proxy, supported spans
    cantilever_over_depth_limit: float = 10.0

    def roof_area_load(self, thickness: float) -> float:
        t = min(thickness, self.cap_thickness)
        return (self.gamma_g * (t * self.rc_density + self.roof_finishes)
                + self.gamma_q * self.snow)

    def floor_area_load(self, thickness: float) -> float:
        t = min(thickness, self.cap_thickness)
        return (self.gamma_g * (t * self.rc_density + self.floor_finishes)
                + self.gamma_q * self.floor_live)

    def strip_moment_capacity(self, thickness: float) -> float:
        """1m-wide RC strip, bottom steel at rho."""
        d_eff = max(min(thickness, self.cap_thickness) - 0.03, 0.01)
        as_area = self.rho * 1.0 * d_eff          # m2 per m width
        return as_area * self.fyd * 0.9 * d_eff   # kNm per m

    def beam_moment_capacity(self, width: float, depth: float) -> float:
        d_eff = max(depth - 0.05, 0.01)
        return self.rho * width * d_eff * self.fyd * 0.9 * d_eff


@dataclass
class _WallLoad:
    wall: object
    samples: dict[float, float] = field(default_factory=dict)  # station -> kN/m

    def add(self, position: float, q: float) -> None:
        key = round(position, 3)
        self.samples[key] = self.samples.get(key, 0.0) + q

    def line_load(self) -> float:
        if not self.samples:
            return 0.0
        return sum(self.samples.values()) / len(self.samples)

    def profile(self, buckets: int = 8) -> list[float]:
        wall = self.wall
        length = math.hypot(wall.end.x - wall.start.x, wall.end.y - wall.start.y)
        if not self.samples or length < 1e-6:
            return [0.0] * buckets
        out = []
        for i in range(buckets):
            lo, hi = length * i / buckets, length * (i + 1) / buckets
            vals = [q for pos, q in self.samples.items() if lo <= pos < hi]
            out.append(sum(vals) / len(vals) if vals else 0.0)
        return out


def _wall_line(w) -> LineString:
    return LineString([(w.start.x, w.start.y), (w.end.x, w.end.y)])


def _position_along(w, x: float, y: float) -> float:
    length = math.hypot(w.end.x - w.start.x, w.end.y - w.start.y)
    if length < 1e-6:
        return 0.0
    ux = (w.end.x - w.start.x) / length
    uy = (w.end.y - w.start.y) / length
    return (x - w.start.x) * ux + (y - w.start.y) * uy


def _analyze_panel(poly, thickness, span_dir, q_area, bearing, basis,
                   wall_loads, panel_name):
    """One-way strip analysis of one roof/floor panel.

    Returns (max_moment_per_m, governing_span, is_cantilever, balance_ratio,
    supported_area_fraction). Strips run along `span_dir`; stations step
    along the other axis; per station the strip may cross several disjoint
    polygon intervals (L-shapes must not bridge — Codex review).
    """
    minx, miny, maxx, maxy = poly.bounds
    stations = []
    lo, hi = (miny, maxy) if span_dir == "x" else (minx, maxx)
    n = max(2, int((hi - lo) / STATION_STEP))
    worst_m = 0.0
    worst_span = 0.0
    worst_cant = False
    reacted = 0.0
    applied = 0.0
    for i in range(n):
        s = lo + (i + 0.5) / n * (hi - lo)
        if span_dir == "x":
            ray = LineString([(minx - 1, s), (maxx + 1, s)])
        else:
            ray = LineString([(s, miny - 1), (s, maxy + 1)])
        inside = ray.intersection(poly)
        pieces = getattr(inside, "geoms", [inside])
        step_w = (hi - lo) / n
        for piece in pieces:
            if piece.is_empty or piece.length < 0.05:
                continue
            a, b = piece.coords[0], piece.coords[-1]
            span_lo = min(a[0], b[0]) if span_dir == "x" else min(a[1], b[1])
            span_hi = max(a[0], b[0]) if span_dir == "x" else max(a[1], b[1])
            applied += q_area * (span_hi - span_lo) * step_w
            # supports: bearing walls crossing this strip interval
            cuts = []
            for w in bearing:
                seg = _wall_line(w)
                hitpt = piece.intersection(seg.buffer(SUPPORT_TOL))
                if hitpt.is_empty:
                    continue
                c = hitpt.centroid
                cut = c.x if span_dir == "x" else c.y
                if span_lo - SUPPORT_TOL <= cut <= span_hi + SUPPORT_TOL:
                    cuts.append((cut, w, c))
            cuts.sort(key=lambda t: t[0])
            if not cuts:
                continue  # fully unsupported strip: counted in balance deficit
            segments = []
            # end cantilever west/south side
            if cuts[0][0] - span_lo > SUPPORT_TOL:
                segments.append(("cant", span_lo, cuts[0][0], cuts[0]))
            for (c1, w1, p1), (c2, w2, p2) in zip(cuts, cuts[1:]):
                segments.append(("span", c1, c2, (c1, w1, p1), (c2, w2, p2)))
            if span_hi - cuts[-1][0] > SUPPORT_TOL:
                segments.append(("cant", cuts[-1][0], span_hi, cuts[-1]))
            for seg_def in segments:
                kind, s0, s1 = seg_def[0], seg_def[1], seg_def[2]
                length = s1 - s0
                if kind == "span":
                    m = q_area * length ** 2 / 8
                    for cut, w, pt in (seg_def[3], seg_def[4]):
                        q_r = q_area * length / 2 * 1.0
                        wall_loads[w.global_id].add(
                            _position_along(w, pt.x, pt.y), q_r)
                        reacted += q_r * step_w
                else:
                    m = q_area * length ** 2 / 2  # cantilever (Gemini review)
                    cut, w, pt = seg_def[3]
                    q_r = q_area * length
                    wall_loads[w.global_id].add(
                        _position_along(w, pt.x, pt.y), q_r)
                    reacted += q_r * step_w
                if m > worst_m:
                    worst_m, worst_span, worst_cant = m, length, kind == "cant"
    balance = reacted / applied if applied > 1e-6 else 1.0
    return worst_m, worst_span, worst_cant, balance


def compute_loads(building: Building, basis: DesignBasis | None = None) -> dict:
    """Per-element structural results keyed by exporter-style names.

    walls: {kind, u, q, a, b, profile}   (gross axial — jamb concentrations
    are documented out of scope)
    beams: {kind, u, q, M, section, over, a, b}  (rc only; other materials
    unresolved)
    slabs/roofs: {kind, u, span, cantilever, M}  (declared one-way span
    only; None span_direction -> unresolved)
    plus "_unresolved": {name: reason} and "_assumptions": design basis.
    """
    basis = basis or DesignBasis()
    stories = sorted(building.stories, key=lambda s: s.elevation)
    result: dict = {}
    unresolved: dict[str, str] = {}

    carry_down: dict[str, float] = {}  # wall global_id (lower) -> extra kN/m
    for story in reversed(stories):     # top down so loads accumulate
        bearing = [w for w in story.walls if w.load_bearing]
        wall_loads = {w.global_id: _WallLoad(w) for w in bearing}

        panels = [(r, r.thickness, r.span_direction,
                   basis.roof_area_load(r.thickness), "roof")
                  for r in story.roofs]
        # floor slabs load the storey BELOW this one; handled when we are
        # that storey via the panels of the storey above:
        above = next((s for s in stories
                      if s.elevation > story.elevation + 0.01), None)
        upper_floor_panels = []
        if above is not None:
            # only the part of an upper floor slab OVER this storey spans;
            # anything outside the footprint below sits on grade and loads
            # the soil, not our walls (villa: deck/pool/lawn + the western
            # half of the ground slab)
            my_polys = [ShapelyPolygon([(v.x, v.y) for v in sl.outline.vertices])
                        for sl in story.slabs if len(sl.outline.vertices) >= 3]
            my_footprint = None
            if my_polys:
                from shapely.ops import unary_union
                my_footprint = unary_union(
                    [make_valid(p) if not p.is_valid else p for p in my_polys]
                ).buffer(0.05)
            for sl in above.slabs:
                if not sl.is_floor or my_footprint is None:
                    continue
                poly = ShapelyPolygon([(v.x, v.y) for v in sl.outline.vertices])
                clipped = poly.intersection(my_footprint)
                if clipped.is_empty or clipped.area < 0.5:
                    continue  # on grade
                upper_floor_panels.append(
                    (sl, sl.thickness, sl.span_direction,
                     basis.floor_area_load(sl.thickness), "floor", clipped))
        for entry in panels + upper_floor_panels:
            element, thickness, span_dir, q_area, kind = entry[:5]
            if len(entry) == 6:
                poly = entry[5]  # pre-clipped floor panel
            else:
                poly = ShapelyPolygon(
                    [(v.x, v.y) for v in element.outline.vertices])
                if not poly.is_valid:
                    poly = make_valid(poly)
            key = element.global_id
            if span_dir not in ("x", "y"):
                unresolved[key] = "no span_direction declared"
                continue
            m, span, cant, balance = _analyze_panel(
                poly, thickness, span_dir, q_area, bearing, basis,
                wall_loads, element.name)
            m_rd = basis.strip_moment_capacity(thickness)
            d_eff = max(min(thickness, basis.cap_thickness) - 0.03, 0.01)
            limit = (basis.cantilever_over_depth_limit if cant
                     else basis.span_over_depth_limit)
            slender = (span / d_eff) / limit if d_eff > 0 else 99.0
            if kind == "roof":  # roofs are view/check targets; floors only load walls
                result[key] = {
                    "kind": "slab",
                    "name": element.name,
                    "u": round(max(m / m_rd, slender), 2),
                    "M": round(m, 1),
                    "span": round(span, 2),
                    "cantilever": cant,
                    "balance": round(balance, 2),
                }

        # wall self-weight + carried-down loads
        for w in bearing:
            wl = wall_loads[w.global_id]
            self_w = basis.gamma_g * story.height * w.thickness * basis.rc_density
            extra = carry_down.get(w.global_id, 0.0) + self_w
            q_total = wl.line_load() + extra
            cap = w.thickness * basis.wall_phi * basis.wall_fd
            profile = [round((p + extra) / cap, 2) for p in wl.profile()]
            result[w.global_id] = {
                "kind": "wall",
                "name": w.name,
                "u": round(q_total / cap, 2),
                "q": round(q_total, 1),
                "a": [w.start.x, w.start.y],
                "b": [w.end.x, w.end.y],
                "profile": profile,
            }

        # beams: station-sampled load over each covering opening (rc only)
        walls_by_id = {w.global_id: w for w in story.walls}
        openings = [(d, d.height) for d in story.doors] + [
            (win, win.sill_height + win.height) for win in story.windows]
        for beam in story.beams:
            if beam.material != "rc":
                unresolved["IfcBeam_" + beam.name.replace(" ", "_")] = (
                    f"material {beam.material!r}: no capacity model in Phase B")
                continue
            for opening, head in openings:
                host = walls_by_id.get(opening.wall_id)
                if host is None or not host.load_bearing:
                    continue
                if not _beam_over_opening(beam, host, opening):
                    continue
                wl = wall_loads.get(host.global_id)
                band = max(host.height - head, 0.0)
                self_w = basis.gamma_g * (
                    beam.width * beam.depth + band * host.thickness
                ) * basis.rc_density
                q_local = (_sampled_q(wl, host, opening) + self_w
                           + carry_down.get(host.global_id, 0.0))
                span = opening.width + 0.25
                m = q_local * span ** 2 / 8
                m_rd = basis.beam_moment_capacity(beam.width, beam.depth)
                result[beam.global_id] = {
                    "kind": "beam",
                    "name": beam.name,
                    "u": round(m / m_rd, 2),
                    "q": round(q_local, 1),
                    "M": round(m, 1),
                    "section": f"{beam.width:.2f}x{beam.depth:.2f}",
                    "over": opening.name,
                    "a": [beam.start.x, beam.start.y],
                    "b": [beam.end.x, beam.end.y],
                }
                break

        # transfer this storey's wall line loads to aligned walls below
        below = next((s for s in reversed(stories)
                      if s.elevation < story.elevation - 0.01), None)
        if below is not None:
            lower_bearing = [w for w in below.walls if w.load_bearing]
            for w in bearing:
                wl = wall_loads[w.global_id]
                q_total = (wl.line_load()
                           + carry_down.get(w.global_id, 0.0)
                           + basis.gamma_g * story.height * w.thickness
                           * basis.rc_density)
                target = _aligned_wall(w, lower_bearing)
                if target is not None:
                    carry_down[target.global_id] = (
                        carry_down.get(target.global_id, 0.0) + q_total)

    result["_unresolved"] = unresolved
    result["_assumptions"] = {
        "basis": "structural plausibility, NOT Eurocode compliance",
        "snow": basis.snow, "roof_finishes": basis.roof_finishes,
        "floor_live": basis.floor_live, "cap_thickness": basis.cap_thickness,
        "wall_capacity": "gross axial t*phi*fd; jamb/pier concentrations out of scope",
        "rc": f"rho {basis.rho}, fyd {basis.fyd / 1000:.0f} MPa",
    }
    return result


def _sampled_q(wl: _WallLoad | None, wall, opening) -> float:
    """Mean sampled line load over the opening extent (not whole-wall avg)."""
    if wl is None or not wl.samples:
        return 0.0
    lo = opening.position
    hi = opening.position + opening.width
    vals = [q for pos, q in wl.samples.items() if lo - 0.3 <= pos <= hi + 0.3]
    return (sum(vals) / len(vals)) if vals else wl.line_load()


def _beam_over_opening(beam, wall, opening) -> bool:
    length = math.hypot(wall.end.x - wall.start.x, wall.end.y - wall.start.y)
    if length < 1e-6:
        return False
    ux = (wall.end.x - wall.start.x) / length
    uy = (wall.end.y - wall.start.y) / length
    bdx, bdy = beam.end.x - beam.start.x, beam.end.y - beam.start.y
    blen = math.hypot(bdx, bdy)
    if blen < 1e-6 or abs(ux * bdy / blen - uy * bdx / blen) > 0.26:
        return False
    for t in (opening.position, opening.position + opening.width):
        px, py = wall.start.x + ux * t, wall.start.y + uy * t
        rx, ry = px - beam.start.x, py - beam.start.y
        along = (rx * bdx + ry * bdy) / blen
        lateral = abs((-rx * bdy + ry * bdx) / blen)
        if lateral > 0.2 or along < -0.2 or along > blen + 0.2:
            return False
    return True


def _aligned_wall(wall, candidates):
    for other in candidates:
        same = (abs(wall.start.x - other.start.x) < 0.2
                and abs(wall.start.y - other.start.y) < 0.2
                and abs(wall.end.x - other.end.x) < 0.2
                and abs(wall.end.y - other.end.y) < 0.2)
        flipped = (abs(wall.start.x - other.end.x) < 0.2
                   and abs(wall.start.y - other.end.y) < 0.2
                   and abs(wall.end.x - other.start.x) < 0.2
                   and abs(wall.end.y - other.start.y) < 0.2)
        if same or flipped:
            return other
    return None
