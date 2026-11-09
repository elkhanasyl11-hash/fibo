"""Safety layer: deterministic keyword rules in Russian and Kazakh, and the level rule."""

import pytest

from app.modules.assistant import safety


@pytest.mark.parametrize(
    "text",
    [
        "Из щита идёт дым",
        "Искрит двигатель",
        "искры летят",
        "Чувствуется запах гари",
        "пахнет горелым",
        "Кабель горит",
        "Видно пламя",
        "Меня ударило током",
        "Бьёт током от станины!",
        "Там оголённый провод",
        "Масло хлещет под давлением",
        "В электрощите треск",
        "щит хлопнул",
        "Түтін шығып тұр",
        "Ұшқын шашырап жатыр",
        "Күйік иісі шығады",
        "Ток соқты",
        "Ток соғады",  # қ -> ғ before a vowel (audit fix)
    ],
)
def test_dangerous_phrases_trigger_stop(text):
    result = safety.check_text([text])
    assert result.triggered and result.kind == "stop" and result.header == safety.STOP_HEADER


@pytest.mark.parametrize(
    "text", ["Шпиндель гудит на высоких оборотах", "Станок стучит", "", None, "давление масла в норме"]
)
def test_normal_descriptions_do_not_trigger(text):
    assert safety.check_text([text]).triggered is False


def test_normalisation():
    assert safety.normalize("  БЬЁТ   током!!! ") == "бьет током"


def test_profile_extra_phrases_and_caption():
    result = safety.check_text([None, "Стружка намоталась на шпиндель"], ["стружка намоталась"])
    assert result.triggered and result.matched == ["стружка намоталась"]


def test_level_rule_and_merge():
    inspect = safety.check_levels("critical", "high")
    assert inspect.triggered and inspect.header == safety.INSPECT_HEADER
    assert not safety.check_levels("critical", "medium").triggered
    assert not safety.check_levels("warning", "high").triggered
    stop = safety.check_text(["дым"])
    merged = safety.merge(inspect, stop)
    assert merged.kind == "stop" and merged.header == safety.STOP_HEADER and len(merged.matched) == 2
    assert safety.merge(safety.SafetyResult(), inspect) is inspect
