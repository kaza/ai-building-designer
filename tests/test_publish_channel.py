"""Publish channels (specs/web-deployment.md, specs/design-arena.md).

`publish <project> --as <channel>` re-keys every blob under `<channel>/`
so arena candidates can sit next to the real project on the live site.
The destination logic is pure and tested here; the upload path itself is
exercised end-to-end only by a real publish (az CLI, network).
"""

import pytest

from archicad_builder.publish import channel_dest


class TestChannelDest:
    def test_no_channel_publishes_under_the_project_name(self):
        assert channel_dest("villa-maketa", None) == "villa-maketa"

    def test_channel_becomes_the_blob_prefix(self):
        assert channel_dest("villa-maketa", "villa-maketa--b-garage") \
            == "villa-maketa--b-garage"

    def test_channel_must_extend_the_owning_project(self):
        # an alias must never be able to clobber ANOTHER project's blobs
        with pytest.raises(SystemExit, match="must start with"):
            channel_dest("villa-maketa", "other-project--x")

    def test_bare_project_name_is_not_a_channel(self):
        # publishing the plain project via --as would dodge nothing and
        # confuse the record — the alias needs a suffix
        with pytest.raises(SystemExit, match="must start with"):
            channel_dest("villa-maketa", "villa-maketa")

    def test_empty_suffix_rejected(self):
        with pytest.raises(SystemExit, match="empty"):
            channel_dest("villa-maketa", "villa-maketa--")

    def test_double_dash_is_reserved_for_channels(self):
        # a plain project named like a channel would be clobberable by
        # project "alpha"'s channel "alpha--beta" (Codex review 2026-08-13)
        with pytest.raises(SystemExit, match="reserved"):
            channel_dest("alpha--beta", None)
        with pytest.raises(SystemExit, match="reserved"):
            channel_dest("alpha--beta", "alpha--beta--x")

    def test_channel_charset_is_url_and_blob_safe(self):
        # path segment in the web app + blob key prefix: lowercase
        # kebab only, same alphabet as project ids
        with pytest.raises(SystemExit, match="lowercase"):
            channel_dest("villa-maketa", "villa-maketa--B Garage")
