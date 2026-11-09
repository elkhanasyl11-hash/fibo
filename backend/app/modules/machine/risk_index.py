"""Fibo Machine: combine all available signals into one risk index between 0 and 1.

Signals (each 0..1, or None when unavailable):
  p_model    calibrated failure probability from the AI4I model
  s_audio    clip((audio_z - 1) / 3, 0, 1)            latest machine-sound check within 7 days
  s_visual   normal 0 / warning 0.5 / critical 1       latest photo check within 7 days
  s_overdue  clip(hours_since_maintenance / interval - 1, 0, 1)   0 until the interval is reached,
             1 when twice the interval has passed
  s_history  clip(problem incidents / 3, 0, 1)         warning/critical incidents of the last 30 days
             plus older ones still unresolved

risk_index = sum(w_i * s_i) / sum(w_i), over signals that are available AND have weight > 0.
Weights come from the workshop's profile YAML. A missing signal does not count as "0 risk": it is
left out, and the remaining weights are renormalised. inputs_used lists what was included.
"""

from dataclasses import asdict, dataclass

from app.profiles.loader import RiskWeights

VISUAL_LEVEL_SCORE = {"normal": 0.0, "warning": 0.5, "critical": 1.0}
SIGNAL_TITLES_RU = {
    "p_model": "Вероятность отказа (модель)",
    "s_audio": "Звук станка",
    "s_visual": "Фото инструмента/детали",
    "s_overdue": "Просрочка ТО",
    "s_history": "Недавние инциденты",
}


def clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def audio_signal(audio_z: float | None) -> float | None:
    return None if audio_z is None else clip01((audio_z - 1) / 3)


def visual_signal(level: str | None) -> float | None:
    return None if level is None else VISUAL_LEVEL_SCORE[level]


def overdue_signal(hours_since_maintenance: float | None, interval_hours: float | None) -> float | None:
    if hours_since_maintenance is None or not interval_hours:
        return None
    return clip01(hours_since_maintenance / interval_hours - 1)


def history_signal(problem_incidents: int) -> float:
    return clip01(problem_incidents / 3)


@dataclass
class Signals:
    p_model: float | None = None
    s_audio: float | None = None
    s_visual: float | None = None
    s_overdue: float | None = None
    s_history: float | None = None


def combine(signals: Signals, weights: RiskWeights) -> tuple[float, list[str]]:
    """Weighted average over the available signals. Returns (risk_index, inputs_used)."""
    total, weight_sum, used = 0.0, 0.0, []
    weight_by_name = weights.model_dump()
    for name, value in asdict(signals).items():
        weight = weight_by_name[name]
        if value is None or weight <= 0:
            continue
        total += weight * value
        weight_sum += weight
        used.append(name)
    if weight_sum == 0:
        return 0.0, []
    return round(clip01(total / weight_sum), 4), used


def signal_entries(signals: Signals, weights: RiskWeights) -> list[dict]:
    """Per-signal values for the dashboard ("why is the index this high?")."""
    weight_by_name = weights.model_dump()
    return [
        {
            "name": name,
            "title_ru": SIGNAL_TITLES_RU[name],
            "value": None if value is None else round(value, 4),
            "weight": weight_by_name[name],
        }
        for name, value in asdict(signals).items()
    ]
