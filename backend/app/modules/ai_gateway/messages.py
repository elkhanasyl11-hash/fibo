"""Card texts for AI input errors, in Russian and Kazakh (Kazakh = drafts for a native speaker, D77).

The AI service sends its own retake advice for blurry photos (retake_advice_ru / _kk); the other input
errors get these fixed texts. Plain text only: the bot escapes and shows it as is.
"""

from app.modules.ai_gateway.client import FiboAIError

TEXTS = {
    "ru": {
        "ai_asr_low_confidence": "🎙 Не удалось разобрать речь. Запишите сообщение ещё раз, ближе к телефону и без шума.",
        "ai_audio_too_short": "🔊 Запись слишком короткая или тихая. Запишите 10–15 секунд работы станка.",
        "ai_manual_unavailable": "📖 Паспорт станка сейчас недоступен — ссылки на страницы не добавлены.",
        "ai_photo_retake": "📷 Фото не подходит для анализа. Переснимите при хорошем свете, держа телефон неподвижно.",
    },
    "kk": {
        "ai_asr_low_confidence": "🎙 Сөзді тану мүмкін болмады. Хабарды телефонға жақын, шусыз қайта жазыңыз.",
        "ai_audio_too_short": "🔊 Жазба тым қысқа немесе тым тыныш. Станок жұмысын 10–15 секунд жазыңыз.",
        "ai_manual_unavailable": "📖 Станок төлқұжаты қазір қолжетімсіз — бет сілтемелері қосылмады.",
        "ai_photo_retake": "📷 Фото талдауға жарамсыз. Жақсы жарықта, телефонды қозғалтпай қайта түсіріңіз.",
    },
}
MAX_ADVICE = 500  # AI-supplied text: cap it so a card stays far below Telegram's 4096 characters
CODE_TO_KEY = {
    "ASR_LOW_CONFIDENCE": "ai_asr_low_confidence",
    "AUDIO_TOO_SHORT": "ai_audio_too_short",
    "AUDIO_SILENT": "ai_audio_too_short",
    "PHOTO_QUALITY_LOW": "ai_photo_retake",
}


def text(key: str, lang: str) -> str:
    return TEXTS.get(lang, TEXTS["ru"])[key]


def input_error_text(error: FiboAIError, lang: str) -> str:
    """Card text for an input error. PHOTO_QUALITY_LOW prefers the service's own retake advice."""
    if error.code == "PHOTO_QUALITY_LOW":
        advice = error.details.get(f"retake_advice_{lang}") or error.details.get("retake_advice_ru")
        if isinstance(advice, str) and advice.strip():
            return f"📷 {advice.strip()[:MAX_ADVICE]}"
    return text(CODE_TO_KEY.get(error.code, "ai_audio_too_short"), lang)
