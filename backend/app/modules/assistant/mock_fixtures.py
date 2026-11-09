"""Deterministic answers for MockLLMClient (FIBO_AI_MODE=mock). No randomness, no network.

transcript_for(audio bytes)  one of MOCK_TRANSCRIPTS, picked by a hash of the audio, so the same
                             recording always gives the same text.
SymptomExtraction            keyword rules: a transcript containing "гудит" -> spindle bearings…
IncidentCard                 level from the extraction's urgency (high/medium/low ->
                             critical/warning/normal). The mock DELIBERATELY never looks at safety
                             keywords: tests use it to prove the safety layer overrides the model.
                             It also always cites a non-existent manual page 999, so tests can
                             prove that invented pages are dropped.
"""

import hashlib

from app.modules.assistant import mock_chat

MOCK_TRANSCRIPTS = [
    "Шпиндель гудит на высоких оборотах, раньше так не было",
    "Станок стучит при подаче, вибрация сильнее обычного",
    "Деталь перегревается, охлаждающая жидкость идёт слабо",
]
INVENTED_PAGE = 999

# (keywords, extraction fields). First rule whose keyword occurs in the transcript wins.
EXTRACTION_RULES = [
    (
        ("гудит", "гул", "воет"),
        {
            "symptom": "гул шпинделя на высоких оборотах",
            "conditions": "на высоких оборотах",
            "urgency": "medium",
            "causes": ["износ подшипников шпинделя", "недостаток смазки шпинделя"],
            "actions": [
                "Снизьте обороты до осмотра",
                "Проверьте уровень и состояние смазки",
                "Сообщите механику о замене подшипников",
            ],
        },
    ),
    (
        ("стучит", "стук", "вибрац", "дірілд"),
        {
            "symptom": "стук и повышенная вибрация",
            "conditions": "под нагрузкой",
            "urgency": "medium",
            "causes": ["люфт направляющих или винта", "ослабленное крепление"],
            "actions": ["Остановите обработку и проверьте крепление детали", "Проверьте люфт направляющих"],
        },
    ),
    (
        ("перегрев", "горяч", "охлажд"),
        {
            "symptom": "перегрев детали и слабое охлаждение",
            "conditions": None,
            "urgency": "low",
            "causes": ["засорён фильтр СОЖ", "низкий уровень СОЖ"],
            "actions": ["Проверьте уровень СОЖ", "Очистите фильтр насоса СОЖ"],
        },
    ),
]
DEFAULT_EXTRACTION = {
    "symptom": "неопределённая неисправность",
    "conditions": None,
    "urgency": "low",
    "causes": ["недостаточно данных"],
    "actions": ["Опишите, что именно происходит со станком"],
}
URGENCY_TO_LEVEL = {"high": "critical", "medium": "warning", "low": "normal"}


def transcript_for(audio: bytes) -> str:
    index = int(hashlib.sha256(audio).hexdigest(), 16) % len(MOCK_TRANSCRIPTS)
    return MOCK_TRANSCRIPTS[index]


def _rule_for(text: str) -> dict:
    lowered = text.lower()
    for keywords, fields in EXTRACTION_RULES:
        if any(keyword in lowered for keyword in keywords):
            return fields
    return DEFAULT_EXTRACTION


def _extraction(payload: dict) -> dict:
    transcript = payload["transcript"]
    rule = _rule_for(transcript)
    unclear = rule is DEFAULT_EXTRACTION
    return {
        "machine_mentioned": None,
        "symptom": rule["symptom"] if not unclear else transcript[:120],
        "conditions": rule["conditions"],
        "urgency": rule["urgency"],
        "clarifying_question": "При каких условиях это происходит?" if unclear else None,
    }


AUDIO_CAUSES = [  # (word in the audio description, causes, actions)
    (
        "шумность",
        ["износ подшипников", "трение или посторонний предмет"],
        ["Остановите станок при росте шума", "Проверьте смазку и подшипники"],
    ),
    ("пик-фактор", ["удары: люфт или ослабленное крепление"], ["Проверьте крепления и люфт узлов"]),
    (
        "энергия в полосе",
        ["изменение тонального состава: износ или дисбаланс"],
        ["Сравните звук на холостом ходу", "Проверьте балансировку и ремни"],
    ),
]


