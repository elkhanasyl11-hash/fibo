"""Backend-side state of the AI service's artifacts: audio baseline artifacts (D78).

The AI service builds a BaselineArtifact from >= 3 reference recordings and the backend keeps it, unchanged,
in the newest audio baseline's stats["ai_artifact"]; incidents send it back as baseline_ref. The backend's
own statistics in the same stats dict stay untouched, so the builtin fallback keeps working.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.baseline import Baseline
from app.modules.ai_gateway import provider
from app.modules.ai_gateway.errors import AIRequestRejected
from app.modules.ai_gateway.ids import m_id
from app.modules.ai_gateway.paths import shared_path
from app.modules.machine.audio_baselines import audio_baselines

log = logging.getLogger("fibo.ai_gateway")

MIN_RECORDINGS = 3  # the AI service refuses fewer (AI_INTEGRATION.md §3.2)


def latest_artifact(baselines: list[Baseline]) -> dict | None:
    for baseline in reversed(baselines):
        if (baseline.stats or {}).get("ai_artifact"):
            return baseline.stats["ai_artifact"]
    return None


def store_artifact(baselines: list[Baseline], artifact: dict) -> None:
    newest = baselines[-1]
    newest.stats = {**(newest.stats or {}), "ai_artifact": artifact}  # new dict: JSON change is detected


async def _no_artifact() -> None:
    return None


async def sync_audio_baseline(session: AsyncSession, machine_id: int) -> dict | None:
    """Ask the AI service for a baseline artifact once the machine has enough recordings.
    Never raises for AI problems: without an artifact incidents simply use the builtin audio analysis."""
    if not provider.sidecar_enabled():
        return None
    baselines = await audio_baselines(session, machine_id)
    if len(baselines) < MIN_RECORDINGS:
        return None
    paths = [shared_path(b.file_path) for b in baselines]
    try:
        outcome = await provider.build_audio_baseline(m_id(machine_id), paths, _no_artifact)
    except AIRequestRejected as exc:  # e.g. a recording the AI service cannot read: keep the builtin baseline
        log.warning("AI service rejected the baseline of machine %s: %s", machine_id, exc)
        return None
    if outcome.source != "ai" or outcome.value is None:
        log.info("no AI baseline artifact for machine %s (%s)", machine_id, outcome.degraded)
        return None
    store_artifact(baselines, outcome.value)
    await session.commit()
    return outcome.value
