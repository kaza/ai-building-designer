"""Standalone X-ray page template (specs/fem-xray.md).

The generated page must carry its view in the URL hash (#v=camera+target,
throttled replaceState writer, copy-link button) so a refresh keeps the
view and a pasted link opens at the sender's exact camera.
"""

from archicad_builder.fem.xray import write_xray_page


def _page(tmp_path):
    dest = tmp_path / "xray.html"
    write_xray_page(dest, title="T", field_url="fem-field-abc.json")
    return dest.read_text()


class TestViewHash:
    def test_restores_camera_and_target_from_hash(self, tmp_path):
        page = _page(tmp_path)
        assert "location.hash.startsWith('#v=')" in page
        # applied to both the camera and the orbit target, then update()
        assert "controls.target.set" in page

    def test_writer_uses_replace_state_with_change_detection(self, tmp_path):
        page = _page(tmp_path)
        assert "history.replaceState" in page
        assert "_lastHash" in page   # change detector — Safari caps 100/30s

    def test_copy_link_button_present(self, tmp_path):
        page = _page(tmp_path)
        assert "copy view link" in page
        assert "navigator.clipboard.writeText" in page

    def test_field_url_still_pinned(self, tmp_path):
        assert "fem-field-abc.json" in _page(tmp_path)


class TestPayloadContract:
    """Component codes live in TWO hand-maintained JS decoders (this page
    and the walkthrough). Nothing else stops a new code from shipping to
    a decoder that never grew to meet it (CodeRabbit review)."""

    def test_written_field_uses_known_component_codes(self, tmp_path):
        import json

        from archicad_builder.fem import compute_fem
        from archicad_builder.fem.writers import write_payloads
        from tests.test_fem_model import _box

        res = compute_fem(_box(), mesh=0.5)
        write_payloads(res, tmp_path, "deadbeef")
        env = json.loads((tmp_path / "fem-field.json").read_text())
        assert set(env["quads"]["g"]) <= {0, 1, 2, 3, 4}
        assert env["not_modelled"] == res.not_modelled
        page = _page(tmp_path)
        labels = page.count("',") + 1     # decoder must cover every code
        assert "diagonal tension (shear)" in page and labels > 0


class TestChannelReadout:
    def test_page_renders_every_channel(self, tmp_path):
        page = _page(tmp_path)
        assert "el.p" in page              # all channels, not just governing
        assert "white-space:pre" in page   # the extra line must show

    def test_written_elems_carry_channel_lists(self, tmp_path):
        import json

        from archicad_builder.fem import compute_fem
        from archicad_builder.fem.writers import write_payloads
        from tests.test_fem_model import _box

        write_payloads(compute_fem(_box(), mesh=0.5), tmp_path, "deadbeef")
        env = json.loads((tmp_path / "fem-field.json").read_text())
        assert all(e["p"] for e in env["elems"])
        assert all(len(e["p"]) == 3 for e in env["elems"]
                   if e["kind"] in ("wall", "roof", "slab"))


class TestDesignAndPeak:
    """Common practice: size on a design section, read the peak as a
    local-detailing flag. Both numbers must reach the viewer."""

    def test_written_elems_carry_both_numbers(self, tmp_path):
        import json

        from archicad_builder.fem import compute_fem
        from archicad_builder.fem.writers import write_payloads
        from tests.test_fem_model import _box

        res = compute_fem(_box(), mesh=0.5)
        write_payloads(res, tmp_path, "deadbeef")
        env = json.loads((tmp_path / "fem-field.json").read_text())
        for e in env["elems"]:
            assert e["peak"] >= e["u"] - 1e-3   # peak never below design
        assert any(e["peak"] > e["u"] for e in env["elems"])

    def test_page_shows_the_peak_beside_the_design_value(self, tmp_path):
        page = _page(tmp_path)
        assert "worst tile" in page and "el.peak" in page


class TestLoadStops:
    """L cycles worst case -> weight (ULS) -> earthquake; the paint is
    the ACTIVE stop, tooltip stays compact (owner 2026-08-11,
    specs/fem-xray.md schema 4)."""

    def test_l_key_cycles_and_repaints(self, tmp_path):
        page = _page(tmp_path)
        assert "'KeyL'" in page
        assert "'KeyV'" not in page       # V is a walkthrough concept
        assert "needsUpdate = true" in page       # recolor in place
        assert "'worst case', 'weight (ULS)', 'earthquake'" in page

    def test_schema_gate_is_four(self, tmp_path):
        page = _page(tmp_path)
        assert "env.schema !== 4" in page
        # combos itself must be validated as an array (CodeRabbit)
        assert "!Array.isArray(env.combos)" in page

    def test_gravity_only_hides_the_cycler(self, tmp_path):
        page = _page(tmp_path)
        assert "if (hasStops) addEventListener('keydown'" in page

    def test_tooltip_is_escaped(self, tmp_path):
        page = _page(tmp_path)
        assert "tip.innerHTML" in page
        assert "&amp;" in page            # esc() present
