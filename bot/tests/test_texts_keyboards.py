"""Texts exist in both languages; keyboards follow Telegram's limits."""

import re

from bot import keyboards
from bot.texts import MENU_ACTIONS, TEXTS, t


def test_ru_and_kk_have_the_same_keys_and_placeholders():
    assert TEXTS["ru"].keys() == TEXTS["kk"].keys()
    for key in TEXTS["ru"]:
        assert set(re.findall(r"{(\w+)}", TEXTS["ru"][key])) == set(
            re.findall(r"{(\w+)}", TEXTS["kk"][key])
        ), key


def test_menu_buttons_recognised_in_both_languages():
    assert MENU_ACTIONS[t("ru", "btn_sound")] == "sound" and MENU_ACTIONS[t("kk", "btn_sound")] == "sound"
    assert set(MENU_ACTIONS.values()) == {"report", "sound", "photo", "panel", "machines"}


def test_unknown_language_falls_back_to_russian():
    assert t("en", "menu") == TEXTS["ru"]["menu"]


def _callbacks(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def test_callback_data_under_64_bytes():
    machines = [{"id": 2_000_000_000, "name": "ЧПУ-1 фрезерный Haas VF-2 с длинным названием"}]
    data = _callbacks(keyboards.machines(machines, "report")) + _callbacks(
        keyboards.card({"id": 2_000_000_000, "manual_pages": [3]})
    )
    assert data and all(len(item.encode()) <= 64 for item in data)


def test_manual_button_only_with_pages():
    assert _callbacks(keyboards.card({"id": 5, "manual_pages": []})) == ["res:5", "esc:5"]
    assert _callbacks(keyboards.card({"id": 5, "manual_pages": [12]})) == ["res:5", "esc:5", "pg:5"]
