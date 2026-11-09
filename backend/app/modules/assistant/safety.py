"""Fibo Assistant: the safety layer. Plain Python rules, NOT AI, fully unit-tested.

It runs BEFORE any LLM output is used, and its result is saved on the incident immediately, so
the operator sees the stop instruction even if every later stage fails. The LLM can never lower a
level the safety layer raised.

Two kinds of trigger:
  stop     a dangerous word/phrase in the transcript or caption (smoke, sparks, burning smell,
           electric shock, ...), in Russian or Kazakh, plus the profile's extra phrases
           -> STOP_HEADER, level forced to CRITICAL.
  inspect  the audio or photo check says "critical" AND the operator's urgency is "high"
           -> INSPECT_HEADER, level forced to CRITICAL.

Text is normalised first (lowercase, ё -> е, punctuation removed) so "Бьёт током!" matches.
The patterns are regular expressions on word stems ("искр" matches искры, искрит, искрение).
Kazakh phrases are drafts to be verified by a native speaker (docs/decisions.md).
"""

import re
from dataclasses import dataclass, field

STOP_HEADER = (
    "⛔ НЕМЕДЛЕННО ОСТАНОВИТЕ СТАНОК И ОТКЛЮЧИТЕ ПИТАНИЕ. Не приближайтесь, пока не прибудет ответственный."
)
INSPECT_HEADER = "⛔ Остановите станок до осмотра механиком"

# (label shown in `matched`, pattern on normalised text)
BASE_PATTERNS: list[tuple[str, str]] = [
    ("дым", r"\bдым\w*"),
    ("искры", r"\bискр\w*"),
    ("запах гари", r"\b(запах\w*|пахнет|пахн\w*)\s+(гар\w*|горел\w*|жжен\w*)|\bгарью\b"),
    ("горит", r"\b(горит|горят|загорел\w*|возгоран\w*)\b"),
    ("пламя", r"\b(плам\w*|огонь|огня)\b"),
    ("удар током", r"\b(удар\w*|бьет|бьют|шибанул\w*|дернул\w*)\s+током\b|\bтоком\s+(ударил\w*|бьет)\b"),
    ("оголённый провод", r"\bоголен\w*\s+провод\w*|\bпровод\w*\s+оголен\w*"),
    ("утечка масла под давлением", r"\bмасл\w*\s+(\w+\s+){0,3}под\s+давлением"),
    (
        "треск/хлопок в электрощите",
        r"\b(треск\w*|трещ\w*|хлоп\w*)\b.{0,30}\b(электро)?щит\w*|"
        r"\b(электро)?щит\w*\b.{0,30}\b(треск\w*|трещ\w*|хлоп\w*)",
    ),
    # Kazakh (drafts, verify with a native speaker)
    ("түтін (дым)", r"\bтүтін\w*"),
    ("ұшқын (искры)", r"\bұшқын\w*"),
    ("күйік иісі (запах гари)", r"\bкүйік\s+иіс\w*|\bкүйген\s+иіс\w*"),
    ("ток соқты (удар током)", r"\bток\s+со[қғ]\w*"),  # қ -> ғ before a vowel: соқты, соғады
    ("өрт / жалын (огонь)", r"\b(өрт\w*|жалын\w*)\b"),
]
_COMPILED = [(label, re.compile(pattern)) for label, pattern in BASE_PATTERNS]


@dataclass
class SafetyResult:
    triggered: bool = False
    kind: str | None = None  # "stop" | "inspect"
    matched: list[str] = field(default_factory=list)
    header: str | None = None


def normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text)  # punctuation -> space (\w keeps Cyrillic and Kazakh letters)
    return re.sub(r"\s+", " ", text).strip()


def check_text(texts: list[str | None], extra_phrases: list[str] | None = None) -> SafetyResult:
    """Look for dangerous words in the transcript / caption."""
    combined = normalize(" ".join(t for t in texts if t))
    if not combined:
        return SafetyResult()
    matched = [label for label, pattern in _COMPILED if pattern.search(combined)]
    for phrase in extra_phrases or []:
        if normalize(phrase) and normalize(phrase) in combined:
            matched.append(phrase)
    if not matched:
        return SafetyResult()
    return SafetyResult(True, "stop", matched, STOP_HEADER)


def check_levels(sensor_level: str | None, urgency: str | None) -> SafetyResult:
    """Audio/vision says critical AND the operator says it is urgent."""
    if sensor_level == "critical" and urgency == "high":
        return SafetyResult(True, "inspect", ["critical sensor level + high urgency"], INSPECT_HEADER)
    return SafetyResult()


def merge(first: SafetyResult, second: SafetyResult) -> SafetyResult:
    """Combine two results; "stop" is stronger than "inspect"."""
    if not first.triggered:
        return second
    if not second.triggered:
        return first
    strongest = first if first.kind == "stop" or second.kind != "stop" else second
    return SafetyResult(True, strongest.kind, first.matched + second.matched, strongest.header)
