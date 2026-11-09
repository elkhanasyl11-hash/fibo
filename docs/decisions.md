# Fibo — decisions log

Choices made where the spec left room, or where we deliberately deviate. Newest phase at the bottom.

---

## Phase 1

### D1. Background work: FastAPI `BackgroundTasks`, no Celery/Redis
Fewer moving parts (no broker, no worker container), and every teammate can explain it. Pipeline
functions take only IDs and open their own DB session, so they could move to a worker queue later
without changes to their logic. Trade-off: a task in flight is lost if the backend restarts; the
`POST /incidents/{id}/retry` endpoint covers that for the demo.

### D2. No user authentication in the MVP
The bot authenticates with a shared secret (`X-Fibo-Bot-Token`); the dashboard with an optional
API key (`X-Fibo-Api-Key`, disabled when `FIBO_DASHBOARD_API_KEY` is empty). There are no user
logins or per-user permissions. Out of scope for a hackathon MVP; must be added before real use.

### D3. `/health` and `/profiles` are open (no API key)
`/health` must work for the Docker healthcheck. `/profiles` contains only static configuration
(no workshop data) and both the bot and the dashboard need it.

### D4. `/health` returns 503 with the health body when the database is down
Not the generic error shape: the response is a status report, and the healthcheck only looks at
the status code. Everything else in the API uses the single error shape.

### D5. Timestamps: `UTCDateTime` type instead of bare `DateTime(timezone=True)`
SQLite drops timezone info. `app/db/base.py::UTCDateTime` wraps `DateTime(timezone=True)`,
attaches UTC on read and rejects naive datetimes on write. The stored column type is unchanged,
so PostgreSQL works the same. Migrations render it as `sa.DateTime(timezone=True)`.

