"""Walkthrough page template invariants (specs/browser-walkthrough.md).

The generated page is project-tier (villa-maketa), but two of its URL
contracts regress silently and are worth a cheap guard: the shareable
`#v=` view state must be frozen before the model loads and written back
throttled, and it must never touch the older `#debug=` seam that headless
screenshots and the P-filename camera replay depend on.

Substring assertions only — there is no JS runtime here. Behaviour is
verified in a real browser (headless Chrome over CDP) when the page changes.
"""

import re
from pathlib import Path

import pytest

TEMPLATE_PY = (Path(__file__).resolve().parents[1]
               / "projects" / "villa-maketa" / "make_walkthrough.py")


@pytest.fixture(scope="module")
def template() -> str:
    return TEMPLATE_PY.read_text()


class TestViewHash:
    def test_initial_view_is_frozen_before_the_model_loads(self, template):
        # the loader's top-level await must not race the writer
        assert "const INITIAL_VIEW = (() => {" in template
        assert template.index("const INITIAL_VIEW") < template.index(
            "const resp = await fetch('villa.glb')")

    def test_writer_is_throttled_and_change_detected(self, template):
        assert "history.replaceState" in template
        assert "_lastViewHash" in template
        assert "_viewLast > 1000" in template

    def test_malformed_specs_are_rejected(self, template):
        assert "if (!nums.every(Number.isFinite)) return null;" in template
        assert "s.trim() === ''" in template      # Number('') is 0
        assert "Math.abs(v) > 5000" in template   # finite but absurd

    def test_xray_token_round_trips(self, template):
        assert "parts[5] === 'xray'" in template
        assert "structuralMode === 'fem' ? ',xray' : ''" in template

    def test_copy_link_bound_to_key_and_menu(self, template):
        assert "'KeyK'" in template
        assert "m-link" in template
        assert "navigator.clipboard.writeText" in template


class TestDebugSeamUntouched:
    def test_writer_is_off_in_debug_mode(self, template):
        assert "const DEBUG_MODE = location.hash.startsWith('#debug');" \
            in template
        assert "if (!viewHashOn || DEBUG_MODE) return;" in template

    def test_debug_hash_is_never_a_view_hash(self, template):
        assert "if (DEBUG_MODE || !location.hash.startsWith('#v=')) return null;" \
            in template

    def test_screenshot_camera_contract_intact(self, template):
        # the P filename doubles as #debug= numbers — same cameraSpec source
        assert re.search(r"a\.download = 'villa-shot_' \+ cameraSpec\(\)",
                         template)
