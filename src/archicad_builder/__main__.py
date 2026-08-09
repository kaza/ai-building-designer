"""ArchiCAD Builder CLI.

Usage:
    python -m archicad_builder <command> <project> [options]

All building modifications go through the 'apply' command with JSON actions.
Read-only commands (validate, assess, render, list) use simple CLI args.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from archicad_builder.models.building import Building
from archicad_builder.validators.phases import validate_all_phases
from archicad_builder.validators.waivers import (
    WaiverConfig,
    load_waivers,
    partition_findings,
)

app = typer.Typer(
    name="archicad_builder",
    help="ArchiCAD Builder — CLI for building design and validation.",
    no_args_is_help=True,
)

PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_building(project: str) -> Building:
    """Load building.json for a project."""
    path = PROJECTS_DIR / project / "building.json"
    if not path.exists():
        typer.echo(json.dumps({"ok": False, "error": f"Project not found: {path}"}))
        raise typer.Exit(1)
    return Building.load(path)


def _save_building(building: Building, project: str) -> Path:
    """Save building.json for a project."""
    path = PROJECTS_DIR / project / "building.json"
    building.save(path)
    return path


def _validate_json(building: Building, waivers: WaiverConfig | None = None) -> dict:
    """Run all validators and return structured results.

    With a WaiverConfig, waived findings move to 'waived' (with reasons),
    counts exclude them, and unmatched waivers are listed as 'stale_waivers'.
    Without one, output shape is unchanged (no waiver keys at all).
    """
    errors = validate_all_phases(building)

    waived: list[dict] = []
    stale: list[dict] = []
    if waivers is not None:
        errors, waived, stale = partition_findings(errors, waivers)

    details = []
    for e in errors:
        detail = {"severity": e.severity, "message": e.message}
        if hasattr(e, "element_type") and e.element_type:
            detail["element_type"] = e.element_type
        details.append(detail)

    result = {
        "errors": sum(1 for e in errors if e.severity == "error"),
        "warnings": sum(1 for e in errors if e.severity == "warning"),
        "optimizations": sum(1 for e in errors if e.severity == "optimization"),
        "details": details,
    }
    if waivers is not None:
        result["waived"] = waived
        result["waived_count"] = len(waived)
        result["stale_waivers"] = stale
    return result


def _load_project_waivers(project: str) -> WaiverConfig | None:
    """Load projects/<name>/validation.json; exit with JSON error if malformed."""
    try:
        return load_waivers(PROJECTS_DIR / project / "validation.json")
    except ValueError as e:
        typer.echo(json.dumps({"ok": False, "error": str(e)}))
        raise typer.Exit(1) from e


def _output(data: dict) -> None:
    """Print JSON output to stdout."""
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Read-only commands
# ---------------------------------------------------------------------------

@app.command()
def validate(
    project: str = typer.Argument(..., help="Project directory name"),
    strict: bool = typer.Option(
        False, "--strict",
        help="Exit 1 when unwaived errors remain (for pipeline gates)."),
):
    """Run all validators on a building."""
    building = _load_building(project)
    waivers = _load_project_waivers(project)
    result = _validate_json(building, waivers)
    _output({"ok": True, "validation": result})
    # Without --strict this command has ALWAYS exited 0, which made the
    # "validate" step in the documented pipeline a gate that could never
    # fail (Codex plan review 2026-08-09). Default behaviour is unchanged
    # because agents parse the JSON.
    if strict and result.get("errors"):
        raise typer.Exit(1)


@app.command()
def assess(project: str = typer.Argument(..., help="Project directory name")):
    """Full assessment: validation + building summary + area stats."""
    building = _load_building(project)
    waivers = _load_project_waivers(project)
    validation = _validate_json(building, waivers)

    # Build summary
    stories_info = []
    for story in building.stories:
        apts = []
        for apt in story.apartments:
            spaces = []
            for sp in apt.spaces:
                area = sp.boundary.area
                spaces.append({
                    "name": sp.name,
                    "type": sp.room_type.value,
                    "area_m2": round(area, 1),
                })
            apts.append({
                "name": apt.name,
                "spaces": spaces,
                "total_area_m2": round(sum(s["area_m2"] for s in spaces), 1),
            })
        stories_info.append({
            "name": story.name,
            "walls": len(story.walls),
            "apartments": apts,
        })

    _output({
        "ok": True,
        "building": building.name,
        "stories": stories_info,
        "validation": validation,
    })


@app.command()
def render(
    project: str = typer.Argument(..., help="Project directory name"),
    story: str | None = typer.Option(None, "--story", "-s", help="Render specific story"),
    output_dir: str | None = typer.Option(None, "--output", "-o", help="Output directory"),
):
    """Render floor plan(s) to PNG."""
    building = _load_building(project)
    out = Path(output_dir) if output_dir else PROJECTS_DIR / project / "output"
    out.mkdir(parents=True, exist_ok=True)

    rendered = []
    for s in building.stories:
        if story and s.name != story:
            continue
        filename = f"floor_{s.name.lower().replace(' ', '_')}.png"
        img_path = out / filename
        building.render_floorplan(s.name, str(img_path))
        rendered.append({"story": s.name, "path": str(img_path)})

    _output({"ok": True, "rendered": rendered})


@app.command("loads")
def loads_cmd(
    project: str = typer.Argument(..., help="Project directory name"),
    output: str | None = typer.Option(None, "--output", "-o"),
):
    """Structural load analysis (Phase B) -> output/loads.json."""
    import json as _json

    from archicad_builder.structural import compute_loads

    building = _load_building(project)
    result = compute_loads(building)
    out = (Path(output) if output
           else PROJECTS_DIR / project / "output" / "loads.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json.dumps(result, indent=1, sort_keys=True))
    worst = sorted(
        ((k, v["u"]) for k, v in result.items()
         if not k.startswith("_")), key=lambda t: -t[1])[:5]
    _output({
        "ok": True,
        "written": str(out),
        "elements": sum(1 for k in result if not k.startswith("_")),
        "unresolved": result["_unresolved"],
        "worst": [{"element": k, "u": u} for k, u in worst],
    })


@app.command("fem")
def fem_cmd(
    project: str = typer.Argument(..., help="Project directory name"),
    mesh: float = typer.Option(0.25, "--mesh", help="Quad size in metres"),
    xray: bool = typer.Option(True, "--xray/--no-xray",
                              help="Also write output/xray.html"),
):
    """FEM X-ray (specs/fem-xray.md) -> output/fem-field.json + fem-loads.json."""
    from archicad_builder.fem import compute_fem
    from archicad_builder.fem.writers import building_digest, write_payloads
    from archicad_builder.fem.xray import write_xray_page

    building = _load_building(project)
    result = compute_fem(building, mesh=mesh)
    out = PROJECTS_DIR / project / "output"
    out.mkdir(parents=True, exist_ok=True)
    digest = building_digest(PROJECTS_DIR / project / "building.json")
    write_payloads(result, out, digest)
    if xray:
        write_xray_page(out / "xray.html", building.name)
    worst = sorted(result.elements.values(), key=lambda e: -e["u"])[:5]
    _output({
        "ok": True,
        "written": str(out / "fem-field.json"),
        "quads": len(result.field["quads"]),
        "balance": round(result.balance, 4),
        "unresolved": result.unresolved,
        "worst": [{"element": e["name"], "kind": e["kind"],
                   "u": round(e["u"], 2)} for e in worst],
    })


@app.command("list")
def list_cmd(
    project: str = typer.Argument(..., help="Project directory name"),
    what: str = typer.Argument(..., help="What to list: stories, apartments, rooms, walls"),
    story: str | None = typer.Option(None, "--story", "-s", help="Filter by story"),
    apartment: str | None = typer.Option(None, "--apartment", "-a", help="Filter by apartment"),
):
    """List building elements."""
    building = _load_building(project)
    result: dict = {"ok": True}

    if what == "stories":
        result["stories"] = [
            {"name": s.name, "elevation": s.elevation, "height": s.height,
             "walls": len(s.walls), "apartments": len(s.apartments)}
            for s in building.stories
        ]

    elif what == "apartments":
        apts = []
        for s in building.stories:
            if story and s.name != story:
                continue
            for apt in s.apartments:
                v = apt.boundary.vertices
                apts.append({
                    "story": s.name,
                    "name": apt.name,
                    "spaces": len(apt.spaces),
                    "boundary": [[round(p.x, 2), round(p.y, 2)] for p in v],
                })
        result["apartments"] = apts

    elif what == "rooms":
        if not apartment:
            _output({"ok": False, "error": "Specify --apartment for room listing"})
            raise typer.Exit(1)
        rooms = []
        for s in building.stories:
            if story and s.name != story:
                continue
            for apt in s.apartments:
                if apt.name != apartment:
                    continue
                for sp in apt.spaces:
                    v = sp.boundary.vertices
                    x0, x1 = min(p.x for p in v), max(p.x for p in v)
                    y0, y1 = min(p.y for p in v), max(p.y for p in v)
                    rooms.append({
                        "story": s.name,
                        "apartment": apt.name,
                        "name": sp.name,
                        "type": sp.room_type.value,
                        "width": round(x1 - x0, 2),
                        "height": round(y1 - y0, 2),
                        "area_m2": round(sp.boundary.area, 1),
                        "boundary": [[round(p.x, 2), round(p.y, 2)] for p in v],
                    })
        result["rooms"] = rooms

    elif what == "walls":
        walls = []
        for s in building.stories:
            if story and s.name != story:
                continue
            for w in s.walls:
                walls.append({
                    "story": s.name,
                    "name": w.name,
                    "start": [round(w.start.x, 2), round(w.start.y, 2)],
                    "end": [round(w.end.x, 2), round(w.end.y, 2)],
                    "thickness": w.thickness,
                    "length": round(w.length, 2) if hasattr(w, "length") else None,
                })
        result["walls"] = walls
    else:
        _output({"ok": False, "error": f"Unknown list target: {what}. Use: stories, apartments, rooms, walls"})
        raise typer.Exit(1)

    _output(result)


@app.command()
def stats(project: str = typer.Argument(..., help="Project directory name")):
    """Apartment statistics: per floor, per apartment — rooms, area."""
    building = _load_building(project)
    from archicad_builder.models.spaces import RoomType

    floors = []
    totals = {"apartments": 0, "area_m2": 0}

    for story in building.stories:
        apts_info = []
        for apt in story.apartments:
            # Count bedrooms for room-type classification
            bedrooms = [s for s in apt.spaces if s.room_type == RoomType.BEDROOM]
            rooms = len(bedrooms) + 1  # bedrooms + living = "X-room"
            has_living = any(s.room_type == RoomType.LIVING for s in apt.spaces)
            if not has_living and not bedrooms:
                rooms = 0  # studio/unknown

            # Wohnnutzfläche = apartment boundary area (everything inside the apartment)
            # Kitchen, WC, Vorraum — all count. Only building common areas don't.
            net_area = apt.boundary.area

            apt_type = "Studio" if rooms == 0 else f"{rooms}-room"

            apts_info.append({
                "name": apt.name,
                "type": apt_type,
                "rooms": rooms,
                "bedrooms": len(bedrooms),
                "net_area_m2": round(net_area, 1),
                "spaces": [
                    {"name": s.name, "type": s.room_type.value,
                     "area_m2": round(s.boundary.area, 1)}
                    for s in apt.spaces
                ],
            })
            totals["apartments"] += 1
            totals["area_m2"] += net_area

        floors.append({
            "story": story.name,
            "apartments": apts_info,
            "floor_apartments": len(apts_info),
            "floor_area_m2": round(sum(a["net_area_m2"] for a in apts_info), 1),
        })

    totals["area_m2"] = round(totals["area_m2"], 1)

    # Wohnnutzfläche / BGF ratio
    # BGF = gross floor area per storey (from slab or bounding box of exterior walls)
    bgf_per_floor = 0.0
    for story in building.stories:
        if story.slabs:
            # Use first slab area
            slab = story.slabs[0]
            if hasattr(slab, "boundary") and slab.boundary:
                bgf_per_floor = slab.boundary.area
                break
        # Fallback: bounding box of all walls
        if story.walls:
            xs = []
            ys = []
            for w in story.walls:
                xs.extend([w.start.x, w.end.x])
                ys.extend([w.start.y, w.end.y])
            if xs and ys:
                bgf_per_floor = (max(xs) - min(xs)) * (max(ys) - min(ys))
                break

    total_bgf = bgf_per_floor * len(building.stories)
    wohnnutzflaeche = totals["area_m2"]
    ratio = round(wohnnutzflaeche / total_bgf * 100, 1) if total_bgf > 0 else 0

    totals["bgf_per_floor_m2"] = round(bgf_per_floor, 1)
    totals["bgf_total_m2"] = round(total_bgf, 1)
    totals["wohnnutzflaeche_m2"] = wohnnutzflaeche
    totals["wohnnutzflaeche_bgf_ratio"] = ratio

    _output({
        "ok": True,
        "building": building.name,
        "floors": floors,
        "totals": totals,
    })


@app.command("export")
def export_cmd(
    project: str = typer.Argument(..., help="Project directory name"),
    format: str = typer.Option("ifc", "--format", "-f", help="Export format (ifc)"),
):
    """Export building to IFC."""
    building = _load_building(project)
    out = PROJECTS_DIR / project / "output"
    out.mkdir(parents=True, exist_ok=True)

    if format == "ifc":
        ifc_path = out / f"{project}.ifc"
        building.export_ifc(str(ifc_path))
        _output({"ok": True, "exported": str(ifc_path), "format": "ifc"})
    else:
        _output({"ok": False, "error": f"Unknown format: {format}"})
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Apply command (modifications)
# ---------------------------------------------------------------------------

def _dispatch_action(building: Building, action: dict) -> dict:
    """Dispatch a single action to the Building API. Returns result dict."""
    cmd = action.get("action")
    story = action.get("story")

    try:
        if cmd == "add-wall":
            wall = building.add_wall(
                story_name=story,
                start=tuple(action["start"]),
                end=tuple(action["end"]),
                height=action.get("height", 2.89),
                thickness=action.get("thickness", 0.25),
                name=action.get("name", ""),
                description=action.get("description", ""),
                is_external=action.get("is_external", False),
                load_bearing=action.get("load_bearing", False),
            )
            return {"action": cmd, "name": wall.name, "id": wall.global_id}

        elif cmd == "remove-wall":
            building.remove_wall(story, action["wall"])
            return {"action": cmd, "wall": action["wall"]}

        elif cmd == "move-wall":
            new_start = tuple(action["start"]) if "start" in action else None
            new_end = tuple(action["end"]) if "end" in action else None
            wall = building.move_wall(story, action["wall"], new_start, new_end)
            return {"action": cmd, "wall": wall.name}

        elif cmd == "rename-wall":
            building.rename_wall(story, action["wall"], action["new_name"])
            return {"action": cmd, "old": action["wall"], "new": action["new_name"]}

        elif cmd == "add-door":
            door = building.add_door(
                story_name=story,
                wall_name=action["wall"],
                position=action["position"],
                width=action["width"],
                height=action.get("height", 2.10),
                name=action.get("name", ""),
                description=action.get("description", ""),
            )
            return {"action": cmd, "name": door.name, "id": door.global_id}

        elif cmd == "remove-door":
            building.remove_door(story, action["door"])
            return {"action": cmd, "door": action["door"]}

        elif cmd == "resize-door":
            door = building.resize_door(story, action["door"], action["width"])
            return {"action": cmd, "door": door.name, "width": action["width"]}

        elif cmd == "add-window":
            window = building.add_window(
                story_name=story,
                wall_name=action["wall"],
                position=action["position"],
                width=action["width"],
                height=action.get("height", 1.50),
                sill_height=action.get("sill_height", 0.90),
                name=action.get("name", ""),
                description=action.get("description", ""),
            )
            return {"action": cmd, "name": window.name, "id": window.global_id}

        elif cmd == "remove-window":
            building.remove_window(story, action["window"])
            return {"action": cmd, "window": action["window"]}

        elif cmd == "resize-window":
            window = building.resize_window(
                story, action["window"],
                new_width=action.get("width"),
                new_height=action.get("height"),
            )
            return {"action": cmd, "window": window.name}

        elif cmd == "add-slab":
            slab = building.add_slab(
                story_name=story,
                vertices=[tuple(v) for v in action["vertices"]],
                thickness=action.get("thickness", 0.25),
                is_floor=action.get("is_floor", True),
                name=action.get("name", ""),
            )
            return {"action": cmd, "name": slab.name}

        elif cmd == "add-staircase":
            from archicad_builder.models.elements import StaircaseType
            stair_type = StaircaseType(action.get("stair_type", "HALF_TURN_STAIR"))
            staircase = building.add_staircase(
                story_name=story,
                vertices=[tuple(v) for v in action["vertices"]],
                width=action.get("width", 1.20),
                name=action.get("name", ""),
                stair_type=stair_type,
            )
            return {"action": cmd, "name": staircase.name}

        elif cmd == "add-apartment":
            from archicad_builder.models.geometry import Point2D, Polygon2D
            from archicad_builder.models.spaces import Apartment
            apt = Apartment(
                name=action["name"],
                boundary=Polygon2D(vertices=[
                    Point2D(x=v[0], y=v[1]) for v in action["boundary"]
                ]),
            )
            s = building.get_story(story)
            if not s:
                raise ValueError(f"Story '{story}' not found")
            s.apartments.append(apt)
            return {"action": cmd, "name": apt.name}

        elif cmd == "remove-apartment":
            s = building.get_story(story)
            if not s:
                raise ValueError(f"Story '{story}' not found")
            apt = next((a for a in s.apartments if a.name == action["apartment"]), None)
            if not apt:
                raise ValueError(f"Apartment '{action['apartment']}' not found on {story}")
            s.apartments.remove(apt)
            return {"action": cmd, "apartment": action["apartment"]}

        elif cmd == "resize-apartment":
            from archicad_builder.models.geometry import Point2D, Polygon2D
            s = building.get_story(story)
            if not s:
                raise ValueError(f"Story '{story}' not found")
            apt = next((a for a in s.apartments if a.name == action["apartment"]), None)
            if not apt:
                raise ValueError(f"Apartment '{action['apartment']}' not found")
            apt.boundary = Polygon2D(vertices=[
                Point2D(x=v[0], y=v[1]) for v in action["boundary"]
            ])
            return {"action": cmd, "apartment": apt.name}

        elif cmd == "add-space":
            from archicad_builder.models.geometry import Point2D, Polygon2D
            from archicad_builder.models.spaces import RoomType, Space
            s = building.get_story(story)
            if not s:
                raise ValueError(f"Story '{story}' not found")
            apt = next((a for a in s.apartments if a.name == action["apartment"]), None)
            if not apt:
                raise ValueError(f"Apartment '{action['apartment']}' not found")
            space = Space(
                name=action["name"],
                room_type=RoomType(action["type"]),
                boundary=Polygon2D(vertices=[
                    Point2D(x=v[0], y=v[1]) for v in action["boundary"]
                ]),
            )
            apt.spaces.append(space)
            return {"action": cmd, "name": space.name, "type": action["type"]}

        elif cmd == "resize-space":
            from archicad_builder.models.geometry import Point2D, Polygon2D
            s = building.get_story(story)
            if not s:
                raise ValueError(f"Story '{story}' not found")
            apt = next((a for a in s.apartments if a.name == action["apartment"]), None)
            if not apt:
                raise ValueError(f"Apartment '{action['apartment']}' not found")
            space = next((sp for sp in apt.spaces if sp.name == action["space"]), None)
            if not space:
                raise ValueError(f"Space '{action['space']}' not found in {action['apartment']}")
            space.boundary = Polygon2D(vertices=[
                Point2D(x=v[0], y=v[1]) for v in action["boundary"]
            ])
            return {"action": cmd, "space": space.name}

        elif cmd == "remove-space":
            s = building.get_story(story)
            if not s:
                raise ValueError(f"Story '{story}' not found")
            apt = next((a for a in s.apartments if a.name == action["apartment"]), None)
            if not apt:
                raise ValueError(f"Apartment '{action['apartment']}' not found")
            space = next((sp for sp in apt.spaces if sp.name == action["space"]), None)
            if not space:
                raise ValueError(f"Space '{action['space']}' not found")
            apt.spaces.remove(space)
            return {"action": cmd, "space": action["space"]}

        elif cmd == "add-story":
            building.add_story(
                name=action["name"],
                height=action.get("height", 2.89),
                elevation=action.get("elevation", 0.0),
            )
            return {"action": cmd, "name": action["name"]}

        else:
            return {"action": cmd, "error": f"Unknown action: {cmd}"}

    # Approved broad catch: every action failure is SURFACED in the JSON
    # result (apply reports it and exits non-zero) — nothing is swallowed.
    except Exception as e:  # noqa: BLE001
        return {"action": cmd, "error": str(e)}


@app.command()
def apply(
    project: str = typer.Argument(..., help="Project directory name"),
    actions_json: str | None = typer.Argument(None, help="JSON array of actions"),
    file: str | None = typer.Option(None, "--file", "-f", help="Read actions from JSON file"),
    stdin: bool = typer.Option(False, "--stdin", help="Read actions from stdin"),
    no_validate: bool = typer.Option(False, "--no-validate", help="Skip validation after apply"),
    render_story: str | None = typer.Option(None, "--render", "-r", help="Render story after apply"),
):
    """Apply modifications to a building via JSON actions."""
    # Parse actions from one of: positional arg, --file, --stdin
    if stdin:
        raw = sys.stdin.read()
    elif file:
        raw = Path(file).read_text()
    elif actions_json:
        raw = actions_json
    else:
        _output({"ok": False, "error": "Provide actions as argument, --file, or --stdin"})
        raise typer.Exit(1)

    try:
        actions = json.loads(raw)
    except json.JSONDecodeError as e:
        _output({"ok": False, "error": f"Invalid JSON: {e}"})
        raise typer.Exit(1)

    if not isinstance(actions, list):
        actions = [actions]  # allow single action without wrapping in array

    # Load, apply, save
    building = _load_building(project)

    results = []
    for i, action in enumerate(actions):
        result = _dispatch_action(building, action)
        results.append(result)
        if "error" in result:
            # Stop on first error
            _output({
                "ok": False,
                "error": f"Action {i} ({action.get('action', '?')}) failed: {result['error']}",
                "applied": i,
                "results": results,
            })
            raise typer.Exit(1)

    _save_building(building, project)

    output: dict = {
        "ok": True,
        "actions_applied": len(results),
        "results": results,
    }

    if not no_validate:
        output["validation"] = _validate_json(building)

    if render_story:
        out = PROJECTS_DIR / project / "output"
        out.mkdir(parents=True, exist_ok=True)
        for s in building.stories:
            if s.name == render_story or render_story == "all":
                fname = f"floor_{s.name.lower().replace(' ', '_')}.png"
                img_path = out / fname
                building.render_floorplan(s.name, str(img_path))
                output.setdefault("rendered", []).append({
                    "story": s.name, "path": str(img_path),
                })

    _output(output)


# ---------------------------------------------------------------------------
# Generate command
# ---------------------------------------------------------------------------

@app.command()
def generate(
    project: str = typer.Argument(..., help="Project directory name"),
    generator: str = typer.Argument(..., help="Generator name (e.g. 4apt, 3apt)"),
):
    """Generate a building from a generator module."""
    proj_dir = PROJECTS_DIR / project
    proj_dir.mkdir(parents=True, exist_ok=True)

    if generator == "4apt":
        from archicad_builder.generators.building_4apt import generate_building_4apt_interior
        building = generate_building_4apt_interior()
    elif generator == "3apt":
        # TODO: extract generate_3apt.py logic into generators/building_3apt.py
        _output({"ok": False, "error": "3apt generator not yet extracted into module. Use existing building.json."})
        raise typer.Exit(1)
    else:
        _output({"ok": False, "error": f"Unknown generator: {generator}. Available: 4apt, 3apt"})
        raise typer.Exit(1)

    _save_building(building, project)
    validation = _validate_json(building)

    _output({
        "ok": True,
        "generator": generator,
        "project": project,
        "stories": len(building.stories),
        "validation": validation,
    })


@app.command("export-obj")
def export_obj_cmd(project: str = typer.Argument(..., help="Project directory name")):
    """Tessellate the project's IFC into an OBJ for Blender."""
    from archicad_builder.export.obj import ifc_to_obj
    out = PROJECTS_DIR / project / "output"
    ifc = out / f"{project}.ifc"
    if not ifc.is_file():
        typer.echo(f"no IFC at {ifc} — run `export {project}` first", err=True)
        raise typer.Exit(1)
    res = ifc_to_obj(ifc, out / f"{project}.obj", label=project)
    for skip in res.skipped:
        typer.echo(f"skipped {skip}", err=True)
    _output({"ok": True, "products": res.products, "vertices": res.vertices,
             "skipped": len(res.skipped),
             "written": str(out / f"{project}.obj")})


