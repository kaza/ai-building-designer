"""Seismic ELF plausibility engine — specs/seismic-lateral.md (S1).

Eurocode 8 lateral force method, structural plausibility screening
(NOT EN 1998 compliance — a licensed engineer signs real buildings).
Structure type assumed: unreinforced masonry bearing walls + RC ring
beams + RC slabs (q = 1.5). Weights reuse the gravity engines'
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
# direction as % of floor area. Rows: ag*S ceiling (g); columns: number
# of storeys 1..4. None = construction type NOT acceptable there.
# National annexes may override — the values are published assumptions.
WALL_DENSITY_MIN = [
    (0.07, [2.0, 2.0, 3.0, 5.0]),
    (0.10, [2.0, 2.5, 5.0, None]),
    (0.15, [3.5, 5.0, None, None]),
    (0.20, [None, None, None, None]),
]


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


def _density_minimum(ag_s: float, n_storeys: int) -> tuple[float | None, bool]:
    """(minimum %, acceptable) from Table 9.3. acceptable=False means URM
    is not an acceptable construction type at this seismicity/height."""
    if n_storeys > 4:
        return None, False
    for ceiling, row in WALL_DENSITY_MIN:
        if ag_s <= ceiling + 1e-9:
            minimum = row[n_storeys - 1]
            return minimum, minimum is not None
    return None, False


def compute_seismic(building: Building, site: Site,
                    basis: SeismicBasis | None = None) -> dict:
    """ELF results: weights, T1, Sd, Fb, storey forces, per-direction
    capacity/density/torsion per storey. Raises on site=None — callers
    gate (no site -> unresolved, never guessed)."""
    if site is None:
        raise ValueError("compute_seismic requires a [site] configuration")
    basis = basis or SeismicBasis()
    db = DesignBasis()
    stories = sorted(building.stories, key=lambda s: s.elevation)
    if not stories:
        raise ValueError("building has no stories")
    unresolved: dict[str, str] = {}

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
                         basis.q, basis.beta)
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
        d_min, acceptable = _density_minimum(ag_s, n_storeys)

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

    return {
        "W": round(w_active, 1), "W_model": round(total_w, 1),
        "dead_total": round(dead_total, 1), "com": com_global,
        "base": base_elev, "H": round(h_total, 3),
        "T1": round(t1, 4), "Sd": round(sd, 4),
        "lambda": lam, "Fb": round(fb, 1),
        "forces": forces, "storeys": storeys_out,
        "_unresolved": unresolved,
        "_assumptions": {
            "basis": ("seismic PLAUSIBILITY per EN 1998-1 lateral force "
                      "method, NOT Eurocode compliance — a licensed "
                      "engineer signs real buildings"),
            "structure": ("unreinforced masonry bearing walls + RC ring "
                          "beams + RC slabs (EN 1998-1 section 9)"),
            "q": basis.q, "psi2": basis.psi2,
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
                     "subtracted from mass (conservative); snow psi2=0"),
            "wall_density_table": ("EN 1998-1 Table 9.3 recommended "
                                   "values (NA-overridable)"),
        },
    }
