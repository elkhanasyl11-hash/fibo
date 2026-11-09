"""Live smoke test of a running Fibo stack (backend + AI service). NOT part of pytest or CI.

Usage (stack started with `docker compose --profile ai up` and FIBO_AI_PROVIDER=sidecar):
    python scripts/smoke_live.py --backend http://localhost:8000 --voice sample.ogg --machine-id 1 \
        --telegram-id 123456

It makes at most MAX_AI_REQUESTS requests that reach the AI service (and through it, OpenAI), prints only
status codes and field names — never keys, tokens or card text — and exits non-zero on the first failed
check. Secrets come from the environment: FIBO_BOT_SHARED_SECRET (bot endpoints) and
FIBO_DASHBOARD_API_KEY (dashboard endpoints); they are sent as headers and never printed.
Checks: health reports the sidecar ready; a voice incident reaches OPEN with ai_source "ai"; the card is
plain text with page numbers only; a risk recompute answers with a model version.
"""

import argparse
import os
import sys
import time

import httpx

MAX_AI_REQUESTS = 10
POLL_SECONDS, POLL_LIMIT = 2.0, 30


def check(condition: bool, label: str) -> None:
    print(("PASS " if condition else "FAIL ") + label)
    if not condition:
        sys.exit(1)


def _wait_for_incident(client: httpx.Client, incident_id: int, headers: dict) -> dict:
    incident: dict = {}
    for _ in range(POLL_LIMIT):
        incident = client.get(f"/incidents/{incident_id}", headers=headers).json()
        if incident.get("status") in {"open", "failed"}:
            break
        time.sleep(POLL_SECONDS)
    return incident


def main() -> None:
    parser = argparse.ArgumentParser(description="Live smoke test of a running Fibo stack")
    parser.add_argument("--backend", default="http://localhost:8000")
    parser.add_argument("--voice", required=True, help="a short voice message (ogg/wav) describing a symptom")
    parser.add_argument("--machine-id", type=int, required=True)
    parser.add_argument("--telegram-id", type=int, required=True, help="a registered operator")
    args = parser.parse_args()
    bot = {"X-Fibo-Bot-Token": os.environ.get("FIBO_BOT_SHARED_SECRET", "")}
    dashboard = {"X-Fibo-Api-Key": os.environ.get("FIBO_DASHBOARD_API_KEY", "")}
    ai_requests = 0

    with httpx.Client(base_url=args.backend.rstrip("/") + "/api/v1", timeout=60) as client:
        health = client.get("/health").json()
        ai_requests += 2  # /readyz + /v1/meta/models
        check(health.get("ai_provider") == "sidecar", "health: ai_provider is sidecar")
        check(health.get("ai_sidecar") == "ready", f"health: ai_sidecar = {health.get('ai_sidecar')}")

        with open(args.voice, "rb") as voice:
            files = {"file": (os.path.basename(args.voice), voice, "audio/ogg")}
            form = {"telegram_id": str(args.telegram_id), "machine_id": str(args.machine_id), "mode": "auto"}
            accepted = client.post("/ingest/voice", data=form, files=files, headers=bot)
        ai_requests += 1  # /v1/incident/analyze (the AI service calls OpenAI from there)
        check(accepted.status_code == 202, f"ingest voice: HTTP {accepted.status_code}")
        incident = _wait_for_incident(client, accepted.json()["incident_id"], bot)
        check(incident.get("status") == "open", f"incident status = {incident.get('status')}")
        source, degraded = incident.get("ai_source"), incident.get("degraded")
        check(source == "ai", f"ai_source = {source}, degraded = {degraded}")
        text = incident.get("card_text") or ""
        check("<" not in text and ">" not in text, "card_text is plain text")
        check(all(isinstance(p, int) for p in incident.get("manual_pages", [])), "manual_pages are numbers")

        score = client.post("/risk-scores/recompute", json={"machine_id": args.machine_id}, headers=dashboard)
        ai_requests += 1  # /v1/risk/predict
        check(score.status_code == 200, f"risk recompute: HTTP {score.status_code}")
        version = (score.json() or [{}])[0].get("model_version")
        check(bool(version), f"risk model_version = {version}")
    check(ai_requests <= MAX_AI_REQUESTS, f"AI requests used: {ai_requests} (limit {MAX_AI_REQUESTS})")


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as exc:  # no traceback: it could echo request headers in some httpx versions
        print(f"FAIL backend not reachable: {type(exc).__name__}")
        sys.exit(2)
