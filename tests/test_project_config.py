"""ProjectConfig — projects/<name>/project.toml (specs/project-config.md).

The contract: strict (a typo is fatal, because a palette typo used to mean
silent magenta geometry), fully defaulted (a minimal project needs nothing),
and the pipeline hashes the file so a config change rebuilds what consumed it.
"""

from pathlib import Path

import pytest

from archicad_builder.project_config import ConfigError, ProjectConfig

VILLA = Path(__file__).parent.parent / "projects" / "villa-maketa"

MINIMAL = ""

FULL = """
[project]
title = "Villa Maketa"

[appearance.palette]
Parquet = [0.55, 0.40, 0.24, 1.0]
Accent  = [0.905, 0.533, 0.072, 1.0]

[render]
sun = { sky_elevation_deg = 45, sky_rotation_deg = 135, energy = 2.2 }

[render.camera.perspective]
location = [14.0, 21.0, 8.5]
target = [4.75, 8.5, 0.6]
lens = 38
resolution = [1600, 1200]

[render.camera.top]
location = [4.75, 8.75, 30]
ortho_scale = 19.5
resolution = [1100, 2000]

[[render.ground]]
location = [4.75, 67.5, -1.79]
size = [200, 120, 3.0]

[walkthrough]
start = [8.2, 1.7, 4.0]

[[asset]]
source = "polyhaven"
id = "mid_century_lounge_chair"

[[asset]]
source = "objaverse"
id = "sectional_sofa"
uid = "0eb6c94aa40c41b480cf35de229e8e88"
path = "glbs/000-027/0eb6c94aa40c41b480cf35de229e8e88.glb"
sha256 = "59a533d53544430fd81f3a4b055b430908faacc92dba2c6160270222ae1a9f0b"
name = "Escuadra Victoria Izquierda II"
author = "Pablo.Portela"

[[asset]]
source = "kenney-kit"
id = "kenney"
url = "https://kenney.nl/media/pages/assets/furniture-kit/x/kit.zip"
sha256 = "e67652d0932cee41683f74711c03d3e192a2af9979ef8e6b237711f5482d46b0"
models = ["toilet", "shower"]
"""


def write(tmp_path, text):
    d = tmp_path / "proj"
    d.mkdir(exist_ok=True)
    (d / "project.toml").write_text(text)
    return d


class TestLoading:
    def test_missing_file_yields_defaults(self, tmp_path):
        cfg = ProjectConfig.load(tmp_path)
        assert cfg.project.title == tmp_path.name
        assert cfg.appearance.palette == {}
        assert cfg.assets == []

    def test_minimal_file_yields_defaults(self, tmp_path):
        cfg = ProjectConfig.load(write(tmp_path, MINIMAL))
        assert cfg.render.camera.perspective.lens == 38

    def test_full_file_round_trips(self, tmp_path):
        cfg = ProjectConfig.load(write(tmp_path, FULL))
        assert cfg.project.title == "Villa Maketa"
        assert cfg.appearance.palette["Accent"] == (0.905, 0.533, 0.072, 1.0)
        assert cfg.render.camera.perspective.location == (14.0, 21.0, 8.5)
        assert cfg.render.camera.top.ortho_scale == 19.5
        assert cfg.render.ground[0].size == (200, 120, 3.0)
        assert cfg.walkthrough.start == (8.2, 1.7, 4.0)
        assert len(cfg.assets) == 3

    def test_villa_config_parses(self):
        cfg = ProjectConfig.load(VILLA)
        assert cfg.appearance.palette          # non-empty
        assert any(a.source == "objaverse" for a in cfg.assets)


class TestStrictness:
    def test_unknown_table_is_fatal(self, tmp_path):
        with pytest.raises(ConfigError, match="wibble"):
            ProjectConfig.load(write(tmp_path, "[wibble]\nx = 1\n"))

    def test_unknown_key_is_fatal(self, tmp_path):
        with pytest.raises(ConfigError, match="lense"):
            ProjectConfig.load(write(
                tmp_path, "[render.camera.perspective]\nlense = 50\n"))

    def test_malformed_color_is_fatal(self, tmp_path):
        with pytest.raises(ConfigError, match="Parquet"):
            ProjectConfig.load(write(
                tmp_path, "[appearance.palette]\nParquet = [1.0, 0.5]\n"))

    def test_color_out_of_range_is_fatal(self, tmp_path):
        with pytest.raises(ConfigError):
            ProjectConfig.load(write(
                tmp_path,
                "[appearance.palette]\nParquet = [2.0, 0.5, 0.5, 1.0]\n"))

    def test_bad_toml_is_fatal(self, tmp_path):
        with pytest.raises(ConfigError, match="TOML"):
            ProjectConfig.load(write(tmp_path, "not [ toml"))

    def test_unknown_asset_source_is_fatal(self, tmp_path):
        with pytest.raises(ConfigError):
            ProjectConfig.load(write(
                tmp_path, '[[asset]]\nsource = "napster"\nid = "x"\n'))

    def test_objaverse_asset_requires_hash(self, tmp_path):
        with pytest.raises(ConfigError):
            ProjectConfig.load(write(
                tmp_path,
                '[[asset]]\nsource = "objaverse"\nid = "sofa"\n'
                'uid = "u"\npath = "p"\nname = "n"\nauthor = "a"\n'))

    def test_duplicate_asset_id_is_fatal(self, tmp_path):
        with pytest.raises(ConfigError, match="duplicate"):
            ProjectConfig.load(write(
                tmp_path,
                '[[asset]]\nsource = "polyhaven"\nid = "chair"\n'
                '[[asset]]\nsource = "polyhaven"\nid = "chair"\n'))
