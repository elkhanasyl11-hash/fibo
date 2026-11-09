"""Collects every v1 router. main.py mounts this under /api/v1.

New routers are added here phase by phase.
"""

from fastapi import APIRouter

from app.api.v1 import (
    activity,
    assistant,
    auth,
    baselines,
    health,
    incidents,
    ingest,
    machines,
    manuals,
    media,
    profiles,
    readings,
    reports,
    risk_scores,
    users,
    web_ai,
    workshops,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(profiles.router)
api_router.include_router(auth.router)
api_router.include_router(web_ai.router)
api_router.include_router(workshops.router)
api_router.include_router(users.router)
api_router.include_router(users.bot_router)
api_router.include_router(machines.router)
api_router.include_router(baselines.router)
api_router.include_router(baselines.vision_router)
api_router.include_router(manuals.router)
api_router.include_router(reports.router)
api_router.include_router(activity.router)
api_router.include_router(assistant.router)
api_router.include_router(readings.router)
api_router.include_router(readings.vision_router)
api_router.include_router(incidents.router)
api_router.include_router(ingest.router)
api_router.include_router(ingest.vision_router)
api_router.include_router(risk_scores.router)
api_router.include_router(media.router)