def _audio_card(payload: dict) -> dict:
    audio = payload["audio"]
    if audio["level"] == "normal":
        return {
            "verdict": "Звук станка близок к эталону",
            "level": "normal",
            "confidence": 0.7,
            "causes": [],
            "actions": ["Продолжайте работу, повторите запись через неделю"],
            "manual_pages": [],
        }
    causes, actions = ["звук отличается от эталона"], ["Позовите механика для осмотра"]
    strongest = audio["description"].split(",")[0]  # the description lists the largest deviation first
    for word, rule_causes, rule_actions in AUDIO_CAUSES:
        if word in strongest:
            causes, actions = rule_causes, rule_actions
            break
    # level "normal" on purpose: tests prove the measured audio level still wins (card.finalize).
    return {
        "verdict": f"Звук отличается от эталона: {audio['description']}",
        "level": "normal",
        "confidence": 0.6,
        "causes": causes,
        "actions": actions,
        "manual_pages": [INVENTED_PAGE],
    }


def _vision_card(payload: dict) -> dict:
    vision = payload["vision"]
    if not vision["defect_found"]:
        return {
            "verdict": "Видимых дефектов не обнаружено",
            "level": "normal",
            "confidence": vision["confidence"],
            "causes": [],
            "actions": ["Продолжайте работу"],
            "manual_pages": [],
        }
    return {
        "verdict": f"Обнаружено: {vision['explanation']}",
        "level": "normal",
        "confidence": vision["confidence"],
        "causes": ["износ инструмента", "неправильные режимы резания"],
        "actions": ["Остановите обработку и осмотрите инструмент", "Замените или переточите инструмент"],
        "manual_pages": [INVENTED_PAGE],
    }


def _visual_inspection(payload: dict) -> dict:
    """The mock cannot see images: it judges by how different the photo is from the reference."""
    diff = payload.get("pixel_difference")
    if diff is None or diff < 12:
        return {
            "defect_found": False,
            "defect_type": "none",
            "zone": None,
            "level": "normal",
            "confidence": 0.6 if diff is not None else 0.3,
            "explanation": "Отличий от эталона не видно",
        }
    if diff < 30:
        return {
            "defect_found": True,
            "defect_type": "edge_wear",
            "zone": "режущая кромка",
            "level": "warning",
            "confidence": 0.6,
            "explanation": "заметный износ режущей кромки",
        }
    return {
        "defect_found": True,
        "defect_type": "chip",
        "zone": "режущая кромка",
        "level": "critical",
        "confidence": 0.7,
        "explanation": "скол на режущей кромке",
    }


PANEL_VALUES = {  # (field, value, confidence, raw text); None = the mock "could not read" it
    "metalworking": [
        ("spindle_rpm", 2800, 0.92, "S 2800"),
        ("load_pct", 64, 0.85, "LOAD 64%"),
        ("temperature_c", 41, 0.7, "T 41°C"),
        ("operating_hours", None, 0.2, "####"),
    ],
    "bakery": [("temperature_c", 230, 0.9, "230°C"), ("humidity_pct", 72, 0.8, "RH 72%")],
}


def _panel(payload: dict) -> dict:
    rows = PANEL_VALUES.get(payload["profile"], [("temperature_c", 38, 0.8, "38°C")])
    return {"values": [{"field": f, "value": v, "confidence": c, "raw_text": raw} for f, v, c, raw in rows]}


def _card(payload: dict) -> dict:
    if payload.get("vision"):
        return _vision_card(payload)
    if payload.get("audio") and not payload.get("extraction"):
        return _audio_card(payload)
    extraction = payload.get("extraction") or {}
    rule = _rule_for(extraction.get("symptom", ""))
    pages = [chunk["page"] for chunk in payload.get("manual_chunks", [])][:2]
    return {
        "verdict": f"Вероятная причина: {rule['causes'][0]}",
        "level": URGENCY_TO_LEVEL[extraction.get("urgency", "low")],
        "confidence": 0.6,
        "causes": rule["causes"],
        "actions": rule["actions"],
        "manual_pages": [*pages, INVENTED_PAGE],
        "clarifying_question": extraction.get("clarifying_question"),
    }


def answer(schema_name: str, payload: dict) -> dict:
    if schema_name == "SymptomExtraction":
        return _extraction(payload)
    if schema_name == "IncidentCard":
        return _card(payload)
    if schema_name == "VisualInspection":
        return _visual_inspection(payload)
    if schema_name == "PanelReadout":
        return _panel(payload)
    raise NotImplementedError(f"no mock answer for {schema_name}")


def tool_answer(messages: list[dict], tools: list[dict]) -> dict:
    """The AI chat with tools: see mock_chat.py."""
    return mock_chat.tool_answer(messages, tools)
