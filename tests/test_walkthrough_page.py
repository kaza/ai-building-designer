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

TEMPLATE_HTML = (Path(__file__).resolve().parents[1] / "src"
                 / "archicad_builder" / "walkthrough" / "template.html")


@pytest.fixture(scope="module")
def template() -> str:
    return TEMPLATE_HTML.read_text()


class TestViewHash:
    def test_initial_view_is_frozen_before_the_model_loads(self, template):
        # the loader's top-level await must not race the writer
        assert "const INITIAL_VIEW = (() => {" in template
        assert template.index("const INITIAL_VIEW") < template.index(
            "const resp = await fetch('__MODEL__.glb')")

    def test_writer_is_throttled_and_change_detected(self, template):
        assert "history.replaceState" in template
        assert "_lastViewHash" in template
        assert "_viewLast > 1000" in template

    def test_malformed_specs_are_rejected(self, template):
        assert "if (!nums.every(Number.isFinite)) return null;" in template
        assert "s.trim() === ''" in template      # Number('') is 0
        assert "Math.abs(v) > 5000" in template   # finite but absurd

    def test_xray_token_round_trips(self, template):
        assert "flags.has('xray')" in template   # flag-set grammar (2026-08-09)
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
        assert re.search(r"a\.download = '__MODEL__-shot_' \+ cameraSpec\(\)",
                         template)


class TestXrayReadability:
    """Owner 2026-08-09: the pale HUD was unreadable against the ghosted
    (near-white) X-ray model."""

    def test_dark_hud_panel_in_xray_mode(self, template):
        assert "body.xray #hud" in template
        assert "body.xray #aim-chip" in template

    def test_xray_class_toggles_with_the_mode(self, template):
        assert "classList.add('xray')" in template
        assert "classList.remove('xray')" in template

    def test_all_channels_in_both_readouts(self, template):
        # the aim block (femReadout) and the I detail both read el.p
        assert template.count("el.p || []") >= 2

    def test_readout_is_two_blocks_with_a_divider(self, template):
        assert "const FEM_RULE" in template
        assert "function femReadout" in template
        assert "text-align: left" in template   # monospace columns align

    def test_peak_travels_with_the_design_value(self, template):
        # sized on the design value, peak shown as a detailing flag
        assert "femCell('peak'" in template
        assert "worst fragment" in template


class TestStructureView:
    """G toggles the construction X-ray: everything transparent, hard
    edges (specs/browser-walkthrough.md 2026-08-10)."""

    def test_flag_set_parser_ignores_unknown_flags(self, template):
        assert "const flags = new Set(parts.slice(5));" in template
        assert "flags.has('xray')" in template
        # legacy ,ghost links map onto the x-ray state
        assert "(flags.has('struct') || flags.has('ghost')) ? 1 : 0" \
            in template
        assert "parts.length !== 5 && !xray" not in template

    def test_struct_unwound_before_fem_fetch(self, template):
        i_set = template.index("function setStructuralMode(mode) {")
        i_unw = template.index("if (mode === 'fem') _unapplyStruct();")
        i_fetch = template.index("fetch(FEM_FIELD_URL)")
        assert i_set < i_unw < i_fetch

    def test_struct_returns_after_fem_exit_and_failure(self, template):
        assert template.count("_applyStruct(structWanted);") >= 2

    def test_bindings_hash_and_bearing_payload(self, template):
        assert "if (e.code === 'KeyG' && !e.repeat) cycleStruct();" in template
        assert 'id="m-ghost"' in template
        assert "const BEARING = __BEARING__;" in template
        assert ",struct'" in template

    def test_everything_transparent_with_edges(self, template):
        # every structural element gets a translucent clone + edge lines;
        # furniture is hidden, nothing stays opaque
        assert "EdgesGeometry" in template
        assert "n.visible = false;" in template
        assert "opacity: bearing ? 0.16 : (isWall ? 0.10 : 0.06)" in template
        assert "AdditiveBlending" in template
        assert "scene.background = new THREE.Color(0x04070d);" in template
        assert "_structEdges" in template

    def test_split_mesh_suffix_is_stripped_for_bearing_lookup(self, template):
        # stone walls become two GLB nodes (_1/_2) — the garage rendered
        # non-bearing until the suffix strip (owner catch 2026-08-10)
        assert template.count(".replace(/_\\d+$/, '')") >= 2

    def test_real_attribute_beats_name_parsing(self, template):
        # userData (glTF extras) is the primary source; names are the
        # fallback for old GLBs (owner 2026-08-10)
        assert "o.userData.ab_kind" in template
        assert "meta ? !!meta.ab_load_bearing" in template
