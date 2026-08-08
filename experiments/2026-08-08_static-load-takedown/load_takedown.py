"""Static load takedown for villa-maketa: does any opening's wall band
carry the roof beyond plausibility? See AGENTS.md for the model and all
assumptions. Experiment code — allowed to hack, promoted only via spec.

    ../../.venv/bin/python load_takedown.py
"""
import json
import math
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon

REPO = Path(__file__).resolve().parents[2]
BUILDING = REPO / "projects" / "villa-maketa" / "building.json"

# --- load assumptions (AGENTS.md § Setup) -----------------------------------
SCENARIOS = {
    "A as-modeled 0.45m RC": 0.45 * 25.0,          # kN/m2 dead
    "B realistic 0.20m RC + build-up": 0.20 * 25.0 + 2.0,
}
SNOW = 1.65 * 0.8            # kN/m2, sk * mu1
GAMMA_G, GAMMA_Q = 1.35, 1.5
WALL_DENSITY = 25.0          # kN/m3, band self-weight
BEARING = 0.25               # m added to opening width -> effective span
FCTD = 1.0e3                 # kN/m2 (1.0 MPa) design tension, plain band
AS_MM2, FYD = 226.0, 435.0   # 2xO12 B500, N/mm2
SAMPLE_STEP = 0.1            # m along each wall
PARALLEL_TOL = math.radians(15)


def load_model():
    doc = json.loads(BUILDING.read_text())
    gf = next(s for s in doc["stories"] if s["elevation"] == 0)
    return gf


def wall_dir(w):
    dx = w["end"]["x"] - w["start"]["x"]
    dy = w["end"]["y"] - w["start"]["y"]
    length = math.hypot(dx, dy)
    return (dx / length, dy / length), length


def line_load(gf, wall, roofs, lb_walls):
    """ULS roof line load (kN/m) on `wall` per scenario, via one-way strips:
    interior tributary = half distance to nearest parallel LB wall, exterior
    tributary = roof overhang beyond the wall line. Sampled along the wall."""
    (ux, uy), length = wall_dir(wall)
    nx, ny = -uy, ux  # unit normal
    n = max(2, int(length / SAMPLE_STEP))
    per_scenario = {name: [] for name in SCENARIOS}
    covered = 0
    for i in range(n):
        t = (i + 0.5) / n * length
        px = wall["start"]["x"] + ux * t
        py = wall["start"]["y"] + uy * t
        roof = next((r for r in roofs if r["poly"].buffer(0.05).contains(Point(px, py))), None)
        if roof is None:
            for name in per_scenario:
                per_scenario[name].append(0.0)
            continue
        covered += 1
        # distances to roof edge along +/- normal (bounded ray)
        spans = {}
        for sgn in (+1, -1):
            ray = LineString([(px, py), (px + sgn * nx * 30, py + sgn * ny * 30)])
            inside = ray.intersection(roof["poly"])
            spans[sgn] = inside.length if not inside.is_empty else 0.0
        # nearest parallel load-bearing wall on each side
        trib = 0.0
        for sgn in (+1, -1):
            best = None
            for other in lb_walls:
                if other is wall:
                    continue
                (ox, oy), _ = wall_dir(other)
                cross = abs(ux * oy - uy * ox)
                if cross > math.sin(PARALLEL_TOL):
                    continue
                ray = LineString([(px, py), (px + sgn * nx * 30, py + sgn * ny * 30)])
                seg = LineString([(other["start"]["x"], other["start"]["y"]),
                                  (other["end"]["x"], other["end"]["y"])])
                hit = ray.intersection(seg)
                if hit.is_empty:
                    continue
                d = Point(px, py).distance(hit)
                if 0.05 < d and (best is None or d < best):
                    best = d
            if best is not None:
                trib += min(best, spans[sgn] * 2) / 2  # half-span, capped by roof
            else:
                trib += spans[sgn]  # no support that way: cantilever, full width
        for name, dead in SCENARIOS.items():
            q_area = GAMMA_G * dead + GAMMA_Q * SNOW
            per_scenario[name].append(q_area * trib)
    coverage = covered / n
    avgs = {name: (sum(v) / len(v)) for name, v in per_scenario.items()}
    return avgs, coverage, per_scenario


