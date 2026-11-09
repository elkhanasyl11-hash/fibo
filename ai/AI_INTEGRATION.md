# Fibo AI / ML Integration Guide (for Backend & Bot Teammates)

Welcome to the Fibo AI integration guide. The AI service runs as an HTTP sidecar (`http://ai:8001` inside Docker Compose) or as an in-process Python module (`fibo_ai.FiboAI`). It is **not stateless**: it stores acoustic baseline artifacts, the manual vector index and manual indexing statuses on its own volume (`/data/ai` in Compose, `./data/ai` on the host). The backend remains the source of truth for workshops, machines, incidents, baselines and manuals.

---

## 1. Quick Start

### Option A: Run the Stub Server (Phase 0)
```bash
make stub
# Uvicorn running on http://0.0.0.0:8001 (reloading on code changes)
```

### Option B: Copy the Typed Python Client
Copy `fibo_ai_client.py` into your backend repository:
```python
from fibo_ai_client import FiboAIClient

async with FiboAIClient("http://localhost:8001") as ai:
    res = await ai.analyze_incident(
        workshop_id="ws-shymkent-01",
        machine_id="ЧПУ-2",
        text="Шпиндель сильно греется и появился запах гари",
    )
    # Send ready-rendered HTML card directly to Telegram bot
    print(res["card"]["card_text"])
```

### Backend and Telegram bot connection

The Telegram bot should send the voice/photo/text to the **backend**. The backend stores the
incident and its attachments, writes media under the shared volume, then calls the AI sidecar
over the private service network. In Docker Compose the base URL is `http://ai:8001`; when
both processes run directly on one host use `http://127.0.0.1:8001`. Do not use `localhost`
from one container to address another container.

Mount the same shared directory into the backend and AI container at the same path — in Fibo's
Compose file `./data/media:/app/data/media` (`FIBO_SHARED_DIR=/app/data/media`). Send those paths in `panel_photo_path`, `audio_file_path`, and `voice_file_path`.
Keep the AI port off the public internet. If `AI_SERVICE_TOKEN` is configured, pass it to
`FiboAIClient(base_url, token=...)`; the client sends `Authorization: Bearer <token>` on every
request. The token is optional for local development and required when set in the service.

The bot renders `response["card"]["card_text"]` and turns `suggested_buttons` into Telegram
callback buttons. The backend persists the response and owns button actions such as assigning
preventive maintenance; the AI service does not write to the workshop database.

The dashboard assistant is a special case: it uses the read-only `DataRepository` Protocol.
For the in-process integration, construct `FiboAI(settings, repo=backend_repository)`. A standalone
HTTP sidecar without that injected Python repository returns `MODEL_NOT_READY` for dashboard
queries; the backend must either host FiboAI in-process or implement a separately scoped read-only
data adapter before using that endpoint.

### OpenAI API configuration

OpenAI is configured on the AI service, not in the Telegram bot or frontend. The repo already
contains an OpenAI-compatible structured text and vision client. To enable it, put the following
in the ignored repo-root `.env` file for local Docker Compose use, or inject them through the
deployment secret manager:

```dotenv
AI_STUB_MODE=false
LLM_PROVIDER=openai
LLM_MODEL=gpt-6-luna
LLM_VISION_MODEL=gpt-6-luna
OPENAI_API_KEY=<secret>
```

Do not commit the key. The ChatGPT subscription and API Platform usage are billed separately.
The bot continues to call `POST /v1/incident/analyze`; Fibo calls the configured model only for
schema-validated language/vision stages, after deterministic photo quality and safety gates.
Live API requests are not part of offline verification.

