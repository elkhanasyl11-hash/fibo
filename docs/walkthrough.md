# Fibo backend — walkthrough

Plain-language tour of the code, written for a teammate who did not write it. One section per
build phase. Paths are relative to `backend/`.

---

## Phase 1 — Skeleton

### What exists after this phase

A FastAPI app that starts, connects to SQLite, knows all nine database tables, loads the five
industry profiles, and answers `GET /api/v1/health` and `GET /api/v1/profiles`. No business
logic yet.

### Files

| File | What it does |
| --- | --- |
| `app/main.py` | Creates the FastAPI app and wires everything together. On startup (`lifespan`) it sets up logging, creates the `data/` folders, loads the profiles and tries to load the risk model. No logic of its own. |
| `app/core/config.py` | All settings in one `Settings` class. Values come from environment variables starting with `FIBO_` or from a `.env` file. Defaults are safe for local mock mode. |
| `app/core/logging.py` | Makes every log line a JSON object with the request id in it, so logs can be searched by request or incident. |
| `app/core/middleware.py` | Gives every HTTP request an id (`X-Request-ID`): takes the client's if it is safe, otherwise makes a new one. Puts it into logs, into `request.state`, and into the response header. |
| `app/core/errors.py` | Our error classes (`NotFoundError` → 404, `ConflictError` → 409, …) and the handlers that turn *every* error into the same JSON shape. Unexpected crashes become a generic 500; the traceback goes only to the log. |
| `app/core/security.py` | Two checks used as FastAPI dependencies: the bot's shared secret (`X-Fibo-Bot-Token`) and the dashboard key (`X-Fibo-Api-Key`, off when not configured). |
| `app/db/base.py` | Enums (roles, statuses, levels…), `utcnow()`, the `UTCDateTime` column type, the `str_enum()` column helper, and the `Base` class all models inherit from. |
| `app/db/session.py` | Creates the async database engine and sessions. Turns on SQLite WAL mode, foreign keys and a lock timeout. |
| `app/models/*.py` | One file per table (workshops, users, machines, readings, risk_scores, baselines, manuals, incidents, attachments). Each file's docstring says what the table is for. |
| `app/profiles/loader.py` + `*.yaml` | The five industry profiles and the Pydantic schema that validates them. A broken YAML stops the app at startup with the file name in the message. |
| `app/api/deps.py` | Dependencies routers share: DB session, `Pagination` (limit/offset), auth checks. |
| `app/api/v1/router.py` | Collects all v1 routers; mounted at `/api/v1`. |
| `app/api/v1/health.py` | `GET /health`: pings the DB, reports whether the risk model is loaded, the AI mode, profile count. |
| `app/api/v1/profiles.py` | `GET /profiles`: the profiles with their equipment catalogs. |
| `app/modules/machine/risk_model.py` | **Stub.** Always returns "no model" for now, so the app runs in index-only mode. Real loading comes in phase 3. |
| `alembic/env.py`, `alembic/versions/0001_initial_schema.py` | Database migrations. `alembic upgrade head` creates all tables. The URL comes from the same settings as the app. |
| `tests/` | See "How we know it works" below. |

### How a request flows

```
client ──HTTP──> CORSMiddleware ──> RequestIDMiddleware ──> router (/api/v1/...) ──> endpoint
                                         │                                              │
                                         └── sets request id ──> logs + response header │
                                                                                        ▼
                                  errors.py handlers <── raised AppError / validation error / crash
                                         │
                                         └── {"error": {code, message, details, request_id}}
```

### Things worth understanding

- **Why `UTCDateTime`?** SQLite has no timezone-aware datetime type. If we stored an aware
  datetime and read it back, SQLite would give us a *naive* one, and subtracting it from an aware
  `utcnow()` (e.g. downtime = resolved_at − created_at) would crash. `UTCDateTime` attaches UTC
  when reading and refuses naive datetimes when writing.
- **Why `str_enum()`?** By default SQLAlchemy stores an enum's *name* (`"OPERATOR"`). We want the
  *value* (`"operator"`) in the database, so the data reads naturally and matches the API.
- **Why `passive_deletes=True` on relationships?** Deleting a workshop must delete its machines,
  readings, incidents… The database does this itself (`ON DELETE CASCADE`, enabled by
  `PRAGMA foreign_keys=ON`). `passive_deletes` tells SQLAlchemy not to load all children first.
- **Why are the profile rules checked in code?** `check_consistency` in `loader.py` catches
  mistakes like a food profile that still gives weight to the AI4I model, or a reading range with
  min > max, before the demo instead of during it.
- **Index-only mode.** Without trained model files, `app.state.risk_model` is `None`. Later phases
  compute the risk index from the other signals; `/health` shows `risk_model_loaded: false`.

### How we know it works

`pytest` (27 tests) checks:
- `/health` answers 200 with `database: ok`, `ai_mode: mock`, `risk_model_loaded: false`.
- Error format for 404 (unknown route and our `NotFoundError`), 405, 422 (field details), 500
  (generic message, no secret text leaks), request id echo and replacement of unsafe ids.
- Bot token / dashboard key checks.
- All five profiles load; only metalworking uses the model; broken/missing YAML is rejected.
- Models: enums stored as values, timestamps come back in UTC, naive datetimes are refused, the
  criticality CHECK works, deleting a workshop cascades, deleting a user sets `incidents.user_id`
  to NULL.
