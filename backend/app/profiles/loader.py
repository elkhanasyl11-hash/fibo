"""Industry profiles: load and validate app/profiles/*.yaml at startup.

A profile is configuration, not code: equipment catalog, risk-index weights, valid reading ranges,
profile-specific reading fields, extra safety keywords and assistant prompt context.

The Pydantic models below are the schema of a profile file. load_profiles() validates every file
and raises ProfileConfigError with the file name and the reason if anything is wrong, so the
application refuses to start with a broken profile instead of failing later during the demo.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.db.base import Profile

PROFILES_DIR = Path(__file__).parent


class ProfileConfigError(Exception):
    """A profile YAML file is missing or invalid."""


class RiskWeights(BaseModel):
    """Weights of the risk-index signals (modules/machine/risk_index.py). 0 = signal not used."""

    model_config = ConfigDict(extra="forbid")

    p_model: float = Field(default=0.0, ge=0)
    s_audio: float = Field(default=0.0, ge=0)
    s_visual: float = Field(default=0.0, ge=0)
    s_overdue: float = Field(default=0.0, ge=0)
    s_history: float = Field(default=0.0, ge=0)


class ExtraField(BaseModel):
    """A profile-specific reading value, stored in readings.extra (e.g. humidity_pct)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    title_ru: str
    title_kk: str | None = None
    unit: str


class EquipmentType(BaseModel):
    """One entry of the equipment catalog offered when a machine is added."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    title_ru: str
    title_kk: str | None = None
    default_criticality: int = Field(ge=1, le=3)


class ProfileConfig(BaseModel):
    """Schema of one app/profiles/<id>.yaml file."""

    model_config = ConfigDict(extra="forbid")

    id: Profile
    title_ru: str
    title_kk: str
    nominal_torque_nm: float | None = Field(default=None, gt=0)
    default_air_temperature_k: float = Field(default=298.0, gt=0)
    model_applicable: bool
    risk_weights: RiskWeights
    reading_ranges: dict[str, tuple[float, float]]
    extra_fields: list[ExtraField] = []
    equipment_catalog: list[EquipmentType] = Field(min_length=1)
    safety_keywords_extra: list[str] = []
    assistant_context_ru: str
    assistant_context_kk: str | None = None

    @model_validator(mode="after")
    def check_consistency(self) -> "ProfileConfig":
        weights = self.risk_weights
        total = weights.p_model + weights.s_audio + weights.s_visual + weights.s_overdue + weights.s_history
        if total <= 0:
            raise ValueError("risk_weights must contain at least one positive weight")
        if self.model_applicable and (self.nominal_torque_nm is None or weights.p_model <= 0):
            raise ValueError("model_applicable=true needs nominal_torque_nm and a positive p_model weight")
        if not self.model_applicable and weights.p_model != 0:
            raise ValueError("model_applicable=false requires risk_weights.p_model = 0")
        for name, (low, high) in self.reading_ranges.items():
            if low >= high:
                raise ValueError(f"reading_ranges.{name}: min {low} must be below max {high}")
        for field in self.extra_fields:
            if field.name not in self.reading_ranges:
                raise ValueError(f"extra field '{field.name}' needs an entry in reading_ranges")
        types = [item.type for item in self.equipment_catalog]
        if len(types) != len(set(types)):
            raise ValueError("equipment_catalog contains duplicate types")
        return self


def load_profile_file(path: Path) -> ProfileConfig:
    """Read and validate one YAML file. The `id` inside must match the file name."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ProfileConfigError(f"{path.name}: cannot read YAML: {exc}") from exc
    try:
        profile = ProfileConfig.model_validate(raw)
    except ValidationError as exc:
        raise ProfileConfigError(f"{path.name}: invalid profile:\n{exc}") from exc
    if profile.id.value != path.stem:
        raise ProfileConfigError(f"{path.name}: id '{profile.id.value}' does not match the file name")
    return profile


def load_profiles(directory: Path = PROFILES_DIR) -> dict[Profile, ProfileConfig]:
    """Load all profiles. Every value of the Profile enum must have exactly one YAML file."""
    profiles: dict[Profile, ProfileConfig] = {}
    for profile_id in Profile:
        path = directory / f"{profile_id.value}.yaml"
        if not path.exists():
            raise ProfileConfigError(f"missing profile file: {path.name}")
        profiles[profile_id] = load_profile_file(path)
    return profiles


_loaded_profiles: dict[Profile, ProfileConfig] | None = None


def get_profiles() -> dict[Profile, ProfileConfig]:
    """Profiles loaded once per process (startup, background tasks, seed all share them)."""
    global _loaded_profiles
    if _loaded_profiles is None:
        _loaded_profiles = load_profiles()
    return _loaded_profiles