def main():
    gf = load_model()
    roofs = [{"name": r["name"],
              "poly": Polygon([(v["x"], v["y"]) for v in r["outline"]["vertices"]]),
              "thickness": r["thickness"]}
             for r in gf["roofs"]]
    walls = {w["global_id"]: w for w in gf["walls"]}
    lb_walls = [w for w in gf["walls"] if w.get("load_bearing")]

    openings = []
    for kind in ("windows", "doors"):
        for o in gf[kind]:
            w = walls.get(o["wall_id"])
            if w is None or not w.get("load_bearing"):
                continue
            head = o.get("sill_height", 0.0) + o["height"]
            band = w["height"] - head
            openings.append((o, w, head, band))

    beams = gf.get("beams", []) if isinstance(gf, dict) else []

    def covering_beam(w, o):
        # same coverage idea as E062, simplified for the known geometry
        (ux, uy), wl = wall_dir(w)
        a = o["position"]; bpos = o["position"] + o["width"]
        for bm in beams:
            bux = bm["end"]["x"] - bm["start"]["x"]
            buy = bm["end"]["y"] - bm["start"]["y"]
            bl = math.hypot(bux, buy)
            if bl < 1e-6: continue
            bux, buy = bux / bl, buy / bl
            if abs(ux * buy - uy * bux) > 0.26: continue
            for t in (a, bpos):
                px = w["start"]["x"] + ux * t; py = w["start"]["y"] + uy * t
                rx, ry = px - bm["start"]["x"], py - bm["start"]["y"]
                along = rx * bux + ry * buy
                lat = abs(-rx * buy + ry * bux)
                if lat > 0.2 or along < -0.2 or along > bl + 0.2: break
            else:
                return bm
        return None

    print(f"{'opening':34s} {'beam b x d':>10s} {'span':>5s} "
          f"{'q_A':>6s} {'q_B':>6s} {'M_A':>6s} {'M_B':>6s} "
          f"{'util_A':>7s} {'util_B':>7s}")
    results = []
    for o, w, head, band in openings:
        q, coverage, _samples = line_load(gf, w, roofs, lb_walls)
        span = o["width"] + BEARING
        bm = covering_beam(w, o)
        if bm is None:
            note = ("below 1.25m threshold, band carries it"
                    if o["width"] < 1.25 else "-> E062 fires")
            print(f"{o['name'][:34]:34s} {'NO BEAM':>10s} {span:5.2f}  {note}")
            continue
        bw, bd = bm["width"], bm["depth"]
        # beam self-weight + the wall band's weight riding on it
        self_w = GAMMA_G * (bw * bd + max(band, 0) * w["thickness"]) * WALL_DENSITY
        rows = {}
        for name, ql in q.items():
            q_tot = ql + self_w
            m = q_tot * span ** 2 / 8
            d_eff = max(bd - 0.05, 0.01)
            as_mm2 = 0.005 * bw * d_eff * 1e6  # rho 0.5%
            m_rd = as_mm2 * FYD * 0.9 * d_eff * 1e-3  # kNm
            rows[name] = (q_tot, m, m / m_rd)
        a, bsc = rows[list(SCENARIOS)[0]], rows[list(SCENARIOS)[1]]
        print(f"{o['name'][:34]:34s} {bw:4.2f}x{bd:4.2f} {span:5.2f} "
              f"{a[0]:6.1f} {bsc[0]:6.1f} {a[1]:6.1f} {bsc[1]:6.1f} "
              f"{a[2]:7.2f} {bsc[2]:7.2f}")
        results.append((o["name"], bm["name"], rows))

    # --emit-json: write per-element load data for the walkthrough's Loads
    # view (owner 2026-08-08). Beams carry true utilization (scenario B, the
    # design target); bearing walls carry their ULS line load, with a
    # relative 0..0.9 shade so one color ramp serves both.
    if "--emit-json" in sys.argv:
        out_path = Path(sys.argv[sys.argv.index("--emit-json") + 1])
        data = {}
        b_name = list(SCENARIOS)[1]  # realistic build-up
        for oname, bname, rows in results:
            bm = next(x for x in beams if x["name"] == bname)
            key = "IfcBeam_" + bname.replace(" ", "_")
            data[key] = {
                "kind": "beam",
                "u": round(rows[b_name][2], 2),
                "q": round(rows[b_name][0], 1),
                "M": round(rows[b_name][1], 1),
                "section": f"{bm['width']:.2f}x{bm['depth']:.2f}",
                "over": oname,
                "a": [bm["start"]["x"], bm["start"]["y"]],
                "b": [bm["end"]["x"], bm["end"]["y"]],
            }
        # Walls: TRUE axial utilization (owner 2026-08-08: "show me what
        # would fail, not a light show" — no relative shading, no cutoffs).
        # Capacity per meter = thickness × Φ·f_d (f_d 3.0 MPa conservative
        # masonry/RC-wall design value, Φ 0.6 slenderness) = t × 1800 kN/m².
        # Wall q includes its own self-weight (3.0m storey, 25 kN/m³, γ_G).
        PHI_FD = 0.6 * 3000.0  # kN/m2

        def wall_entry(w, q_total, samples_total, extra=0.0):
            cap = w["thickness"] * PHI_FD
            self_w = GAMMA_G * 3.0 * w["thickness"] * 25.0
            nb = 8
            per = max(1, len(samples_total) // nb)
            profile = [
                round((sum(samples_total[i * per:(i + 1) * per])
                       / max(1, len(samples_total[i * per:(i + 1) * per]))
                       + self_w + extra) / cap, 2)
                for i in range(nb)
            ]
            return {
                "kind": "wall",
                "u": round((q_total + self_w + extra) / cap, 2),
                "q": round(q_total + self_w + extra, 1),
                "a": [w["start"]["x"], w["start"]["y"]],
                "b": [w["end"]["x"], w["end"]["y"]],
                "profile": profile,
            }

        gf_wall_q = {}
        for w in lb_walls:
            q, coverage, samples = line_load(gf, w, roofs, lb_walls)
            gf_wall_q[w["name"]] = (w, q[b_name])
            data["IfcWallStandardCase_" + w["name"].replace(" ", "_")] = \
                wall_entry(w, q[b_name], samples[b_name])

        # Garage storey (owner: "I want to see the garage"): each garage
        # wall carries the aligned GF wall's roof load + that wall's own
        # weight + a one-way strip of the GF slab (0.25m RC + 1.5 finishes
        # dead, 2.0 live → ULS ≈ 13.5 kN/m²), spanning between garage walls.
        doc_all = json.loads(BUILDING.read_text())
        gar = next(s for s in doc_all["stories"] if s["elevation"] != 0)
        gar_lb = [w for w in gar["walls"] if w.get("load_bearing")]
        Q_SLAB = GAMMA_G * (0.25 * 25.0 + 1.5) + GAMMA_Q * 2.0
        gf_slab_polys = [Polygon([(v["x"], v["y"]) for v in s["outline"]["vertices"]])
                        for s in gf["slabs"] if len(s["outline"]["vertices"]) >= 3]
        slab_areas = [{"name": "GF slab", "poly": p, "thickness": 0.25}
                      for p in gf_slab_polys]

        def aligned_gf_q(gw):
            for name, (w, q) in gf_wall_q.items():
                if (abs(w["start"]["x"] - gw["start"]["x"]) < 0.2
                        and abs(w["start"]["y"] - gw["start"]["y"]) < 0.2
                        and abs(w["end"]["x"] - gw["end"]["x"]) < 0.2
                        and abs(w["end"]["y"] - gw["end"]["y"]) < 0.2) or (
                        abs(w["start"]["x"] - gw["end"]["x"]) < 0.2
                        and abs(w["start"]["y"] - gw["end"]["y"]) < 0.2
                        and abs(w["end"]["x"] - gw["start"]["x"]) < 0.2
                        and abs(w["end"]["y"] - gw["start"]["y"]) < 0.2):
                    return q + GAMMA_G * 3.0 * w["thickness"] * 25.0
            return 0.0

        gar_wall_q = {}
        for gw in gar_lb:
            avgs, cov, samples = line_load(gar, gw, slab_areas, gar_lb)
            # line_load scales by SCENARIOS; renormalize to the slab load
            scale = Q_SLAB / (GAMMA_G * list(SCENARIOS.values())[1] + GAMMA_Q * SNOW)
            q_slab_strip = avgs[b_name] * scale
            slab_samples = [s * scale for s in samples[b_name]]
            from_above = aligned_gf_q(gw)
            gar_wall_q[gw["name"]] = q_slab_strip + from_above
            data["IfcWallStandardCase_" + gw["name"].replace(" ", "_")] = \
                wall_entry(gw, q_slab_strip, slab_samples, extra=from_above)

        # Garage vehicle-door beam: checked against its wall's line load
        gar_beams = gar.get("beams", [])
        for gd in gar["doors"]:
            gwall = next((w for w in gar_lb if w["global_id"] == gd["wall_id"]), None)
            bm = next((x for x in gar_beams if gd["name"] in x["name"]), None)
            if gwall is None or bm is None:
                continue
            span = gd["width"] + BEARING
            q_tot = gar_wall_q.get(gwall["name"], 0.0)
            m = q_tot * span ** 2 / 8
            d_eff = max(bm["depth"] - 0.05, 0.01)
            m_rd = 0.005 * bm["width"] * d_eff * 435000.0 * 0.9 * d_eff
            data["IfcBeam_" + bm["name"].replace(" ", "_")] = {
                "kind": "beam",
                "u": round(m / m_rd, 2),
                "q": round(q_tot, 1),
                "M": round(m, 1),
                "section": f"{bm['width']:.2f}x{bm['depth']:.2f}",
                "over": gd["name"],
                "a": [bm["start"]["x"], bm["start"]["y"]],
                "b": [bm["end"]["x"], bm["end"]["y"]],
            }
        out_path.write_text(json.dumps(data, indent=1, sort_keys=True))
        print(f"\nwrote {out_path} ({len(data)} elements)")

    print("\nutil = M_ed / M_rd of the PLACED beam (RC, rho 0.5%, fyd 435)."
          "\nScenario A = roof as modeled (0.45m solid RC), B = realistic"
          "\nbuild-up (0.20m RC + 2.0). ULS 1.35G+1.5S. util <= 1.0 passes.")
    if results:
        worst = max(results, key=lambda r: r[2][list(SCENARIOS)[0]][2])
        print(f"\nworst beam: {worst[1]} ({worst[0]}): "
              f"{worst[2][list(SCENARIOS)[0]][2]:.2f} (A) / "
              f"{worst[2][list(SCENARIOS)[1]][2]:.2f} (B)")


if __name__ == "__main__":
    main()
