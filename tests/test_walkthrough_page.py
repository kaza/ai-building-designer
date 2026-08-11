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

    def test_view_token_round_trips(self, template):
        assert "flags.has('xray')" in template   # flag-set grammar (2026-08-09)
        assert "viewState === 2 ? ',load' : viewState === 1 ? ',xray'" \
            in template

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

    def test_channels_in_the_aim_readout(self, template):
        # the compact aim block keeps the element channels; the I panel
        # is tile-first per-combination since 2026-08-11
        assert "el.p || []" in template
        assert "femBoldIdx" in template

    def test_readout_is_two_blocks_with_a_divider(self, template):
        assert "const FEM_RULE" in template
        assert "function femReadout" in template
        assert "text-align: left" in template   # monospace columns align

    def test_peak_travels_with_the_design_value(self, template):
        # sized on the design value, peak shown as a detailing flag
        assert "femCell('peak'" in template
        assert "worst tile" in template


class TestStructureView:
    """G toggles the construction X-ray: everything transparent, hard
    edges (specs/browser-walkthrough.md 2026-08-10)."""

    def test_flag_set_parser_ignores_unknown_flags(self, template):
        assert "const flags = new Set(parts.slice(5));" in template
        # one view state in the hash: 'load' -> 2, 'xray'/'struct' -> 1
        assert "flags.has('load') ? 2" in template
        assert "flags.has('xray') || flags.has('struct')" in template

    def test_struct_unwound_before_fem_fetch(self, template):
        i_set = template.index("function setStructuralMode(mode) {")
        i_unw = template.index("if (mode === 'fem') _unapplyStruct();")
        i_fetch = template.index("fetch(FEM_FIELD_URL)")
        assert i_set < i_unw < i_fetch

    def test_states_are_exclusive_after_fem_exit(self, template):
        # leaving the load view returns to NORMAL, never to the hologram
        # (states are exclusive since 2026-08-11)
        assert "_applyStruct(structWanted)" not in template
        assert "leaving load returns to NORMAL" in template

    def test_bindings_and_hash(self, template):
        assert "if (e.code === 'KeyV' && !e.repeat) cycleView();" in template
        assert "viewState === 2 ? ',load' : viewState === 1 ? ',xray'" \
            in template

    def test_everything_transparent_with_edges(self, template):
        # every structural element gets a translucent clone + edge lines;
        # furniture is hidden, nothing stays opaque
        assert "EdgesGeometry" in template
        assert "n.visible = false;" in template
        assert "opacity: bearing ? 0.16 : (isWall ? 0.10 : 0.06)" in template
        assert "AdditiveBlending" in template
        assert "scene.background = new THREE.Color(0x04070d);" in template
        assert "_structEdges" in template

    def test_no_name_fallback_and_loud_on_missing_metadata(self, template):
        # metadata-only (owner 2026-08-10): the name-parsing fallback and
        # the BEARING payload are gone; a metadata-less GLB says so
        assert "__BEARING__" not in template
        assert "BEARING[clean]" not in template
        assert "carries no metadata" in template

    def test_real_attribute_is_the_only_source(self, template):
        assert "o.userData.ab_kind" in template
        assert "const bearing = !!meta.ab_load_bearing;" in template


class TestViewAndLoadKeys:
    """V cycles normal -> x-ray -> load; L cycles worst -> weight ->
    quake inside the load view; G is gone (owner 2026-08-11,
    specs/browser-walkthrough.md, fem-xray.md schema 4)."""

    def test_v_and_l_keys_wired(self, template):
        assert "'KeyV'" in template and "cycleView" in template
        assert "'KeyL'" in template and "cycleLoad" in template
        assert "'KeyG'" not in template

    def test_l_jumps_straight_into_the_load_view(self, template):
        # owner 2026-08-11: L outside the load view enters it directly;
        # V circles back through normal/x-ray
        assert "if (viewState !== 2) { setView(2); return; }" in template

    def test_single_view_state_machine(self, template):
        assert "let viewState = 0;" in template
        assert "'normal', 'x-ray', 'load'" in template
        assert "'worst case', 'weight (ULS)', 'earthquake'" in template

    def test_menu_buttons_collapsed(self, template):
        assert 'id="m-view"' in template and 'id="m-load"' in template
        for gone in ('id="m-loads"', 'id="m-ghost"', 'id="m-femview"'):
            assert gone not in template

    def test_schema_gate_is_four(self, template):
        assert "env.schema !== 4" in template

    def test_hud_is_escaped_rich_text(self, template):
        # everything escaped FIRST, then only the bold markers become
        # tags (Gemini plan review: GLB names are untrusted)
        assert "function escapeHtml" in template
        assert "hud.innerHTML = escapeHtml(" in template
        assert "replace(/\\x01/g, '<b>')" in template.replace("\x01", "\\x01") or "x01" in template

    def test_legacy_params_deleted(self, template):
        assert "seams.get('loads')" not in template
        assert "seams.get('xray')" not in template