OpenAI Docs: [GPT-6 Luna model/API support](https://developers.openai.com/api/docs/models/gpt-6-luna),
[API key quickstart](https://developers.openai.com/api/docs/quickstart), and
[ChatGPT/API billing separation](https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform).

---

## 2. Endpoint Table

| Method | Endpoint | Description | Target p95 (not measured) |
|---|---|---|---|
| `GET` | `/healthz` | Process liveness probe | < 5 ms |
| `GET` | `/readyz` | Readiness probe (models loaded) | < 10 ms |
| `GET` | `/v1/meta/models` | Active model versions & evaluation metrics | < 50 ms |
| `POST` | `/v1/risk/predict` | Failure probability + SHAP factors + KZT ranking | < 150 ms |
| `POST` | `/v1/risk/rank` | Sorted priority ranking for N machines | < 250 ms |
| `POST` | `/v1/risk/what-if` | Simulated maintenance actions & savings in KZT | < 100 ms |
| `POST` | `/v1/anomaly/readings` | Multi-variate Isolation Forest sensor drift | < 80 ms |
| `POST` | `/v1/audio/route` | VAD routing (voice note vs machine sound) | < 500 ms |
| `POST` | `/v1/audio/baseline` | Register acoustic baseline from 3 reference clips | < 2.0 s |
| `POST` | `/v1/audio/analyze` | Anomaly z-score + PSD descriptors + spectrogram | < 4.0 s |
| `POST` | `/v1/speech/transcribe` | Faster-Whisper ASR with hallucination guards | < 6.0 s |
| `POST` | `/v1/speech/parse` | Extract symptom, category, conditions, safety | < 1.5 s |
| `POST` | `/v1/vision/quality` | Laplacian blur & exposure quality gate | < 100 ms |
| `POST` | `/v1/vision/panel` | CNC panel reading + OCR cross-verification | < 8.0 s |
| `POST` | `/v1/vision/tool-compare` | Compare tool photo with reference (3 levels) | < 8.0 s |
| `POST` | `/v1/vision/part-defect` | PatchCore anomaly heatmap on finished parts — **not validated, not in demo** | < 3.0 s |
| `POST` | `/v1/manuals/index` | Ingest PDF machine manual into vector store | Async / < 15 s |
| `GET` | `/v1/manuals/{id}/status` | Check manual indexing status | < 10 ms |
| `POST` | `/v1/manuals/query` | Retrieve cited fragments with page numbers | < 300 ms |
| `POST` | `/v1/incident/analyze` | **The Main Flow**: End-to-end multimodal incident card | < 12.0 s |
| `POST` | `/v1/assistant/operator` | Grounded chat with machine manual for operator | < 2.5 s |
| `POST` | `/v1/assistant/dashboard` | Verified natural-language analytics for owner | < 3.5 s |

---

## 3. Key Request & Response Formats

### 3.1 Main Incident Analysis (`POST /v1/incident/analyze`)
This is the single primary endpoint the Telegram bot calls when an operator sends an audio, photo, or text message.

#### curl Example:
```bash
curl -X POST "http://localhost:8001/v1/incident/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "workshop_id": "ws-shymkent-01",
    "machine_id": "ЧПУ-2",
    "profile": "metalworking",
    "lang": "ru",
    "text": "Появился запах гари и странный высокочастотный звук в шпинделе",
    "context": {
      "criticality": "high",
      "expected_repair_hours": 5.0,
      "cost_per_hour_kzt": 25000,
      "hours_since_last_pm": 310.0,
      "pm_interval_h": 250.0
    }
  }'
```

#### Rendered Telegram Card Example:
```html
🔴 <b>ЧПУ-2 · Критично · уверенность: средняя</b>

<b>Что найдено:</b> запах гари (правило безопасности → «Критично»); звук отличается от нормы этого станка.
<b>Возможные причины</b> (по паспорту, с. 47): 1. Перегрев подшипников шпинделя из-за масляного голодания.
<b>Что делать сейчас:</b>
1. Остановите станок и отключите питание.
2. Проверьте уровень масла в маслостанции №2 (паспорт, с. 47).
```

### 3.2 Machine sound baseline and analysis

Put recordings inside `FIBO_SHARED_DIR`. Record all three normal reference clips through the
same phone/Telegram codec that will be used for later checks. `/v1/audio/baseline` returns a
hashed `BaselineArtifact`; persist it and send that artifact in the analyze request.

```json
POST /v1/audio/baseline
{
  "machine_id": "ЧПУ-2",
  "file_paths": ["/shared/normal-1.ogg", "/shared/normal-2.ogg", "/shared/normal-3.ogg"],
  "embedder_id": "mfcc_baseline"
}
```

```json
POST /v1/audio/analyze
{
  "machine_id": "ЧПУ-2",
  "file_path": "/shared/current.ogg",
  "baseline_ref": {
    "request_id": "req-baseline-001",
    "machine_id": "ЧПУ-2",
    "embedder_id": "mfcc_baseline",
    "embedder_version": "mfcc-1",
    "blob_path": "baselines/audio/%D0%A7%D0%9F%D0%A3-2.npz",
    "sha256": "<sha256 from baseline response>",
    "created_at": "<timestamp from baseline response>",
    "stats": { "mean_distance": 0.01, "spread": 0.05, "spread_floor": 0.05 },
    "window_params": { "duration_s": 2.0, "overlap": 0.5 },
    "model_version": "0.1.0",
    "config_version": "0.1.0",
    "degraded": []
  }
}
```

In production, pass the full `BaselineArtifact` object returned by the baseline call; the
example values above only show its JSON shape.

`/v1/audio/route` accepts a `file_path` for voice-vs-machine routing, or a manual
`mode` override from the bot. Analysis returns a baseline-relative z-score, deterministic
ru/kk spectrum descriptors, and a base64 side-by-side spectrogram. It reports deviation from
this machine's own sound, not a specific fault type.

### 3.3 Voice transcription and machine resolution

Keep voice files inside `FIBO_SHARED_DIR` and send their shared-volume path. The ASR request
accepts `profile` and `catalog_machines`; the profile adds industry vocabulary to Whisper's
`initial_prompt`, while catalog entries are added for workshop-specific names. Detection is
limited to Russian, Kazakh, and English. A failed quality/hallucination guard returns
`ASR_LOW_CONFIDENCE` with a re-record hint.

```json
POST /v1/speech/transcribe
{
  "file_path": "/shared/voice.ogg",
  "language_hint": "ru",
  "profile": "metalworking",
  "catalog_machines": ["ЧПУ-1", "ЧПУ-2"]
}
```

For typed text, `/v1/speech/parse` accepts `catalog_machines` and returns `machine_id`,
`machine_candidates`, and `needs_clarification`. Include the workshop catalog; when the
spoken name is missing or ambiguous, the service returns candidates and a localized
`clarifying_prompt` instead of guessing. `/v1/incident/analyze` accepts the same field for
its voice-to-card flow.

### 3.4 Manual indexing, retrieval, and citations

Index PDFs saved under `FIBO_SHARED_DIR`. Poll `/v1/manuals/{id}/status`: a valid manual is
`ready`; validation or extraction failures are `failed` with an error. Query results include
page/section metadata. Multilingual E5 is used when its optional dependency and model weights
are available; otherwise responses mark the lexical cross-language glossary fallback in
`degraded`. Treat retrieved pages as the citation allow-list: claims citing pages not returned
by retrieval are removed. Manual contents are untrusted data and cannot override deterministic
safety rules.

### 3.5 Panel photos and tool wear

Pass photo paths inside `FIBO_SHARED_DIR`. Panel reading and tool comparison run the configured
image quality gate before any vision-model call. Rejected photos return `PHOTO_QUALITY_LOW`
(422) with issues and localized retake advice; the expensive model is skipped. The quality
endpoint itself returns `is_acceptable` plus the measured blur/exposure indicators.

```json
POST /v1/vision/panel
{
  "file_path": "/shared/cnc-panel.jpg",
  "workshop_id": "ws-shymkent-01",
  "machine_id": "ЧПУ-2",
  "lang": "ru"
}
```

Unreadable panel fields are `null`. If Tesseract is installed, every extracted numeric value
and numeric alarm code must also appear among OCR tokens or the value is dropped. Without
Tesseract the response marks `ocr_unavailable_crosscheck_skipped`; install OCR for that
additional cross-check. Tool comparison requires both a known-good reference and a current
photo (`/v1/vision/tool-compare`), and returns qualitative wear (`none|slight|moderate|severe`)
plus confidence (`low|medium|high`); it does not estimate a wear percentage.

### 3.6 Operator and dashboard assistants

`/v1/assistant/operator` retrieves manual fragments for the machine and question. It cites only
retrieved pages; an absent manual produces a not-found response. Safety triggers bypass the
LLM and return the deterministic stop line. `/v1/assistant/dashboard` uses only allow-listed,
read-only `DataRepository` methods (`get_incidents`, `get_downtime`, `top_machines`,
`get_risk_ranking`, `get_machine`). It returns a markdown table and `data_refs`; generated
summary numbers are checked against tool rows, with a code-rendered fallback on mismatch.
The production `FiboAI` instance must be constructed with the backend's read-only repository
implementation; without one, dashboard queries return `MODEL_NOT_READY`. The built-in
`FakeRepository` is only for stub mode, contains synthetic demo records, and marks them in
`degraded`.

---

## 4. Error Model & Codes

All errors return JSON in this schema:
```json
{
  "error": {
    "code": "UPPER_SNAKE",
    "message": "Human-readable explanation",
    "retriable": false,
    "details": {}
  }
}
```

### Standard Error Codes:
- `VALIDATION_ERROR` (400): Request schema validation failed (extra fields forbidden).
- `FILE_TOO_LARGE` (413): File exceeded size limits (image > 10 MB, audio > 15 MB, PDF > 50 MB).
- `UNSUPPORTED_MEDIA` (415): File format not recognized by content header.
- `AUDIO_TOO_SHORT` (422): Audio under 3 seconds.
- `AUDIO_SILENT` (422): RMS volume below noise floor.
- `PHOTO_QUALITY_LOW` (422): Photo blurry or glaring; returns `retake_advice_ru` and `retake_advice_kk`.
- `ASR_LOW_CONFIDENCE` (422): Speech hallucination flagged or unintelligible.
- `MACHINE_AMBIGUOUS` (422): Machine name cannot be resolved unambiguously.
- `BASELINE_MISSING` (404): No acoustic baseline exists for this machine yet.
- `BASELINE_VERSION_MISMATCH` (409): Baseline created with previous incompatible embedder.
- `MANUAL_NOT_INDEXED` (404): Manual is still indexing or not uploaded.
- `LLM_UNAVAILABLE` (503): Provider timed out or circuit breaker open.

---

## 5. Security & Shared Files
- If running on the same server/Docker network, you can pass `"file_path": "/shared/audio_123.ogg"` pointing to `FIBO_SHARED_DIR` to avoid re-uploading file bytes.
- Internal authentication: supply `Authorization: Bearer <AI_SERVICE_TOKEN>` if `AI_SERVICE_TOKEN` is configured in `.env`.

---

## 6. Changelog
- **2026-11-07 (Phase 0)**: Initial contract specification, 22 endpoints, `fibo_ai_client.py` and OpenAPI 3.1 schema exported.
- **2026-11-08 (Phase 2)**: Added optional `file_paths` to baseline requests and the body form for audio analysis with a persisted `baseline_ref`; legacy query parameters remain accepted. Responses now include real baseline metadata and generated audio diagnostics.
- **2026-11-08 (Phase 3)**: Added `profile` and `catalog_machines` to transcription requests and `catalog_machines` to incident requests; callers should provide workshop machine names for conservative resolution. Voice parsing, manual retrieval/citation verification, deterministic safety guards, and template card fallback are implemented. See regenerated `openapi.json` for additive schemas.
- **2026-11-08 (Phase 4)**: Panel requests add optional `workshop_id` and `lang`; incident requests add `tool_reference_photo_path`. The incident endpoint now forwards accepted panel readings into `risk.predict`, plus tool wear signals. Photo analysis uses a first-stage quality gate; panel OCR cross-check is optional and explicitly marked when unavailable.
- **2026-11-09 (backend integration, steps 2–4)**: Client: one request path with per-endpoint timeouts,
  at most two retries for transport/429/5xx only, typed `FiboAIError` from the error envelope;
  `analyze_audio` uses the JSON body with `baseline_ref`; `transcribe` sends `profile` and
  `catalog_machines`; `create_baseline` no longer sends `clip_count`. Docs: the service is not
  stateless (`/data/ai`); latency budgets are targets, not measurements; PatchCore is not validated;
  the example card no longer pairs a 3,1σ deviation with «Критично» (the measured critical threshold is
  16.092σ — the level there comes from the safety rule); section order fixed. Still open in the service
  itself (its code is not in the Fibo repo): workshop-scoped artifact ids, the shared-dir path guard, the
  structured plain-text card, `reasoning_effort`, the `spectral_z` evaluation and the slim image.
