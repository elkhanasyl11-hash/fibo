"""Deterministic stand-in for the AI chat model (FIBO_AI_MODE=mock).

Step 1 (no tool results yet for the last question): pick ONE tool by keywords in the question:
  risk / dangerous / priority / which machine           -> get_risk_ranking
  downtime / losses / report / MTBF                     -> get_downtime_report
  incident / breakdown / problem                        -> get_incidents
  a machine name with a digit (e.g. "ЧПУ-1")            -> get_machine_summary
  anything else                                         -> a short help text, no tool
Step 2 (tool results present, or tools no longer offered): write the answer ONLY from those results,
in Russian or Kazakh (read from "reply_language:" in the system prompt). Like the real model, it
cannot see the database — only what the tools returned.
"""

import json
import re

RANKING_WORDS = ("риск", "опасн", "приоритет", "какой станок", "каком станке", "қауіп", "қай станок")
DOWNTIME_WORDS = ("простой", "простоя", "потер", "убыт", "отчет", "отчёт", "mtbf", "шығын", "тоқта")
INCIDENT_WORDS = ("инцидент", "полом", "проблем", "авари", "оқиға", "ақау")
MACHINE_TOKEN = re.compile(r"[A-Za-zА-Яа-яЁё]+-?\d+")
HELP = {
    "ru": "Я могу рассказать, какой станок в зоне риска, о простоях и потерях, об инцидентах или о конкретном "
    "станке. Уточните вопрос.",
    "kk": "Мен қай станок қауіпті екенін, тұрып қалу мен шығындарды, оқиғаларды немесе нақты станокты айта аламын.",
}


def _language(messages: list[dict]) -> str:
    match = re.search(r"reply_language: (\w+)", messages[0].get("content") or "")
    return match.group(1) if match else "ru"


def _tool_results(messages: list[dict]) -> dict[str, dict]:
    """Results of tools called after the last user message, by tool name."""
    last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
    names = {
        call["id"]: call["function"]["name"]
        for m in messages[last_user:]
        if m["role"] == "assistant"
        for call in m.get("tool_calls") or []
    }
    return {
        names[m["tool_call_id"]]: json.loads(m["content"])
        for m in messages[last_user:]
        if m["role"] == "tool" and m["tool_call_id"] in names
    }


def _choose_tool(question: str) -> tuple[str, dict] | None:
    text = question.lower()
    token = MACHINE_TOKEN.search(question)
    machine = {"machine_name_or_id": token.group(0)} if token else {}
    if token and any(
        word in text for word in ("после то", "после обслуживания", "если", "эффект то", "тқ кейін")
    ):
        return "compare_maintenance", machine
    if any(
        word in text
        for word in (
            "график то",
            "план обслуж",
            "срок то",
            "план работ",
            "когда обслуж",
            "тқ жоспары",
            "техническое обслуживание",
        )
    ):
        return "get_maintenance_plan", {}
    if any(
        word in text
        for word in ("температур", "нагрузк", "динамик", "тренд", "замер", "изменил", "өлшем", "жүктеме")
    ):
        return "get_reading_trends", {
            **machine,
            "days": 30 if any(word in text for word in ("месяц", "айда")) else 7,
        }
    if token:
        return "get_machine_summary", machine
    if any(word in text for word in RANKING_WORDS):
        return "get_risk_ranking", {}
    if any(word in text for word in DOWNTIME_WORDS):
        return "get_downtime_report", {}
    if any(word in text for word in INCIDENT_WORDS):
        return "get_incidents", {}
    return None


def _ranking_text(data: dict, lang: str) -> str:
    items = data["ranking"]
    if not items:
        return "Оценок риска пока нет." if lang == "ru" else "Тәуекел бағалары әзірге жоқ."
    top = items[0]
    p = top["failure_probability"]
    if lang == "kk":
        return f"Ең қауіпті станок — {top['machine']}: күтілетін шығын {top['priority_kzt']} ₸, тәуекел индексі {top['risk_index']:.2f}."
    text = f"Самый рискованный станок — {top['machine']}: ожидаемые потери {top['priority_kzt']} ₸, индекс риска {top['risk_index']:.2f}"
    text += f", вероятность отказа {p:.0%}." if p is not None else "."
    if top["main_factors"]:
        text += " Основные факторы: " + ", ".join(top["main_factors"]) + "."
    if len(items) > 1:
        text += " Далее: " + ", ".join(f"{i['machine']} ({i['priority_kzt']} ₸)" for i in items[1:3]) + "."
    return text


def _downtime_text(data: dict, lang: str) -> str:
    t = data["totals"]
    causes = ", ".join(c["cause"] for c in data["top_causes"][:3]) or "нет данных"
    if lang == "kk":
        return f"Кезеңде: тұрып қалу {t['downtime_hours']} сағ, шығын {t['loss_kzt']} ₸."
    return (
        f"За период: простой {t['downtime_hours']} ч, потери {t['loss_kzt']} ₸; ещё не закрыто "
        f"{t['ongoing_hours']} ч (≈{t['ongoing_loss_kzt']} ₸). Частые причины: {causes}."
    )


def _incidents_text(data: dict, lang: str) -> str:
    if not data["count"]:
        return "Инцидентов не найдено." if lang == "ru" else "Оқиғалар табылмады."
    last = data["incidents"][0]
    return f"Найдено инцидентов: {data['count']}. Последний: {last['machine']} — {last['verdict']} ({last['level']})."


