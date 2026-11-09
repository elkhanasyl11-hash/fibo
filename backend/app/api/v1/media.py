"""System: GET /media/{path} serves stored files (photos, spectrograms) to the dashboard.

The path goes through storage.files.resolve_media_path, which refuses anything outside media_dir.
Protected by the dashboard key: the frontend loads images with fetch() + header and shows them
as blob URLs (a plain <img src> cannot send headers).
"""

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.api.deps import require_dashboard_key
from app.storage.files import resolve_media_path

router = APIRouter(prefix="/media", tags=["System"], dependencies=[Depends(require_dashboard_key)])


@router.get("/{file_path:path}", summary="Download a stored file", response_class=FileResponse)
async def get_media(file_path: str) -> FileResponse:
    path = resolve_media_path(file_path)
    return FileResponse(path, headers={"X-Content-Type-Options": "nosniff"})
