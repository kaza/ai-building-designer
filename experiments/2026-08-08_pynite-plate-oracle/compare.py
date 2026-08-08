"""FEM vs strip-engine comparison + mesh convergence table.

Run: ../../.venv/bin/python compare.py logs/villa-fem-mesh0.4.json \
        logs/villa-fem-mesh0.25.json [logs/villa-fem-mesh0.18.json]
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
strip = json.load(open(REPO / "projects/villa-maketa/output/loads.json"))
runs = [json.load(open(p)) for p in sys.argv[1:]]
meshes = [r["mesh"] for r in runs]


def strip_u(kind, elem):
    slug = elem.replace(" ", "_")
    key = ("IfcWallStandardCase_" if kind == "wall" else "IfcSlab_") + slug
    entry = strip.get(key)
    return entry["u"] if entry else None


names = sorted(runs[-1]["results"], key=lambda n: -runs[-1]["results"][n]["u"])
hdr = "  ".join(f"fem@{m}" for m in meshes)
print(f"{'element':40s} {'strip':>6s}  {hdr}   note")
for name in names:
    kind, elem = name.split(" ", 1)
    su = strip_u(kind, elem)
    fus = [r["results"].get(name, {}).get("u") for r in runs]
    cells = "  ".join(f"{u:7.2f}" if u is not None else "      -" for u in fus)
    ref = fus[-1]
    note = ""
    if len([u for u in fus if u]) >= 2 and fus[-2] and ref:
        drift = abs(ref - fus[-2]) / max(ref, 1e-9)
        note += "conv" if drift < 0.10 else f"DRIFT {drift:.0%}"
    if su is not None and ref:
        ratio = ref / su
        if ratio > 1.25 or ratio < 0.8:
            note += f"  strip {'UNDER' if ratio > 1 else 'over'}x{ratio:.1f}"
    print(f"{name:40s} {su if su is not None else float('nan'):6.2f}  {cells}   {note}")

print("\nbalance:", ", ".join(f"mesh {r['mesh']}: {r['reactions']/r['applied']:.4f}" for r in runs))