def _machine_text(data: dict, lang: str) -> str:
    risk = data["latest_risk"]
    risk_text = (
        f"индекс риска {risk['risk_index']:.2f}, приоритет {risk['priority_kzt']} ₸"
        if risk
        else "оценки риска нет"
    )
    return f"{data['machine']}: {risk_text}; открытых инцидентов: {len(data['open_incidents'])}."


def _trends_text(data: dict, lang: str) -> str:
    if not data["readings"]:
        return (
            f"{data['machine']}: за {data['days']} дн. замеров нет. Добавьте показания, чтобы сравнить динамику."
            if lang == "ru"
            else f"{data['machine']}: {data['days']} күнде өлшемдер жоқ."
        )
    labels = (
        {
            "temperature_c": "Температура",
            "load_pct": "Нагрузка",
            "spindle_rpm": "Обороты",
            "operating_hours": "Наработка",
        }
        if lang == "ru"
        else {
            "temperature_c": "Температура",
            "load_pct": "Жүктеме",
            "spindle_rpm": "Айналым",
            "operating_hours": "Жұмыс уақыты",
        }
    )
    parts = [
        f"{data['machine']} · {data['days']} дн. · {data['readings']} замеров"
        if lang == "ru"
        else f"{data['machine']} · {data['days']} күн · {data['readings']} өлшем"
    ]
    for name, values in data["fields"].items():
        parts.append(
            f"{labels.get(name, name)}: {values['first']:g} → {values['latest']:g}; Δ {values['change']:+g}; min–max {values['min']:g}–{values['max']:g}"
        )
    parts.append(
        "Это сравнение сохранённых замеров, а не диагноз. Для вывода о неисправности нужны условия измерения и осмотр."
        if lang == "ru"
        else "Бұл сақталған өлшемдерді салыстыру. Ақау туралы қорытынды үшін өлшеу жағдайлары мен тексеру қажет."
    )
    return "\n\n".join(parts)


def _maintenance_text(data: dict, lang: str) -> str:
    if not data["machines"]:
        return "Оборудование пока не добавлено." if lang == "ru" else "Жабдық әлі қосылмаған."
    parts = []
    for item in data["machines"][:5]:
        hours = item["hours_until_maintenance"]
        schedule = (
            "график не задан"
            if hours is None
            else f"просрочено на {-hours:.0f} ч"
            if hours < 0
            else f"до ТО {hours:.0f} ч"
        )
        if lang == "kk":
            schedule = (
                "кесте жоқ"
                if hours is None
                else f"{-hours:.0f} сағ кешікті"
                if hours < 0
                else f"ТҚ дейін {hours:.0f} сағ"
            )
        parts.append(f"{item['machine']}: {schedule}")
    parts.append(
        "Сроки рассчитаны в календарных часах от последнего ТО."
        if lang == "ru"
        else "Мерзімдер соңғы ТҚ бастап күнтізбелік сағатпен есептелді."
    )
    return "\n\n".join(parts)


def _scenario_text(data: dict, lang: str) -> str:
    if lang == "kk":
        return f"{data['machine']}: ТҚ сценарийінде тәуекел {data['current_risk']:.2f} → {data['scenario_risk']:.2f}, басымдық {data['current_priority_kzt']} → {data['scenario_priority_kzt']} ₸. Бұл болжамды сценарий, кепілдік емес. Деректер сақталған жоқ."
    return f"{data['machine']}: в сценарии после ТО индекс риска {data['current_risk']:.2f} → {data['scenario_risk']:.2f}, приоритет {data['current_priority_kzt']} → {data['scenario_priority_kzt']} ₸. Это расчётный сценарий, а не гарантированная экономия. Данные не изменены."


WRITERS = {
    "get_reading_trends": _trends_text,
    "get_maintenance_plan": _maintenance_text,
    "compare_maintenance": _scenario_text,
    "get_risk_ranking": _ranking_text,
    "get_downtime_report": _downtime_text,
    "get_incidents": _incidents_text,
    "get_machine_summary": _machine_text,
}


def tool_answer(messages: list[dict], tools: list[dict]) -> dict:
    lang = _language(messages)
    results = _tool_results(messages)
    if not results and tools:
        question = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        # Carry a concrete machine into short follow-up questions when the user omits its name.
        if not MACHINE_TOKEN.search(question):
            previous = " ".join(
                str(message.get("content") or "")
                for message in messages[:-1]
                if message["role"] in {"user", "assistant"}
            )
            matches = MACHINE_TOKEN.findall(previous)
            if matches and any(
                word in question.lower()
                for word in ("него", "нём", "этого", "его", "после то", "температур", "жүктеме", "оның")
            ):
                question += " " + matches[-1]
        choice = _choose_tool(question)
        if choice is None:
            return {"role": "assistant", "content": HELP.get(lang, HELP["ru"]), "tool_calls": []}
        name, arguments = choice
        call = {
            "id": f"call_{name}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
        }
        return {"role": "assistant", "content": None, "tool_calls": [call]}
    parts = []
    for name, data in results.items():
        parts.append(
            f"Не удалось получить данные: {data['error']}" if "error" in data else WRITERS[name](data, lang)
        )
    return {"role": "assistant", "content": " ".join(parts) or HELP.get(lang, HELP["ru"]), "tool_calls": []}
