"""Stored media paths -> the path the AI container sees on the shared volume.

The backend stores relative paths (e.g. `voice/2026/11/<uuid>.ogg`). Both containers mount the same
media folder; the AI service sees it at FIBO_AI_SHARED_DIR (`/app/data/media` in Compose). The relative
path first goes through the backend's own path guard (storage.files.resolve_media_path: must exist and
stay inside the media folder), so a path that escapes the folder can never be sent to the AI service.
"""

from app.core.config import settings
from app.storage.files import resolve_media_path


def shared_path(relative: str) -> str:
    local = resolve_media_path(relative)
    inside_media = local.relative_to(settings.media_dir.resolve())
    return (settings.ai_shared_dir / inside_media).as_posix()
