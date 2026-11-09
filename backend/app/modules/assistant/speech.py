"""Fibo Assistant: audio preparation, speech detection and transcription.

prepare_wav: any uploaded recording -> 16 kHz mono 16-bit WAV (what VAD, Whisper and the audio
  features expect). Main path: ffmpeg, started with create_subprocess_exec (no shell, so a file
  name can never become a command). If ffmpeg is not installed (some dev laptops), libsndfile
  decodes OGG/Opus, WAV and MP3 and scipy resamples; m4a then needs ffmpeg.
has_speech: webrtcvad (Google's WebRTC voice activity detector) on 30 ms frames. A recording
  counts as speech if at least 0.3 s and 10% of the frames are voiced. Machine-sound recordings
  normally fail this test, which sends them to the audio branch of the pipeline.
transcribe: through the LLM client (Whisper-compatible API, or the mock). With
  FIBO_SPEECH_BACKEND=local and live mode, faster-whisper runs on this machine instead.
"""

import asyncio
import logging
import shutil
import uuid
from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf
import webrtcvad
from scipy.signal import resample_poly

from app.core.config import settings
from app.core.errors import ModelUnavailableError, UnsupportedMediaError
from app.modules.assistant.llm import LLMClient

logger = logging.getLogger("fibo.assistant.speech")

SAMPLE_RATE = 16000
FFMPEG_TIMEOUT_S = 60
VAD_FRAME_MS = 30
VAD_AGGRESSIVENESS = 2  # 0 (lenient) .. 3 (strict)
MIN_SPEECH_SECONDS = 0.3
MIN_SPEECH_SHARE = 0.10
# Peak below this (of full scale) = an empty recording: Telegram Desktop without microphone access,
# a muted phone. Such files decode to (near) digital silence; real speech/machines peak far above.
SILENCE_PEAK = 0.002


def work_dir() -> Path:
    path = settings.data_dir / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def _convert_with_ffmpeg(ffmpeg: str, src: Path, dst: Path) -> None:
    process = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-nostdin",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-sample_fmt",
        "s16",
        str(dst),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=FFMPEG_TIMEOUT_S)
    except TimeoutError:
        process.kill()
        raise UnsupportedMediaError("Audio conversion timed out") from None
    if process.returncode != 0:
        raise UnsupportedMediaError(
            "Audio file cannot be decoded", details={"ffmpeg": stderr.decode()[-300:]}
        )


def _convert_with_libsndfile(src: Path, dst: Path) -> None:
    try:
        data, rate = sf.read(src, dtype="float32", always_2d=True)
    except (sf.LibsndfileError, RuntimeError) as exc:
        raise UnsupportedMediaError("Audio file cannot be decoded without ffmpeg") from exc
    mono = data.mean(axis=1)
    if rate != SAMPLE_RATE:
        divisor = gcd(SAMPLE_RATE, rate)
        mono = resample_poly(mono, SAMPLE_RATE // divisor, rate // divisor)
    sf.write(dst, np.clip(mono, -1, 1), SAMPLE_RATE, subtype="PCM_16")


async def prepare_wav(src: Path) -> Path:
    """Convert to a temporary 16 kHz mono WAV. The caller deletes it when done."""
    dst = work_dir() / f"{uuid.uuid4().hex}.wav"
    ffmpeg = shutil.which(settings.ffmpeg_binary)
    if ffmpeg:
        await _convert_with_ffmpeg(ffmpeg, src, dst)
    else:
        logger.warning("ffmpeg not found, decoding with libsndfile")
        await asyncio.to_thread(_convert_with_libsndfile, src, dst)
    return dst


def is_silent(wav_path: Path) -> bool:
    """True if the 16 kHz mono WAV is (near) digital silence. CPU work: call via to_thread."""
    samples = sf.read(wav_path, dtype="float32")[0]
    return samples.size == 0 or float(np.abs(samples).max()) < SILENCE_PEAK


def has_speech(wav_path: Path) -> bool:
    """True if the 16 kHz mono WAV contains enough voiced frames. CPU work: call via to_thread."""
    pcm = sf.read(wav_path, dtype="int16")[0].tobytes()
    vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
    frame_bytes = SAMPLE_RATE * VAD_FRAME_MS // 1000 * 2  # 2 bytes per 16-bit sample
    frames = [pcm[i : i + frame_bytes] for i in range(0, len(pcm) - frame_bytes + 1, frame_bytes)]
    if not frames:
        return False
    voiced = sum(1 for frame in frames if vad.is_speech(frame, SAMPLE_RATE))
    return voiced * VAD_FRAME_MS / 1000 >= MIN_SPEECH_SECONDS and voiced / len(frames) >= MIN_SPEECH_SHARE


def _transcribe_local(wav_path: Path, language: str | None) -> str:
    try:
        from faster_whisper import WhisperModel  # optional dependency, only for speech_backend=local
    except ImportError as exc:
        raise ModelUnavailableError("faster-whisper is not installed (FIBO_SPEECH_BACKEND=local)") from exc
    segments, _info = WhisperModel(settings.whisper_model).transcribe(str(wav_path), language=language)
    return " ".join(segment.text.strip() for segment in segments)


async def transcribe(client: LLMClient, wav_path: Path, language: str | None) -> str:
    if settings.ai_mode == "live" and settings.speech_backend == "local":
        return await asyncio.to_thread(_transcribe_local, wav_path, language)
    return await client.transcribe(wav_path, language)
