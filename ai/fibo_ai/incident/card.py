"""Localized deterministic operator card construction and Telegram-safe rendering."""

import html
from typing import Any

from fibo_ai.core.i18n import LEVEL_ICONS, get_confidence_text, get_level_text, get_stop_line
from fibo_ai.schemas.common import Confidence, IncidentLevel, Lang
from fibo_ai.schemas.incident import (
    ActionItem,
    CauseItem,
    IncidentCard,
)
from fibo_ai.schemas.rag import ManualFragment
from fibo_ai.schemas.speech import ParsedSymptom

SECTION_LABELS = {
    Lang.ru: ("Что найдено", "Возможные причины", "Что делать сейчас"),
    Lang.kk: ("Белгілер", "Ықтимал себептер", "Қазір не істеу керек"),
    Lang.en: ("Findings", "Possible causes", "What to do now"),
}


def _escape(value: str, max_chars: int = 350) -> str:
    return html.escape(value[:max_chars], quote=False)


def render_card_text(card: IncidentCard, force_stop: bool = False) -> str:
    findings_label, causes_label, actions_label = SECTION_LABELS[card.lang]
    lines: list[str] = []
    if force_stop or card.level == IncidentLevel.critical:
        lines.append(get_stop_line(card.lang))
    headline = (
        f"{LEVEL_ICONS[card.level]} <b>{_escape(card.headline)}</b>"
        if card.headline
        else f"{LEVEL_ICONS[card.level]} <b>{_escape(get_level_text(card.level, card.lang))}</b>"
    )
    lines.append(headline)
    if card.findings:
        findings = "; ".join(_escape(item) for item in card.findings[:4])
        lines.append(f"<b>{findings_label}:</b> {findings}")
    if card.possible_causes:
        lines.append(f"<b>{causes_label}:</b>")
        for index, cause in enumerate(card.possible_causes[:3], start=1):
            citation = (
                f" (с. {cause.manual_page})"
                if card.lang == Lang.ru and cause.manual_page
                else (
                    f" (б. {cause.manual_page})"
                    if card.lang == Lang.kk and cause.manual_page
                    else f" (p. {cause.manual_page})"
                    if cause.manual_page
                    else ""
                )
            )
            lines.append(f"{index}. {_escape(cause.text)}{citation}")
    if card.actions_now:
        lines.append(f"<b>{actions_label}:</b>")
        for index, action in enumerate(card.actions_now[:4], start=1):
            citation = ""
            if action.manual_page is not None:
                citation = (
                    f" (с. {action.manual_page})"
                    if card.lang == Lang.ru
                    else f" (б. {action.manual_page})"
                    if card.lang == Lang.kk
                    else f" (p. {action.manual_page})"
                )
            lines.append(f"{index}. {_escape(action.text)}{citation}")
    if card.clarifying_question:
        lines.append(f"<b>{_escape(card.clarifying_question)}</b>")
    result = "\n".join(lines)
    if len(result) > 4096:
        result = result[:4080].rsplit("\n", 1)[0]
    return result


