"""Seismic ELF plausibility engine — specs/seismic-lateral.md (S1).

Eurocode 8 lateral force method, structural plausibility screening
(NOT EN 1998 compliance — a licensed engineer signs real buildings).
Structure type: unreinforced masonry bearing walls + RC ring beams +
RC slabs (q = 1.5) by default; the [structure] preset swaps q and the
Table 9.3 row as data, gated FAIL-CLOSED on tie-column evidence
(§Structure presets). Weights reuse the gravity engines'
DesignBasis densities and finish loads so every engine agrees on what
the building weighs (conservative for masonry: 25 > ~18 kN/m3).

Mass lumping: each storey is one level at its ceiling (z = elevation +
height) carrying the storey's walls and roofs plus the floor slabs
resting at that z (the storey above's floor, with finishes and
psi_E x live). Slabs on grade (z <= GROUND_EPS) carry no seismic mass.
Wall mass is gross (openings not subtracted) — conservative.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from archicad_builder.models import Building
from archicad_builder.project_config import Site
from archicad_builder.structural import DesignBasis

GROUND_EPS = 0.01
LEVEL_TOL = 0.02      # z-match tolerance when assigning slabs to levels

# EN 1998-1 Tables 3.2 / 3.3, recommended values (verified 2026-08-10):
# (spectrum_type, ground_type) -> (S, TB, TC, TD)
SPECTRUM = {
    (1, "A"): (1.00, 0.15, 0.40, 2.0),
    (1, "B"): (1.20, 0.15, 0.50, 2.0),
    (1, "C"): (1.15, 0.20, 0.60, 2.0),
    (1, "D"): (1.35, 0.20, 0.80, 2.0),
    (1, "E"): (1.40, 0.15, 0.50, 2.0),
    (2, "A"): (1.00, 0.05, 0.25, 1.2),
    (2, "B"): (1.35, 0.05, 0.25, 1.2),
    (2, "C"): (1.50, 0.10, 0.25, 1.2),
    (2, "D"): (1.80, 0.10, 0.30, 1.2),
    (2, "E"): (1.60, 0.05, 0.25, 1.2),
}
# BA and AT annexes prescribe Type 1. Germany's NA actually defines its
# own spectral shapes and soil classes (R/T/S) — Type 2 is a documented
# low-seismicity APPROXIMATION, printed in _assumptions, never presented
# as the German NA (Gemini plan review 2026-08-10).
COUNTRY_SPECTRUM_TYPE = {"BA": 1, "AT": 1, "DE": 2}
GAMMA_I = {"I": 0.8, "II": 1.0, "III": 1.2, "IV": 1.4}

# EN 1998-1 Table 9.3 recommended minima for "simple masonry buildings",
# unreinforced masonry: minimum sum of shear-wall cross-section per
# direction as % of floor area. Rows: ag*S ceiling (g), STRICT `<` (the
# old <=+epsilon selected the lenient column at exact band edges — spec
# §Structure presets 2026-08-13); columns: number of storeys 1..4.
# None = construction type NOT acceptable there.
# National annexes may override — the values are published assumptions.
WALL_DENSITY_MIN = [
    (0.07, [2.0, 2.0, 3.0, 5.0]),
    (0.10, [2.0, 2.5, 5.0, None]),
    (0.15, [3.5, 5.0, None, None]),
    (0.20, [None, None, None, None]),
]
# Table 9.3, confined masonry column (verified against the standard
# 2026-08-13 — values enter the code only as quotes, never from memory):
# columns are storey counts 2..5; the confined table STARTS at 2 storeys.
CONFINED_DENSITY_MIN = [
    (0.07, [2.0, 2.0, 4.0, 6.0]),
    (0.10, [2.5, 3.0, 5.0, None]),
    (0.15, [3.0, 4.0, None, None]),
    (0.20, [3.5, None, None, None]),
]
# [structure] presets (specs/seismic-lateral.md §Structure presets): the
# preset swaps q (EN 1998-1 Table 9.1 recommended values) and the
# Table 9.3 density row AS DATA — one EC8 code path.
STRUCTURE_PRESETS = {
    "urm": dict(q=1.5, table=WALL_DENSITY_MIN, min_storeys=1),
    "confined": dict(q=2.0, table=CONFINED_DENSITY_MIN, min_storeys=2),
}

# Confinement evidence rules, EN 1998-1 §9.5.3 (quoted 2026-08-13,
# spec decision log — grounded search beat both reviewers' memory):
TIE_NEAR = 1.5          # m: max distance intersection -> confining element
TIE_SPACING_MAX = 5.0   # m: max spacing along any load-bearing wall
TIE_OPENING_AREA = 1.5  # m2: openings above this need jamb ties
TIE_PLACE_TOL = 0.3     # m: "at" a jamb/free end (placement tolerance,
#                         not a clause number)


@dataclass
class SeismicBasis:
    """Every seismic number the analysis assumes, in one visible place.
    Densities/finishes come from DesignBasis (shared with the gravity
    engines — two engines must agree on what the building weighs)."""

    q: float = 1.5            # behavior factor, URM per EN 1998-1 9.3
    psi2: float = 0.3         # residential quasi-permanent live factor
    phi_top: float = 1.0      # EN 1998-1 4.2.4: top storey
    phi_other: float = 0.5
    ct: float = 0.05          # T1 = ct * H^0.75 (masonry/other)
    beta: float = 0.2         # lower bound factor on Sd
    fvk0: float = 200.0       # kPa initial masonry shear strength
    gamma_m: float = 1.5      # masonry material factor (seismic)

    def fvd(self) -> float:
        """Design shear strength, kPa. The compression benefit
        (0.4 * sigma_d) is deliberately dropped — conservative, and
        needs no load coupling in S1 (spec decision log)."""
        return self.fvk0 / self.gamma_m


def design_spectrum(t: float, ag: float, spectrum_type: int, ground: str,
                    q: float, beta: float = 0.2) -> float:
    """EN 1998-1 3.2.2.5 design spectrum Sd(T), in units of g."""
    s, tb, tc, td = SPECTRUM[(spectrum_type, ground)]
    if t <= tb:
        return ag * s * (2 / 3 + t / tb * (2.5 / q - 2 / 3))
    if t <= tc:
        return ag * s * 2.5 / q
    if t <= td:
        return max(ag * s * (2.5 / q) * (tc / t), beta * ag)
    return max(ag * s * (2.5 / q) * (tc * td / t ** 2), beta * ag)


def wall_direction(w) -> str | None:
    """'x' within 15 deg of the x axis, 'y' within 15 deg of y, else None
    (a diagonal wall counts toward NO direction — conservative)."""
    dx = abs(w.end.x - w.start.x)
    dy = abs(w.end.y - w.start.y)
    ang = math.degrees(math.atan2(dy, dx))
    if ang <= 15.0:
        return "x"
    if ang >= 75.0:
        return "y"
    return None


def wall_net_length(story, w) -> float:
    """Wall length minus its hosted openings, as a UNION of clipped
    intervals — overlapping or end-clipped openings must not double-cut
    (Codex plan review 2026-08-10)."""
    length = math.hypot(w.end.x - w.start.x, w.end.y - w.start.y)
    intervals = sorted(
        (max(0.0, o.position), min(length, o.position + o.width))
        for o in (*story.doors, *story.windows)
        if o.wall_id == w.global_id)
    cut = 0.0
    cur_lo: float | None = None
    cur_hi = 0.0
    for lo, hi in intervals:
        if hi <= lo:
            continue
        if cur_lo is None or lo > cur_hi:
            if cur_lo is not None:
                cut += cur_hi - cur_lo
            cur_lo, cur_hi = lo, hi
        else:
            cur_hi = max(cur_hi, hi)
    if cur_lo is not None:
        cut += cur_hi - cur_lo
    return max(length - cut, 0.0)


def _density_minimum(ag_s: float, n_storeys: int,
                     preset: dict) -> tuple[float | None, bool]:
    """(minimum %, acceptable) from the preset's Table 9.3 row.
    acceptable=False means the construction type is not acceptable at
    this seismicity/height. Band edges are STRICT `<`: at exactly the
    ceiling the next (stricter) band governs."""
    idx = n_storeys - preset["min_storeys"]
    if idx < 0 or idx > 3:
        return None, False
    for ceiling, row in preset["table"]:
        if ag_s < ceiling:
            minimum = row[idx]
            return minimum, minimum is not None
    return None, False


def _confinement_failures(building: Building) -> list[dict]:
    """Geometric eligibility evidence for the confined classification
    (EN 1998-1 §9.5.3, quoted in specs/seismic-lateral.md): RC
    tie-columns at wall intersections (within 1.5 m), at free wall
    ends, at both jambs of openings > 1.5 m2, spacing <= 5 m. One entry
    per missing location: {story_id, text}. Only host-placed columns
    count — the model already restricts the tie role to full-height rc
    with sides >= 150 mm, and free posts (steel or not) never confine."""
    from shapely.geometry import LineString, Point

    failures: list[dict] = []
    for s in building.stories:
        ties = []
        for c in s.columns:
            if c.wall_id is None:
                continue
            cx, cy, _ux, _uy, _h = s.column_placement(c)
            ties.append((cx, cy))
        bearing = [w for w in s.walls if w.load_bearing]
        segs = {w.global_id: LineString([(w.start.x, w.start.y),
                                         (w.end.x, w.end.y)])
                for w in bearing}

        def fail(text: str, story=s) -> None:
            failures.append({"story_id": story.global_id, "text": text})

        def near_tie(x: float, y: float, tol: float,
                     tie_pts=ties) -> bool:
            return any(math.hypot(tx - x, ty - y) <= tol
                       for tx, ty in tie_pts)

        for w in bearing:
            length = math.hypot(w.end.x - w.start.x, w.end.y - w.start.y)
            if length < 1e-6:
                continue
            ux = (w.end.x - w.start.x) / length
            uy = (w.end.y - w.start.y) / length
            stations = []
            for tx, ty in ties:
                t = (tx - w.start.x) * ux + (ty - w.start.y) * uy
                off = abs(-(tx - w.start.x) * uy + (ty - w.start.y) * ux)
                if off <= w.thickness / 2 + 0.1 and -0.1 <= t <= length + 0.1:
                    stations.append(min(max(t, 0.0), length))
            # free edges: an endpoint that touches no other bearing wall
            for ex, ey in ((w.start.x, w.start.y), (w.end.x, w.end.y)):
                connected = any(
                    other is not w
                    and segs[other.global_id].distance(Point(ex, ey))
                    <= other.thickness / 2 + 0.05
                    for other in bearing)
                if not connected and not near_tie(ex, ey, TIE_PLACE_TOL):
                    fail(f"story '{s.name}': free end of wall '{w.name}' "
                         f"at ({ex:.2f}, {ey:.2f}) has no RC tie-column "
                         "(EN 1998-1 §9.5.3 free edges)")
            # openings > 1.5 m2 need ties at both jambs
            for o in (*s.doors, *s.windows):
                if o.wall_id != w.global_id:
                    continue
                area = o.width * o.height
                if area <= TIE_OPENING_AREA:
                    continue
                for jamb in (o.position, o.position + o.width):
                    if not any(abs(st - jamb) <= TIE_PLACE_TOL
                               for st in stations):
                        fail(f"story '{s.name}': opening '{o.name}' "
                             f"({area:.1f} m2) on wall '{w.name}' has no "
                             f"tie-column at its jamb ({jamb:.2f} m from "
                             "the wall start) (EN 1998-1 §9.5.3 openings)")
            # spacing along the wall <= 5 m between confining elements
            cuts = sorted([0.0, *stations, length])
            for a, b in zip(cuts, cuts[1:]):
                if b - a > TIE_SPACING_MAX:
                    fail(f"story '{s.name}': wall '{w.name}' runs "
                         f"{b - a:.1f} m between confining elements — over "
                         f"the {TIE_SPACING_MAX:.0f} m maximum "
                         "(EN 1998-1 §9.5.3 spacing)")
        # intersections: a tie within 1.5 m of every bearing-wall crossing
        for i, wa in enumerate(bearing):
            for wb in bearing[i + 1:]:
                inter = segs[wa.global_id].intersection(segs[wb.global_id])
                if inter.is_empty:
                    continue
                if inter.geom_type == "Point":
                    pts = [inter]
                elif inter.geom_type == "MultiPoint":
                    pts = list(inter.geoms)
                else:
                    continue    # collinear overlap is not an intersection
                for p in pts:
                    if not near_tie(p.x, p.y, TIE_NEAR):
                        fail(f"story '{s.name}': intersection of walls "
                             f"'{wa.name}' and '{wb.name}' at "
                             f"({p.x:.2f}, {p.y:.2f}) has no RC tie-column "
                             f"within {TIE_NEAR} m (EN 1998-1 §9.5.3 "
                             "intersections)")
    return failures


def _any_unwaived_e103(building: Building, waivers) -> bool:
    """True if the building has a lateral discontinuity (E103 geometry)
    not covered by a waiver — the §9.3(5) q-cut proxy."""
    # lazy import: validators import seismic lazily, so this direction
    # must be lazy too to stay cycle-free
    from archicad_builder.validators.phases import e103_findings
    findings = e103_findings(building)
    if not findings:
        return False
    if waivers is None:
        return True
    from archicad_builder.validators.waivers import partition_findings
    active, _waived, _stale = partition_findings(findings, waivers)
    return bool(active)


def compute_seismic(building: Building, site: Site,
                    basis: SeismicBasis | None = None,
                    structure=None, waivers=None) -> dict:
    """ELF results: weights, T1, Sd, Fb, storey forces, per-direction
    capacity/density/torsion per storey. Raises on site=None — callers
    gate (no site -> unresolved, never guessed).

    `structure` is the [structure] preset (project_config.Structure);
    None = urm, today's behaviour. The confined reward is FAIL-CLOSED:
    the effective type is derived HERE from tie-column geometry, and
    `waivers` gate only the E103 q-cut proxy — waiving E109 documents a
    disagreement, it never unlocks q = 2.0 (spec decision log)."""
    if site is None:
        raise ValueError("compute_seismic requires a [site] configuration")
    basis = basis or SeismicBasis()
    db = DesignBasis()
    stories = sorted(building.stories, key=lambda s: s.elevation)
    if not stories:
        raise ValueError("building has no stories")
    unresolved: dict[str, str] = {}

    # ---------- structure preset (fail-closed) ----------
    declared = structure.type if structure is not None else "urm"
    failures: list[dict] = []
    effective = declared
    if declared == "confined":
        failures = _confinement_failures(building)
        if failures:
            effective = "urm"
    preset = STRUCTURE_PRESETS[effective]
    # basis.q stays the URM default; once a non-URM system earns its
    # classification, the preset is the authority
    q = preset["q"] if effective != "urm" else basis.q
    # EN 1998-1 §9.3(5): elevation-irregular buildings lose 20% of q
    # (floor 1.5). The full §4.2.3.3 assessment is out of scope — proxy:
    # any unwaived E103 discontinuity (spec decision log 2026-08-13).
    q_eff = q
    q_eff_note = None
    if _any_unwaived_e103(building, waivers):
        q_eff = max(1.5, 0.8 * q)
        q_eff_note = ("unwaived E103 discontinuity: q cut by 20% (floor "
                      "1.5) per EN 1998-1 §9.3(5) proxy — elevation "
                      "regularity to be confirmed by the engineer")

    # ---------- level weights (dead + phi*psi2*live), with centroids ----
    def poly_area_centroid(outline):
        vs = [(v.x, v.y) for v in outline.vertices]
        if len(vs) < 3:
            return 0.0, (0.0, 0.0)
        a = cx = cy = 0.0
        for (x0, y0), (x1, y1) in zip(vs, vs[1:] + vs[:1]):
            cross = x0 * y1 - x1 * y0
            a += cross
            cx += (x0 + x1) * cross
            cy += (y0 + y1) * cross
        a *= 0.5
        if abs(a) < 1e-9:
            return 0.0, (0.0, 0.0)
        return abs(a), (cx / (6 * a), cy / (6 * a))

    levels = []      # one per storey: dict(story, z, dead, live, items)
    for s in stories:
        items = []   # (weight kN, x, y) for the CoM
        dead = live = 0.0
        for w in s.walls:
            length = math.hypot(w.end.x - w.start.x, w.end.y - w.start.y)
            wt = length * w.thickness * w.height * db.rc_density
            dead += wt
            items.append((wt, (w.start.x + w.end.x) / 2,
                          (w.start.y + w.end.y) / 2))
        for c in s.columns:
            cx, cy, _ux, _uy, ch = s.column_placement(c)
            rho = db.rc_density if c.material == "rc" else db.steel_density
            if c.wall_id is not None:
                # material-exclusive (specs/columns.md): the host wall's
                # gross mass above already covers the overlap volume at
                # rc density — add only the density DIFFERENCE there plus
                # the full overhang, never both volumes (Codex)
                host = s.get_wall(c.wall_id)
                overlap_d = min(c.depth, host.thickness)
                wt = ((rho - db.rc_density) * c.width * overlap_d * ch
                      + rho * c.width * (c.depth - overlap_d) * ch)
            else:
                wt = rho * c.width * c.depth * ch
            dead += wt
            items.append((wt, cx, cy))
        for r in s.roofs:
            area, (cx, cy) = poly_area_centroid(r.outline)
            wt = area * (min(r.thickness, db.cap_thickness) * db.rc_density
                         + db.roof_finishes)   # snow: psi2 = 0, documented
            dead += wt
            items.append((wt, cx, cy))
        levels.append(dict(story=s, z=s.elevation + s.height,
                           dead=dead, live=live, items=items))

    # floor slabs rest on the level whose z matches their elevation;
    # slabs on grade carry no seismic mass
    for s in stories:
        if s.elevation <= GROUND_EPS:
            continue
        target = next((lv for lv in levels
                       if abs(lv["z"] - s.elevation) < LEVEL_TOL), None)
        for sl in s.slabs:
            if not sl.is_floor:
                continue
            area, (cx, cy) = poly_area_centroid(sl.outline)
            wt = area * (min(sl.thickness, db.cap_thickness) * db.rc_density
                         + db.floor_finishes)
            lv = target
            if lv is None:
                unresolved[sl.global_id] = (
                    f"slab '{sl.name}': no level at z={s.elevation}; "
                    "mass assigned to its own storey")
                lv = next(l_ for l_ in levels if l_["story"] is s)
            lv["dead"] += wt
            lv["live"] += area * db.floor_live
            lv["items"].append((wt, cx, cy))

    top_z = max(lv["z"] for lv in levels)
    for lv in levels:
        phi = basis.phi_top if abs(lv["z"] - top_z) < LEVEL_TOL \
            else basis.phi_other
        lv["W"] = lv["dead"] + phi * basis.psi2 * lv["live"]

    total_w = sum(lv["W"] for lv in levels)

    # ---------- base shear ----------
    # explicit seismic base: diaphragms at or below it carry no lateral
    # force (rigid basement top / grade — Codex plan review 2026-08-10)
    base_elev = (site.seismic_base_elevation
                 if site.seismic_base_elevation is not None
                 else max(0.0, min(s.elevation for s in stories)))
    active = [lv for lv in levels if lv["z"] > base_elev + GROUND_EPS]
    if not active:
        raise ValueError("no diaphragm above the seismic base — check "
                         "seismic_base_elevation")
    w_active = sum(lv["W"] for lv in active)
    h_total = top_z - base_elev
    t1 = basis.ct * h_total ** 0.75
    ag_d = site.ag * GAMMA_I[site.importance_class]
    stype = site.spectrum_type or COUNTRY_SPECTRUM_TYPE[site.country]
    sd = design_spectrum(t1, ag_d, stype, site.ground_type,
                         q_eff, basis.beta)
    tc = SPECTRUM[(stype, site.ground_type)][2]
    lam = 0.85 if (len(active) > 2 and t1 <= 2 * tc) else 1.0
    fb = sd * w_active * lam
    # lateral-force-method applicability is 4*TC / 2.0 s (EN 1998-1
    # 4.3.3.2.1); 2*TC is only the lambda threshold (Codex plan review)
    if t1 > min(4 * tc, 2.0) or h_total > 40.0:
        unresolved["elf"] = (
            f"T1={t1:.2f}s / H={h_total:.1f}m outside the lateral-force "
            "method's applicability (T1 <= min(4*TC, 2.0 s), H <= 40 m)")

    denom = sum((lv["z"] - base_elev) * lv["W"] for lv in active)
    forces = []
    for lv in levels:
        f = (fb * (lv["z"] - base_elev) * lv["W"] / denom
             if lv in active and denom > 0 else 0.0)
        lv["F"] = f
        forces.append(dict(story=lv["story"].name, z=round(lv["z"], 3),
                           W=round(lv["W"], 1), F=round(f, 1)))

    # ---------- per-storey, per-direction ----------
    storeys_out = []
    for s in stories:
        shear = sum(lv["F"] for lv in levels
                    if lv["z"] > s.elevation + GROUND_EPS)
        floor_area = sum(poly_area_centroid(sl.outline)[0]
                         for sl in s.slabs)
        if floor_area <= 0:
            floor_area = sum(poly_area_centroid(r.outline)[0]
                             for r in s.roofs)
        lv = next(l_ for l_ in levels if l_["story"] is s)
        w_items = sum(i[0] for i in lv["items"])
        com = ((sum(i[0] * i[1] for i in lv["items"]) / w_items,
                sum(i[0] * i[2] for i in lv["items"]) / w_items)
               if w_items > 0 else (0.0, 0.0))

        walls = [(w, wall_direction(w), wall_net_length(s, w))
                 for w in s.walls if w.load_bearing]
        skipped = [w.name for w, d, _l in walls if d is None]
        if skipped:
            unresolved[s.global_id] = (
                f"story '{s.name}': diagonal walls counted toward no "
                f"direction (conservative): {', '.join(skipped)}")

        entry: dict = dict(story=s.name, story_id=s.global_id,
                           V=round(shear, 1),
                           floor_area=round(floor_area, 1),
                           # a storey whose ceiling is at or below the
                           # seismic base is a rigid basement: braced by
                           # soil, not judged by Table 9.3 (Codex
                           # re-review 2026-08-10)
                           below_base=(s.elevation + s.height
                                       <= base_elev + GROUND_EPS))
        # centers of rigidity, then torsional radius about (crx, cry)
        stiff = {"x": [], "y": []}   # (k, x, y) per direction
        for w, d, l_net in walls:
            if d is None:
                continue
            stiff[d].append((w.thickness * l_net,
                             (w.start.x + w.end.x) / 2,
                             (w.start.y + w.end.y) / 2))
        kx = sum(k for k, _x, _y in stiff["x"])
        ky = sum(k for k, _x, _y in stiff["y"])
        crx = (sum(k * x for k, x, _y in stiff["y"]) / ky) if ky else None
        cry = (sum(k * y for k, _x, y in stiff["x"]) / kx) if kx else None
        ktheta = 0.0
        if crx is not None and cry is not None:
            ktheta = (sum(k * (y - cry) ** 2 for k, _x, y in stiff["x"])
                      + sum(k * (x - crx) ** 2 for k, x, _y in stiff["y"]))
        xs = [c for w in s.walls for c in (w.start.x, w.end.x)]
        ys = [c for w in s.walls for c in (w.start.y, w.end.y)]
        lx = (max(xs) - min(xs)) if xs else 0.0
        ly = (max(ys) - min(ys)) if ys else 0.0
        ls = math.sqrt((lx ** 2 + ly ** 2) / 12) if (lx or ly) else 0.0

        # Table 9.3 counts the storeys of the SEISMIC system — levels
        # above the base; a rigid basement is not a storey the quake
        # sways (Codex code review 2026-08-10)
        n_storeys = len(active)
        ag_s = ag_d * SPECTRUM[(stype, site.ground_type)][0]
        if effective == "confined" and n_storeys < preset["min_storeys"]:
            # the confined column of Table 9.3 starts at 2 storeys — an
            # invented row would be a lie (spec §Structure presets)
            unresolved["density_table"] = (
                "confined masonry with 1 storey: Table 9.3 simple rules "
                "not applicable, explicit analysis required")
            d_min, acceptable = None, True
        else:
            d_min, acceptable = _density_minimum(ag_s, n_storeys, preset)

        for d in ("x", "y"):
            cap = basis.fvd() * sum(k for k, _x, _y in stiff[d])
            density = (100.0 * sum(k for k, _x, _y in stiff[d]) / floor_area
                       if floor_area > 0 else 0.0)
            k_dir = kx if d == "x" else ky
            perp_com = com[1] if d == "x" else com[0]
            perp_cr = cry if d == "x" else crx
            e0 = abs(perp_com - perp_cr) if perp_cr is not None else None
            r = (math.sqrt(ktheta / k_dir)
                 if k_dir and ktheta > 0 else None)
            regular = (e0 is not None and r is not None
                       and e0 <= 0.30 * r and r >= ls)
            entry[d] = dict(
                capacity=round(cap, 1),
                density=round(density, 2),
                density_min=d_min, acceptable=acceptable,
                e0=None if e0 is None else round(e0, 2),
                r=None if r is None else round(r, 2),
                ls=round(ls, 2), regular=regular)
        storeys_out.append(entry)

    dead_total = sum(lv["dead"] for lv in levels)
    all_items = [it for lv in levels for it in lv["items"]]
    dead_w = sum(i[0] for i in all_items)
    com_global = ([round(sum(i[0] * i[1] for i in all_items) / dead_w, 3),
                   round(sum(i[0] * i[2] for i in all_items) / dead_w, 3)]
                  if dead_w > 0 else [0.0, 0.0])

    assumptions_structure = {
        "urm": ("unreinforced masonry bearing walls + RC ring "
                "beams + RC slabs (EN 1998-1 section 9)"),
        "confined": ("confined masonry bearing walls + RC tie-columns, "
                     "ring beams + RC slabs (EN 1998-1 section 9)"),
    }
    result_structure = {
        "declared": declared, "effective": effective,
        "q": q, "q_eff": q_eff,
        "fallback": (None if effective == declared else
                     "geometric eligibility evidence failed — numbers "
                     "fall back to URM (waivers gate findings, not "
                     "physics)"),
    }
    extra_assumptions = {}
    if q_eff_note:
        extra_assumptions["q_eff_note"] = q_eff_note
    if declared == "confined":
        extra_assumptions["confinement_evidence"] = (
            "geometric eligibility evidence only (tie-column positions "
            "per EN 1998-1 §9.5.3) — NOT §9.5.3 compliance: "
            "reinforcement, stirrups, anchorage and casting sequence "
            "are verified by the engineer")

    return {
        "W": round(w_active, 1), "W_model": round(total_w, 1),
        "dead_total": round(dead_total, 1), "com": com_global,
        "base": base_elev, "H": round(h_total, 3),
        "T1": round(t1, 4), "Sd": round(sd, 4),
        "lambda": lam, "Fb": round(fb, 1),
        "forces": forces, "storeys": storeys_out,
        "structure": result_structure,
        "confinement_failures": failures,
        "_unresolved": unresolved,
        "_assumptions": {
            "basis": ("seismic PLAUSIBILITY per EN 1998-1 lateral force "
                      "method, NOT Eurocode compliance — a licensed "
                      "engineer signs real buildings"),
            "structure": assumptions_structure[effective],
            "structure_declared": declared,
            "structure_effective": (
                effective if effective == declared else
                f"{effective} (declared '{declared}' — "
                + result_structure["fallback"] + ")"),
            **extra_assumptions,
            "q": q, "q_eff": q_eff, "psi2": basis.psi2,
            "fvk0_kpa": basis.fvk0, "gamma_m": basis.gamma_m,
            "fvd": ("fvk0/gamma_m, compression benefit 0.4*sigma_d "
                    "deliberately dropped (conservative)"),
            "spectrum_type": stype,
            "spectrum_params_S_TB_TC_TD":
                list(SPECTRUM[(stype, site.ground_type)]),
            "gamma_I": GAMMA_I[site.importance_class],
            "ag_design_g": round(ag_d, 4),
            "country_note": (
                "DE: DIN EN 1998-1/NA defines its own spectra and soil "
                "classes (R/T/S); Type 2 here is a documented "
                "approximation" if site.country == "DE" else
                f"{site.country}: national annex prescribes Type "
                f"{COUNTRY_SPECTRUM_TYPE[site.country]}"),
            "mass": ("DesignBasis densities/finishes shared with the "
                     "gravity engines; storey lumped at its ceiling; "
                     "slabs on grade excluded; wall openings not "
                     "subtracted from mass (conservative); snow psi2=0; "
                     "column self-weight material-exclusive (embedded "
                     "overlap counted once)"),
            "wall_density_table": ("EN 1998-1 Table 9.3 recommended "
                                   f"values, {effective} row "
                                   "(NA-overridable)"),
        },
    }
