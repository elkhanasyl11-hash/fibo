"""Post-generation citation validation helpers."""

from collections.abc import Iterable

from fibo_ai.schemas.incident import IncidentCard


def verify_card_citations(card: IncidentCard, retrieved_pages: Iterable[int]) -> tuple[IncidentCard, list[int]]:
    allowed = set(retrieved_pages)
    card.possible_causes = [
        cause for cause in card.possible_causes if cause.manual_page is None or cause.manual_page in allowed
    ]
    card.actions_now = [
        action for action in card.actions_now if action.manual_page is None or action.manual_page in allowed
    ]
    used = {
        page
        for page in [
            *(cause.manual_page for cause in card.possible_causes),
            *(action.manual_page for action in card.actions_now),
        ]
        if page is not None and page in allowed
    }
    card.manual_pages = sorted(used)
    return card, sorted(allowed)
