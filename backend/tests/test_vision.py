"""Fibo Vision units: photo quality, pixel difference, panel value validation, image attachment."""

import base64

import pytest

from app.db.base import Profile
from app.modules.assistant.llm import _with_images
from app.modules.vision import panel_ocr
from app.modules.vision.quality import check_quality, pixel_difference
from app.profiles.loader import load_profiles
from tests.image_samples import blurred, damaged, jpeg, tool_image

PROFILES = load_profiles()


@pytest.fixture
def photos(tmp_path):
    images = {
        "sharp": tool_image(),
        "blurry": blurred(tool_image()),
        "dark": (tool_image() * 0.2).astype("uint8"),
        "chipped": damaged(tool_image(), 0.3),
    }
    paths = {}
    for name, image in images.items():
        paths[name] = tmp_path / f"{name}.jpg"
        paths[name].write_bytes(jpeg(image))
    (tmp_path / "broken.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)
    paths["broken"] = tmp_path / "broken.jpg"
    return paths


def test_quality_checks(photos):
    assert check_quality(photos["sharp"]).ok
    blurry = check_quality(photos["blurry"])
    assert not blurry.ok and blurry.reasons == ["blurry"] and "размытое" in blurry.text_ru
    assert check_quality(photos["dark"]).reasons == ["too_dark"]
    assert check_quality(photos["broken"]).reasons == ["unreadable"]


def test_pixel_difference(photos):
    assert pixel_difference(photos["sharp"], photos["sharp"]) == 0
    assert pixel_difference(photos["sharp"], photos["chipped"]) > 30


def _readout(*items):
    return panel_ocr.PanelReadout(
        values=[panel_ocr.PanelValue(field=f, value=v, confidence=0.9) for f, v in items]
    )


def test_panel_values_are_checked_against_the_profile():
    metal = PROFILES[Profile.METALWORKING]
    accepted, rejected = panel_ocr.validate(
        _readout(("spindle_rpm", 2800), ("load_pct", 300), ("humidity_pct", 50), ("temperature_c", None)),
        metal,
    )
    assert [a.field for a in accepted] == ["spindle_rpm"]
    reasons = {r.field: r.reason for r in rejected}
    assert reasons["load_pct"].startswith("outside valid range")
    assert reasons["humidity_pct"] == "field not used by this profile"
    assert reasons["temperature_c"] == "not readable"
    bakery = PROFILES[Profile.BAKERY]
    assert panel_ocr.allowed_fields(bakery)["humidity_pct"] == "extra"
    assert "spindle_rpm" not in panel_ocr.allowed_fields(bakery)


def test_images_are_sent_as_data_urls(photos):
    messages = _with_images([{"role": "user", "content": "x"}], [photos["sharp"]])
    parts = messages[-1]["content"]
    assert parts[0] == {"type": "text", "text": "x"}
    url = parts[1]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == photos["sharp"].read_bytes()
