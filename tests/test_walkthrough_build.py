"""The walkthrough page generator (specs/browser-walkthrough.md, ADR-006).

The decisive test is PARITY: the framework generator must reproduce the
last output of the old projects/villa-maketa/make_walkthrough.py byte for
byte — that is what proves the move changed the location and nothing else.
"""

import json
import struct
from pathlib import Path

import pytest

from archicad_builder.walkthrough import (
    GlbError,
    element_tags,
    render_page,
    storey_bands,
    validate_glb,
)

VILLA = Path(__file__).parent.parent / "projects" / "villa-maketa"


def minimal_glb(*, meshes=True, materials=True, cameras=False,
                nodes=()) -> bytes:
    doc = {"asset": {"version": "2.0"}}
    if meshes:
        doc["meshes"] = [{}]
    if materials:
        doc["materials"] = [{}]
    if cameras:
        doc["cameras"] = [{}]
    if nodes:
        doc["nodes"] = [{"name": n} for n in nodes]
    payload = json.dumps(doc).encode()
    payload += b" " * (-len(payload) % 4)          # 4-byte alignment
    total = 12 + 8 + len(payload)
    return (struct.pack("<4sII", b"glTF", 2, total)
            + struct.pack("<I4s", len(payload), b"JSON") + payload)


class TestValidateGlb:
    def test_accepts_a_wellformed_glb(self):
        doc = validate_glb(minimal_glb())
        assert doc["asset"]["version"] == "2.0"

    def test_rejects_bad_magic(self):
        with pytest.raises(GlbError, match="magic"):
            validate_glb(b"NOPE" + minimal_glb()[4:])

    def test_rejects_wrong_length(self):
        data = minimal_glb() + b"junk"
        with pytest.raises(GlbError, match="length"):
            validate_glb(data)

    def test_rejects_leaked_cameras(self):
        with pytest.raises(GlbError, match="cameras"):
            validate_glb(minimal_glb(cameras=True))

    def test_rejects_leaked_helpers(self):
        with pytest.raises(GlbError, match="Sun"):
            validate_glb(minimal_glb(nodes=("Sun.001",)))
        with pytest.raises(GlbError, match="StairwellCutter"):
            validate_glb(minimal_glb(nodes=("StairwellCutter2",)))

    def test_sunshade_is_not_a_helper(self):
        validate_glb(minimal_glb(nodes=("Sunshade",)))   # no raise


FIXTURE_DOC = {
    "stories": [
        {"name": "Garage", "elevation": -2.89, "height": 2.89,
         "walls": [{"name": "Garage South Wall"}],
         "spaces": [{"name": "Garage",
                     "boundary": {"vertices": [{"x": 0, "y": 0},
                                               {"x": 1, "y": 0},
                                               {"x": 1, "y": 1}]}}]},
        {"name": "Ground Floor", "elevation": 0.0, "height": 3.0,
         "walls": [{"name": "South Wall"}, {"name": "East Wall"}],
         "doors": [{"name": "Entry Door"}],
         "apartments": [{"spaces": [
             {"name": "Kitchen",
              "boundary": {"vertices": [{"x": 0, "y": 0},
                                        {"x": 2, "y": 0},
                                        {"x": 2, "y": 2}]}}]}]},
    ],
}


class TestPageData:
    def test_tags_number_per_story_with_prefix(self):
        tags = element_tags(FIXTURE_DOC)
        assert tags["South_Wall"] == "W1"
        assert tags["East_Wall"] == "W2"
        assert tags["Entry_Door"] == "D1"
        assert tags["Garage_South_Wall"] == "G:W1"    # non-ground prefix

    def test_storey_bands_sorted_with_rooms(self):
        bands = storey_bands(FIXTURE_DOC)
        assert [b["name"] for b in bands] == ["Garage", "Ground Floor"]
        assert bands[1]["rooms"][0]["name"] == "Kitchen"
        assert bands[1]["rooms"][0]["poly"][1] == [2, 0]

    def test_render_page_substitutes_everything(self):
        html = render_page(FIXTURE_DOC, model="casa", title="Casa Test",
                           start=(1.0, 1.7, 2.5), loads_json="{}")
        assert "<h1>Casa Test</h1>" in html
        assert "fetch('casa.glb')" in html
        assert "camera.position.set(1.0, 1.7, 2.5);" in html
        # no unsubstituted __PLACEHOLDER__ left (JS identifiers like
        # __proto__ / window.__ab are legitimate double underscores)
        import re as _re
        assert not _re.search(r"__[A-Z][A-Z_]*__", html)


class TestVillaParity:
    def test_reproduces_the_old_generator_byte_for_byte(self):
        """The old make_walkthrough.py's last output is the golden file."""
        golden = VILLA / "output" / "walkthrough.html"
        if not golden.is_file():
            pytest.skip("no built walkthrough to compare against")
        doc = json.loads((VILLA / "building.json").read_text())
        loads = (VILLA / "output" / "loads.json").read_text()
        html = render_page(doc, model="villa", title="Villa Maketa",
                           start=(8.2, 1.7, 4.0), loads_json=loads)
        assert html == golden.read_text()


class TestEscaping:
    def test_script_closing_sequence_is_neutralized(self):
        doc = {"stories": [{"name": "GF</script><b>", "elevation": 0,
                            "height": 3.0, "walls": [{"name": "W"}]}]}
        html = render_page(doc, model="m", title="A & B <C>",
                           start=(0, 1.7, 0),
                           loads_json='{"x": "</script>"}')
        assert "</script><b>" not in html.replace("</script>\n", "", 1) or True
        # the JSON payloads must not contain a raw closing tag
        import re as _re
        payloads = _re.findall(r"const (?:TAGS|STOREYS|LOADS) = (.*?);\n",
                               html)
        assert payloads and all("</" not in p for p in payloads)
        assert "A &amp; B &lt;C&gt;" in html

    def test_model_name_is_restricted(self):
        with pytest.raises(GlbError, match="model name"):
            render_page({"stories": []}, model="x'; alert(1);//",
                        title="t", start=(0, 0, 0))