### D6. Enums stored by value in VARCHAR(20)
`str_enum()` stores `"operator"`, not `"OPERATOR"`, with `native_enum=False`. No CHECK constraint
on enum columns (SQLAlchemy's default); Python/Pydantic validate values.

### D7. Attachment `kind` is a string with a CHECK constraint, not a new enum
The spec lists the values but no enum; a CHECK keeps the DB honest without adding an enum class.

### D8. Constraint naming convention
`Base.metadata` has a naming convention (`ck_<table>_<name>`, `fk_…`, `ix_…`), so Alembic can find
and alter constraints later, especially on SQLite (batch mode) and PostgreSQL.

### D9. `.env` lookup and data paths
Settings read `../.env` (repo root) and then `backend/.env`, so one `.env` at the root works when
running from `backend/`. `.env.example` points data to `../data` (the repo's `data/` folder);
Docker overrides these paths for containers. Empty values (`FIBO_X=`) mean "use the default"
(`env_ignore_empty=True`), otherwise an empty dashboard key would switch auth on.

### D10. Library versions
Pinned to the current releases at build time; notably SQLAlchemy **2.1.8** (the spec says "2.0":
we use the 2.0-style typed API, which 2.1 keeps). Phase-1 `requirements.txt` holds only what
phase 1 uses; ML/audio/RAG/vision libraries are added in the phase that needs them.

### D11. Profile file schema details
- `extra_fields` entries are objects `{name, title_ru, title_kk, unit}` (the spec example shows
  only `[]`), and every extra field must have a range in `reading_ranges`.
- Catalog entries and profiles got an optional `title_kk` / `assistant_context_kk`.
- Validation rules: at least one positive risk weight; `model_applicable: true` requires
  `nominal_torque_nm` and `p_model > 0`; `model_applicable: false` requires `p_model = 0`.
- **All Kazakh strings are drafts and must be checked by a native speaker** before the demo.

### D12. Development environment on the team laptop
The laptop had only Python 3.9, so Python 3.11 was installed with `uv`. The virtualenv lives in
`~/.venvs/fibo-backend`, outside the project: `~/Desktop` is synced to iCloud there, which makes
cold file reads very slow (thousands of site-packages files). Not relevant for Docker or other
machines; the README's standard `.venv` instructions still apply.

---

## Phase 2

### D13. Service layer in `app/services/`
The spec's ingest example calls `users_service`, `machines_service`, `incidents_service`, but
the layout has no folder for them. They live in `app/services/` (one file per resource) so the
same functions serve routers, background pipelines, the seed and tests.
`app/modules/machine/service.py` remains the *risk* service from the spec.

### D14. The bot token also opens the dashboard endpoints
The bot must poll `GET /incidents/{id}`, resolve incidents and confirm panel readings, which are
dashboard endpoints. `require_dashboard_key` therefore also accepts a valid `X-Fibo-Bot-Token`.
The reverse is not true: `/bot/*` and `/ingest/*` accept only the bot token.

### D15. `/media` needs the dashboard key
The files are photos from a workshop, so they are not public. The frontend must load them with
`fetch()` and the `X-Fibo-Api-Key` header and show them as blob URLs; a plain `<img src>` cannot
send headers. (With the key disabled in dev, `<img src>` works.) Paths are unguessable UUIDs as a
second line of defence.

### D16. Uploads: magic-byte check in addition to extension + MIME
The extension and MIME type are chosen by the client and can lie. The first bytes of the file are
also checked against the expected format (OGG, WAV, MP3, M4A, JPEG, PNG, WEBP, PDF). One small
function, no extra library.

### D17. Input datetimes must carry a timezone
`AwareDatetime` everywhere in requests: `2026-11-07T10:00:00` (no offset) is rejected with 422,
because it is unclear whether it means Almaty time or UTC. Responses are always UTC.

### D18. Readings: strict profile validation
A value is accepted only if the workshop profile defines a range for it (a bakery reading with
`spindle_rpm` is rejected) and only inside that range (this also rejects NaN/infinity).
`extra` keys must be profile extra fields. Readings more than 5 minutes in the future are rejected
(phone clocks drift a little). All problems are returned at once in `details.fields`.

### D19. Machine `type` is not restricted to the profile catalog
The catalog in the YAML is what the bot and dashboard *offer*; a workshop may also own machines
outside it (e.g. a compressor in a bakery). The risk model does not depend on `type`.

### D20. Incident feed: extra `workshop_id` filter
The spec lists `machine_id, status, level, from, to`. Without auth scoping the dashboard needs
`workshop_id` to show one workshop's feed, so it was added (join through machines).

### D21. Resolve rules
Any status except RESOLVED can be resolved (a FAILED incident may still have been fixed on the
spot). Loss is computed from exact seconds with `Decimal` and rounded half-up to 0.01 ₸;
`downtime_hours` is stored rounded to 4 decimals.

### D22. `tool_changed_at` is editable via the machine API
It is a ★ column used for tool-wear minutes in phase 3, so it was added to the machine
create/update schemas (the spec's example schema did not include it).

### D23. Demo seed details
Fixed invite codes `DEMO01` (metalworking) and `DEMO02` (bakery). They contain 0/1, which
generated codes never use, so they cannot collide. Demo users have no `telegram_id`; team
members join the demo workshop through the bot with the invite code. Random values use seed 42.

---

## Phase 3

### D24. Documented feature approximations (also returned in every score's `assumptions`)
| Model feature | From | Note |
| --- | --- | --- |
| Rotational speed [rpm] | `spindle_rpm` | direct |
| Torque [Nm] | `load_pct / 100 × profile.nominal_torque_nm` (60 Nm for metalworking) | **approximation**; no per-machine override yet |
| Process temperature [K] | `temperature_c + 273.15`; if missing: air + 10 K | the +10 K is the typical AI4I gap |
| Air temperature [K] | `profile.default_air_temperature_k` (298 K) | **approximation**: not measured |
| Tool wear [min] | operating-hours counter since `tool_changed_at` (fallback: wall-clock minutes), capped at the training max 253 min | AI4I's wear scale is a lab one, real tools often exceed it → capped and reported |
| Type L/M/H | criticality 1/2/3 | **approximation** |
The model also needs a reading with rpm and load from the last 14 days; otherwise it is not used.
Values outside the training range are allowed but flagged.

### D25. Priority uses risk_index, not P(failure)
The spec's formula multiplies by P(failure), but P does not exist for non-CNC machines and food or
sewing profiles. `risk_index` exists for every machine, so all machines are ranked on one scale.

### D26. Explanations stored in the `shap_factors` JSON list with a `kind`
The spec allows the per-signal values in `shap_factors` "or a separate signals key". To keep the
single initial migration, each entry carries `kind`: `shap`, `signal` or `note` (assumption,
anomaly result, why the model was not used). The API returns them split into `shap_top3`,
`signals`, `assumptions`, `anomaly_reason`, `model_not_used_reasons`.

### D27. Signal details
- `s_overdue` uses wall-clock hours since `last_maintenance_at` (operating hours at the time of
  maintenance are usually unknown).
- `s_history` counts only warning/critical incidents of the last 30 days, plus older ones that
  were still unresolved; a "normal" photo check is not a problem.
- `s_audio`/`s_visual` use the latest check of the last 7 days.

### D28. Isolation Forest inputs
Columns present in the latest reading (rpm, load, temperature + numeric `extra` values); the
operating-hours counter is excluded because it only grows. ≥ 20 complete readings required.

### D29. Model loading and the active model
Loaded once at startup into a module-level holder (`set_active_model` / `get_active_model`) so that
background tasks, which receive only IDs, use the same model. Missing or broken artifacts → warning
log and index-only mode; `/health` shows `risk_model_loaded`.

### D30. Training details
Fixed hyperparameters (300 trees, depth 4, lr 0.05), no early stopping, so the validation split is
used only for calibration and the threshold. `n_jobs=1` for bit-identical retraining.
`model_version = xgb-ai4i-<sha256 prefix of the CSV>`. Artifacts are committed (~0.5 MB).
The dataset itself (UCI AI4I 2020, CC BY 4.0) is not committed; it was downloaded to
`data/datasets/` (gitignored).

### D31. Ranking response
`{workshop_id, items[], unscored_machine_ids[]}`: machines with no score yet are listed separately
instead of being silently dropped. Recompute is synchronous (a workshop has 5–30 machines).
what-if returns both the current and the scenario score (`saved: false`), so the UI can show
"risk drops from X to Y".

### D32. macOS dev machine: OpenMP for xgboost
xgboost's macOS wheel needs `libomp.dylib` (normally `brew install libomp`). This laptop has no
Homebrew, so the copy bundled with scikit-learn was placed in the uv Python's `lib/` folder,
which is on xgboost's library search path. Linux/Docker use the system `libgomp`; nothing in the
code depends on this.

---

## Phase 4

### D33. webrtcvad instead of silero-vad
silero-vad needs PyTorch (~1 GB); the team laptop has a few GB free and phase 7 needs torch for
embeddings anyway. The spec allows webrtcvad as the fallback; `webrtcvad-wheels` installs without a
compiler. Rule: speech if ≥ 0.3 s and ≥ 10% of 30 ms frames are voiced (aggressiveness 2).

### D34. Audio decoding without ffmpeg
ffmpeg (no shell, 60 s timeout) is the main path and is installed in the Docker image. When it is
missing, libsndfile decodes OGG/Opus, WAV and MP3 and scipy resamples to 16 kHz; m4a then fails
with a clear 415-style error. Setting: `FIBO_FFMPEG_BINARY`.

### D35. `mode` is stored as the incident's input type
`/ingest/voice` with `mode=machine_sound` creates `input_type=audio` (the spec's enum value for a
machine sound). The pipeline derives the branch from `input_type`, so `process_incident(id)` and
retry need no extra arguments. A voice message without speech (VAD) also goes to the audio branch
but stays `input_type=voice`.

### D36. Caption handling
The optional caption is passed to the first pipeline run and checked by the safety layer; it is
not stored (no column). On retry it is not re-checked, but its safety result was already saved and
is never removed.

### D37. Safety false positives are accepted
Patterns match word stems, so "горит лампочка" (a lamp is lit) also triggers the stop text. For
safety, a false alarm is cheaper than a missed fire. The stop/inspect headers are Russian only: an
unverified translation of a safety instruction is a risk; the Kazakh keywords are drafts for a
native speaker to check.

### D38. Mock LLM answers
Transcripts are picked by a hash of the audio bytes (same recording → same text). Extraction uses
keyword rules; the card level follows urgency only. The mock ignores safety and always adds page
999 on purpose (see walkthrough).

### D39. Bot details
- Settings: `FIBO_TELEGRAM_BOT_TOKEN`, `FIBO_API_URL`, `FIBO_BOT_SHARED_SECRET` (same as backend).
- FSM storage is in memory: after a bot restart users just pick the machine again.
- Added `bot/delivery.py` (polling) and `bot/handlers/common.py` (user lookup) to the layout.
- Photo buttons appear in phase 6 together with Fibo Vision; `/ingest/photo` too.
- "Call mechanic" skips masters who never opened the bot (Telegram refuses) and notifies the rest.
- `pg:` button shows the cited page numbers; text excerpts come with RAG in phase 7.
- Owners can also add machines from the bot (they register through the dashboard).

### D40. Project lives outside iCloud (`~/dev/fibo`)
On the team laptop `~/Desktop` is synced to iCloud, and with the disk ~98% full macOS evicted most
source files to the cloud ("dataless"); the backend then hung for minutes while importing them,
and the code would have been unreadable offline at the demo. The project was moved to
`/Users/aplle/dev/fibo` (verified byte-identical, tests re-run). Keep it there, and keep the repo
pushed to a remote, so no copy depends on iCloud.

---

## Phase 5

### D41. Audio features and details
14 features (8 mel-band energies, RMS dB, centroid, 85% roll-off, flatness, ZCR, crest factor) on
1 s windows with 50% overlap of a 10 s clip; STFT n_fft 1024, hop 256; log-mel in absolute dB.
Recordings of 2–10 s are looped to 10 s instead of zero-padded. Optional pretrained embeddings
(PANNs/BEATs) were not added (time, disk, explainability).

### D42. Baseline storage and readiness
One `baselines` row per reference recording; `embedding` = its 19×14 window features, `stats` =
combined statistics over all audio baselines at that moment (newest row = current). Scoring works
from the first recording, but cards and API say "x of 3" until 3 exist.

### D43. Measured audio level is a floor for the card
`finalize(min_level=...)`: the LLM may make the card more severe than the z-score, never less.
The safety "inspect" rule (critical sensor + high urgency) needs an urgency, which only exists in the
speech branch; a pure machine-sound recording is judged by its z-score.

### D44. Photo baseline (minimal)
`POST /machines/{id}/baselines/photo` stores the reference photo with width/height/format (Pillow,
already a dependency of matplotlib). Comparison uses it in phase 6.

### D45. MIMII/DCASE evaluation data
DCASE 2020 Task 2 development set, machine type **slider** (zenodo record 3678171, CC BY-NC-SA 4.0).
zenodo served ~60 KB/s, so instead of the 1 GB zip only the needed clips were fetched with HTTP range
requests (a scratch helper, not part of the project): all 4 machine ids, 100 normal training clips per
id as baseline, 100 normal + up to 100 anomalous test clips per id. Not committed (`data/` is ignored).

### D46. Audio evaluation result and thresholds (honest numbers)
`python -m ml.eval_audio_mimii --data ../data/datasets/dcase2020-slider` → `ml/artifacts/audio_metrics.json`:

| machine id | ROC-AUC | normal clips with z < 2 | anomalies with z ≥ 2 | normal z p95 |
| --- | --- | --- | --- | --- |
| id_00 | 0.82 | 95 % | 2 % | 1.83 |
| id_02 | 0.68 | 97 % | 5 % | 1.73 |
| id_04 | 0.61 | 97 % | 7 % | 1.44 |
| id_06 | 0.42 | 100 % | 2 % | 1.57 |
| **mean** | **0.63** | | | |

(60 baseline clips per id; 60 normal + 60–99 anomalous test clips per id.)
Reading: the method rarely raises false alarms, but DCASE slider anomalies are subtle and mostly stay
below z = 2; on id_06 the score does not separate them at all. The "largest single |z|" variant is not
better (0.42–0.78). Thresholds stay at 2 / 3: they keep false alarms near 5 %, and the faults this
product targets (knocks, bearing noise, rubbing) change the sound far more (synthetic tests: z 8–14).
This is stated as a limitation, not hidden. A stronger detector (e.g. pretrained audio embeddings or an
autoencoder) would be the next step if time allowed.

---

## Phase 6

### D47. Photo quality thresholds
Image scaled to 1024 px on the long side; blurry if Laplacian variance < 60, too dark if mean grey
< 40, overexposed if > 225 (settings `FIBO_PHOTO_*`). Chosen on synthetic images (sharp ≈ 3000–5000,
blurred ≈ 1); to be re-checked on a few real workshop phone photos before the demo.

### D48. Pixel difference as a hint
`pixel_difference` (mean |grey difference| at 256×256) is sent to the vision model as context and is
the only input of the mock. It is not used as a defect measure in live mode: lighting and angle change
it as much as a chip does.

### D49. Panel values: suggestion only
`POST /readings/panel-photo` stores the photo (for traceability) and returns values; it never creates
a reading. A blurry/dark display photo is rejected with 422 before any AI call. Corrections in the bot
use the field names ("load_pct=70"); the backend validates the final values again on POST /readings.

### D50. No difference heatmap
The `attachments.kind` list allows "heatmap", but a pixel heatmap between two hand-held photos mostly
shows misalignment, which would mislead. Not built; PatchCore (phase 9, optional) would be the place.

---

## Phase 7

### D51. e5 through onnxruntime instead of sentence-transformers
Same model (intfloat/multilingual-e5-small, MIT), official int8 ONNX export from the model's own
repository (`onnx/model_qint8_avx512_vnni.onnx`, 118 MB) + its tokenizer, mean pooling and L2
normalisation as in the model card, `query:` / `passage:` prefixes. Reason: PyTorch + sentence-transformers
need ~1 GB on a laptop with ~2 GB free. The int8 model runs on ARM and x86. Tests use a deterministic
word-hash embedder (`FIBO_EMBEDDING_BACKEND=hash`) so no model is downloaded in tests.

### D52. Retrieval threshold 0.83 (e5) and page rules
Relevant Russian chunks scored 0.83–0.89, unrelated ones up to ~0.82 in a small calibration set, so
0.83. Below it the card states "not found in the manual" and gives general safety advice. Cited pages
must be among retrieved chunks; others are dropped (and logged as `dropped_pages`).

### D53. Retrieval only over READY manuals that exist in the database
Chunks of deleted machines/manuals remain in Chroma (cascade deletes do not reach it), and SQLite can
reuse ids. Filtering by the machine's READY manual ids makes stale chunks harmless without a cleanup job.

### D54. Profile knowledge base
`app/profiles/kb/<profile>.md`, one "## " section per symptom; indexed at startup into `profile_kb`
(skipped with a warning if the embedding model is unavailable). Used as extra context only.

### D55. Scanned PDFs
Pages with < 50 characters of text are reported in `manuals.error_message`; a PDF with no text at all is
FAILED with an explanation. OCR is out of scope for the MVP.

### D56. Silent-edit lesson (bot wiring)
Several bot edits in phases 5–6 had silently not applied (helper functions missing; the "📸 reference
photo" button had no handler). They only failed when pressed in Telegram. Fixed, and
`bot/tests/test_wiring.py` now checks every keyboard function, API method, text key, state and button
handler statically.

---

## Phase 8

### D57. Report period and counting
Incidents are counted by `created_at` in [from, to]; default period = last 30 days. Resolved incidents
contribute their stored downtime/loss; unresolved ones count from report time until now (or `to`) in
separate `ongoing_*` fields — this is time since the report, not proof that the machine stood still.

### D58. MTBF
operating hours / failures, failures = incidents with level warning or critical. Operating hours = max − min
of the operating-hours counter in the period; without a counter, the calendar period (marked
`operating_hours_source = calendar`). No failures → `null`.

### D59. CSV format
UTF-8 with BOM, `;` separator (Russian-locale Excel), dot as decimal separator, one row per machine + ИТОГО.

### D60. Assistant design
Four read-only tools, workshop id never exposed to the model, max 4 tool rounds then a final answer
without tools, only user/assistant turns accepted from clients. Referenced ids come from the tools that
were called (ranking: top 3 machines). The mock chooses tools by keywords and composes answers only
from tool output, so the acceptance test checks the data path, not a canned sentence.

---

## Phase 9

### D61. Docker images
python:3.11-slim, system packages ffmpeg, libsndfile1, libgomp1, libglib2.0-0; non-root user (uid 1000 by
default, build arg `UID`); healthcheck with Python's urllib (no curl in slim images); the backend runs
`alembic upgrade head` before uvicorn. Compose `environment` overrides the laptop paths from `.env`.

### D62. xgboost-cpu on Linux
`xgboost==3.2.0; sys_platform == "darwin"` and `xgboost-cpu==3.2.0; sys_platform == "linux"`: same
library and version (the committed model loads in both), without 350 MB of unused GPU libraries in the image.

### D63. Model cache location
`FIBO_MODEL_CACHE_DIR` (default `<data dir>/models`). Images use `/app/model-cache`, outside the `./data`
volume, so `FIBO_PRELOAD_EMBEDDINGS=true` can bake the e5 model into the image. Without preloading, the
model is downloaded on first start (≈135 MB) and again after the container is recreated.

### D64. Verification limits
`docker compose up` was not run on the team laptop (no Docker, ~2 GB free disk). Mitigations: Linux
wheel resolution checked for x86_64 and arm64, compose file validated as YAML, every non-Docker README
step run verbatim on a clean copy. Optional PatchCore (anomalib) was not added: no time and no disk,
and the multimodal comparison already covers the demo.

---

## Audit against the master spec (after phase 9)

A section-by-section audit of the finished code against the spec found these gaps; all were fixed or
documented in one commit.

### D65. Bot messages escape every dynamic value
User names, workshop names and machine names were inserted into HTML messages unescaped (registration,
machine prompts, machine list, "machine added"). A name such as "Ali & Co" would make Telegram reject the
message. All are `html.escape`d now; `bot/tests/test_wiring.py::test_dynamic_message_values_are_html_escaped`
fails if a new unescaped value appears (verified against the old code).

### D66. Paging on every list endpoint, Fibo Vision tag, demo label on risk scores
- `GET /machines/{id}/baselines` and `/manuals` take `limit`/`offset`; `risk-history` now honours `offset`
  (it was accepted but ignored).
- The three Vision endpoints (`/readings/panel-photo`, `/machines/{id}/baselines/photo`, `/ingest/photo`)
  are tagged "Fibo Vision" through small second routers with the same prefix and auth.
- Risk score responses carry `is_demo` (from the machine: `RiskScore.machine` is loaded with
  `lazy="joined"` and `RiskScore.is_demo` is a read-only property, so no new column or migration).
- The photo pixel-difference hint runs in a worker thread like all other CPU work.

### D67. The safety "inspect" rule cannot trigger yet (known limitation)
Spec 8.6: "critical audio/vision level together with urgency high → inspect header". `safety.check_levels`
implements and tests it, but one incident is either speech (has an urgency, no measured level) or a machine
sound / photo (has a level, no urgency), so the two never meet in one incident. Making it reachable would
mean combining a voice report with a recent sound/photo check of the same machine (e.g. within an hour) —
a new feature, not built (ground rule 8). The stop rule (dangerous words) is unaffected and always active.

### D68. Kazakh safety keywords (to be checked by a native speaker)
Base patterns in `app/modules/assistant/safety.py` (matched after lowercasing; stems match word forms):

| Kazakh pattern | Meaning | Matches e.g. |
| --- | --- | --- |
| `түтін…` | smoke (дым) | түтін, түтіні шығып тұр |
| `ұшқын…` | sparks (искры) | ұшқын, ұшқындар |
| `күйік иіс…`, `күйген иіс…` | burning smell (запах гари) | күйік иісі, күйген иіс шығады |
| `ток соқ…`, `ток соғ…` | electric shock (удар током) | ток соқты, ток соғады |
| `өрт…`, `жалын…` | fire / flame (огонь, пламя) | өрт, жалын |

Profile additions: bakery and confectionery `газ иісі` (smell of gas). The audit found that `соғады`
(present tense, ғ) was not matched by the stem `соқ`; the pattern now accepts both letters (қ → ғ before a
vowel). This is the kind of case the native-speaker check must cover for every keyword.

### D69. Shape of POST /risk-scores/recompute
The spec shows `{machine_id?}` with "all machines of a workshop if omitted". Without a machine id the
backend still needs to know which workshop, so the body is exactly one of `{machine_id}` or `{workshop_id}`
(422 otherwise).

---

## ECC review fixes (group A)

### D70. Audio tolerance depends on the number of baseline recordings
Measured on DCASE slider (5 random baselines of k clips per machine id): with 1 / 3 / 10 / 60 clips, healthy
recordings reached z ≥ 2 in 70% / 23% / 7% / 3% of cases — a one-recording baseline flagged a healthy
machine most of the time. A few recordings under-estimate natural variation, so z is divided by
`TOLERANCE_BY_RECORDINGS` {1: 4.3, 2: 2.2, 3: 1.7, 4: 1.5, 5: 1.4, 10: 1.1, 20+: 1.0} (= 95th percentile of
healthy z / 2). Measured result: about 5% of healthy recordings reach z ≥ 2 for every baseline size. AUC is
unchanged (scaling does not change ranking). More recordings still give a sharper detector.

### D71. AI4I product class fixed to L; criticality no longer feeds the model
The review showed that mapping criticality 1/2/3 to AI4I's L/M/H changed P(failure) non-monotonically
(criticality 2 got 40–65% lower probability than 1 or 3 for identical readings). In AI4I L/M/H is a product
quality variant, not criticality. The class is now fixed to L (the most common, 60% of rows) for every
machine, the constant class factor is dropped from SHAP explanations, and criticality only affects the
priority in tenge. A test checks that the probability is identical for criticality 1, 2 and 3.

### D72. Reliability and safety fixes from the review
- PATCH with an explicit `null` on a non-nullable field (machine name/criticality/cost/repair hours, user
  name/role/language) returns 422 instead of a 500 from the database.
- "Resolved" on an incident that is still RECEIVED/PROCESSING returns 409; before, the pipeline re-opened it
  when it finished and the loss could be counted twice.
- Startup sweep (`pipelines/recovery.py`): incidents left RECEIVED/PROCESSING and manuals left
  PENDING/INDEXING by a restart are marked FAILED with "interrupted … please retry"; safety results stay.
- Pipelines record failures in a fresh session (after rolling back the broken one) and skip rows deleted
  before the task ran.
- `FIBO_ENV=prod` refuses to start with the default/short bot secret or without a dashboard key; dev logs
  warnings (backend and bot).
- Bot: up to 3 failed polls in a row are tolerated; after the 180 s wait or any delivery error the user gets a
  message instead of silence; the global error handler cannot crash on its own reply.

---

## AI service integration (FIBO_AI_FIX_AND_INTEGRATION_PROMPT)

### D73. AI service material in `ai/`; the service source is not available
Rule R9 requires all code in this repo. Only three files of the AI service exist on the team laptop
(`AI_INTEGRATION.md`, `README_ML.md`, `fibo_ai_client.py`); its application code, `openapi.json`,
evaluation scripts, metrics file, tests and Dockerfile are not. The three files were copied unchanged into
`ai/` (no git history to preserve). Consequences: AI-side steps (ids, path guard, structured card, GPT
settings, `spectral_z` evaluation, image) cannot be done here; the contract is taken from
`AI_INTEGRATION.md` plus the structured card defined by the integration prompt; every assumed response
field is listed in `backend/app/modules/ai_gateway/adapters.py`. See `docs/plan-ai-integration.md`.

### D74. AI client: typed errors, bounded retries, contract from the docs
`ai/fibo_ai_client.py` sends every request through one `_call()`: per-endpoint timeouts (analyze 12 s,
vision 8 s, transcription 6 s, manual index 15 s, others 5 s), at most two retries (0.5 s, 1.5 s) and only
for transport errors, 429 and 5xx — a 4xx input error is never retried even if marked `retriable`.
Errors are `FiboAIError(status, code, message, retriable, details)`; transport failures are
`UNREACHABLE`. `analyze_audio` now sends the documented JSON body with the full `baseline_ref`,
`transcribe` sends `profile` and `catalog_machines`, `create_baseline` no longer sends `clip_count`, and
`None` fields are omitted (the service forbids extras). Without `openapi.json`, `ai/tests/contract.py`
transcribes the request contract of all 22 endpoints from `AI_INTEGRATION.md` and the Phase-0 client.

### D75. AI-service steps 3–4: only the documentation could be done here
Workshop-scoped artifact ids, the `FIBO_SHARED_DIR` path guard, the structured plain-text card,
`reasoning_effort`/structured outputs for GPT-6 Luna, the `spectral_z` evaluation on DCASE fan and the slim
AI image all live in the AI service's code, which is not in this repository (D73). Done here:
`ai/AI_INTEGRATION.md` no longer calls the service stateless (it keeps baselines and the manual index in
`/data/ai`), labels latency budgets as unmeasured targets, marks PatchCore as not validated, fixes the
misleading example card (3,1σ with «Критично» while the critical threshold is 16.092σ), uses Fibo's
Compose host `ai` and shared dir `/app/data/media`, orders sections 3.1–3.6 and has a changelog entry.
`ai/README_ML.md` is kept unchanged: it can only be regenerated by the service's own script. The backend
already uses the same 14-feature z-score that `spectral_z` describes (D41, measured in D46). The backend
gateway (D76+) protects itself from the missing service changes: it renders its own plain-text card and
falls back to the builtin modules on any unexpected answer.

### D76. Backend AI gateway: sidecar first, builtin fallback, `builtin` by default
`backend/app/modules/ai_gateway/` is the only place that talks to the AI service. `client.py` is a byte
copy of `ai/fibo_ai_client.py` (a test compares them; it is excluded from the backend's ruff run because
`ai/` formats at 120 columns). `provider.with_fallback()` applies one rule to every path: the AI answer is
adapted (`adapters.py`) or, on any failure, the existing builtin module runs and the result carries a
`degraded` tag (`ai_sidecar_unavailable`, `ai_manual_not_indexed`, `ai_baseline_mismatch`,
`ai_contract_mismatch`). Input errors (blurry photo, silent audio, failed ASR) are not replaced by the
builtin — it would fail the same way — but turned into an explanatory card (`messages.py`). Rejected
requests (400/413/415) raise `AIRequestRejected`, so the incident is FAILED with `ai: <code>` instead of
silently answering something else. The default is `FIBO_AI_PROVIDER=builtin`, not `sidecar` as the
integration prompt suggested: the AI service code is not in this repository (D73), so `sidecar` would make
every demo request wait for an unreachable host before falling back. Compose puts the `ai` service under
profile `ai` with `required: false`, no published port and a read-only media mount; `/api/v1/health`
reports `ai_provider`, `ai_sidecar` (ready/unreachable/disabled, never fails health) and `ai_models`
(cached 60 s). The response shapes the adapters expect are assumptions, listed in `adapters.py`. The
whole backend suite runs in both modes; with `sidecar` the conftest makes the AI service "down"
(MockTransport), so no test reaches the network. GPT-6 Luna: the backend's own LLM client now sends
`reasoning_effort` (`FIBO_LLM_REASONING_EFFORT`, default `low`; `none` for tool calls) instead of
`temperature`; `off` restores temperature 0 for classic models.

### D77. Kazakh texts of the AI input-error cards are drafts
The four new card texts in `ai_gateway/messages.py` (speech not recognised, audio too short/silent, manual
unavailable, photo retake) were written in Russian and translated without a native speaker. They join the
Kazakh safety keywords (D68) on the list for a native-speaker check before a Kazakh-language demo.

### D78. Backend paths switched to the AI gateway; migration 0002
With `FIBO_AI_PROVIDER=sidecar` five paths ask the AI service first and keep their old code as the fallback:
- **Incidents** (`pipelines/incident_ai.py`): one `/v1/incident/analyze` call with `ws-`/`m-` ids, shared
  media paths, the machine's economics (criticality, repair hours, KZT per hour, hours since maintenance,
  interval), the workshop's machine names and the stored audio baseline artifact. The backend still owns
  the card: the caption is safety-checked before the call, the AI transcript is saved and checked before
  the card, an AI danger flag can only add a stop header, the measured audio z-score is a level floor
  (backend thresholds), pages are only those the AI both claimed and cited, and the text is the backend's
  plain-text render. `BASELINE_VERSION_MISMATCH` rebuilds the artifact once and retries.
- **Risk** (`machine/risk_model_part.py`): `/v1/risk/predict` with the backend's mapped features (one-hot
  class sent as `type`); the local model is the fallback, index-only mode without it. Without local
  artifacts the features are clipped to the AI4I training ranges.
- **Panel photo**: the local blur check stays first; values come from `/v1/vision/panel` and go through
  the same backend range validation, so `PanelPhotoResult` is unchanged.
- **Audio baselines**: from the 3rd recording the AI artifact is stored in the newest baseline's
  `stats["ai_artifact"]`; the builtin statistics stay next to it.
- **Manuals**: after the backend's own index is READY the PDF is also sent to `/v1/manuals/index`. Its
  status is logged, not mirrored into a column: the backend index is the source of truth for
  `index_status`, and an AI index that is missing only makes incidents fall back (`MANUAL_NOT_INDEXED`).
Migration `0002` adds `incidents.ai_source` (`ai`/`builtin`, NULL for older rows) and `incidents.degraded`
(JSON list, default `[]`), both in `IncidentRead`; no existing field changed (bot contract). In production
`sidecar` requires `FIBO_AI_TOKEN` (24+ characters). The dashboard assistant and the operator chat stay
on the backend's own LLM client.

### D79. Released with known review findings (team decision)
The code and security reviews of the AI integration (`a65ba30..HEAD`) found no CRITICAL issues. Two
security MEDIUMs were fixed (spectrogram size cap, retake-advice length cap). The team chose to package
without fixing the rest; they only affect `FIBO_AI_PROVIDER=sidecar`, except the last MEDIUM item:
- HIGH: an AUDIO incident with no stored AI baseline artifact gets the "no baseline" card from the AI
  (`BASELINE_MISSING` is an input error) although the builtin baseline could analyse it.
- HIGH: a 400/413/415 from the AI on the risk or panel-photo path raises `AIRequestRejected`, which only
  the incident, manual and baseline paths catch → HTTP 500 there.
- MEDIUM: severe tool wear from the AI is not a level floor; retrying an incident adds another
  spectrogram and keeps the previous transcript / z-score; the shared `.env` gives `OPENAI_API_KEY` to the
  backend and bot containers too (`env_file`); raw AI error text can reach logs; per-item lengths of AI
  causes/actions are not capped.
- MEDIUM (also builtin): earlier review fixes changed builtin behaviour on purpose — fixed product class L
  (D71), default `limit=50` on the baseline/manual lists, explicit nulls refused in `MachineUpdate`.
Mitigation for the demo: keep the default `builtin` provider unless the AI service is deployed and tested.
Update: both HIGH findings and the tool-wear floor were fixed with the real-API adapters (D81); the
spectrogram duplication no longer applies (the real answer carries no spectrogram).

### D80. AI service source added to ai/fibo_ai (from fibo_ai.zip)
The team supplied the AI service package (`fibo_ai`, 74 Python files: FastAPI app `api/main.py`, risk,
audio, speech, vision, RAG, incident card, safety, assistant). Committed first exactly as received
(`chore(ai): add AI service source as received`), without macOS metadata and `.pyc` files, then formatted
with ruff at the `ai/` line length (120). Lint config: FastAPI `Depends`/`Body` defaults are allowed
(B008); long schema descriptions and prompt texts keep E501; blocking `pathlib` calls in two async
modules (`facade.py`, `rag/service.py`, ASYNC240) are a known TODO. Not in the archive: tests,
Dockerfile, dependency list with versions, `openapi.json`, trained artifacts. Third-party imports used:
fastapi, pydantic, pydantic_settings, httpx, numpy, pandas, scipy, sklearn, shap, joblib, matplotlib,
PIL, rapidfuzz, yaml (plus ffmpeg/ffprobe/tesseract binaries and an optional PANNs checkpoint download).
The code was only parsed, not run. Its defaults differ from the integration docs (`llm_provider="fake"`,
`llm_model="gemini-1.5-flash"`, `ai_stub_mode=True`); checking its real API against the backend's assumed
response shapes (D73, `ai_gateway/adapters.py`) is the next step.

### D81. Backend adapters rewritten to the AI service's real API
With the service source in `ai/fibo_ai` (D80), the guessed contract of D76/D78 was checked against its
Pydantic schemas. Routes, auth, error envelope and codes, health, baselines and manuals matched; incident,
risk and panel did not. Now:
- **Incident request:** `context` is the service's `MachineContext` (`criticality` low/medium/high from 1..3,
  KZT as integers, extra fields are forbidden there) — the old integer criticality was a 400.
- **Incident answer:** level `attention` → `warning`; verdict = first finding (else `headline`);
  `possible_causes`/`actions_now` items with `manual_page`; `manual_pages` is the AI's citation list
  (allow-list); the backend still renders its own plain text and ignores the Telegram-HTML `card_text`.
  The answer has **no transcript**, so the backend safety layer runs on every text the AI returns
  (findings, causes, actions) and `signals.safety_triggers` add a stop header. The AI's own
  `audio_level` and `photo_wear` are level floors (fixes the review's wear finding). The AI z-score uses
  another embedder and scale, so it is shown on the card but not stored in `audio_zscore` (which feeds
  the backend's risk index).
- **Audio:** without a stored AI baseline artifact (after one attempt to build it) an AUDIO incident goes
  to the builtin path with `ai_baseline_missing`; a `BASELINE_MISSING` answer does the same (review HIGH 1).
- **Risk:** `RiskRequest` with the latest reading as `readings` (`spindle_load_pct`, `temp_c`,
  `tool_hours` from tool wear, `runtime_h`, ambient from the profile) + `context`; `p_model_cal` and the
  AI's `factors` (stored as `shap` entries with `source: "ai"`). A rejected request falls back to the local
  model with a `degraded` note instead of a 500 (review HIGH 2); the panel photo does the same.
- **Panel:** AI field names mapped to reading fields (`spindle_load_pct` → `load_pct`, `temp_c` →
  `temperature_c`, `runtime_h` → `operating_hours`), word confidences mapped, null values skipped.
- 401/403 from the service is tagged `ai_auth_failed`; manual status reads `pages_indexed`.
`tests/test_ai_contract.py` validates the test samples (`tests/ai_samples.py`), the service's own schema
example and the requests the backend builds — including bodies captured from real pipeline runs — against
the service's models, so the mocks cannot drift again. Still only tested against mocks: the service was not
started (no Docker, no dependency list).

### D82. First live run: OpenAI key, GPT-6 Luna, Whisper; AI service run locally
The team's OpenAI key is in the git-ignored `.env` only (`FIBO_LLM_API_KEY`, `OPENAI_API_KEY`, mode 600) —
not in code, git or the release zip (rule R2); it was shared in a chat, so it should be rotated after the
hackathon. `.env`: `FIBO_AI_MODE=live`, `FIBO_LLM_MODEL` / `FIBO_LLM_VISION_MODEL` = `gpt-6-luna`,
`FIBO_WHISPER_MODEL=whisper-1`. Live through the backend's own code (builtin provider): Whisper transcribed a
synthesized Russian voice note correctly; symptom extraction and the incident card came back as valid JSON
(about 3 s each); a tool call (`get_ranking`) and a panel-photo request worked — on a photo without a
display every value came back null, nothing invented. The Telegram token answers `getMe`; no real chat.
AI service run locally (no Docker) from the new `ai/requirements.txt`, called by the backend gateway:
- It sent `temperature: 0.0`, which gpt-6-luna rejects (HTTP 400): every LLM call would have failed.
  Fixed: with `LLM_REASONING_EFFORT` set, `reasoning_effort` is sent instead (`core/llm/openai_compat.py`).
- Without its model file it answered `p_model_cal: 0.0`; the backend now takes the probability only when
  `coverage.used` contains `"model"`, otherwise "unknown" — never "0 %".
- **Blocker, not fixed:** `fibo_ai.zip` has no `configs/` folder (levels, audio_thresholds,
  safety_keywords, risk_index, rag, asr, vision, feature_labels, pricing), no `reports/metrics.json`, no
  `artifacts/`. `/v1/incident/analyze` crashes on `configs/levels.yaml` (500, so the backend falls back to
  builtin as designed) and `/readyz` answers 503. These hold thresholds and safety word lists, so they are
  not re-invented here; the sidecar needs them from the AI developer.
- Speech in the AI service is local faster-whisper only (no OpenAI provider), see `ai/requirements-ml.txt`.
  `ai/Dockerfile` is written but unverified (no Docker here, no configs/).
Compose: the bot container now gets only its five variables (no AI or dashboard keys).

## Local registration and production UI fixes (2026-11-09)

- `scripts/dev.sh` applies migrations and starts API + web together. The local embedding default is the offline hash backend; it is not described as semantic retrieval. Live AI still requires configured credentials.
- Onboarding questions are available immediately from the shared built-in catalog. Network/AI adaptation is optional and does not replace typed answers in the background. Registration submits a real form and opens the dashboard on success.
- Web sessions refresh through `/auth/me`, use an HttpOnly SameSite cookie for authenticated media, and retain the signed token for API compatibility. Local signing keys persist in ignored `backend/data/` with mode 0600. Browser requests are checked against the signed-in workshop; trusted bot/shared-key clients retain their integration access.
- Daily activity is counted from readings, new incidents and resolved incidents in the requested timezone. Charts display stored data, including zero-activity days; demo chart data from the component registry was removed.
- A reading save schedules its own risk calculation. The form no longer issues a second calculation that could duplicate scores or turn a successful save into a visible error. Ranking selects one latest score per machine, including equal-timestamp ties.
- Assistant tools now support reading trends, maintenance schedules and hypothetical maintenance comparisons, all scoped to the workshop. Offline mode is labelled as rules, not represented as a live language model. A live provider failure falls back explicitly with `source=builtin` and `degraded` reasons.
- Maintenance intervals are calendar hours in the current risk engine. UI labels now say this; machine editing preserves the local date/time of tool changes.

- The public Vite/nginx proxy no longer injects the trusted integration API key. Sign-up, sign-in and public profile questions work without that key; data requests use the signed browser session. This prevents anonymous visitors from inheriting internal integration access.
