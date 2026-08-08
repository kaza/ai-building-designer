"""Static load takedown for villa-maketa: does any opening's wall band
carry the roof beyond plausibility? See AGENTS.md for the model and all
assumptions. Experiment code — allowed to hack, promoted only via spec.

    ../../.venv/bin/python load_takedown.py
"""
import json
import math
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
    return {name: (sum(v) / len(v)) for name, v in per_scenario.items()}, coverage


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

    print(f"{'opening':34s} {'wall':24s} {'span':>5s} {'band':>5s} "
          f"{'q_A':>6s} {'q_B':>6s} {'M_A':>6s} {'util_plain_A':>12s} "
          f"{'util_plain_B':>12s} {'util_2xO12_A':>12s}")
    results = []
    for o, w, head, band in openings:
        q, coverage = line_load(gf, w, roofs, lb_walls)
        span = o["width"] + BEARING
        b = w["thickness"]
        # band self-weight on top of the roof strip load
        self_w = GAMMA_G * band * b * WALL_DENSITY
        rows = {}
        for name, ql in q.items():
            q_tot = ql + self_w
            m = q_tot * span ** 2 / 8
            w_el = b * band ** 2 / 6 if band > 0 else 0.0  # m3
            m_plain = w_el * FCTD
            d_eff = max(band - 0.04, 0.01)
            m_rc = AS_MM2 * FYD * 0.9 * d_eff * 1e-3  # kNm
            rows[name] = (q_tot, m,
                          m / m_plain if m_plain > 0 else float("inf"),
                          m / m_rc)
        a, bsc = rows[list(SCENARIOS)[0]], rows[list(SCENARIOS)[1]]
        print(f"{o['name'][:34]:34s} {w['name'][:24]:24s} {span:5.2f} {band:5.2f} "
              f"{a[0]:6.1f} {bsc[0]:6.1f} {a[1]:6.1f} {a[2]:12.2f} "
              f"{bsc[2]:12.2f} {a[3]:12.2f}")
        results.append((o["name"], w["name"], span, band, rows, coverage))

    print("\nutil > 1.0 = section fails that check (plain = unreinforced band;"
          "\n2xO12 = minimally reinforced RC ring beam). Scenario A = roof as"
          "\nmodeled (0.45m solid RC), B = realistic build-up. ULS 1.35G+1.5S.")
    worst = max(results, key=lambda r: r[4][list(SCENARIOS)[0]][2])
    print(f"\nworst plain-band utilization: {worst[0]} over {worst[1]}: "
          f"{worst[4][list(SCENARIOS)[0]][2]:.1f}x (scenario A)")


if __name__ == "__main__":
    main()
