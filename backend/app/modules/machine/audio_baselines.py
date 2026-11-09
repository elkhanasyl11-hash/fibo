"""Fibo Machine: audio baselines in the database, and scoring a new machine sound against them.

Storage (table `baselines`, kind=audio), one row per uploaded reference recording:
  file_path  the stored recording
  embedding  that recording's window features (19 x 14 numbers), so the combined statistics can
             be recomputed later without decoding the audio again
  stats      combined mean/std over ALL audio baselines of the machine at the time this row was
             added -> the newest row always holds the current statistics
At least 3 recordings are recommended (different moments of normal operation); scoring works from
the first one but reports how many recordings the baseline has.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import DomainValidationError
from app.db.base import BaselineKind
from app.models.attachment import Attachment
from app.models.baseline import Baseline
from app.modules.assistant.speech import prepare_wav
from app.modules.machine import audio
from app.storage.files import resolve_media_path, save_generated

RECOMMENDED_RECORDINGS = 3


@dataclass
class AudioResult:
    baseline_missing: bool
    audio_z: float | None = None
    level: str | None = None  # normal | warning | critical
    description: str | None = None  # e.g. "энергия в полосе 4–8 кГц +3.4σ"
    n_recordings: int = 0
    z_by_feature: dict | None = None
    spectrogram_path: str | None = None


def _load_clip(wav_path: Path) -> np.ndarray:
    signal, _rate = sf.read(wav_path, dtype="float32")  # prepare_wav guarantees 16 kHz mono
    try:
        return audio.fit_length(signal)
    except audio.RecordingTooShortError as exc:
        raise DomainValidationError(f"Recording is too short: at least {audio.MIN_SECONDS} s needed") from exc


def _features(wav_path: Path) -> tuple[np.ndarray, np.ndarray]:
    clip = _load_clip(wav_path)
    return clip, audio.window_features(clip)


async def audio_baselines(session: AsyncSession, machine_id: int) -> list[Baseline]:
    stmt = (
        select(Baseline)
        .where(Baseline.machine_id == machine_id, Baseline.kind == BaselineKind.AUDIO)
        .order_by(Baseline.created_at, Baseline.id)
    )
    return list((await session.scalars(stmt)).all())


async def add_audio_baseline(
    session: AsyncSession, machine_id: int, stored_path: str, wav_path: Path
) -> Baseline:
    """Store one reference recording and recompute the machine's combined statistics."""
    _clip, windows = await asyncio.to_thread(_features, wav_path)
    previous = [np.array(b.embedding) for b in await audio_baselines(session, machine_id) if b.embedding]
    stats = audio.baseline_stats([*previous, windows])
    baseline = Baseline(
        machine_id=machine_id,
        kind=BaselineKind.AUDIO,
        file_path=stored_path,
        embedding=windows.round(6).tolist(),
        stats=stats,
    )
    session.add(baseline)
    await session.commit()
    await session.refresh(baseline)
    return baseline


def _score_and_draw(wav_path: Path, stats: dict, reference_path: Path) -> tuple[audio.AudioScore, bytes]:
    clip, windows = _features(wav_path)
    result = audio.score(windows, stats, settings.audio_z_warning, settings.audio_z_critical)
    reference = audio.fit_length(sf.read(reference_path, dtype="float32", always_2d=True)[0].mean(axis=1))
    return result, audio.spectrogram_png(reference, clip)


async def analyze(
    session: AsyncSession, machine_id: int, wav_path: Path, incident_id: int | None = None
) -> AudioResult:
    """Score a 16 kHz WAV against the machine's baseline; attach a spectrogram to the incident."""
    baselines = await audio_baselines(session, machine_id)
    if not baselines:
        return AudioResult(baseline_missing=True)
    latest = baselines[-1]
    reference = await _reference_wav(baselines[0])
    try:
        result, png = await asyncio.to_thread(_score_and_draw, wav_path, latest.stats, reference)
    finally:
        reference.unlink(missing_ok=True)
    spectrogram = save_generated(png, kind="spectrogram", ext="png")
    if incident_id is not None:
        session.add(Attachment(incident_id=incident_id, kind="spectrogram", file_path=spectrogram))
    return AudioResult(
        False,
        result.audio_z,
        result.level,
        result.description,
        latest.stats["n_recordings"],
        result.z_by_feature,
        spectrogram,
    )


async def _reference_wav(baseline: Baseline) -> Path:
    """The first baseline recording as 16 kHz WAV (for the left half of the spectrogram)."""
    return await prepare_wav(resolve_media_path(baseline.file_path))
