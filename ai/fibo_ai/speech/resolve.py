"""Conservative spoken machine-name resolution."""

import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process

NUMBER_WORDS = {
    "одна": "1",
    "первый": "1",
    "первого": "1",
    "одинін": "1",
    "бір": "1",
    "бірінші": "1",
    "один": "1",
    "два": "2",
    "две": "2",
    "второй": "2",
    "второго": "2",
    "екі": "2",
    "екінші": "2",
    "три": "3",
    "третий": "3",
    "үш": "3",
    "үшінші": "3",
    "четыре": "4",
    "четвертый": "4",
    "төрт": "4",
    "төртінші": "4",
    "пять": "5",
    "пятый": "5",
    "бес": "5",
    "бесінші": "5",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
}


@dataclass(frozen=True)
class MachineResolution:
    machine_id: str | None
    candidates: list[str]
    needs_clarification: bool


def normalize_machine_text(text: str) -> str:
    folded = text.casefold().replace("ё", "е")
    tokens = re.findall(r"[\w-]+", folded, flags=re.UNICODE)
    normalized = [NUMBER_WORDS.get(token, token) for token in tokens]
    return "".join(re.sub(r"[^\w]", "", token) for token in normalized)


def resolve_machine(
    text: str,
    catalog_machines: list[str],
    preferred_machine: str | None = None,
) -> MachineResolution:
    catalog = list(dict.fromkeys(name.strip() for name in catalog_machines if name.strip()))
    if preferred_machine:
        exact = next(
            (name for name in catalog if normalize_machine_text(name) == normalize_machine_text(preferred_machine)),
            None,
        )
        if exact:
            return MachineResolution(exact, [exact], False)
    if not catalog:
        return MachineResolution(None, [], True)

    query = normalize_machine_text(text)
    normalized_catalog = {name: normalize_machine_text(name) for name in catalog}
    if re.search(r"(?:1|2|3|4|5)\s*(?:или|немесе|or)\s*(?:1|2|3|4|5)", text.casefold()):
        numbers = set(re.findall(r"\d", text))
        choices = [
            name for name, value in normalized_catalog.items() if any(value.endswith(number) for number in numbers)
        ]
        if len(choices) > 1:
            return MachineResolution(None, choices[:3], True)
    exact_matches = [name for name, value in normalized_catalog.items() if value and value in query]
    if len(exact_matches) == 1:
        return MachineResolution(exact_matches[0], exact_matches, False)
    if len(exact_matches) > 1:
        return MachineResolution(None, exact_matches[:3], True)

    scored = process.extract(
        query,
        normalized_catalog,
        scorer=fuzz.ratio,
        limit=min(3, len(catalog)),
    )
    ranked = [(catalog_name, float(score)) for _, score, catalog_name in scored]
    candidates = [name for name, score in ranked if score >= 45.0]
    if ranked and ranked[0][1] >= 82.0 and (len(ranked) == 1 or ranked[0][1] - ranked[1][1] >= 8.0):
        return MachineResolution(ranked[0][0], [ranked[0][0]], False)
    return MachineResolution(None, candidates, True)
