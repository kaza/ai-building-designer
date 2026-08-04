"""Tests for per-project validation waivers (specs/validation-waivers.md)."""
import json

import pytest
from pydantic import ValidationError as PydanticValidationError

from archicad_builder.validators.structural import ValidationError
from archicad_builder.validators.waivers import (
    WaiverConfig,
    load_waivers,
    partition_findings,
)


def _err(code, msg, severity="warning"):
    return ValidationError(
        severity=severity, element_type="X", element_id="id",
        message=f"{code}: {msg}",
    )


class TestValidationErrorCode:
    def test_code_parsed_from_message(self):
        assert _err("E044", "no facade").code == "E044"
        assert _err("E041b", "small bath").code == "E041b"
        assert _err("W001", "height").code == "W001"

    def test_no_code_prefix_gives_none(self):
        e = ValidationError(severity="error", element_type="Door",
                            element_id="d", message="Door references nothing")
        assert e.code is None


class TestPartition:
    def test_waived_moves_out_with_reason(self):
        findings = [_err("W060", "door 1.4m wide"), _err("W001", "height")]
        cfg = WaiverConfig.model_validate(
            {"waivers": [{"rule": "W060", "reason": "French door"}]})
        active, waived, stale = partition_findings(findings, cfg)
        assert stale == []
        assert [f.code for f in active] == ["W001"]
        assert len(waived) == 1
        assert waived[0]["rule"] == "W060"
        assert waived[0]["reason"] == "French door"
        assert stale == []

    def test_one_waiver_matches_multiple_findings(self):
        findings = [_err("E041b", "bath A"), _err("E041b", "bath B")]
        cfg = WaiverConfig.model_validate(
            {"waivers": [{"rule": "E041b", "reason": "villa"}]})
        active, waived, stale = partition_findings(findings, cfg)
        assert active == [] and stale == []
        assert len(waived) == 2

    def test_match_substring_narrows(self):
        findings = [_err("W042", "Room 'Garage Stair' aspect"),
                    _err("W042", "Room 'Pantry' aspect")]
        cfg = WaiverConfig.model_validate(
            {"waivers": [{"rule": "W042", "match": "Garage Stair",
                          "reason": "stairs are tunnels"}]})
        active, waived, stale = partition_findings(findings, cfg)
        assert len(active) == 1
        assert "Pantry" in active[0].message
        assert len(waived) == 1
        assert stale == []

    def test_unmatched_waiver_is_stale(self):
        findings = [_err("W001", "height")]
        cfg = WaiverConfig.model_validate(
            {"waivers": [{"rule": "E044", "reason": "gone after fix"}]})
        active, waived, stale = partition_findings(findings, cfg)
        assert len(active) == 1
        assert waived == []
        assert stale == [{"rule": "E044", "match": None, "reason": "gone after fix"}]

    def test_finding_without_code_never_waived(self):
        e = ValidationError(severity="error", element_type="Door",
                            element_id="d", message="no code here")
        cfg = WaiverConfig.model_validate(
            {"waivers": [{"rule": "E044", "reason": "x"}]})
        active, waived, _ = partition_findings([e], cfg)
        assert len(active) == 1 and waived == []


class TestSchema:
    def test_reason_mandatory(self):
        with pytest.raises(PydanticValidationError):
            WaiverConfig.model_validate({"waivers": [{"rule": "W060"}]})

    def test_blank_reason_rejected(self):
        with pytest.raises(PydanticValidationError):
            WaiverConfig.model_validate(
                {"waivers": [{"rule": "W060", "reason": "   "}]})

    def test_unknown_keys_rejected(self):
        with pytest.raises(PydanticValidationError):
            WaiverConfig.model_validate(
                {"waivers": [{"rule": "W060", "reason": "x", "extra": 1}]})
        with pytest.raises(PydanticValidationError):
            WaiverConfig.model_validate(
                {"waivers": [], "unknown_top": True})

    def test_blank_match_rejected(self):
        with pytest.raises(PydanticValidationError):
            WaiverConfig.model_validate(
                {"waivers": [{"rule": "W060", "reason": "x", "match": "  "}]})

    def test_bad_rule_pattern_rejected(self):
        with pytest.raises(PydanticValidationError):
            WaiverConfig.model_validate(
                {"waivers": [{"rule": "not a code", "reason": "x"}]})

    def test_duplicate_rule_match_rejected(self):
        with pytest.raises(PydanticValidationError):
            WaiverConfig.model_validate({"waivers": [
                {"rule": "W060", "reason": "a"},
                {"rule": "W060", "reason": "b"},
            ]})

    def test_same_rule_different_match_allowed(self):
        cfg = WaiverConfig.model_validate({"waivers": [
            {"rule": "W042", "match": "Stair", "reason": "a"},
            {"rule": "W042", "match": "Pantry", "reason": "b"},
        ]})
        assert len(cfg.waivers) == 2


class TestShadowing:
    def test_broad_waiver_does_not_shadow_specific(self):
        """Specific (match) waivers are consumed before broad ones, so the
        specific waiver is credited and not reported stale."""
        findings = [_err("W042", "Room 'Garage Stair' aspect")]
        cfg = WaiverConfig.model_validate({"waivers": [
            {"rule": "W042", "reason": "broad"},
            {"rule": "W042", "match": "Garage Stair", "reason": "specific"},
        ]})
        active, waived, stale = partition_findings(findings, cfg)
        assert active == []
        assert waived[0]["reason"] == "specific"
        # The broad waiver also matches the finding, so it is not stale —
        # stale means "matched nothing in the raw findings".
        assert stale == []


class TestLoader:
    def test_missing_file_returns_none(self, tmp_path):
        assert load_waivers(tmp_path / "validation.json") is None

    def test_valid_file_loads(self, tmp_path):
        p = tmp_path / "validation.json"
        p.write_text(json.dumps(
            {"waivers": [{"rule": "W001", "reason": "villa height"}]}))
        cfg = load_waivers(p)
        assert cfg is not None and cfg.waivers[0].rule == "W001"

    def test_malformed_json_raises(self, tmp_path):
        p = tmp_path / "validation.json"
        p.write_text("{not json")
        with pytest.raises(ValueError):
            load_waivers(p)

    def test_invalid_schema_raises(self, tmp_path):
        p = tmp_path / "validation.json"
        p.write_text(json.dumps({"waivers": [{"rule": "W001"}]}))
        with pytest.raises(ValueError):
            load_waivers(p)