- Migration: `alembic upgrade head` on an empty DB produces exactly the schema of the models
  (Alembic's own comparison finds no difference), and `downgrade base` works.
- `.env.example` parses into safe dev defaults.

---

## Phase 2 — Core CRUD, file storage, demo seed

### What exists after this phase

The dashboard can create workshops, users and machines, add readings and see the incident
feed; the bot can register users by invite code and look them up. Uploaded files are stored
safely and served back through `/media`. `python -m app.db.seed` fills the database with two
labelled demo workshops.

### New files

| File | What it does |
| --- | --- |
| `app/schemas/common.py` | `Money` (tenge, always returned as a string `"15000.00"`) and `UTCDatetime` (input datetimes must have a timezone, otherwise 422). |
| `app/schemas/{workshop,user,machine,reading,incident,risk_score}.py` | Request/response shapes of each resource. These are the frontend's contract (see `/docs`). |
| `app/services/workshops.py` | Create a workshop with a random 6-character invite code (no look-alike characters such as 0/O, 1/I). |
| `app/services/users.py` | Web users, bot registration by invite code (one Telegram account = one workshop), list of masters. |
| `app/services/machines.py` | Lookups (`get_in_workshop_or_404` hides machines of other workshops), the machine summary page. |
| `app/services/readings.py` | Checks a reading against the workshop profile, saves it, reading history. |
| `app/services/incidents.py` | Creates incidents (used by ingest in phase 4), feed filters, and **resolve**: downtime and loss. |
| `app/storage/files.py` | Saves uploads safely and resolves stored paths (see below). |
| `app/api/v1/workshops.py`, `users.py`, `machines.py`, `readings.py`, `incidents.py`, `media.py` | Thin HTTP layers over the services. `users.py` holds two routers: `/users` (dashboard) and `/bot/*` (bot token). |
| `app/modules/machine/service.py` | **Stub** `recompute_risk(machine_id)`: already called after each new reading; real logic in phase 3. |
| `app/db/seed.py` + `seed_data.py` | Demo data: the logic and the fixed content, kept apart. |

### Flows

**Bot registration**
```
bot ── POST /bot/register {telegram_id, invite_code "demo01 ", role, language}  (X-Fibo-Bot-Token)
        └─ users_service.register_bot_user
             ├─ normalise code ("DEMO01") → find workshop, else 404
             ├─ telegram_id already used → 409
             └─ create user → 201
bot ── GET /bot/users/{telegram_id} → {user, workshop, machines}   (the bot's machine keyboard)
```

**New reading**
```
dashboard ── POST /readings {machine_id, load_pct, ...}
   └─ readings_service.create_reading
        ├─ load machine → its workshop → its profile (YAML)
        ├─ validate_reading_values: every value needs a range in the profile and must be inside it;
        │   extra keys must be profile extra fields; recorded_at not in the future → else 422 listing ALL bad fields
        └─ save → 201, then BackgroundTasks runs recompute_risk(machine_id)  (stub until phase 3)
```

**Resolve an incident**
```
PATCH /incidents/{id}/resolve
   └─ incidents_service.resolve_incident
        ├─ already RESOLVED → 409
        ├─ resolved_at = now
        ├─ compute_downtime: hours = (resolved_at − created_at) / 3600 s
        │                    loss  = hours × machine.downtime_cost_per_hour_kzt, Decimal, rounded to 0.01
        └─ status RESOLVED, save
```
Example: reported 10:00, resolved 13:30, 15 000 ₸/h → 3.5 h, loss "52500.00".

### File storage (`app/storage/files.py`)

Saving an upload checks, in order: extension allow-list → declared MIME allow-list → the first
bytes really are that format (e.g. PNG starts with `\x89PNG`) → size, counted while streaming
in 1 MB chunks. Any failure deletes the partial file. The file is stored as
`media/<kind>/<yyyy>/<mm>/<uuid4>.<ext>`; the client's filename never appears in the path. The
database stores only the part after `media/`.

Reading a file back (`resolve_media_path`) joins the stored path to `media/`, resolves it
(this follows `..` and symlinks) and refuses anything that ends up outside `media/`. Requests
like `/media/..%2f..%2f.env` get a 404.

### Demo seed

`python -m app.db.seed` creates two workshops, both named with "(демо-данные)":
- metalworking `DEMO01`: 6 machines, 3 users (operator, master, owner), 30 days of readings
  (twice a day), 5 incidents. "ЧПУ-1" has rising load and temperature in the last week (the
  risky machine for the phase 3 ranking).
- bakery `DEMO02`: 3 machines with humidity readings, 1 incident in Kazakh.
Every row has `is_demo=True`. A second run does nothing; `--reset` deletes **only** demo
workshops (everything inside goes with them through ON DELETE CASCADE) and recreates them.
Resolved demo incidents use the same `compute_downtime` as the API.

### How we know it works

64 tests in total. New in this phase:
- `test_incidents.py`: resolve with fixed timestamps (10:00 → 13:30 at 15 000 ₸/h = 3.5 h and
  52 500.00 ₸), rounding to the tiyn, 409 on double resolve, feed filters, attachment URLs.
- `test_files.py`: path traversal (`../`, absolute paths, NUL byte, symlink out of `media/`,
  URL-encoded `..%2f` over HTTP), wrong extension/MIME/content, empty and oversized files leave
  nothing on disk, stored names are UUIDs.
- `test_workshops_users.py`, `test_machines.py`, `test_readings.py`: CRUD, invite codes, bot
  token, money format, timezone rule, profile range validation, history filters, the background
  recompute hook.
- `test_seed.py`: counts, everything labelled demo, idempotent, `--reset` leaves real data alone.

---

## Phase 3 — Risk engine

### What exists after this phase

Every machine gets a **risk score**: a calibrated failure probability (when the AI4I model applies),
a **risk index** 0–1 combining all available signals, an **anomaly flag**, and a **priority in tenge**
used to rank maintenance work. Scores are recomputed after every new reading (background task),
on demand, and "as of" past days in the demo seed (for the chart). A what-if endpoint shows how
the score would change after e.g. a tool change, without saving anything.

### New / changed files

| File | What it does |
| --- | --- |
| `ml/train_risk_model.py` | Trains XGBoost on AI4I 2020, calibrates it, writes `ml/artifacts/*` and `metrics.json`. |
| `ml/artifacts/` | The trained model (committed, so a fresh checkout works without retraining). |
| `app/modules/machine/risk_model.py` | Feature names (shared with training), leakage list, `RiskModel` (load, predict, SHAP), `get_active_model()`. |
| `app/modules/machine/feature_map.py` | Workshop readings → the 8 model features, and the list of approximations used. |
| `app/modules/machine/inputs.py` | Loads readings, incidents and maintenance for one machine "as of" a moment. |
| `app/modules/machine/risk_index.py` | Normalises each signal to 0..1 and combines them with the profile weights. |
| `app/modules/machine/anomaly.py` | Isolation Forest: is the latest reading unusual for this machine? |
| `app/modules/machine/priority.py` | Priority in tenge. |
| `app/modules/machine/service.py` | `compute_score` (the one place a score is computed), recompute, ranking, what-if, history. |
| `app/schemas/risk_score.py`, `app/api/v1/risk_scores.py` | API: recompute, ranking, what-if, risk history. |
| `app/profiles/loader.py` | + `get_profiles()`: profiles loaded once, also usable from background tasks. |
| `app/db/seed.py` | + 7 days of daily risk scores per demo machine. |

### Training (`python -m ml.train_risk_model --data path/to/ai4i2020.csv`)

```
CSV (10 000 rows, 3.4 % failures)
 └─ build_feature_frame: Type → type_L/M/H, 5 physical columns renamed; UDI, Product ID,
    TWF/HDF/PWF/OSF/RNF dropped (the failure-mode flags ARE the answer → leakage)
 └─ split 60/20/20 stratified, seed 42
 └─ XGBoost (300 trees, depth 4), scale_pos_weight = 28.6 (negatives / positives)
 └─ isotonic calibration on the validation split  (raw score → real failure frequency)
 └─ threshold = best F1 on validation
 └─ metrics on the untouched test split → metrics.json
```
Test results: **ROC-AUC 0.976, PR-AUC 0.735, Brier 0.0205 → 0.0139 after calibration**;
at the threshold 43 of 68 failures caught, 8 false alarms (precision 0.84, recall 0.63).
We do not show accuracy: "never fails" would already be 96.6 % accurate.

### One score, step by step (`service.compute_score`)

```
machine + workshop profile
 ├─ inputs.load_inputs(as_of): readings of the last 30 days, incidents, hours since maintenance
 ├─ model? (loaded AND profile.model_applicable AND recent rpm+load reading AND tool_changed_at)
 │    feature_map  → 8 features + assumptions   (load% → torque, criticality → L/M/H, …)
 │    RiskModel.predict → calibrated p, SHAP factors (the 3 type columns merged into one)
 ├─ Isolation Forest on the machine's own readings → is_anomaly
 ├─ signals:  p_model, s_audio, s_visual, s_overdue, s_history   (each 0..1 or None)
 ├─ risk_index = Σ w·s / Σ w over AVAILABLE signals (weights from the profile YAML)
 └─ priority_kzt = risk_index × {0.5,1,1.5}[criticality] × cost/h × avg repair h (+ risk × batch value for food)
```
Where the model is not used, the response says why (`model_not_used_reasons`), e.g.
`model_not_applicable_for_profile` for a bakery, `risk_model_not_loaded` in index-only mode.

### Things worth understanding

- **SHAP explains the raw model, not the calibrated probability.** TreeExplainer works on the
  XGBoost output in log-odds. Calibration is monotonic (a higher raw score never gets a lower
  probability), so the sign and ranking of the factors still hold. A positive contribution
  pushes towards failure.
- **Why calibrate?** With `scale_pos_weight` the model treats every failure as ~29 rows, so its raw
  outputs are much too high to read as probabilities. Isotonic regression maps them to frequencies
  observed on the validation split. It is a step function, so very safe machines can show
  `failure_probability = 0` — read it as "lower than anything seen failing in validation".
- **Missing ≠ zero.** If a signal is unavailable (no sound check this week), it is left out and the
  other weights are renormalised, instead of pretending the risk from it is 0.
- **Assumptions are part of every answer.** The torque, air-temperature and machine-class mappings
  are approximations; each score lists the ones it used, plus warnings when a value is outside the
  training data (the model then extrapolates).
- **what-if never writes.** It computes the current score and a scenario with the same
  `compute_score` function on plain copies of the readings; the test checks the row count.
- **Background recompute** gets only the machine id; it opens its own DB session and takes the
  model and profiles from `get_active_model()` / `get_profiles()`.

### How we know it works

86 tests. New: leakage guard (feature list, feature frame and committed artifacts), training
pipeline on a synthetic AI4I-shaped table (artifacts + metrics written, reloadable), predictions
monotonic in wear/torque with 6 SHAP factors sorted by size, feature-map rules and every
approximation code, signal normalisation and renormalised combination, priority formula with and
without batch value, Isolation Forest (too little history / outlier / typical), API: index-only
mode, ranking sorted with top-3 SHAP and `inputs_used`, what-if lowers risk and saves nothing,
background recompute after a reading, risk history order.

---

## Phase 4 — Telegram bot, speech, safety layer, incident pipeline

### What exists after this phase

An operator records a voice message in Telegram → the bot uploads it → the backend answers 202
at once and processes it in the background → the bot polls and sends back the **incident card**
with buttons **Resolved / Call mechanic / Manual page**. Dangerous words (smoke, sparks, electric
shock, …) always produce the stop instruction, even if the AI is down. Everything runs offline in
mock mode.

### New files (backend)

| File | What it does |
| --- | --- |
| `app/modules/assistant/llm.py` | `LLMClient` interface; `LiveLLMClient` (OpenAI-compatible HTTP, timeouts, retries, JSON repair); `MockLLMClient`; `get_llm_client()` picks one from `FIBO_AI_MODE`. |
| `app/modules/assistant/mock_fixtures.py` | The mock's fixed answers (keyword rules). Deliberately ignores safety and invents page 999, so tests prove our rules work. |
| `app/modules/assistant/speech.py` | Recording → 16 kHz mono WAV (ffmpeg, or libsndfile without ffmpeg), speech detection (webrtcvad), transcription. |
| `app/modules/assistant/extraction.py` | Transcript → `SymptomExtraction` (symptom, conditions, urgency, clarifying question). |
| `app/modules/assistant/safety.py` | **Not AI.** Regex rules on word stems (ru + kk) + profile phrases → stop header; critical sensor + high urgency → inspect header. |
| `app/modules/assistant/card.py` | LLM card → `finalize` (only retrieved pages, safety forces CRITICAL) → message text. |
| `app/modules/assistant/rag.py` | **Stub** until phase 7: always "not found in the manual". |
| `app/modules/machine/audio.py` | **Stub** until phase 5: "no baseline recorded" (true until baselines can be uploaded). |
| `app/pipelines/incident_pipeline.py` | `process_incident(id)`: the steps below, with stage logging and failure handling. |
| `app/api/v1/ingest.py` | `POST /ingest/voice`, `/ingest/audio` (bot token): save file, create incident, schedule pipeline, 202. |
| `app/api/v1/incidents.py` | + `POST /incidents/{id}/retry`, `POST /incidents/{id}/escalate`. |

### New files (bot, `bot/`)

| File | What it does |
| --- | --- |
| `bot/main.py` | Starts long polling; global error handler (log + apology, polling never stops). |
| `bot/api_client.py` | The only code that calls the backend (bot token header, 30 s timeout, errors → `FiboApiError`). |
| `bot/texts.py` | Every message in ru and kk (a test checks both have the same keys). |
| `bot/keyboards.py` | Menu, machine choice, roles, languages, card buttons (`res:/esc:/pg:<id>`). |
| `bot/states.py` | Dialogue states: registration, "next voice is a machine sound", add machine. |
| `bot/delivery.py` | Poll the incident (1, 2, 3, 5, 5… s; 60 s, then background up to 3 min), send the card HTML-escaped. |
| `bot/handlers/start.py` | `/start`: invite code → role → language → `POST /bot/register`. |
| `bot/handlers/machines.py` | Menu buttons, machine choice (remembered), "My machines", add machine (masters). |
| `bot/handlers/voice.py` | Voice/audio message → `/ingest/voice` (`mode=machine_sound` after "🔊 Записать звук"). |
| `bot/handlers/callbacks.py` | Resolved → resolve; Call mechanic → escalate + message every master; Manual page. |

### The pipeline, step by step

```
bot ──voice.ogg──> POST /ingest/voice ──> save file, incident RECEIVED ──> 202 {incident_id}
                                                  │ BackgroundTasks (id only)
                                                  ▼
process_incident(id)   own DB session
 1  status PROCESSING; SAFETY on the caption (saved at once if triggered)
 2  prepare_wav (16 kHz mono) → VAD
      ├─ input AUDIO ("record machine sound") or no speech → audio branch → (phase 5) / "record a baseline"
      └─ speech → transcribe → save transcript
 3  SAFETY on the transcript → saved at once: safety_triggered, level CRITICAL, stop text
 4  extraction (LLM) → RAG (phase 7) → card (LLM) → finalize:
        pages not retrieved are dropped; safety → level CRITICAL, header first
 5  save card, status OPEN → recompute the machine's risk
 any error → status FAILED, error_message "<stage>: <error>"; safety text and level stay
bot polls GET /incidents/{id} → OPEN: card + buttons │ FAILED: safety text (if any) + "try again"
```

### Things worth understanding

- **Safety comes first and is saved first.** The stop instruction is written to the incident
  before the LLM is even called. If the AI then fails, the incident is FAILED but the bot still
  shows the stop text. `finalize` makes the level CRITICAL whatever the model said, and a retry
  never switches `safety_triggered` off.
- **The mock is adversarial on purpose.** It never raises the level for dangerous words and always
  cites page 999. The tests pass only because our own rules fix that.
- **Mode lives in the data.** "Record machine sound" creates an incident with `input_type=audio`,
  so a retry knows what to do without remembering the original request.
- **No ffmpeg on the laptop?** libsndfile (inside the `soundfile` package) decodes Telegram's
  OGG/Opus, WAV and MP3 directly; ffmpeg is still the main path in Docker.
- **The bot is thin.** No database, no ML; FSM memory only holds the chosen machine and language.

### How we know it works

Backend: 132 tests. New: safety phrases ru/kk (17 dangerous, 5 harmless), normalisation, profile
phrases, level rule and merge; card rules (invented page dropped, safety forces CRITICAL even
when the model says normal, "not found in manual" stated); live LLM client (5xx/429/timeout retried,
4xx not, JSON repaired once, missing config); audio conversion without ffmpeg (stereo 44.1 kHz WAV,
Telegram-style OGG/Opus, garbage rejected), VAD on silence; **end-to-end in mock mode**: upload →
card OPEN with transcript, safety keyword → CRITICAL with stop header, AI failure → FAILED with the
safety card kept → retry → OPEN, machine sound → "record a baseline", silence → audio branch,
escalate → masters, rejected uploads (401/404/415).
Bot: 12 tests — texts complete in both languages, callback data ≤ 64 bytes, API client (auth
header, error mapping, multipart), polling backoff and budget, HTML escaping, safety text on failure.

---

## Phase 5 — Machine sound vs. its own baseline

### What exists after this phase

A master records 3 short "healthy" sounds of a machine (bot: ⚙️ Мои станки → 🎚 Эталонный звук,
or the dashboard). Later, any operator can record the machine again ("🔊 Записать звук станка");
Fibo says how far the sound is from normal (in σ), what changed ("шумность спектра +46σ"), shows
a spectrogram baseline-vs-now, and the deviation feeds the machine's risk index (`s_audio`).

### New / changed files

| File | What it does |
| --- | --- |
| `app/modules/machine/audio.py` | The method (pure functions): 10 s clip, 19 windows, 14 features, baseline mean/std, z-score, level, description, spectrogram PNG. |
| `app/modules/machine/audio_baselines.py` | Database side: store a reference recording + recompute combined stats; score a new recording; attach the spectrogram. |
| `app/api/v1/baselines.py` | `POST /machines/{id}/baselines/audio`, `POST …/photo`, `GET …/baselines`. |
| `app/pipelines/incident_pipeline.py` | Audio branch now: score → LLM card → `finalize(min_level=measured level)`. Reorganised into small stage functions sharing a `Context`. |
| `app/modules/assistant/card.py` | `finalize(..., min_level)`: the model may raise the measured level, never lower it. |
| `ml/eval_audio_mimii.py` | Runs the same method on MIMII/DCASE data, writes ROC-AUC per machine id to `ml/artifacts/audio_metrics.json`. |
| `bot/…` | Masters: "🎚 Эталонный звук" → choose machine → voice messages until 3 recordings. |

### The method in one picture

```
recording ─► 16 kHz mono ─► exactly 10 s (cut, or loop if 2–10 s)
          ─► 19 windows of 1 s (50% overlap)
          ─► per window 14 numbers:
               8 band energies (dB) │ loudness │ spectral centre │ 85% roll-off │ flatness │ ZCR │ crest factor
baseline  = mean and std of every number over all windows of all reference recordings
            (std ≥ 5% of |mean| and ≥ 1e-6, so a feature that never varies cannot explode)
new sound ─► z = (value − mean) / std per feature, averaged over its 19 windows
          ─► audio_z = √(mean of z²)          < 2 normal │ 2–3 warning │ > 3 critical
          ─► description = the 3 largest |z| with plain names, e.g. "пик-фактор (удары) +30σ"
```

### Things worth understanding

- **Why classic features, not a neural network?** Every number has a physical meaning a mechanic
  understands (louder, noisier, more impacts, more energy at 3 kHz). The baseline is the
  machine's *own* sound, so no training data from other machines is needed.
- **Absolute dB (`ref=1.0`).** Using "relative to the loudest moment" would hide a machine that got
  louder overall. The phone must be held roughly the same way each time; the card says so.
- **Why loop short recordings?** Padding with silence would add silent windows and look abnormal;
  repeating keeps the sound's statistics.
- **The measured level is a floor.** The mock card always says "normal" for audio; the test proves
  the incident is still CRITICAL when z > 3, because `finalize(min_level=...)` keeps it.
- **One limitation:** averaging z² over 14 features dilutes a deviation that shows in only one
  feature (a new 3 kHz whine: its band +4.8σ, overall z ≈ 1.4 on a quiet tone). The evaluation
  also reports the "largest single |z|" variant for comparison (`roc_auc_max_abs_z`).
- **Baseline storage:** every reference recording keeps its own 19×14 numbers (`embedding`), and the
  newest row holds the combined statistics (`stats`), so adding a recording never re-decodes old audio.

### How we know it works

147 backend tests (+ 12 bot). New: 19×14 features, length rules (cut / loop / < 2 s rejected), std floor,
**same recording vs. its baseline < 2**, **noise / tone / knock all score higher** (spec acceptance),
added noise is critical and explained, level boundaries, valid spectrogram PNG; API: 3 uploads →
`ready`, list, 422 for a 1 s recording, healthy sound → normal + spectrogram served by `/media`,
noisy sound → CRITICAL although the mock card said normal, `s_audio = 1.0` in the risk score;
evaluation script on a tiny synthetic DCASE-shaped folder.
**Real data (DCASE 2020 slider, 4 machine ids): mean ROC-AUC 0.63** (0.82 / 0.68 / 0.61 / 0.42) —
few false alarms, but subtle slider anomalies mostly stay below z = 2 (details in decisions D46). Live: Telegram-style OGG/Opus
recordings through the bot client gave z = 0.2 (healthy), 14.0 (noise), 8.2 (knocks).

---

## Phase 6 — Fibo Vision: photo quality, comparison with a reference, panel readings

### What exists after this phase

- **Tool / part photo** (bot: 📷): checked for blur and lighting; if fine, compared with the
  machine's reference photo by the multimodal model → card with a level and confidence (never a
  wear percentage).
