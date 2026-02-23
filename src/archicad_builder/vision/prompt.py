"""Build comparison prompts from building model state.

Generates structured prompts for Gemini to compare an original
floor plan image against our rendered model and return corrections.
"""

from __future__ import annotations

from archicad_builder.models.building import Building, Story


def _element_data_section(story: Story) -> str:
    """Generate the element data section for the prompt."""
    story.ensure_tags()
    lines: list[str] = []

    # Walls
    lines.append(f"### Walls ({len(story.walls)})")
    for w in story.walls:
        lines.append(
            f"- {w.tag} \"{w.name}\": "
            f"({w.start.x:.2f},{w.start.y:.2f})→({w.end.x:.2f},{w.end.y:.2f}), "
            f"{w.length:.2f}m, t={w.thickness:.2f}m, "
            f"lb={w.load_bearing}, ext={w.is_external}"
        )

    # Doors
    lines.append(f"\n### Doors ({len(story.doors)})")
    for d in story.doors:
        host = story.get_wall(d.wall_id)
        htag = host.tag if host else "?"
        swing = "inward" if d.swing_inward else "outward"
        lines.append(
            f"- {d.tag} \"{d.name}\": on {htag}, "
            f"pos={d.position:.2f}m, w={d.width:.2f}m, h={d.height:.2f}m, "
            f"op={d.operation_type.value}, swing={swing}"
        )

    # Windows
    lines.append(f"\n### Windows ({len(story.windows)})")
    for win in story.windows:
        host = story.get_wall(win.wall_id)
        htag = host.tag if host else "?"
        lines.append(
            f"- {win.tag} \"{win.name}\": on {htag}, "
            f"pos={win.position:.2f}m, w={win.width:.2f}m, "
            f"h={win.height:.2f}m, sill={win.sill_height:.2f}m"
        )

    return "\n".join(lines)


def build_comparison_prompt(
    building: Building,
    story_name: str,
    round_num: int = 1,
    previous_rounds: list[str] | None = None,
) -> str:
    """Build a comparison prompt for Gemini.

    Args:
        building: Current building model.
        story_name: Name of the story to compare.
        round_num: Current round number (1-indexed).
        previous_rounds: Summary of corrections from previous rounds.

    Returns:
        Markdown prompt string to send to Gemini.
    """
    story = building.get_story(story_name)
    if story is None:
        raise ValueError(f"Story '{story_name}' not found")

    element_data = _element_data_section(story)

    # Build previous rounds section
    prev_section = ""
    if previous_rounds:
        prev_lines = "\n".join(
            f"**Round {i+1}:** {summary}"
            for i, summary in enumerate(previous_rounds)
        )
        prev_section = f"""
## Previous Rounds
{prev_lines}

All corrections above have been applied. Look for REMAINING discrepancies only.
Do NOT repeat corrections from previous rounds.
"""

    is_final = "This is the final review round — be thorough." if round_num >= 3 else ""

    return f"""# Floor Plan Comparison — Correction Round {round_num}

You are a BIM specialist reviewing a reconstructed floor plan against the original architectural drawing.

## Context
We are recreating a real apartment floor plan as a digital building model (IFC 2x3 aligned). The original architectural drawing is the ground truth. Our rendered model must match it as closely as possible — wall positions, room proportions, door/window placement, and structural classification are all safety-critical for construction documentation.
{prev_section}
## Your Task
Compare the TWO images provided:
1. **Image 1**: Original architectural floor plan (ground truth)
2. **Image 2**: Our rendered model (elements labeled with tags)

Identify ALL remaining discrepancies. {is_final}Check:
- Wall positions, lengths, and endpoints
- Wall structural classification (hatching = load-bearing, thickness)
- Door positions and widths
- **Door swing direction**: compare the arc drawn on the original plan with our model's operation_type (SINGLE_SWING_LEFT/RIGHT) and swing_inward (true/false). The arc shows which way the door opens.
- Window positions and widths
- Missing or extra elements
- Room proportions and shapes

## Current Element Data

{element_data}

## Response Format

Return a JSON object with this exact structure:

```json
{{
  "assessment": "needs_corrections | perfect_match",
  "confidence": 0.0-1.0,
  "corrections": [
    {{
      "element_tag": "W1",
      "action": "modify",
      "field": "thickness",
      "current_value": 0.10,
      "corrected_value": 0.20,
      "reason": "Why this correction is needed"
    }}
  ],
  "notes": "Overall assessment of model accuracy"
}}
```

For MODIFY actions, specify one field per correction entry. If multiple fields need changing on the same element, use separate entries.

Valid fields for walls: start, end, thickness, load_bearing, is_external, name
Valid fields for doors: position, width, height, host_wall_tag, operation_type (SINGLE_SWING_LEFT, SINGLE_SWING_RIGHT, SLIDING_TO_LEFT, SLIDING_TO_RIGHT), swing_inward (true/false)
Valid fields for windows: position, width, height, sill_height, host_wall_tag

For ADD actions, include full element data:
```json
{{
  "element_tag": "W18",
  "action": "add",
  "element_type": "wall",
  "data": {{
    "name": "New Wall",
    "start": {{"x": 0, "y": 0}},
    "end": {{"x": 1, "y": 0}},
    "thickness": 0.10,
    "height": 2.7,
    "load_bearing": false,
    "is_external": false
  }},
  "reason": "..."
}}
```

For doors/windows being added:
```json
{{
  "element_tag": "D11",
  "action": "add",
  "element_type": "door",
  "data": {{
    "name": "New Door",
    "host_wall_tag": "W5",
    "position": 1.5,
    "width": 0.8,
    "height": 2.0
  }},
  "reason": "..."
}}
```

For REMOVE actions:
```json
{{
  "element_tag": "W3",
  "action": "remove",
  "reason": "..."
}}
```

## Rules
- ONLY report genuine discrepancies visible in the original drawing
- Use element tags (W1, D1, Win1) to reference existing elements
- Be precise with coordinates and dimensions
- Ignore furniture, appliances, and fixtures — we only model walls, doors, windows
- If the model already matches the original well, say so: `"assessment": "perfect_match"`
- Do NOT invent elements not visible in the original
- One field per correction entry (don't combine multiple fields)
"""
