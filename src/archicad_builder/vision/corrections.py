"""Parse and apply Gemini comparison corrections to a Building model.

Handles the structured correction JSON that Gemini returns,
resolves element references by tag, and applies modifications.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field as dataclass_field
from typing import Any

from archicad_builder.models.building import Building, Story
from archicad_builder.models.elements import Door, DoorOperationType, Wall, Window
from archicad_builder.models.geometry import Point2D

logger = logging.getLogger(__name__)


@dataclass
class Correction:
    """A single correction from Gemini."""
    element_tag: str
    action: str  # "modify", "add", "remove"
    field: str = ""
    current_value: Any = None
    corrected_value: Any = None
    element_type: str = ""  # for "add": "wall", "door", "window"
    data: dict = dataclass_field(default_factory=dict)
    reason: str = ""


@dataclass
class ComparisonResult:
    """Result of a Gemini comparison round."""
    assessment: str  # "needs_corrections" or "perfect_match"
    confidence: float
    corrections: list[Correction]
    notes: str = ""

    @property
    def is_perfect(self) -> bool:
        return self.assessment == "perfect_match"


def parse_response(response_text: str) -> ComparisonResult:
    """Parse Gemini's JSON response into a ComparisonResult.

    Handles JSON wrapped in markdown code fences.
    """
    # Strip markdown code fences if present
    text = response_text.strip()
    if text.startswith("```"):
        # Remove first line (```json) and last line (```)
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    data = json.loads(text)

    corrections = []
    for c in data.get("corrections", []):
        # Handle compound field names (e.g., "coordinates, length" or "lb, t")
        # by splitting into individual corrections
        raw_field = c.get("field", "")
        fields = [f.strip() for f in raw_field.split(",") if f.strip()] if raw_field else [""]

        if len(fields) > 1 and c.get("action") == "modify":
            # Gemini combined multiple fields — we'll create one correction
            # with the compound field name. apply_corrections handles this.
            pass

        corrections.append(Correction(
            element_tag=c.get("element_tag", ""),
            action=c.get("action", "modify"),
            field=raw_field,
            current_value=c.get("current_value"),
            corrected_value=c.get("corrected_value"),
            element_type=c.get("element_type", ""),
            data=c.get("data", {}),
            reason=c.get("reason", ""),
        ))

    return ComparisonResult(
        assessment=data.get("assessment", "needs_corrections"),
        confidence=data.get("confidence", 0.0),
        corrections=corrections,
        notes=data.get("notes", ""),
    )


def _find_by_tag(story: Story, tag: str) -> Wall | Door | Window | None:
    """Find any element by its tag."""
    for w in story.walls:
        if w.tag == tag:
            return w
    for d in story.doors:
        if d.tag == tag:
            return d
    for win in story.windows:
        if win.tag == tag:
            return win
    return None


def _resolve_wall_by_tag(story: Story, tag: str) -> Wall | None:
    """Find a wall by its tag."""
    return next((w for w in story.walls if w.tag == tag), None)


def _parse_point(value: Any) -> Point2D | None:
    """Parse a point from various Gemini formats."""
    if isinstance(value, dict):
        return Point2D(x=value.get("x", 0), y=value.get("y", 0))
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return Point2D(x=value[0], y=value[1])
    if isinstance(value, str):
        # Try "(x,y)" format
        m = re.match(r"\(?([\d.]+)\s*,\s*([\d.]+)\)?", value)
        if m:
            return Point2D(x=float(m.group(1)), y=float(m.group(2)))
    return None


def _apply_modify(
    story: Story,
    correction: Correction,
    changelog: list[str],
) -> None:
    """Apply a modify correction to an element."""
    element = _find_by_tag(story, correction.element_tag)
    if element is None:
        changelog.append(f"⚠️ {correction.element_tag}: not found, skipping")
        return

    field = correction.field.strip().lower()
    value = correction.corrected_value

    # Handle compound fields (Gemini sometimes returns "field1, field2")
    # In that case, try to parse the corrected_value intelligently
    if "," in field:
        _apply_compound_modify(story, element, correction, changelog)
        return

    # Normalize field names
    field_map = {
        "lb": "load_bearing",
        "t": "thickness",
        "ext": "is_external",
        "pos": "position",
        "w": "width",
        "h": "height",
        "host_wall_tag": "_host_wall_tag",
        "host_wall": "_host_wall_tag",
        "wall": "_host_wall_tag",
    }
    field = field_map.get(field, field)

    tag = correction.element_tag

    if field in ("start", "end") and isinstance(element, Wall):
        point = _parse_point(value)
        if point:
            old = getattr(element, field)
            setattr(element, field, point)
            changelog.append(
                f"✏️ {tag}.{field}: ({old.x},{old.y})→({point.x},{point.y})"
            )
        else:
            changelog.append(f"⚠️ {tag}.{field}: can't parse point '{value}'")

    elif field == "load_bearing" and isinstance(element, Wall):
        old = element.load_bearing
        element.load_bearing = bool(value)
        changelog.append(f"✏️ {tag}.load_bearing: {old}→{element.load_bearing}")

    elif field == "is_external" and isinstance(element, Wall):
        old = element.is_external
        element.is_external = bool(value)
        changelog.append(f"✏️ {tag}.is_external: {old}→{element.is_external}")

    elif field == "thickness" and isinstance(element, (Wall,)):
        old = element.thickness
        element.thickness = float(value)
        changelog.append(f"✏️ {tag}.thickness: {old}→{element.thickness}")

    elif field == "position" and isinstance(element, (Door, Window)):
        old = element.position
        element.position = float(value)
        changelog.append(f"✏️ {tag}.position: {old}→{element.position}")

    elif field == "width" and isinstance(element, (Door, Window)):
        old = element.width
        element.width = float(value)
        changelog.append(f"✏️ {tag}.width: {old}→{element.width}")

    elif field == "height" and isinstance(element, (Door, Window)):
        old = element.height
        element.height = float(value)
        changelog.append(f"✏️ {tag}.height: {old}→{element.height}")

    elif field == "operation_type" and isinstance(element, Door):
        old = element.operation_type
        element.operation_type = DoorOperationType(str(value))
        changelog.append(f"✏️ {tag}.operation_type: {old.value}→{element.operation_type.value}")

    elif field == "swing_inward" and isinstance(element, Door):
        old = element.swing_inward
        element.swing_inward = bool(value)
        changelog.append(f"✏️ {tag}.swing_inward: {old}→{element.swing_inward}")

    elif field == "sill_height" and isinstance(element, Window):
        old = element.sill_height
        element.sill_height = float(value)
        changelog.append(f"✏️ {tag}.sill_height: {old}→{element.sill_height}")

    elif field == "_host_wall_tag" and isinstance(element, (Door, Window)):
        wall = _resolve_wall_by_tag(story, str(value))
        if wall:
            old_wall = story.get_wall(element.wall_id)
            old_tag = old_wall.tag if old_wall else "?"
            element.wall_id = wall.global_id
            changelog.append(f"✏️ {tag}.host_wall: {old_tag}→{wall.tag}")
        else:
            changelog.append(f"⚠️ {tag}.host_wall: wall '{value}' not found")

    elif field == "name":
        old = element.name
        element.name = str(value)
        changelog.append(f"✏️ {tag}.name: '{old}'→'{element.name}'")

    else:
        changelog.append(
            f"⚠️ {tag}.{field}: unsupported field/element combo, skipping"
        )


def _apply_compound_modify(
    story: Story,
    element: Any,
    correction: Correction,
    changelog: list[str],
) -> None:
    """Handle compound field modifications (e.g., 'coordinates, length')."""
    tag = correction.element_tag
    fields = [f.strip().lower() for f in correction.field.split(",")]
    value = correction.corrected_value

    # Common pattern: "coordinates, length" with value like "(3.70,1.15)→(3.70,6.30), 5.15m"
    # Try to parse start→end from value string
    if isinstance(value, str) and "→" in value and isinstance(element, Wall):
        # Extract coordinate pairs
        coord_match = re.findall(
            r"\(?([\d.]+)\s*,\s*([\d.]+)\)?",
            value.split("→")[0] + " " + value.split("→")[1]
        )
        if len(coord_match) >= 2:
            start = Point2D(x=float(coord_match[0][0]), y=float(coord_match[0][1]))
            end = Point2D(x=float(coord_match[1][0]), y=float(coord_match[1][1]))
            old_start = element.start
            old_end = element.end
            element.start = start
            element.end = end
            changelog.append(
                f"✏️ {tag}: ({old_start.x},{old_start.y})→({old_end.x},{old_end.y}) "
                f"changed to ({start.x},{start.y})→({end.x},{end.y})"
            )
            return

    # Common pattern: "lb, t" with two values
    # This is ambiguous — log and skip
    changelog.append(
        f"⚠️ {tag}: compound field '{correction.field}' — "
        f"apply manually: {correction.corrected_value} ({correction.reason})"
    )


def _apply_add(
    building: Building,
    story: Story,
    correction: Correction,
    changelog: list[str],
) -> None:
    """Apply an add correction — create a new element."""
    data = correction.data
    etype = correction.element_type.lower()
    tag = correction.element_tag

    if etype == "wall":
        start = _parse_point(data.get("start")) or _parse_point(data.get("coordinates", "").split("→")[0] if "→" in data.get("coordinates", "") else None)
        end = _parse_point(data.get("end")) or _parse_point(data.get("coordinates", "").split("→")[1] if "→" in data.get("coordinates", "") else None)

        # Also try "coordinates" as "(x,y)→(x,y)" string
        if (start is None or end is None) and "coordinates" in data:
            coords = data["coordinates"]
            if isinstance(coords, str) and "→" in coords:
                parts = coords.split("→")
                start = _parse_point(parts[0].strip())
                end = _parse_point(parts[1].strip())

        if start is None or end is None:
            changelog.append(f"⚠️ {tag}: can't parse wall coordinates from {data}")
            return

        wall = Wall(
            name=data.get("name", ""),
            start=start,
            end=end,
            height=float(data.get("height", story.height)),
            thickness=float(data.get("thickness", data.get("t", 0.1))),
            load_bearing=bool(data.get("load_bearing", data.get("lb", False))),
            is_external=bool(data.get("is_external", data.get("ext", False))),
        )
        wall.tag = tag
        story.walls.append(wall)
        changelog.append(
            f"➕ {tag} \"{wall.name}\": "
            f"({wall.start.x},{wall.start.y})→({wall.end.x},{wall.end.y}), "
            f"t={wall.thickness}m, lb={wall.load_bearing}"
        )

    elif etype == "door":
        host_tag = data.get("host_wall_tag") or data.get("wall")
        if not host_tag:
            changelog.append(f"⚠️ {tag}: no host_wall_tag in data")
            return
        host = _resolve_wall_by_tag(story, host_tag)
        if not host:
            changelog.append(f"⚠️ {tag}: host wall '{host_tag}' not found")
            return

        op_type = data.get("operation_type", "SINGLE_SWING_LEFT")
        door = Door(
            name=data.get("name", ""),
            wall_id=host.global_id,
            position=float(data.get("position", 0)),
            width=float(data.get("width", 0.8)),
            height=float(data.get("height", 2.0)),
            operation_type=DoorOperationType(op_type) if op_type else DoorOperationType.SINGLE_SWING_LEFT,
            swing_inward=bool(data.get("swing_inward", True)),
        )
        door.tag = tag
        story.doors.append(door)
        changelog.append(
            f"➕ {tag} \"{door.name}\": on {host_tag}, "
            f"pos={door.position}m, w={door.width}m"
        )

    elif etype == "window":
        host_tag = data.get("host_wall_tag") or data.get("wall")
        if not host_tag:
            changelog.append(f"⚠️ {tag}: no host_wall_tag in data")
            return
        host = _resolve_wall_by_tag(story, host_tag)
        if not host:
            changelog.append(f"⚠️ {tag}: host wall '{host_tag}' not found")
            return

        window = Window(
            name=data.get("name", ""),
            wall_id=host.global_id,
            position=float(data.get("position", 0)),
            width=float(data.get("width", 1.0)),
            height=float(data.get("height", 1.2)),
            sill_height=float(data.get("sill_height", data.get("sill", 0.9))),
        )
        window.tag = tag
        story.windows.append(window)
        changelog.append(
            f"➕ {tag} \"{window.name}\": on {host_tag}, "
            f"pos={window.position}m, w={window.width}m"
        )

    else:
        changelog.append(f"⚠️ {tag}: unknown element_type '{etype}'")


def _apply_remove(
    story: Story,
    correction: Correction,
    changelog: list[str],
) -> None:
    """Apply a remove correction — delete an element."""
    tag = correction.element_tag
    element = _find_by_tag(story, tag)
    if element is None:
        changelog.append(f"⚠️ {tag}: not found, can't remove")
        return

    if isinstance(element, Wall):
        # Cascade: remove hosted doors/windows
        hosted_doors = [d for d in story.doors if d.wall_id == element.global_id]
        hosted_windows = [w for w in story.windows if w.wall_id == element.global_id]
        for d in hosted_doors:
            story.doors.remove(d)
            changelog.append(f"🗑️ {d.tag} (cascaded from {tag})")
        for w in hosted_windows:
            story.windows.remove(w)
            changelog.append(f"🗑️ {w.tag} (cascaded from {tag})")
        story.walls.remove(element)
        changelog.append(f"🗑️ {tag} \"{element.name}\"")

    elif isinstance(element, Door):
        story.doors.remove(element)
        changelog.append(f"🗑️ {tag} \"{element.name}\"")

    elif isinstance(element, Window):
        story.windows.remove(element)
        changelog.append(f"🗑️ {tag} \"{element.name}\"")


def apply_corrections(
    building: Building,
    story_name: str,
    result: ComparisonResult,
) -> list[str]:
    """Apply all corrections from a ComparisonResult to the building.

    Args:
        building: Building model to modify (mutated in place).
        story_name: Name of the story to apply corrections to.
        result: Parsed Gemini comparison result.

    Returns:
        Changelog — list of human-readable strings describing what changed.
    """
    story = building.get_story(story_name)
    if story is None:
        return [f"⚠️ Story '{story_name}' not found"]

    if result.is_perfect:
        return [f"✅ Perfect match (confidence: {result.confidence})"]

    story.ensure_tags()
    changelog: list[str] = []

    for correction in result.corrections:
        action = correction.action.lower()

        if action == "modify":
            _apply_modify(story, correction, changelog)
        elif action == "add":
            _apply_add(building, story, correction, changelog)
        elif action == "remove":
            _apply_remove(story, correction, changelog)
        else:
            changelog.append(
                f"⚠️ {correction.element_tag}: unknown action '{action}'"
            )

    return changelog


def summarize_round(changelog: list[str]) -> str:
    """Create a short summary of a correction round for the next prompt."""
    applied = [l for l in changelog if l.startswith(("✏️", "➕", "🗑️"))]
    if not applied:
        return "No corrections applied."

    # Extract just the element tags and actions
    parts = []
    for line in applied:
        # Get the tag (first word after emoji)
        words = line.split()
        if len(words) >= 2:
            tag = words[1].rstrip(".:\"")
            if line.startswith("✏️"):
                parts.append(f"modified {tag}")
            elif line.startswith("➕"):
                parts.append(f"added {tag}")
            elif line.startswith("🗑️"):
                parts.append(f"removed {tag}")

    return "; ".join(parts)
