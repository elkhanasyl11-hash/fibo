"""Industry profiles load, are internally consistent, and broken files stop the app."""

import shutil

import pytest

from app.db.base import Profile
from app.profiles.loader import PROFILES_DIR, ProfileConfigError, load_profiles

FOOD = {Profile.BAKERY, Profile.CONFECTIONERY, Profile.DAIRY}


def test_all_five_profiles_load():
    profiles = load_profiles()
    assert set(profiles) == set(Profile)


def test_only_metalworking_uses_the_model():
    profiles = load_profiles()
    for profile_id, profile in profiles.items():
        if profile_id == Profile.METALWORKING:
            assert profile.model_applicable and profile.risk_weights.p_model > 0
        else:
            assert not profile.model_applicable and profile.risk_weights.p_model == 0


def test_food_profiles_have_extra_fields():
    profiles = load_profiles()
    for profile_id in FOOD:
        assert profiles[profile_id].extra_fields, profile_id


def _copy_profiles(tmp_path):
    for path in PROFILES_DIR.glob("*.yaml"):
        shutil.copy(path, tmp_path / path.name)


def test_invalid_yaml_fails_with_file_name(tmp_path):
    _copy_profiles(tmp_path)
    (tmp_path / "bakery.yaml").write_text("id: bakery\nrisk_weights: [not, a, mapping\n", encoding="utf-8")
    with pytest.raises(ProfileConfigError, match="bakery.yaml"):
        load_profiles(tmp_path)


def test_food_profile_with_model_weight_is_rejected(tmp_path):
    _copy_profiles(tmp_path)
    path = tmp_path / "dairy.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("p_model: 0,", "p_model: 0.3,"), encoding="utf-8"
    )
    with pytest.raises(ProfileConfigError, match="p_model"):
        load_profiles(tmp_path)


def test_missing_profile_file_is_rejected(tmp_path):
    _copy_profiles(tmp_path)
    (tmp_path / "sewing.yaml").unlink()
    with pytest.raises(ProfileConfigError, match="sewing.yaml"):
        load_profiles(tmp_path)


async def test_profiles_endpoint(client):
    response = await client.get("/api/v1/profiles")
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert ids == {p.value for p in Profile}