- **Display photo** (bot: 🖥, or dashboard): the model reads the numbers on a CNC/controller screen;
  plain code keeps only fields the profile knows and values inside the valid ranges; the person sees
  the list and presses ✅ (or ✏️ to correct "field=number") — **only then** is a reading saved.
- **Reference photo** (bot for masters: 📸 Эталонное фото, or `POST /machines/{id}/baselines/photo`).

### New / changed files

| File | What it does |
| --- | --- |
| `app/modules/vision/quality.py` | Sharpness = variance of the Laplacian, brightness = mean grey; `pixel_difference` hint. Plain maths, no AI. |
| `app/modules/vision/compare.py` | `VisualInspection` schema, `inspect()` (reference + photo → multimodal LLM), `reference_photo()`. |
| `app/modules/vision/panel_ocr.py` | `PanelReadout` schema, `read_panel()` (LLM), `validate()` (profile fields + ranges → accepted / rejected). |
| `app/pipelines/incident_pipeline.py` | Photo branch: quality → reference → inspection → card (inspection level is a floor). |
| `app/api/v1/ingest.py` | + `POST /ingest/photo`. |
| `app/api/v1/readings.py` | + `POST /readings/panel-photo` → suggestions only (`saved: false`). |
| `app/modules/assistant/mock_fixtures.py` | Mock vision: judges by pixel difference (it cannot see); mock panel values per profile, one deliberately unreadable. |
| `bot/bot/handlers/photo.py` | Photo flows, ✅/✏️ confirmation, corrections parser. |

