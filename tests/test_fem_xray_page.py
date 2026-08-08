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
