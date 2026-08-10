"""Per-project domain configuration — projects/<name>/project.toml.

specs/project-config.md, ADR-006. The boundary rule: a value a second
building would set DIFFERENTLY lives here (palette colors, cameras, sun,
pinned assets, walkthrough spawn); behaviour every building shares lives in
framework code. `pipeline.toml` stays what it is — the build graph — and
this file is declared as an `inputs` entry on every step that consumes it,
so the existing freshness machinery rebuilds on config change.

Strict on purpose: an unknown key is fatal. A palette typo used to mean
silently magenta geometry; a camera typo would mean a silently missing
render. Everything has a default, so a minimal project needs no file at all.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

FILE_NAME = "project.toml"

Vec3 = tuple[float, float, float]
Rgba = tuple[float, float, float, float]


class ConfigError(Exception):
    """project.toml is wrong — message says where."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProjectMeta(_Strict):
    title: str = ""          # falls back to the directory name on load


class Appearance(_Strict):
    # Blender material name -> flat RGBA stand-in for the GLB export
    palette: dict[str, Rgba] = {}

    @field_validator("palette")
    @classmethod
    def channels_in_range(cls, v: dict[str, Rgba]) -> dict[str, Rgba]:
        for name, rgba in v.items():
            if not all(0.0 <= c <= 1.0 for c in rgba):
                raise ValueError(
                    f"palette entry {name!r}: channels must be 0..1, "
                    f"got {rgba}")
        return v


class Sun(_Strict):
    sky_elevation_deg: float = 45.0
    sky_rotation_deg: float = 135.0
    sky_intensity: float = 0.5
    energy: float = 2.2
    angle_deg: float = 8.6           # ~0.15 rad soft shadow
    rotation_deg: Vec3 = (50.0, -10.0, 105.0)


class PerspectiveCamera(_Strict):
    location: Vec3 = (14.0, 21.0, 8.5)
    target: Vec3 = (4.75, 8.5, 0.6)
    lens: float = 38.0
    dof_fstop: float = 5.6
    resolution: tuple[int, int] = (1600, 1200)
    exposure: float = -0.85


class TopCamera(_Strict):
    location: Vec3 = (4.75, 8.75, 30.0)
    ortho_scale: float = 19.5
    resolution: tuple[int, int] = (1100, 2000)
    exposure: float = -0.6


class Cameras(_Strict):
    perspective: PerspectiveCamera = PerspectiveCamera()
    top: TopCamera = TopCamera()


class GroundBox(_Strict):
    location: Vec3
    size: Vec3
    name: str = ""


class Shell(_Strict):
    """Hollow-cylinder render decor (e.g. a spiral-stair tower straddling
    a facade): outer minus inner, optionally minus the half-space
    y > cut_y_above (the part inside the house)."""
    center: tuple[float, float]
    radius: float
    inner_radius: float
    z_range: tuple[float, float]
    cut_y_above: float | None = None
    name: str = ""


class Render(_Strict):
    sun: Sun = Sun()
    camera: Cameras = Cameras()
    ground: list[GroundBox] = []
    shell: list[Shell] = []
    samples: int = 128
    exposure: float = -0.6           # scene default (blend save)


class Walkthrough(_Strict):
    start: Vec3 = (8.2, 1.7, 4.0)    # camera spawn (x, y=eye height, z)


class Soil(_Strict):
    """[site.soil] — from the project's geotechnical report. sigma_rd has
    no default on purpose: soil strength varies 50-600 kPa across normal
    sites, and a default would be an invented geotech report
    (specs/foundations.md)."""

    sigma_rd: float = Field(gt=0)    # design bearing resistance, kPa
    friction_mu: float = Field(default=0.5, gt=0, le=1.0)


class Site(_Strict):
    """[site] — seismic context (specs/seismic-lateral.md). All three
    countries are Eurocode 8; only National-Annex parameters differ, so
    country selects a spectrum-type default and ag comes off the national
    hazard map. No [site] at all -> seismic checks report unresolved."""

    country: Literal["BA", "DE", "AT"]
    ag: float = Field(gt=0, le=1.0)  # peak ground acceleration, units of g
    ground_type: Literal["A", "B", "C", "D", "E"]
    importance_class: Literal["I", "II", "III", "IV"] = "II"
    spectrum_type: Literal[1, 2] | None = None   # default set by country
    # top of the rigid basement / grade; None = max(0, lowest storey
    # elevation). Diaphragms at or below it carry no lateral force.
    seismic_base_elevation: float | None = None
    soil: Soil | None = None


class PolyhavenAsset(_Strict):
    source: Literal["polyhaven"]
    id: str
    resolution: str = "1k"


class ObjaverseAsset(_Strict):
    source: Literal["objaverse"]
    id: str                          # the key furniture.json refers to
    uid: str
    path: str
    sha256: str
    name: str                        # attribution — CC-BY, must be kept
    author: str


class KenneyKitAsset(_Strict):
    source: Literal["kenney-kit"]
    id: str
    url: str
    sha256: str
    models: list[str]


Asset = Annotated[
    Union[PolyhavenAsset, ObjaverseAsset, KenneyKitAsset],
    Field(discriminator="source"),
]


class ProjectConfig(_Strict):
    project: ProjectMeta = ProjectMeta()
    appearance: Appearance = Appearance()
    render: Render = Render()
    walkthrough: Walkthrough = Walkthrough()
    site: Site | None = None
    assets: list[Asset] = Field(default=[], alias="asset")

    @field_validator("assets")
    @classmethod
    def unique_ids(cls, v: list) -> list:
        seen: set[str] = set()
        for a in v:
            if a.id in seen:
                raise ValueError(f"duplicate asset id {a.id!r}")
            seen.add(a.id)
        return v

    @classmethod
    def load(cls, project_dir: Path) -> ProjectConfig:
        path = Path(project_dir) / FILE_NAME
        if not path.is_file():
            raw: dict = {}
        else:
            try:
                raw = tomllib.loads(path.read_text())
            except tomllib.TOMLDecodeError as exc:
                raise ConfigError(
                    f"{path} is not valid TOML: {exc}") from exc
        try:
            cfg = cls.model_validate(raw)
        except ValidationError as exc:
            raise ConfigError(f"{path}: {exc}") from exc
        if not cfg.project.title:
            # frozen model — rebuild with the default title
            cfg = cfg.model_copy(
                update={"project": ProjectMeta(
                    title=Path(project_dir).name)})
        return cfg