### Flows

```
📷 photo ─► /ingest/photo ─► incident (photo) ─► pipeline:
      safety on caption ─► quality: blurry/dark/overexposed? ─► "retake" card (level normal)
                       ─► no reference photo?               ─► "add a reference" card
                       ─► inspect(reference, photo) ─► card ─► finalize(min_level = inspection level)

🖥 photo ─► /readings/panel-photo ─► quality (422 if bad) ─► read_panel (LLM) ─► validate (profile)
      ─► {values, rejected, saved: false}  ── nothing in the database ──
      bot: list + ✅ / ✏️  ──✅──► POST /readings (source=panel) ─► saved, risk recomputed
```

### Things worth understanding

- **Why check quality without AI first?** A blurry photo would make any model guess. Two numbers
  (edge strength and mean brightness) catch the common phone mistakes before we spend an API call.
- **Why can the model not save readings?** OCR misreads happen (a "1" for a "7"). A wrong load or
  temperature would silently change the risk score, so a person must look at the numbers first.
  The endpoint physically has no code path that writes a reading.
- **No wear percentages.** The schema has only a level and a confidence; the prompt forbids
  percentages, and a test checks the verdict contains none.
- **The mock vision.** It cannot see, so it uses the pixel difference to the reference
  (≈0 identical, 12–30 noticeable, > 30 large). Live mode sends both images to the multimodal model.

