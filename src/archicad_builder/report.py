"""Engineer handoff report — specs/engineer-handoff.md (S4).

ONE self-contained HTML the engineer marks up and signs against. It
presents results computed elsewhere (strip engine, FEM, seismic ELF,
validators) and computes nothing new. Missing inputs render as red
NOT RUN sections — a partial report must look partial.
"""
from __future__ import annotations

import hashlib
import html as _html
import json
from datetime import datetime
from pathlib import Path

from archicad_builder.models import Building
from archicad_builder.project_config import ProjectConfig
from archicad_builder.validators.phases import validate_all_phases
from archicad_builder.validators.waivers import load_waivers, partition_findings

_CSS = """
body { font: 14px/1.5 system-ui, sans-serif; color: #1a1a1a;
       max-width: 60rem; margin: 2rem auto; padding: 0 1rem; }
h1 { font-size: 1.5rem; } h2 { font-size: 1.15rem; margin-top: 2rem;
     border-bottom: 2px solid #444; padding-bottom: 0.2rem; }
table { border-collapse: collapse; margin: 0.6rem 0; width: 100%; }
th, td { border: 1px solid #bbb; padding: 3px 8px; text-align: left;
         font-size: 13px; }
th { background: #eee; }
.banner { background: #fff3cd; border: 2px solid #b8860b;
          padding: 0.8rem 1rem; font-weight: 600; }
.notrun { background: #fdecea; border: 2px solid #c0392b;
          color: #c0392b; padding: 0.8rem 1rem; font-weight: 700; }
.muted { color: #666; font-size: 12px; }
.err { color: #c0392b; } .warn { color: #b8860b; }
@media print { body { max-width: none; } }
"""


def _esc(v) -> str:
    return _html.escape(str(v))


def _table(headers, rows) -> str:
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>"
        for row in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def _kv(d: dict) -> str:
    return _table(["key", "value"], sorted(d.items()))


def _not_run(what: str) -> str:
    return (f'<div class="notrun">NOT RUN — {_esc(what)} is missing. '
            "This report is INCOMPLETE until it is generated.</div>")


