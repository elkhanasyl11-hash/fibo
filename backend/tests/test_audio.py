"""Audio method (spec acceptance): same recording vs. its baseline < 2; a modified one scores higher."""

import numpy as np
import pytest

from app.modules.machine import audio
from tests.audio_samples import machine_sound


def features(signal: np.ndarray) -> np.ndarray:
    return audio.window_features(audio.fit_length(signal))


@pytest.fixture(scope="module")
def stats() -> dict:
    return audio.baseline_stats([features(machine_sound(seed)) for seed in (1, 2, 3)])


def test_nineteen_windows_of_fourteen_features():
    assert features(machine_sound(1)).shape == (19, 14)
    assert len(audio.FEATURES) == 14


def test_length_rules():
    assert len(audio.fit_length(np.zeros(16000 * 15))) == 160000  # cut
    looped = audio.fit_length(np.arange(16000 * 4, dtype=float))  # loop a 4 s recording
    assert len(looped) == 160000 and looped[16000 * 4] == 0
    with pytest.raises(audio.RecordingTooShortError):
        audio.fit_length(np.zeros(16000))


def test_std_floor(stats):
    flat = audio.baseline_stats([np.ones((19, 14)) * 50])
    assert flat["std"][0] == pytest.approx(2.5)  # 5% of |mean| when there is no variation
    assert stats["n_recordings"] == 3 and stats["n_windows"] == 57


def test_same_recording_scores_below_two(stats):
    result = audio.score(features(machine_sound(1)), stats)
    assert result.audio_z < 2 and result.level == "normal"
    assert audio.score(features(machine_sound(42)), stats).audio_z < 2  # a new healthy clip too


@pytest.mark.parametrize("anomaly", ["noise", "tone", "knock"])
def test_modified_recording_scores_higher(stats, anomaly):
    healthy = audio.score(features(machine_sound(42)), stats)
    broken = audio.score(features(machine_sound(42, anomaly=anomaly)), stats)
    assert broken.audio_z > healthy.audio_z + 1
    assert broken.description != "звук близок к эталону"


def test_added_noise_is_critical_and_explained(stats):
    result = audio.score(features(machine_sound(42, anomaly="noise")), stats)
    assert result.level == "critical"
    assert "шумность спектра" in result.description and "σ" in result.description


def test_levels():
    assert audio.level_for(1.99, 2, 3) == "normal"
    assert audio.level_for(2.0, 2, 3) == "warning" and audio.level_for(3.0, 2, 3) == "warning"
    assert audio.level_for(3.01, 2, 3) == "critical"


def test_spectrogram_png():
    png = audio.spectrogram_png(machine_sound(1), machine_sound(2, anomaly="tone"))
    assert png.startswith(b"\x89PNG") and len(png) > 10_000