### How we know it works

159 backend + 16 bot tests. New: quality (sharp ok, blurry, too dark, unreadable file), pixel
difference, panel validation (unknown field, unreadable, out of range; bakery extra fields), images
sent as data URLs; end-to-end: **blurry photo rejected** with a "retake" card, missing reference,
same-as-reference normal, damaged tool CRITICAL although the mock card said normal and without
invented pages or percentages, safety caption on a photo; **panel values are not saved** (reading
count unchanged) until `POST /readings` with source=panel; blurry panel photo → 422; out-of-range
value rejected. Bot: corrections parser, escaped display, extra-field split in the reading body.
Live (bot client → server): blurry → retake, same → 🟢, chipped → 🔴 "скол", panel → suggestions →
corrected → saved.

---

## Phase 7 — Manual search (RAG) with page citations

### What exists after this phase

A master uploads a machine's PDF passport (bot: ⚙️ → 📄 Паспорт, or the dashboard). Fibo cuts it
into page-tagged pieces and stores them as vectors. When an incident is processed, the most relevant
pieces of **that machine's** manual are given to the card, the card cites their page numbers, and
the bot's 📖 button sends the text of those pages. If nothing relevant is found, the card says
"not found in the manual" — and a page the model invents is always removed.

### New / changed files

| File | What it does |
| --- | --- |
| `app/modules/assistant/embeddings.py` | e5-small via onnxruntime (tokenize → model → mean over tokens → normalise), `query:`/`passage:` prefixes; offline `HashEmbedder` for tests; one-time model download. |
| `app/modules/assistant/chroma.py` | Persistent Chroma client, collections `manuals` and `profile_kb` (cosine). |
| `app/modules/assistant/rag_index.py` | PDF → page texts (PyMuPDF) → scanned-page detection → 800/150 chunks per page → vectors; profile notes. |
| `app/modules/assistant/rag.py` | `retrieve()` (this machine's READY manuals, similarity threshold, profile notes), `page_excerpts()`. |
| `app/pipelines/manual_pipeline.py` | Background indexing: INDEXING → READY / FAILED, scanned-page warning. |
| `app/api/v1/manuals.py` | Upload (202), list, status. `GET /incidents/{id}/manual-excerpts` in `incidents.py`. |
| `app/profiles/kb/*.md` | Short "symptom → cause → action" notes per industry, loaded at startup. |
| `bot/bot/handlers/manuals.py` | PDF upload for masters, waits until indexed. `callbacks.py`: 📖 sends page texts. |

### Flow

```
PDF ─► POST /machines/{id}/manuals (202) ─► background index_manual:
        pages (PyMuPDF) ─► page < 50 chars? = "scanned" (warning, OCR out of scope)
        ─► chunks ≤ 800 chars, 150 overlap, never across pages ─► "passage: …" ─► e5 ─► Chroma
           metadata {machine_id, manual_id, page}

incident ─► query = symptom + machine type/model ─► "query: …" ─► e5
         ─► Chroma: nearest 5 chunks WHERE machine_id = X AND manual_id ∈ READY manuals of X
         ─► keep similarity ≥ 0.83 ─► card (LLM) ─► finalize: cited pages ∩ retrieved pages
```

### Things worth understanding

- **Prefixes.** e5 was trained with "query: " / "passage: "; without them its similarities degrade.
- **Why ONNX, not sentence-transformers?** Same model, same vectors in principle; no PyTorch
  (≈1 GB) on a nearly full disk. The int8 export is 118 MB and runs in ~10 ms per sentence.
- **Similarity threshold.** e5 similarities are "compressed" (unrelated Russian text still scores
  ~0.78–0.82), so the threshold is high (0.83). Calibrated on a small set; check with the real manual.
- **Why filter by manual id as well?** Deleting a machine leaves its vectors in Chroma, and SQLite can
  give a new machine the same id. Only manuals that exist and are READY in the database are searched
  (test `test_chunks_of_deleted_manuals_are_ignored`).
- **Invented pages are impossible to keep.** The mock deliberately cites page 999; `finalize` keeps only
  pages present in the retrieved chunks (acceptance test `test_card_cites_only_retrieved_pages`).
- **Profile notes are context, not sources.** They never produce page numbers.

### How we know it works

170 backend + 23 bot tests. New: chunk size/overlap, scanned-page detection, retrieval limited to the
machine (and to existing manuals), unrelated query → not found, re-indexing without duplicates, page
excerpts, profile notes; API: upload → READY with a scanned-page warning, scan-only PDF → FAILED with
a reason, non-PDF → 415, **card cites page 2 and drops page 999**, `/health` chroma ok; every setting
is mirrored in `.env.example`. Bot: manual polling, and a new **wiring test** (every keyboard function,
API method, text key, state used by handlers exists; every button has a handler). Live with the real
e5 model: "шпиндель гудит" retrieved page 3 ("Шпиндельный узел") of a 6-page Russian manual; the card
cited only "стр. 3"; 📖 returned that page's text.

---

## Phase 8 — Reports and the AI assistant

### What exists after this phase

- `GET /reports/summary?workshop_id=&from=&to=`: incidents, downtime hours, losses in ₸, ongoing
  (unresolved) time, MTBF per machine, top causes. `GET /reports/export.csv`: the same as a CSV file.
- `POST /ai/assistant/chat`: the mechanic/owner asks in Russian or Kazakh ("Какой станок самый
  рискованный?"); the model fetches the answer through four tools that can only read this workshop's
  data, and the response lists the machines/incidents it is based on.

### New files

| File | What it does |
| --- | --- |
| `app/modules/reports/downtime.py` | Pure rules: downtime, losses, ongoing time, failures, operating hours (counter or calendar), MTBF, top causes. |
| `app/modules/reports/summary.py` | Loads the period's data, builds the summary, writes the CSV (BOM, `;`). |
| `app/api/v1/reports.py` | The two report endpoints. |
| `app/modules/assistant/tools.py` | Tool definitions + implementations: `get_risk_ranking`, `get_machine_summary`, `get_incidents`, `get_downtime_report`; workshop scope; bad arguments → `{"error": …}`. |
| `app/modules/assistant/chat.py` | The tool-calling loop (≤ 4 rounds, then one answer without tools) and the system prompt. |
| `app/modules/assistant/mock_chat.py` | Offline chat model: picks a tool by keywords, writes the answer only from the tool results (ru/kk). |
| `app/api/v1/assistant.py`, `app/schemas/assistant.py` | The chat endpoint; only user/assistant turns are accepted from clients. |

### The assistant loop

```
client: [{user: "Какой станок самый рискованный?"}], workshop_id, language
  ─► system prompt (workshop, profile context, rules: only tool data, language, demo note)
  ─► model ── tool_calls? ── yes ─► run_tool(name, args, workshop_id from the REQUEST) ─► results ─┐
       ▲                                                                                          │
       └────────────────────────────── up to 4 rounds ◄───────────────────────────────────────────┘
  ─► no tool calls ─► answer  (after 4 rounds: one more call without tools → answer)
  ─► {answer, referenced_machine_ids, referenced_incident_ids, tools_used, is_demo}
```

### Things worth understanding

- **Scope by construction.** No tool takes a workshop id; `run_tool` receives it from the request. Asking
  for another workshop's machine by id simply returns "machine not found in this workshop" (tested).
- **No prompt injection through roles.** Clients may send only `user`/`assistant` turns; `system` or
  `tool` messages are rejected with 422, and the last turn must be the user's.
- **Ongoing downtime is "time since report", not "machine stopped".** Following the spec, unresolved
  incidents count up to now in separate fields (`ongoing_hours`, `ongoing_loss_kzt`); a hum report
  that is never closed keeps growing there. Closing incidents with ✅ keeps reports honest.
- **MTBF** uses the operating-hours counter when readings have it; otherwise calendar time, and the
  row says which (`operating_hours_source`).

### How we know it works

183 backend tests. New: downtime/loss/ongoing/MTBF/causes rules with fixed timestamps, calendar
fallback, period filter, CSV with BOM and TOTAL row, period validation (naive dates, reversed period);
assistant: **"which machine is riskiest" answered from `get_risk_ranking` with the top machine's name,
priority and id** (acceptance), downtime / machine / incident / help answers, Kazakh answer, tools
cannot read another workshop, invalid arguments and unknown tools, bounded loop (4 tool rounds + final
answer), request validation, live client omits an empty tool list. Live (real risk model): "ЧПУ-1
фрезерный: ожидаемые потери 96412.50 ₸, индекс риска 0.43, вероятность отказа 25%…".

---

## Phase 9 — Deployment and documentation

### What exists after this phase

`docker compose up --build` builds two images and starts the backend (migrations run first, then
uvicorn; healthcheck on `/api/v1/health`) and, once the backend is healthy, the bot. The README explains
the product, architecture, AI logic, metrics, assumptions, licences and how to run everything.

### New files

| File | What it does |
| --- | --- |
| `backend/Dockerfile` | python:3.11-slim + ffmpeg, libsndfile1, libgomp1 (OpenMP for xgboost), libglib2.0-0 (OpenCV); non-root user; optional `PRELOAD_EMBEDDINGS` build arg; healthcheck; `alembic upgrade head && uvicorn`. |
| `bot/Dockerfile` | python:3.11-slim, non-root, `python -m bot.main`. |
| `docker-compose.yml` | backend (port 8000, `./data` volume, container paths) + bot (`FIBO_API_URL=http://backend:8000/api/v1`, waits for a healthy backend, `restart: unless-stopped`). |
| `*/.dockerignore` | Keeps venvs, caches, `.env` and data out of the images. |
| `README.md` | The project description for the jury and for teammates. |
| `backend/app/pipelines/incident_steps.py` | Shared pipeline helpers (Context, stage log, safety save, card save) split out of `incident_pipeline.py` to keep files under 250 lines. |

### Things worth understanding

- **Paths differ inside the containers.** `.env` is written for running from `backend/` on a laptop
  (`../data`); compose overrides the data, database, model-artifact and model-cache paths.
- **One writer.** Only the backend touches the SQLite file; the bot has no database at all.
- **Model cache outside the data volume.** A model baked into the image at build time would be hidden by
  the `./data` mount, so `FIBO_MODEL_CACHE_DIR=/app/model-cache`.
- **CPU-only xgboost on Linux.** The default Linux wheel pulls 350 MB of NVIDIA libraries;
  `requirements.txt` chooses `xgboost-cpu` on Linux and `xgboost` on macOS (same version, same import).

### How we know it works (and what is not verified)

- All pinned dependencies resolve to **prebuilt Linux wheels** for x86_64 and arm64 (`uv pip compile
  --python-platform … --only-binary :all:`), so the image build needs no compiler.
- README steps run verbatim in a clean copy of the repository (no `.env`, no database, no model):
  migrations, seed, server start (model downloaded, profile notes indexed, `/health` all ok), backend
  and bot tests and lint, bot start without token (clear error), training (**byte-identical** model and
  metrics) and the audio evaluation (same AUC).
- **Not verified:** `docker compose up` itself — Docker is not installed on the team laptop and the disk
  has ~2 GB free. Run it once on a machine with Docker before the demo.

---

## After phase 9 — spec audit fixes

A read-through of the spec against the code led to small fixes (details in decisions D65–D69):
bot messages now escape every name (with a test that scans the handlers for unescaped values); the
baselines and manuals lists page with `limit`/`offset` and risk history honours `offset`; the three photo
endpoints are listed under "Fibo Vision" in `/docs`; risk scores say `is_demo` (taken from their machine,
loaded together with the score); the OpenCV photo hint runs off the event loop. Two things are documented
rather than built: the safety "inspect" rule cannot meet its two conditions in one incident yet (D67), and
the Kazakh safety keywords are listed for the native-speaker check (D68).

## AI integration — step 5: the AI gateway

### What exists after this step
The backend can use the separate AI service (the "sidecar", `ai/`) as its first choice and its own
modules as the automatic fallback. Nothing uses it yet — step 6 switches the incident, risk, panel, audio
baseline and manual paths over. By default (`FIBO_AI_PROVIDER=builtin`) behaviour is exactly as before.

### New files
- `app/modules/ai_gateway/client.py` — byte copy of `ai/fibo_ai_client.py` (typed `FiboAIError`, retries).
- `errors.py` — `classify()`: what an AI error means (unavailable / input / recoverable / soft / bug).
- `adapters.py` — AI JSON → backend types; anything unexpected raises `ContractError`.
- `provider.py` — `with_fallback()` and one wrapper per path (`analyze_incident`, `predict_risk`, ...).
- `ids.py`, `paths.py` — `ws-3`/`m-42`/`man-7` ids; media paths as the AI container sees them, after the
  backend's own path guard.
- `messages.py` — ru/kk card texts for input errors; `status.py` — the AI part of `/api/v1/health`.

### Things worth understanding
- One rule everywhere: try the AI, adapt its answer, otherwise run the builtin module and say so in
  `degraded`. An operator always gets a card; the only difference is how good it is.
- An input error is different from an outage: if the photo is blurry, the builtin module cannot do
  better, so the operator is asked to retake it instead of getting a guess.
- Safety, citations and the card stay in the backend (rules R4–R6): the gateway only returns data.
- `docker compose --profile ai up` starts the AI service; without the profile the backend starts alone.

### How we know it works
`tests/test_ai_gateway.py` (34 tests): every error class, fallback with the right `degraded` tag,
non-JSON and wrongly shaped answers, input-error cards in both languages, the one retry after a baseline
mismatch, rejected requests, the adapters, path traversal refused, `reasoning_effort` vs `temperature`,
and health with the AI ready, down, slow or disabled. The full suite (228 tests) passes with
`FIBO_AI_PROVIDER=builtin` and with `sidecar` (AI service mocked as down). Not verified: a real AI
service — its code is not in this repository (D73).

## AI integration — step 6: the backend uses the AI service

### What changed
With `FIBO_AI_PROVIDER=sidecar` the incident card, the risk probability, the panel-photo values, the audio
baseline and the manual index come from the AI service first; the old code runs when it fails. Every
incident now says who analysed it (`ai_source`) and what was missing (`degraded`), via migration `0002`.

### New files
- `app/pipelines/incident_ai.py` — builds the AI request, turns the answer into the backend's card.
- `app/pipelines/ai_sync.py` — the AI baseline artifact, stored next to the backend's own statistics.
- `app/modules/machine/risk_model_part.py` — step 3 of the risk score (AI model or local model).
- `alembic/versions/0002_ai_provider.py`.

### Things worth understanding
- The AI proposes, the backend decides: safety words, the danger flag, the measured sound level and the
  citation allow-list are applied by the backend after the AI answers, so the AI can make a card more
  urgent but never less, and can never cite a page it did not retrieve.
- If the photo or recording is unusable, the operator is asked to redo it — no guessing.
- The bot sees the same fields as before plus two new ones it can ignore.

### How we know it works
`tests/test_ai_paths.py` (12 tests) drives the real pipeline with a mocked AI service: cited pages only,
danger in the AI transcript, the AI danger flag, the audio floor and the spectrogram, fallback when the AI
is down, the retake card, a rejected request failing the incident, risk from the AI and its fallback, the
panel photo keeping its response shape, and the baseline artifact after the third recording. The
migration test checks upgrade to `0002`, the models and downgrade. Suite: 241 tests in both modes.

## How an operator's voice message becomes a card

1. The operator records a voice message in Telegram; the bot uploads it to `POST /api/v1/ingest/voice`
   and gets `202` with an incident id at once.
2. A background task (`pipelines/incident_pipeline.py`) marks the incident PROCESSING and runs the
   **safety check on the caption** — a trigger is saved immediately.
3. With `FIBO_AI_PROVIDER=sidecar`, `pipelines/incident_ai.py` sends one request to the AI service (ids
   `ws-`/`m-`, the shared media path, the machine's economics, the stored audio baseline artifact).
   - AI card → the transcript is saved and **safety-checked by the backend first**, an AI danger flag can
     only add a stop header, the sound level is a floor, pages are only those the AI cited; the backend
     renders the plain-text card.
   - Unusable input → a "record again / retake" card.
   - AI down or answering nonsense → step 4, with a `degraded` tag on the incident.
4. Builtin path (default, and the fallback): convert to 16 kHz → VAD → Whisper transcript → safety →
   symptom extraction → manual search → LLM card → the same backend rules.
5. The incident becomes OPEN with `ai_source` = `ai` or `builtin`; the machine's risk is recomputed; the
   bot polls the incident and sends the card with *Resolved / Call mechanic / Manual page* buttons.