def _load_json(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def build_report(project_dir: Path) -> str:
    project_dir = Path(project_dir)
    building_path = project_dir / "building.json"
    building = Building.load(building_path)
    cfg = ProjectConfig.load(project_dir)
    site = cfg.site
    out = project_dir / "output"
    loads = _load_json(out / "loads.json")
    fem = _load_json(out / "fem-loads.json")
    seismic = _load_json(out / "seismic.json")
    digest = hashlib.sha256(building_path.read_bytes()).hexdigest()[:12]

    s: list[str] = []
    s.append(
        '<div class="banner">Generated design — requires verification and '
        'signature by a licensed civil engineer. Nothing in this document '
        'goes to a construction site without that signature. This report '
        'exists to make the verification complete and fast.</div>')

    # identity
    stories = sorted(building.stories, key=lambda st: st.elevation)
    s.append("<h2>Project</h2>")
    s.append(_kv({"name": building.name, "building digest": digest,
                  "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
                  "stories": len(stories)}))
    s.append(_table(
        ["story", "elevation m", "height m", "walls", "slabs", "footings"],
        [[st.name, st.elevation, st.height, len(st.walls), len(st.slabs),
          len(st.footings)] for st in stories]))

    # site & design basis
    s.append("<h2>Site &amp; design basis</h2>")
    if site is None:
        s.append("<p class='err'>unresolved — no [site] in project.toml: "
                 "seismic and foundation checks did not run.</p>")
    else:
        s.append(_kv(site.model_dump(exclude_none=True)))
    from archicad_builder.seismic import SeismicBasis
    from archicad_builder.structural import DesignBasis
    s.append("<h3>Gravity basis (DesignBasis)</h3>")
    s.append(_kv(vars(DesignBasis())))
    s.append("<h3>Seismic basis (SeismicBasis)</h3>")
    s.append(_kv(vars(SeismicBasis())))
    s.append('<p class="muted">Values are EC-recommended or assumed '
             'unless the site config overrides them; every engine '
             'publishes its own _assumptions verbatim below.</p>')

    # gravity — strip engine
    s.append("<h2>Gravity — strip engine</h2>")
    if loads is None:
        s.append(_not_run("output/loads.json"))
    else:
        recs = [(k, v) for k, v in loads.items()
                if not k.startswith("_") and isinstance(v, dict)]
        worst = sorted(recs, key=lambda t: -t[1].get("u", 0))[:10]
        s.append(_table(["element", "kind", "u"],
                        [[v.get("name", k), v.get("kind", "?"),
                          v.get("u", "?")] for k, v in worst]))
        if loads.get("_unresolved"):
            s.append("<p class='warn'>unresolved: "
                     + _esc(loads["_unresolved"]) + "</p>")
        s.append('<p class="muted">assumptions: '
                 + _esc(loads.get("_assumptions", {})) + "</p>")

    # gravity + seismic — FEM
    s.append("<h2>FEM X-ray</h2>")
    if fem is None:
        s.append(_not_run("output/fem-loads.json"))
    else:
        recs = [(k, v) for k, v in fem.items()
                if not k.startswith("_") and isinstance(v, dict)]
        worst = sorted(recs, key=lambda t: -t[1].get("u", 0))[:10]
        s.append(_table(
            ["element", "kind", "design u", "peak", "governing combo"],
            [[v.get("name", k), v.get("kind", "?"), v.get("u", "?"),
              v.get("u_peak", ""), v.get("combo", "ULS")]
             for k, v in worst]))
        s.append('<p class="muted">'
                 + "<br>".join(_esc(a) for a in fem.get("_assumptions", []))
                 + "</p>")

    # seismic ELF
    s.append("<h2>Seismic — lateral force method</h2>")
    if site is None:
        s.append("<p class='err'>unresolved — no [site] configured.</p>")
    elif seismic is None:
        s.append(_not_run("output/seismic.json"))
    elif "_unresolved" in seismic and seismic.get("Fb") is None:
        s.append("<p class='err'>unresolved: "
                 + _esc(seismic["_unresolved"]) + "</p>")
    else:
        s.append(_kv({"total seismic weight W (kN)": seismic["W"],
                      "height H (m)": seismic["H"],
                      "T1 (s)": seismic["T1"],
                      "Sd(T1) (g)": seismic["Sd"],
                      "lambda": seismic["lambda"],
                      "base shear Fb (kN)": seismic["Fb"]}))
        s.append("<h3>Storey forces</h3>")
        s.append(_table(["story", "z m", "W kN", "F kN"],
                        [[f["story"], f["z"], f["W"], f["F"]]
                         for f in seismic["forces"]]))
        s.append("<h3>Per-direction checks</h3>")
        rows = []
        for st in seismic["storeys"]:
            for d in ("x", "y"):
                e = st[d]
                rows.append([st["story"], d, st["V"], e["capacity"],
                             e["density"], e["density_min"],
                             "yes" if e["acceptable"] else "NO",
                             e["e0"], e["r"], e["ls"],
                             "yes" if e["regular"] else "NO"])
        s.append(_table(["story", "dir", "V kN", "capacity kN",
                         "density %", "min %", "URM acceptable",
                         "e0 m", "r m", "ls m", "regular"], rows))
        if seismic.get("_unresolved"):
            s.append("<p class='warn'>unresolved: "
                     + _esc(seismic["_unresolved"]) + "</p>")
        s.append('<p class="muted">assumptions: '
                 + _esc(seismic.get("_assumptions", {})) + "</p>")

    # cantilever inventory
    s.append("<h2>Cantilevers</h2>")
    cants = []
    if loads:
        cants = [v.get("name", k) for k, v in loads.items()
                 if not k.startswith("_") and isinstance(v, dict)
                 and v.get("cantilever")]
    if cants:
        s.append("<p>Cantilevering panels: <b>" + _esc(", ".join(cants))
                 + "</b> — the VERTICAL seismic component on cantilevers "
                 "is not computed by this model and must be verified by "
                 "the engineer (EN 1998-1 4.3.3.5.2).</p>")
    else:
        s.append("<p class='muted'>No cantilevering panels detected "
                 "(strip engine), or the strip engine did not run. The "
                 "vertical seismic component check remains with the "
                 "engineer either way.</p>")

    # foundations
    s.append("<h2>Foundations</h2>")
    lowest = stories[0] if stories else None
    if lowest is None or (not lowest.footings
                          and site is not None and site.soil is None):
        s.append("<p class='err'>unresolved — no footings modeled and/or "
                 "no [site.soil].</p>")
    else:
        if lowest.footings:
            s.append(_table(
                ["footing", "length m", "width m", "height m"],
                [[f.name,
                  round(((f.end.x - f.start.x) ** 2
                         + (f.end.y - f.start.y) ** 2) ** 0.5, 2),
                  f.width, f.height] for f in lowest.footings]))
        else:
            s.append("<p class='warn'>No strip footings modeled — walls "
                     "may stand on a base slab (see validation).</p>")
        if site is not None and site.soil is not None:
            s.append(_kv({"sigma_rd (kPa, design bearing)":
                          site.soil.sigma_rd,
                          "base friction mu": site.soil.friction_mu}))
        else:
            s.append("<p class='err'>unresolved — no [site.soil]: bearing, "
                     "sliding and overturning checks did not run.</p>")
        s.append('<p class="muted">EC7-lite: one bearing number, no '
                 'settlement, no groundwater, no passive pressure, no '
                 'drained/undrained distinction. Seismic bearing increase '
                 '(moment eccentricity M/W) not computed. EN 1998-5 '
                 'foundation tie-beams not validated — strip footings '
                 'under a full wall grid are inherently tied; engineer '
                 'to confirm.</p>')

    # validation
    s.append("<h2>Validation</h2>")
    findings = validate_all_phases(building, site=site)
    waivers = load_waivers(project_dir / "validation.json")
    waived, stale = [], []
    if waivers is not None:
        findings, waived, stale = partition_findings(findings, waivers)
    sev_rank = {"error": 0, "warning": 1, "optimization": 2}
    findings = sorted(findings, key=lambda e: sev_rank.get(e.severity, 3))
    if findings:
        s.append(_table(["severity", "finding"],
                        [[f.severity, f.message] for f in findings]))
    else:
        s.append("<p>No active findings.</p>")
    if waived:
        s.append("<h3>Waived findings (each carries its reason — a "
                 "waiver is a documented engineering conversation)</h3>")
        s.append(_table(["finding", "reason"],
                        [[w["message"], w["reason"]] for w in waived]))
    if stale:
        s.append("<h3>Stale waivers (matched nothing)</h3>")
        s.append(_table(["rule", "reason"],
                        [[w.get("rule", "?"), w.get("reason", "")]
                         for w in stale]))

    # not modelled
    s.append("<h2>Not modelled — the honest gaps</h2>")
    gaps: list[str] = []
    if fem and fem.get("_not_modelled"):
        gaps += fem["_not_modelled"]
    else:
        gaps += ["FEM did not run — its exclusion list is unavailable; "
                 "treat every FEM-adjacent claim as unverified"]
    gaps += [
        "vertical seismic component on cantilevers (flagged above)",
        "accidental torsional eccentricity in the FEM (inherent torsion "
        "only)",
        "soil-structure interaction and settlement",
        "reinforcement detailing, ductility and capacity design "
        "(EN 1998-1 sections 5-9 detailing rules)",
    ]
    s.append("<ul>" + "".join(f"<li>{_esc(g)}</li>" for g in gaps)
             + "</ul>")

    title = _esc(f"{building.name} — engineer handoff report")
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>{title}</title><style>{_CSS}</style></head><body>"
            f"<h1>{title}</h1>" + "".join(s) + "</body></html>")
