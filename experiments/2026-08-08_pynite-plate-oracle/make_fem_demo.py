"""Assemble a LOCAL demo walkthrough whose Loads view shows the FEM
oracle results (walls/roofs/slab from PyNite; beams keep strip-engine
values — clearly bannered). Writes OUTSIDE the repo; production output/
is never touched.

Run: ../../.venv/bin/python make_fem_demo.py <fem-loads.json> <dest-dir>
"""

import json
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "projects/villa-maketa/output"

fem_path, dest = Path(sys.argv[1]), Path(sys.argv[2])
dest.mkdir(parents=True, exist_ok=True)

strip = json.load(open(OUT / "loads.json"))
fem = json.load(open(fem_path))

merged = {k: v for k, v in strip.items() if v.get("kind") == "beam"} if isinstance(strip, dict) else {}
merged.update({k: v for k, v in fem.items() if not k.startswith("_")})
merged["_assumptions"] = fem.get("_assumptions", []) + [
    "beams: strip-engine values (FEM beam extraction not in scope of this demo)"]
merged["_unresolved"] = []

html = (OUT / "walkthrough.html").read_text()
lines = html.split("\n")
hits = [i for i, ln in enumerate(lines) if ln.lstrip().startswith("const LOADS = ")]
assert len(hits) == 1, f"expected exactly one LOADS line, found {len(hits)}"
start = hits[0]
end = next(i for i in range(start, len(lines)) if lines[i].rstrip().endswith("};"))
indent = re.match(r"\s*", lines[start]).group(0)
lines[start:end + 1] = [f"{indent}const LOADS = {json.dumps(merged)};"]
html = "\n".join(lines)

banner = ('<div style="position:fixed;top:0;left:50%;transform:translateX(-50%);'
          'z-index:9999;background:#7c2d92;color:#fff;font:600 12px system-ui;'
          'padding:4px 14px;border-radius:0 0 8px 8px;pointer-events:none">'
          'FEM ORACLE DEMO — PyNite plate model (experiment, not the shipped engine)</div>')
html = html.replace("<body>", "<body>" + banner, 1)

(dest / "walkthrough-fem.html").write_text(html)
if not (dest / "villa.glb").exists():
    shutil.copy(OUT / "villa.glb", dest / "villa.glb")
print(f"demo at {dest}/walkthrough-fem.html ({len(merged)-2} elements)")
