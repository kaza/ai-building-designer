"""Villa pipeline gate: furniture must not block door swings (W100).

    .venv/bin/python projects/villa-maketa/check_furniture.py

Prints findings as JSON. Exit 0 = clean, 1 = violations — fix by MOVING the
offending item in furniture.json (that is the whole point of the rule).
Spec: specs/furniture-door-clearance.md
"""
import json
import sys
from pathlib import Path

from archicad_builder.models.building import Building
from archicad_builder.validators.clearance import (
    FurnitureFootprint,
    check_furniture_clearance,
)

HERE = Path(__file__).parent


def main() -> int:
    building = Building.load(HERE / "building.json")
    story = building.get_story("Ground Floor")
    items = json.loads((HERE / "furniture.json").read_text())["items"]
    # ids must be unique — suffix duplicated names with their list index
    names = [i["name"] for i in items]
    footprints = [
        FurnitureFootprint(
            i["name"] if names.count(i["name"]) == 1 else f"{i['name']}#{idx}",
            i["name"], *i["bounds"],
        )
        for idx, i in enumerate(items)
    ]
    findings = check_furniture_clearance(story, footprints)
    print(json.dumps({
        "ok": not findings,
        "findings": [
            {"severity": f.severity, "door": f.element_id, "message": f.message}
            for f in findings
        ],
    }, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
