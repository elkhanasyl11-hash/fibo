# Plan and progress log — AI service integration (FIBO_AI_FIX_AND_INTEGRATION_PROMPT)

Started 2026-11-08 22:52 Asia/Almaty. Feature freeze 2026-11-09 18:00. Deadline 2026-11-09 23:59.

## Step 1 — inventory and baseline (done)

| Item | Found |
| --- | --- |
| Repo | `~/dev/fibo`, clean, HEAD `3d89409` (review fixes after `790c2a9`), Alembic head `0001` |
| AI service source | **Not available.** `./ai`, `./fibo_ai`, `../fibo_ai` absent; a home-folder search found only three loose files on `~/Desktop` (added 22:23): `AI_INTEGRATION.md`, `README_ML.md`, `fibo_ai_client.py`. No app code, `openapi.json`, `scripts/write_readme_ml.py`, `reports/metrics.json`, tests or Dockerfile. The user confirmed these three files are the input. Copied unchanged into `ai/` (R9, decision D73). |
| Baseline tests | backend **194 passed**, bot **26 passed**, AI service: none available; ruff clean (backend, bot) |
| Keys | `OPENAI_API_KEY` / `FIBO_LLM_API_KEY` not set in `.env` → live check will be skipped; Telegram token set |
| Docker | not installed on this Mac → compose end-to-end cannot run here |
| Disk | ~6 GB free |

### ECC components actually installed (section 3.2, real names)

| Purpose | Agent | Skills / commands present | Used in this run |
| --- | --- | --- | --- |
| Plan | `planner`, `architect` | `/plan`, `backend-patterns`, `search-first` | plan written directly (fallback): context budget was ~87% at start |
| Tests first | `tdd-guide` | `tdd-workflow`, `python-testing` | tests written alongside code (fallback) |
| Python quality | `python-reviewer` | `/python-review`, `python-patterns`, `coding-standards` | on the step-5/6 diff |
| ML / eval | `mle-reviewer` | `eval-harness`, `mle-workflow` | not needed: no AI-service evaluation code available |
| Security | `security-reviewer` | `/security-scan`, `security-review` | on the step-5/6 diff |
| DB migration | `database-reviewer` | — | on migration 0002 |
| Docker / deps | `build-error-resolver` | `/build-fix` | no Docker → not applicable |
| Docs | `doc-updater` | `/update-docs` | docs edited directly |
| Final review | `code-reviewer` | `/code-review`, `/test-coverage`, `verification-loop` | step 8 |
| Session | — | `/context-budget`, `/save-session`, `strategic-compact` | — |
| Hooks seen | GateGuard fact-forcing (first Bash / first Write per file), StrategicCompact | — | worked within them (facts stated) |

## Contract mismatches (client vs. AI_INTEGRATION.md vs. this prompt)

1. `create_baseline` sends `clip_count`; the documented request has none → drop it (step 2.3).
2. `analyze_audio` sends query parameters; the documented form is a JSON body with `baseline_ref` → fix.
3. `transcribe` lacks `profile`, `catalog_machines` (documented in §3.3) → add.
4. Errors surface as raw `httpx.HTTPStatusError`; the documented envelope `{"error": {code, message, retriable, details}}` is not parsed → `FiboAIError`.
5. No retries, one 30 s timeout for everything → per-endpoint timeouts and bounded retries.
6. Docs use display names as `machine_id` ("ЧПУ-2"); the prompt requires `m-<id>` + `machine_name`. Echoing `machine_name` is an AI-service change → needs the service code.
7. Docs: "stateless" although baselines and manual indexes are stored; example card shows "3,1σ · Критично" while the measured critical threshold is 16.092σ; latency column looks measured but README_ML says NOT_VALIDATED; section order 3.1, 3.2, 3.5, 3.6, 3.3, 3.4 → doc fixes (step 4.3).
8. Compose host `fibo-ai` and shared dir `/shared` in the docs vs. the prompt's `ai` and `/app/data/media` → the prompt wins.
9. The AI card `card_text` is HTML; the bot needs plain text → the backend renders its own plain card from structured fields.
10. **No `openapi.json`: response shapes are not documented** (except `BaselineArtifact` and the error envelope). The gateway therefore expects the structured card defined in step 3.3 of the prompt and documents every other assumed field; any response that does not match is treated as a contract bug → automatic builtin fallback with `degraded=["ai_contract_mismatch"]`.