@app.command("check-furniture")
def check_furniture_cmd(project: str = typer.Argument(..., help="Project directory name")):
    """Furniture must not block door swings (W100). Exit 1 on violations."""
    import json as _json

    from archicad_builder.validators.clearance import (
        FurnitureFootprint,
        check_furniture_clearance,
    )
    building = _load_building(project)
    path = PROJECTS_DIR / project / "furniture.json"
    if not path.is_file():
        _output({"ok": True, "findings": [], "note": "no furniture.json"})
        return
    items = _json.loads(path.read_text())["items"]
    names = [i["name"] for i in items]
    footprints = [
        FurnitureFootprint(
            i["name"] if names.count(i["name"]) == 1 else f"{i['name']}#{idx}",
            i["name"], *i["bounds"])
        for idx, i in enumerate(items)
    ]
    # every storey, not just the one the villa happened to furnish
    findings = [f for story in building.stories
                for f in check_furniture_clearance(story, footprints)]
    _output({"ok": not findings,
             "findings": [{"severity": f.severity, "door": f.element_id,
                           "message": f.message} for f in findings]})
    if findings:
        raise typer.Exit(1)


@app.command("render-furnished")
def render_furnished_cmd(
    project: str = typer.Argument(..., help="Project directory name"),
    story: str = typer.Option(None, "--story", help="Storey to render."),
):
    """Floor plan with furniture symbols drawn on top."""
    import json as _json

    from archicad_builder.export.furnished_plan import render_furnished_plan
    building = _load_building(project)
    target = building.get_story(story) if story else building.stories[-1]
    items = _json.loads(
        (PROJECTS_DIR / project / "furniture.json").read_text())["items"]
    out = (PROJECTS_DIR / project / "output"
           / f"floor_{target.name.lower().replace(' ', '_')}_furnished.png")
    render_furnished_plan(target, items, out)
    _output({"ok": True, "written": str(out), "items": len(items)})


