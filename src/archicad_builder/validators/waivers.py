"""Per-project validation waivers (specs/validation-waivers.md).

A project may ship `validation.json` waiving specific validator rules with a
mandatory reason. Waived findings are reported separately, never silently
dropped; waivers that match nothing are reported as stale.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pydantic import (
    ValidationError as PydanticValidationError,
)

from archicad_builder.validators.structural import ValidationError


class Waiver(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule: str = Field(pattern=r"^[EWO]\d+[a-z]?$",
                      description="Rule code, e.g. E044, W001, E041b")
    reason: str = Field(description="Why this rule is waived — mandatory")
    match: str | None = Field(
        default=None,
        description="Optional substring; waiver applies only to findings whose "
                    "message contains it",
    )

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("waiver reason must not be blank")
        return v

    @field_validator("match")
    @classmethod
    def match_not_blank(cls, v: str | None) -> str | None:
        # match="" would sort as "specific" yet match every message,
        # shadowing real targeted waivers and dodging duplicate detection.
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("waiver match must not be blank")
        return v


class WaiverConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    waivers: list[Waiver]

    @model_validator(mode="after")
    def no_duplicate_rule_match(self) -> WaiverConfig:
        seen: set[tuple[str, str | None]] = set()
        for w in self.waivers:
            key = (w.rule, w.match)
            if key in seen:
                raise ValueError(f"duplicate waiver for rule {w.rule!r} "
                                 f"with match {w.match!r}")
            seen.add(key)
        return self


def load_waivers(path: Path) -> WaiverConfig | None:
    """Load validation.json. None if absent; ValueError if malformed."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"{path.name}: invalid JSON — {e}") from e
    try:
        return WaiverConfig.model_validate(data)
    except PydanticValidationError as e:
        raise ValueError(f"{path.name}: invalid waiver config — {e}") from e


def partition_findings(
    findings: list[ValidationError],
    config: WaiverConfig,
) -> tuple[list[ValidationError], list[dict], list[dict]]:
    """Split findings into (active, waived, stale_waivers).

    waived: [{severity, message, element_type, rule, reason}]
    stale_waivers: [{rule, reason}] for waivers that matched no finding.
    """
    active: list[ValidationError] = []
    waived: list[dict] = []
    matched: set[int] = set()

    # Specific waivers (with match) are tried before broad ones (match=None),
    # so a blanket rule waiver can't shadow a targeted one into staleness.
    order = sorted(range(len(config.waivers)),
                   key=lambda i: config.waivers[i].match is None)

    for f in findings:
        hit = None
        if f.code is not None:
            for i in order:
                w = config.waivers[i]
                if w.rule == f.code and (w.match is None or w.match in f.message):
                    hit = i
                    break
        if hit is None:
            active.append(f)
        else:
            matched.add(hit)
            waived.append({
                "severity": f.severity,
                "message": f.message,
                "element_type": f.element_type,
                "rule": config.waivers[hit].rule,
                "reason": config.waivers[hit].reason,
            })

    # Stale = matched NOTHING in the raw findings. Attribution above credits
    # one waiver per finding, but a waiver that also matches an already-waived
    # finding is not stale (overlapping matches like "Garage"/"Garage Stair").
    def _matches_any(w: Waiver) -> bool:
        return any(
            f.code == w.rule and (w.match is None or w.match in f.message)
            for f in findings
        )

    stale = [
        {"rule": w.rule, "match": w.match, "reason": w.reason}
        for i, w in enumerate(config.waivers)
        if i not in matched and not _matches_any(w)
    ]
    return active, waived, stale
