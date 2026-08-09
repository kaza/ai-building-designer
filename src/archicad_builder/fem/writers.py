"""FEM X-ray payload writers (specs/fem-xray.md).

fem-field.json — versioned envelope with flat, quantized arrays so the
browser can decode without a multi-second JSON.parse of nested objects
(plan review: 2 MB nested JSON janks phones):
  { schema, coords, mesh, digest, balance, assumptions, unresolved,
    elems: [{id, name, kind, story, u, peak,
             p: [every channel, preformatted]}...],
    quads: { n, elem: [i...], u: [..], pos: [12*n floats] } }

fem-loads.json — per-element reference results for humans and agents
(keyed by global_id, Ifc-style display name included). NOT consumed by
the walkthrough Loads view — that stays on the strip engine's loads.json.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import FemResult

IFC_PREFIX = {"wall": "IfcWallStandardCase_", "slab": "IfcSlab_",
              "roof": "IfcSlab_", "beam": "IfcBeam_"}


def building_digest(building_json: Path) -> str:
    return hashlib.sha256(building_json.read_bytes()).hexdigest()[:12]


def write_payloads(res: FemResult, out_dir: Path, digest: str) -> None:
    # u = design value (what the element is judged on), peak = worst single
    # fragment. Standard practice is to size from a design section and read
    # the peak only as a local-detailing hint, so both travel together.
    elems = [dict(id=gid, name=e["name"], kind=e["kind"], story=e["story"],
                  u=round(e["u"], 3), peak=round(e.get("u_peak", 0.0), 3),
                  p=e.get("parts", []))
             for gid, e in res.elements.items()]
    index = {e["id"]: i for i, e in enumerate(elems)}
    pos: list[float] = []
    e_idx: list[int] = []
    u_arr: list[float] = []
    g_arr: list[int] = []      # governing component: 0 vert compression,
    s_arr: list[float] = []    # 1 horiz tension, 2 vert tension, 3 bending,
    #                            4 diagonal tension (in-plane shear).
    # s_arr carries a STRESS in kN/m2 for wall codes and 0 for plates, so a
    # decoder can render MPa without unit metadata (Codex review).
    for q in res.field["quads"]:
        e_idx.append(index[q["e"]])
        u_arr.append(q["u"])
        g_arr.append(q.get("g", 3))
        s_arr.append(q.get("s", 0))
        for corner in q["c"]:
            pos.extend(corner)
    envelope = dict(
        schema=1, coords=res.field["coords"], mesh=res.field["mesh"],
        digest=digest, balance=round(res.balance, 4),
        assumptions=res.assumptions, unresolved=res.unresolved,
        not_modelled=res.not_modelled,
        elems=elems,
        quads=dict(n=len(e_idx), elem=e_idx, u=u_arr, g=g_arr, s=s_arr,
                   pos=pos))
    (out_dir / "fem-field.json").write_text(
        json.dumps(envelope, separators=(",", ":")))

    loads = {}
    for gid, e in res.elements.items():
        entry = {k: (round(v, 3) if isinstance(v, float) else v)
                 for k, v in e.items()}
        entry["ifc"] = IFC_PREFIX[e["kind"]] + e["name"].replace(" ", "_")
        loads[gid] = entry
    loads["_assumptions"] = res.assumptions + [f"balance {res.balance:.4f}"]
    loads["_unresolved"] = res.unresolved
    loads["_not_modelled"] = res.not_modelled
    (out_dir / "fem-loads.json").write_text(json.dumps(loads, indent=1))
