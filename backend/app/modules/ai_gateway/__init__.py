"""AI gateway: the backend's only door to the Fibo AI service (sidecar), with an automatic fallback.

Why a sidecar: the AI service owns the heavier models (LightGBM risk model, faster-whisper ASR,
GPT-6 Luna card and vision stages, its own manual index). Why a fallback: the demo must survive the AI
container being down, slow or answering something unexpected. Every call therefore runs:

    FIBO_AI_PROVIDER=builtin  -> the backend's own modules only (default; tests; no AI container)
    FIBO_AI_PROVIDER=sidecar  -> AI service first; on unavailability / contract mismatch / bug the builtin
                                 module answers instead and `degraded` says why; an input error
                                 (blurry photo, too-short audio, ...) becomes an explanatory card

Files: client.py (copy of ai/fibo_ai_client.py), ids.py, paths.py (id and path mapping), errors.py
(classify AI errors), adapters.py (AI JSON -> backend types), messages.py (input-error card texts),
provider.py (the fallback rule), status.py (health probe).
"""
