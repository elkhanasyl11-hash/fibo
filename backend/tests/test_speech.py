"""Audio preparation without ffmpeg (libsndfile path) and voice activity detection."""

import pytest
import soundfile as sf

from app.core.config import settings
from app.core.errors import UnsupportedMediaError
from app.modules.assistant import speech
from tests.audio_samples import ogg_opus_bytes, silence_wav, tone, wav_bytes


@pytest.fixture(autouse=True)
def no_ffmpeg(monkeypatch, started_app):
    monkeypatch.setattr(settings, "ffmpeg_binary", "no-such-ffmpeg-binary")


async def test_stereo_44k_wav_becomes_16k_mono(tmp_path):
    src = tmp_path / "in.wav"
    src.write_bytes(wav_bytes(tone(seconds=1.0, rate=44100, channels=2), rate=44100))
    out = await speech.prepare_wav(src)
    info = sf.info(out)
    assert (info.samplerate, info.channels, info.subtype) == (16000, 1, "PCM_16")
    assert abs(info.duration - 1.0) < 0.01
    out.unlink()


async def test_telegram_style_ogg_opus_is_decoded(tmp_path):
    src = tmp_path / "voice.ogg"
    src.write_bytes(ogg_opus_bytes(tone(seconds=1.0, rate=48000), rate=48000))
    out = await speech.prepare_wav(src)
    assert sf.info(out).samplerate == 16000
    out.unlink()


async def test_garbage_is_rejected(tmp_path):
    src = tmp_path / "x.ogg"
    src.write_bytes(b"OggS" + b"\x00" * 50)
    with pytest.raises(UnsupportedMediaError):
        await speech.prepare_wav(src)


def test_silence_has_no_speech(tmp_path):
    path = tmp_path / "silence.wav"
    path.write_bytes(silence_wav())
    assert speech.has_speech(path) is False