@app.command("fetch-assets")
def fetch_assets_cmd(project: str = typer.Argument(..., help="Project directory name")):
    """Download the project's pinned furniture assets (project.toml)."""
    from archicad_builder.assets import AssetError, fetch_all
    from archicad_builder.project_config import ProjectConfig
    project_dir = PROJECTS_DIR / project
    try:
        fetch_all(project_dir, ProjectConfig.load(project_dir))
    except AssetError as exc:
        typer.echo(f"fetch-assets: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("serve")
def serve_cmd(
    project: str = typer.Argument(..., help="Project directory name"),
    port: int = typer.Option(8123, "--port"),
):
    """Serve the walkthrough locally and receive F-key feedback."""
    from archicad_builder.serve import serve
    root = PROJECTS_DIR / project
    serve(root / "output", root / "feedback", port=port)


@app.command("pipeline")
def pipeline_cmd(
    project: str = typer.Argument(..., help="Project directory name"),
    force: bool = typer.Option(False, "--force", help="Run every step."),
    from_step: str = typer.Option(None, "--from",
                                  help="Resume at this step (prefix must be fresh)."),
    list_only: bool = typer.Option(False, "--list",
                                   help="Print the order without running."),
    profile: str = typer.Option(
        None, "--profile",
        help="web (model + plans) | fem (adds the load calculation, "
             "default) | all (adds the Cycles renders)."),
):
    """Rebuild a project: every step, in order, skipping only what it can
    prove is unchanged (specs/project-pipeline.md)."""
    from archicad_builder.pipeline import (
        DEFAULT_PROFILE,
        PipelineError,
        run_pipeline,
    )
    project_dir = PROJECTS_DIR / project
    try:
        results = run_pipeline(project_dir, force=force, from_step=from_step,
                               list_only=list_only,
                               profile=profile or DEFAULT_PROFILE)
    except PipelineError as exc:
        typer.echo(f"pipeline: {exc}", err=True)
        raise typer.Exit(1) from exc
    for r in results:
        mark = "->" if r.ran else "  "
        typer.echo(f"{mark} {r.name:20} {r.reason}")
    if not list_only:
        typer.echo(f"pipeline complete ({profile or DEFAULT_PROFILE}): "
                   f"{sum(r.ran for r in results)} ran, "
                   f"{sum(not r.ran for r in results)} skipped")


@app.command("ids")
def ids_cmd(
    project: str = typer.Argument(
        ..., help="Project directory name (or a path to one)"),
    strict: bool = typer.Option(False, "--strict",
                                help="Exit non-zero on any finding."),
    repair: bool = typer.Option(False, "--repair",
                                help="Mint and persist missing ids."),
):
    """Audit element identity (specs/ifc-identity.md): every element must
    carry a valid, unique GlobalId. Missing ids are minted only by --repair —
    a read must never silently rewrite the source of truth."""
    import json as _json

    from archicad_builder.models.ifc_id import is_valid_ifc_id
    from archicad_builder.models.reconcile import KINDS

    project_dir = Path(project) if Path(project).is_dir() \
        else PROJECTS_DIR / project
    path = project_dir / "building.json"
    if not path.is_file():
        typer.echo(f"no building.json in {project_dir}", err=True)
        raise typer.Exit(1)
    def audit() -> tuple[list[str], int]:
        """(findings, number of nodes audited) for the file as it is NOW."""
        raw = _json.loads(path.read_text())
        findings: list[str] = []
        seen: dict[str, str] = {}
        audited = 0

        def check(owner: str, node: dict) -> None:
            nonlocal audited
            audited += 1
            gid = node.get("global_id")
            if gid is None:
                findings.append(f"missing id: {owner}")
                return
            if not is_valid_ifc_id(gid):
                findings.append(f"invalid id: {owner} has {gid!r}")
                return
            if gid in seen:
                findings.append(f"duplicate id: {owner} and {seen[gid]} "
                                f"share {gid}")
                return
            seen[gid] = owner

        check("building", raw)
        for story in raw.get("stories", []):
            sname = story.get("name", "?")
            check(f"story {sname!r}", story)
            for kind in (*KINDS, "spaces", "apartments"):
                for el in story.get(kind, []):
                    check(f"{sname}/{kind}/{el.get('name', '?')}", el)
            for apt in story.get("apartments", []):
                for sp in apt.get("spaces", []):
                    check(f"{sname}/apartments/{apt.get('name', '?')}"
                          f"/spaces/{sp.get('name', '?')}", sp)
        return findings, audited

    findings, audited = audit()

    if repair:
        missing = [f for f in findings if f.startswith("missing id")]
        others = [f for f in findings if not f.startswith("missing id")]
        if others:
            # duplicates/invalids need a human decision — minting over them
            # would bury the problem
            _output({"ok": False, "findings": findings,
                     "error": "--repair only fixes MISSING ids; resolve "
                              "duplicates/invalid ids first"})
            raise typer.Exit(1)
        if missing:
            Building.load(path).save(path)   # pydantic mints on load
        # re-audit what is actually ON DISK now — reporting ok from the
        # pre-repair read would trust a state that no longer exists
        # (Codex review 2026-08-09)
        post, _ = audit()
        _output({"ok": not post, "repaired": missing, "findings": post})
        if post:
            raise typer.Exit(1)
        return

    _output({"ok": not findings, "audited": audited,
             "findings": findings})
    if findings and strict:
        raise typer.Exit(1)


@app.command("publish")
def publish_cmd(project: str = typer.Argument(..., help="Project directory name")):
    """Publish built artifacts to the cloud (specs/web-deployment.md)."""
    from archicad_builder.publish import publish
    publish(project)


@app.command("freshness")
def freshness_cmd(project: str = typer.Argument(..., help="Project directory name")):
    """Report why a project's artifacts are (not) publishable."""
    from archicad_builder.pipeline import freshness_problems
    problems = freshness_problems(PROJECTS_DIR / project)
    _output({"ok": not problems, "problems": problems})
    if problems:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
