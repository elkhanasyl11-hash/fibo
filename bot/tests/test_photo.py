"""Panel flow helpers: corrections parsing, safe display, reading body for confirmed values."""

import json

import httpx

from bot.api_client import FiboApi
from bot.handlers.photo import format_values, parse_corrections


def test_corrections_update_and_add_values():
    values, bad = parse_corrections(
        "load_pct=70\n\n temperature_c = 42,5 ", {"load_pct": 64, "spindle_rpm": 2800}
    )
    assert bad is None and values == {"load_pct": 70, "spindle_rpm": 2800, "temperature_c": 42.5}


def test_bad_correction_line_keeps_old_values():
    original = {"load_pct": 64}
    values, bad = parse_corrections("load_pct=70\nнагрузка семьдесят", original)
    assert bad == "нагрузка семьдесят" and values == original


def test_values_are_listed_with_titles_and_escaped():
    text = format_values({"load_pct": 64.0, "<b>x": 1})
    assert "Нагрузка, %: 64" in text and "&lt;b&gt;x: 1" in text


async def test_confirmed_values_go_to_readings_with_extra_split():
    seen = {}

    def handler(request):
        seen["path"], seen["body"] = request.url.path, json.loads(request.content)
        return httpx.Response(201, json={"id": 1})

    api = FiboApi("http://b/api/v1", "s", transport=httpx.MockTransport(handler))
    await api.create_reading(5, {"temperature_c": 230, "humidity_pct": 72}, ["humidity_pct"], user_id=9)
    assert seen["path"] == "/api/v1/readings"
    assert seen["body"] == {
        "machine_id": 5,
        "source": "panel",
        "created_by_user_id": 9,
        "temperature_c": 230,
        "extra": {"humidity_pct": 72},
    }
