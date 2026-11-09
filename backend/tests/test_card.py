"""Card rules the LLM is not trusted with: real pages only, safety forces CRITICAL."""

from app.modules.assistant import card as card_module
from app.modules.assistant import safety
from app.modules.assistant.rag import ManualChunk, RagResult


def _card(**fields) -> card_module.IncidentCard:
    base = {
        "verdict": "Износ подшипников",
        "level": "normal",
        "confidence": 0.6,
        "causes": ["износ"],
        "actions": ["Снизьте обороты"],
        "manual_pages": [12, 999],
    }
    return card_module.IncidentCard(**{**base, **fields})


def test_invented_pages_are_dropped():
    rag = RagResult(found=True, chunks=[ManualChunk(page=12, text="...", similarity=0.8)])
    final = card_module.finalize(_card(), safety.SafetyResult(), rag)
    assert final.card.manual_pages == [12] and final.dropped_pages == [999]


def test_safety_forces_critical_even_if_model_says_normal():
    final = card_module.finalize(_card(level="normal"), safety.check_text(["искры"]), RagResult(found=False))
    assert final.card.level == "critical"
    text = card_module.render_text("ЧПУ-1", final)
    assert text.startswith(safety.STOP_HEADER)
    assert card_module.GENERAL_SAFETY_ADVICE in text  # nothing found in the manual -> said explicitly
    assert final.card.manual_pages == []


def test_buttons_fit_telegram_limit():
    buttons = card_module.button_spec(123456789, has_pages=True)
    assert len(buttons) == 3 and all(len(b["callback_data"].encode()) <= 64 for b in buttons)