def template_card(
    *,
    machine_id: str | None,
    parsed: ParsedSymptom | None,
    lang: Lang,
    level: IncidentLevel,
    confidence: Confidence,
    findings: list[str],
    fragments: list[ManualFragment],
) -> IncidentCard:
    display_machine = machine_id or (
        "Станок не выбран" if lang == Lang.ru else "Станок таңдалмады" if lang == Lang.kk else "Machine not selected"
    )
    level_label = get_level_text(level, lang)
    confidence_label = get_confidence_text(confidence, lang)
    headline = (
        f"{display_machine} · {level_label} · уверенность: {confidence_label}"
        if lang == Lang.ru
        else f"{display_machine} · {level_label} · сенімділік: {confidence_label}"
        if lang == Lang.kk
        else f"{display_machine} · {level_label} · confidence: {confidence_label}"
    )
    causes: list[CauseItem] = []
    if parsed and parsed.symptom_category in {"overheat", "smell_smoke", "electrical"}:
        causes.append(
            CauseItem(
                text=(
                    "Требуется проверка электрической части и узла шпинделя механиком."
                    if lang == Lang.ru
                    else "Электр бөлігі мен шпиндель торабын механик тексеруі керек."
                    if lang == Lang.kk
                    else "A mechanic should inspect the electrical and spindle assemblies."
                )
            )
        )
    elif parsed and parsed.symptom_category == "vibration":
        causes.append(
            CauseItem(
                text=(
                    "Возможны ослабление крепления или износ вращающегося узла."
                    if lang == Lang.ru
                    else "Бекітпе босап немесе айналмалы торап тозуы мүмкін."
                    if lang == Lang.kk
                    else "A loose mount or wear in a rotating assembly is possible."
                )
            )
        )

    actions: list[ActionItem] = []
    if fragments:
        page = fragments[0].page
        actions.append(
            ActionItem(
                text=(
                    "Сверьте проверку узла с соответствующим разделом инструкции."
                    if lang == Lang.ru
                    else "Торапты тексеруді нұсқаулықтың тиісті бөлімімен салыстырыңыз."
                    if lang == Lang.kk
                    else "Use the relevant manual section to check the assembly."
                ),
                manual_page=page,
            )
        )
    if level == IncidentLevel.critical:
        actions.append(
            ActionItem(
                text=(
                    "Не запускайте станок до осмотра механиком."
                    if lang == Lang.ru
                    else "Механик тексермейінше станокты іске қоспаңыз."
                    if lang == Lang.kk
                    else "Do not restart until a mechanic has inspected it."
                )
            )
        )
    elif not actions:
        actions.append(
            ActionItem(
                text=(
                    "Запишите условия работы и повторите проверку."
                    if lang == Lang.ru
                    else "Жұмыс жағдайын жазып, тексеруді қайталаңыз."
                    if lang == Lang.kk
                    else "Record operating conditions and repeat the check."
                )
            )
        )

    buttons = ["call_mechanic"] if level == IncidentLevel.critical else ["resolved"]
    card = IncidentCard(
        level=level,
        confidence=confidence,
        headline=headline,
        findings=findings[:4],
        possible_causes=causes,
        actions_now=actions,
        clarifying_question=parsed.clarifying_prompt if parsed else None,
        suggested_buttons=buttons,
        manual_pages=sorted({fragment.page for fragment in fragments}),
        card_text="",
        lang=lang,
    )
    card.card_text = render_card_text(card, force_stop=level == IncidentLevel.critical)
    return card


def draft_to_card(
    draft: Any,
    *,
    machine_id: str | None,
    lang: Lang,
    level: IncidentLevel,
    confidence: Confidence,
    fallback_findings: list[str],
) -> IncidentCard:
    display_machine = machine_id or ("Станок" if lang == Lang.ru else "Станок" if lang == Lang.kk else "Machine")
    headline = (
        f"{display_machine} · {get_level_text(level, lang)} · уверенность: {get_confidence_text(confidence, lang)}"
        if lang == Lang.ru
        else f"{display_machine} · {get_level_text(level, lang)} · сенімділік: {get_confidence_text(confidence, lang)}"
        if lang == Lang.kk
        else f"{display_machine} · {get_level_text(level, lang)} · confidence: {get_confidence_text(confidence, lang)}"
    )
    card = IncidentCard(
        level=level,
        confidence=confidence,
        headline=headline,
        findings=draft.findings or fallback_findings,
        possible_causes=draft.possible_causes,
        actions_now=draft.actions_now,
        clarifying_question=draft.clarifying_question,
        suggested_buttons=draft.suggested_buttons,
        manual_pages=[],
        card_text="",
        lang=lang,
    )
    card.card_text = render_card_text(card, force_stop=level == IncidentLevel.critical)
    return card
