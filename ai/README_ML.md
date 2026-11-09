# Fibo ML results

Every numeric result below is rendered from `reports/metrics.json` by `scripts/write_readme_ml.py`. These are development measurements, not workshop guarantees.

## Risk model
Dataset: AI4I 2020 Predictive Maintenance (UCI id 601); rows=10000; failures=339; synthetic=True.
Selected model: LightGBM; calibration: isotonic.

| Metric | Measured value |
|---|---:|
| Held-out ROC-AUC | 0.9748 |
| Held-out PR-AUC | 0.8653 |
| Brier, raw → calibrated | 0.0079 → 0.00772 |
| ECE, raw → calibrated | 0.0084 → 0.0069 |

Cross-validation PR-AUC comparison:

| Model | Mean ± standard deviation |
|---|---:|
| LightGBM | 0.8626 ± 0.0453 |
| XGBoost | 0.8008 ± 0.0540 |
| LogisticRegression | 0.4287 ± 0.0431 |

SHAP: TreeExplainer; rows explained=1500; figure=`reports/figures/shap_summary.png`.

## Machine audio
Dataset: DCASE 2020 Task 2 Development Dataset, fan; MIMII-derived real recordings; machine type=fan; SNR=not separately labeled; official mixed factory-noise development subset.
Protocol: same machine ID; 3 train-normal reference clips per baseline; 20 random draws; 25% test normals held out for threshold calibration; remaining test normals vs test anomalies.

| Embedder | ROC-AUC mean ± standard deviation |
|---|---:|
| mfcc_baseline | 0.5484 ± 0.0706 |
| panns_cnn14 | 0.5271 ± 0.1071 |
| ast | 0.6172 ± 0.2479 |

Selected embedder: mfcc_baseline (mean aggregation).
Validation thresholds, in sigma units: attention=6.094; critical=16.092.
Measured validation false-alarm rates: attention=10.0%; critical=2.0%.

## Local endpoint latency

Endpoint latency: NOT_VALIDATED.

## PatchCore

Status: NOT_VALIDATED. Reason: MVTec AD category not found at artifacts/data/mvtec_ad/metal_nut; official download requires form access.

## Not validated

- AI4I is synthetic and rule-generated; its held-out metrics do not establish workshop performance.
- MVTec AD is licensed CC BY-NC-SA 4.0 and disallows commercial use. It is not redistributed by this repository.
- Phone audio has domain shift from the DCASE microphones; no workshop phone recordings are included in the measurements.
- Photo quality thresholds and visual interpretations have not been validated on workshop CNC panels or tools.
- Live ASR, provider-backed LLM calls, and real-manual citations need workshop recordings, a configured key, and source manuals.
- Cost is NOT_VALIDATED until current provider tariffs and actual usage records are supplied.
- Local in-process endpoint timings are not production VPS or concurrent-load measurements.
