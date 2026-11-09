"""Evaluate Fibo's audio z-score method on MIMII / DCASE 2020 Task 2 data.

Usage (from backend/):
    python -m ml.eval_audio_mimii --data path/to/slider [--max-train 300]
        [--out ml/artifacts/audio_metrics.json]

Expected layout (DCASE 2020 Task 2 development set):
    <data>/train/normal_id_00_00000000.wav ...        normal clips only (-> baseline)
    <data>/test/normal_id_00_00000000.wav ...         normal test clips  (label 0)
    <data>/test/anomaly_id_00_00000000.wav ...        anomalous test clips (label 1)

For every machine id: baseline = statistics of its normal training clips, exactly as the app builds
them from reference recordings (app/modules/machine/audio.py); every test clip gets an audio_z.
Reported per machine id:
  roc_auc              how well audio_z separates anomalous from normal clips (0.5 = chance)
  normal_below_warning share of normal test clips with z < warning threshold (no false alarm)
  anomaly_at_warning   share of anomalous clips with z >= warning threshold (caught)
  normal_z_p95/p99     95th/99th percentile of z on normal clips: data for choosing thresholds
  roc_auc_max_abs_z    diagnostic: AUC if we used the largest single-feature |z| instead
The dataset is not committed (licence CC BY-NC-SA 4.0, ~1 GB per machine type).
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from sklearn.metrics import roc_auc_score

from app.modules.machine import audio

FILE_PATTERN = re.compile(r"^(normal|anomaly)_(id_\d+)_\d+\.wav$")


def load_clip(path: Path) -> np.ndarray:
    signal, rate = sf.read(path, dtype="float32", always_2d=True)
    mono = signal.mean(axis=1)
    if rate != audio.SAMPLE_RATE:
        mono = resample_poly(mono, audio.SAMPLE_RATE, rate)
    return audio.fit_length(mono)


def group_files(folder: Path) -> dict[str, list[tuple[Path, int]]]:
    """machine id -> [(file, label)] with label 1 for anomalies."""
    groups: dict[str, list[tuple[Path, int]]] = defaultdict(list)
    for path in sorted(folder.glob("*.wav")):
        match = FILE_PATTERN.match(path.name)
        if match:
            groups[match.group(2)].append((path, int(match.group(1) == "anomaly")))
    return groups


def evaluate_machine(
    train: list[Path], test: list[tuple[Path, int]], warning: float, critical: float
) -> dict:
    stats = audio.baseline_stats([audio.window_features(load_clip(p)) for p in train])
    scores, max_abs, labels = [], [], []
    for path, label in test:
        result = audio.score(audio.window_features(load_clip(path)), stats, warning, critical)
        scores.append(result.audio_z)
        max_abs.append(max(abs(z) for z in result.z_by_feature.values()))
        labels.append(label)
    scores, labels = np.array(scores), np.array(labels)
    normal, anomaly = scores[labels == 0], scores[labels == 1]
    return {
        "train_clips": len(train),
        "test_normal": int(len(normal)),
        "test_anomaly": int(len(anomaly)),
        "roc_auc": round(float(roc_auc_score(labels, scores)), 4),
        "normal_below_warning": round(float((normal < warning).mean()), 4),
        "anomaly_at_warning": round(float((anomaly >= warning).mean()), 4),
        "anomaly_above_critical": round(float((anomaly > critical).mean()), 4),
        "normal_z_median": round(float(np.median(normal)), 3),
        "anomaly_z_median": round(float(np.median(anomaly)), 3),
        "normal_z_p95": round(float(np.percentile(normal, 95)), 3),
        "normal_z_p99": round(float(np.percentile(normal, 99)), 3),
        "roc_auc_max_abs_z": round(float(roc_auc_score(labels, max_abs)), 4),
    }


def evaluate(data: Path, max_train: int | None, warning: float = 2.0, critical: float = 3.0) -> dict:
    train_groups, test_groups = group_files(data / "train"), group_files(data / "test")
    machines = {}
    for machine_id in sorted(test_groups):
        train = [p for p, label in train_groups.get(machine_id, []) if label == 0][:max_train]
        if not train:
            continue
        machines[machine_id] = evaluate_machine(train, test_groups[machine_id], warning, critical)
        print(f"{machine_id}: ROC-AUC {machines[machine_id]['roc_auc']}", flush=True)
    if not machines:
        raise SystemExit(f"no matching train/test clips under {data}")
    return {
        "dataset": data.name,
        "method": "per-feature z-score vs. baseline, audio_z = sqrt(mean(z^2))",
        "features": audio.FEATURES,
        "thresholds": {"warning": warning, "critical": critical},
        "max_train_clips_per_id": max_train,
        "machines": machines,
        "mean_roc_auc": round(float(np.mean([m["roc_auc"] for m in machines.values()])), 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the audio z-score method on MIMII/DCASE data.")
    parser.add_argument("--data", type=Path, required=True, help="machine-type folder with train/ and test/")
    parser.add_argument("--max-train", type=int, default=None, help="limit baseline clips per machine id")
    parser.add_argument("--out", type=Path, default=Path("ml/artifacts/audio_metrics.json"))
    args = parser.parse_args()
    metrics = evaluate(args.data, args.max_train)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"mean ROC-AUC {metrics['mean_roc_auc']} -> {args.out}")


if __name__ == "__main__":
    main()
