import re

from fibo_ai.core.i18n import get_stop_line
from fibo_ai.incident.card import render_card_text
from fibo_ai.safety.rules import SafetyDecision
from fibo_ai.schemas.common import IncidentLevel
from fibo_ai.schemas.incident import ActionItem, IncidentCard

# Unsafe continuations and prompt-injection strings are removed from rendered content.
DANGEROUS_PATTERNS = [
    re.compile(r"продолжа\w*\s+работ\w*", re.IGNORECASE),
    re.compile(r"можно\s+работ\w*", re.IGNORECASE),
    re.compile(r"жұмысты\s+жалғастыр\w*", re.IGNORECASE),
    re.compile(r"keep\s+running", re.IGNORECASE),
    re.compile(r"continue\s+working", re.IGNORECASE),
    re.compile(r"keep\s+operating", re.IGNORECASE),
    re.compile(r"continue\s+to\s+operate", re.IGNORECASE),
    re.compile(r"не\s+останавлива\w*", re.IGNORECASE),
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"игнорируй\s+предыдущ\w+\s+инструкц\w*", re.IGNORECASE),
    re.compile(r"алдыңғы\s+нұсқауларды\s+елеме\w*", re.IGNORECASE),
]


def _contains_dangerous_advice(text: str) -> bool:
    return any(pattern.search(text) for pattern in DANGEROUS_PATTERNS)


def enforce_safety_guard(card: IncidentCard, safety: SafetyDecision) -> IncidentCard:
    # 1. Floor level enforcement
    level_order = [IncidentLevel.normal, IncidentLevel.attention, IncidentLevel.critical]
    if level_order.index(card.level) < level_order.index(safety.floor_level):
        card.level = safety.floor_level

    # 2. If force_stop or critical, ensure stop line is first
    force_stop = safety.force_stop or card.level == IncidentLevel.critical
    card.findings = [value for value in card.findings if not _contains_dangerous_advice(value)]
    card.possible_causes = [cause for cause in card.possible_causes if not _contains_dangerous_advice(cause.text)]
    card.actions_now = [action for action in card.actions_now if not _contains_dangerous_advice(action.text)]
    if force_stop:
        stop_line = get_stop_line(card.lang)
        card.actions_now = [action for action in card.actions_now if action.text.strip() != stop_line.strip()]
        card.actions_now.insert(0, ActionItem(text=stop_line, manual_page=None))

    if card.clarifying_question and _contains_dangerous_advice(card.clarifying_question):
        card.clarifying_question = None
    # Always reconstruct from validated fields so stale or adversarial card_text is discarded.
    card.card_text = render_card_text(card, force_stop=force_stop)

    return card
