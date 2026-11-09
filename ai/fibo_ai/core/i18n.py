from fibo_ai.schemas.common import Confidence, IncidentLevel, Lang

STOP_LINE: dict[Lang, str] = {
    Lang.ru: "Остановите станок и отключите питание.",
    Lang.kk: "Станокты тоқтатып, қуатты өшіріңіз.",
    Lang.en: "Stop the machine and disconnect power immediately.",
}

CONFIDENCE_LABEL: dict[Lang, dict[Confidence, str]] = {
    Lang.ru: {
        Confidence.low: "низкая",
        Confidence.medium: "средняя",
        Confidence.high: "высокая",
    },
    Lang.kk: {
        Confidence.low: "төмен",
        Confidence.medium: "орташа",
        Confidence.high: "жоғары",
    },
    Lang.en: {
        Confidence.low: "low",
        Confidence.medium: "medium",
        Confidence.high: "high",
    },
}

LEVEL_LABEL: dict[Lang, dict[IncidentLevel, str]] = {
    Lang.ru: {
        IncidentLevel.normal: "В норме",
        IncidentLevel.attention: "Внимание",
        IncidentLevel.critical: "Критично",
    },
    Lang.kk: {
        IncidentLevel.normal: "Қалыпты",
        IncidentLevel.attention: "Назар аударыңыз",
        IncidentLevel.critical: "Сыни қауіп",
    },
    Lang.en: {
        IncidentLevel.normal: "Normal",
        IncidentLevel.attention: "Attention",
        IncidentLevel.critical: "Critical",
    },
}

LEVEL_ICONS: dict[IncidentLevel, str] = {
    IncidentLevel.normal: "🟢",
    IncidentLevel.attention: "🟠",
    IncidentLevel.critical: "🔴",
}


def get_stop_line(lang: Lang) -> str:
    return STOP_LINE.get(lang, STOP_LINE[Lang.ru])


def get_confidence_text(confidence: Confidence, lang: Lang) -> str:
    return CONFIDENCE_LABEL.get(lang, CONFIDENCE_LABEL[Lang.ru]).get(confidence, confidence.value)


def get_level_text(level: IncidentLevel, lang: Lang) -> str:
    return LEVEL_LABEL.get(lang, LEVEL_LABEL[Lang.ru]).get(level, level.value)
