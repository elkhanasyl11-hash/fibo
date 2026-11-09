"""ml/eval_audio_mimii.py on a tiny synthetic dataset with the DCASE folder layout."""

from ml.eval_audio_mimii import evaluate
from tests.audio_samples import machine_sound, wav_bytes


def test_evaluation_reports_auc_per_machine(tmp_path):
    (tmp_path / "train").mkdir()
    (tmp_path / "test").mkdir()
    for i in range(4):
        (tmp_path / "train" / f"normal_id_00_{i:08d}.wav").write_bytes(wav_bytes(machine_sound(i)))
    for i in range(4):
        (tmp_path / "test" / f"normal_id_00_{i:08d}.wav").write_bytes(wav_bytes(machine_sound(100 + i)))
        anomaly = ("noise", "tone", "knock", "noise")[i]
        (tmp_path / "test" / f"anomaly_id_00_{i:08d}.wav").write_bytes(
            wav_bytes(machine_sound(200 + i, anomaly=anomaly))
        )
    (tmp_path / "test" / "README.txt").write_text("ignored")

    metrics = evaluate(tmp_path, max_train=None)
    result = metrics["machines"]["id_00"]
    assert result["train_clips"] == 4 and result["test_normal"] == 4 and result["test_anomaly"] == 4
    assert result["roc_auc"] == 1.0 and metrics["mean_roc_auc"] == 1.0
    assert result["normal_below_warning"] == 1.0