## What cannot be done here (reported, not faked)

| Step | Item | Reason |
| --- | --- | --- |
| 2 | contract test against `openapi.json` | file not available → tested against request schemas transcribed from `AI_INTEGRATION.md` |
| 3 | AI-side ids, path guard, structured card | AI service code not available |
| 4 | GPT settings in the AI service, `spectral_z` on DCASE fan, regenerated README_ML, AI image | AI service code, eval script and fan data not available; the backend already implements the same 14-feature z-score (decision D46) |
| 7 | `docker compose up` checks 1–2 | Docker not installed |
| 7 | live GPT smoke | no API key in `.env`, no AI service to call |

## Plan for the remaining steps

| Step | Files | Risk |
| --- | --- | --- |
| 2 | `ai/fibo_ai_client.py`, `ai/tests/` | contract guessed from docs |
| 4 (docs only) | `ai/AI_INTEGRATION.md` | none |
| 5 | `docker-compose.yml` (ai under profile `ai`), `.env.example`, `core/config.py`, `modules/ai_gateway/*`, `api/v1/health.py`, `modules/assistant/llm.py` (reasoning_effort), texts | default `builtin` keeps behaviour identical |
| 6 | migration `0002_ai_provider`, `models/incident.py`, `schemas/incident.py`, `pipelines/incident_pipeline.py`, `machine/service.py`, `api/v1/readings.py`, `machine/audio_baselines.py`, `pipelines/manual_pipeline.py` | assumed response shapes → mismatch falls back |
| 7 | `scripts/smoke_live.py` (not run: no key) | — |
| 8 | README, walkthrough, decisions, zip | — |

## Progress log

- 22:52 step 1 started; 23:05 plan written, AI files copied to `ai/`.
- ~23:00 step 2: client rewritten (typed errors, retries, timeouts, documented bodies); AI tests 0 → 29.
- 23:05 step 3 skipped (needs AI-service code, D75); step 4: only AI_INTEGRATION.md fixes (D75).
- 23:14 step 5: AI gateway (`modules/ai_gateway`), health AI status, Compose profile `ai`, reasoning_effort;
  backend tests 194 → 228, green with `FIBO_AI_PROVIDER=builtin` and `sidecar` (D76, D77).
- 23:24 step 6: incident/risk/panel/baseline/manual paths on the gateway, migration 0002; backend tests
  228 → 241, green in both modes (D78). Manual AI-index status is logged, not mirrored (D78).
- 23:27 step 7: Docker checks 1–2 (compose build, `--profile ai` end-to-end) NOT run — Docker is not
  installed on this laptop and `ai/` has no service source or Dockerfile (D73). Check 3 (builtin suite)
  passes: 241 backend + 26 bot + 29 AI-client tests. Live check NOT run: no `OPENAI_API_KEY` /
  `FIBO_LLM_API_KEY` in `.env` and no AI service to call. `scripts/smoke_live.py` written for the team
  (≤ 10 AI requests, prints no secrets); verified only that it parses arguments and fails cleanly (exit 2)
  when the backend is not reachable.
- 03:14 (9 Nov) step 8: code-reviewer + security-reviewer run (no CRITICAL); 2 security MEDIUMs fixed;
  rest packaged as is by team decision (D79). README AI section, walkthrough, coverage 89 % (backend).
- 9 Nov: AI service source added (D80); adapters rewritten to its real schemas, both review HIGHs fixed,
  contract test against the service's Pydantic models; backend tests 241 → 252 in both modes (D81).
