"""Safe saving and loading of uploaded and generated files.

Saving an upload (save_upload):
  1. The extension of the client's filename must be on the allow-list for this kind of file.
  2. The declared MIME type must be on the allow-list too.
  3. The first bytes must match the real file format ("magic bytes"), so a renamed .exe is refused.
  4. The file is streamed to disk in 1 MB chunks; above max_upload_mb we stop and delete it.
  5. It is stored as media/<kind>/<yyyy>/<mm>/<uuid4>.<ext>. The client's filename is never used
     in the path (it could contain "../" or odd characters); routers keep it only in the DB.
The function returns the path RELATIVE to media_dir; only relative paths go into the database.

Loading (resolve_media_path): the relative path is joined to media_dir, resolved (following
"..", symlinks) and must still be inside media_dir. This is the path-traversal guard.
"""

import uuid
from pathlib import Path, PurePosixPath

from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import NotFoundError, PayloadTooLargeError, UnsupportedMediaError
from app.db.base import utcnow

CHUNK_SIZE = 1024 * 1024

_AUDIO_EXT = {"ogg", "oga", "mp3", "wav", "m4a"}
_AUDIO_MIME = {
    "audio/ogg",
    "audio/opus",
    "application/ogg",
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/vnd.wave",
    "audio/mp4",
    "audio/x-m4a",
    "audio/m4a",
}
_PHOTO_EXT = {"jpg", "jpeg", "png", "webp"}
_PHOTO_MIME = {"image/jpeg", "image/png", "image/webp"}

ALLOWED: dict[str, tuple[set[str], set[str]]] = {
    "voice": (_AUDIO_EXT, _AUDIO_MIME),
    "audio": (_AUDIO_EXT, _AUDIO_MIME),
    "photo": (_PHOTO_EXT, _PHOTO_MIME),
    "manual": ({"pdf"}, {"application/pdf"}),
}


def _looks_like(ext: str, head: bytes) -> bool:
    """Check the file signature ("magic bytes") against the extension's format."""
    if ext in {"ogg", "oga"}:
        return head.startswith(b"OggS")
    if ext == "wav":
        return head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    if ext == "mp3":
        return head.startswith(b"ID3") or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)
    if ext == "m4a":
        return head[4:8] == b"ftyp"
    if ext in {"jpg", "jpeg"}:
        return head.startswith(b"\xff\xd8\xff")
    if ext == "png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == "webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if ext == "pdf":
        return head.startswith(b"%PDF-")
    return False


def _extension(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def _new_relative_path(kind: str, ext: str) -> PurePosixPath:
    now = utcnow()
    return PurePosixPath(kind, f"{now:%Y}", f"{now:%m}", f"{uuid.uuid4().hex}.{ext}")


async def save_upload(upload: UploadFile, kind: str, max_bytes: int | None = None) -> str:
    """Validate and store an uploaded file. Returns its path relative to media_dir."""
    if kind not in ALLOWED:
        raise ValueError(f"unknown upload kind: {kind}")
    allowed_ext, allowed_mime = ALLOWED[kind]
    ext = _extension(upload.filename)
    mime = (upload.content_type or "").split(";")[0].strip().lower()
    if ext not in allowed_ext or mime not in allowed_mime:
        raise UnsupportedMediaError(
            f"File type not allowed for {kind}",
            details={"extension": ext, "content_type": mime, "allowed_extensions": sorted(allowed_ext)},
        )

    limit = max_bytes if max_bytes is not None else settings.max_upload_mb * 1024 * 1024
    relative = _new_relative_path(kind, ext)
    target = settings.media_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    try:
        with target.open("wb") as out:
            while chunk := await upload.read(CHUNK_SIZE):
                if written == 0 and not _looks_like(ext, chunk[:16]):
                    raise UnsupportedMediaError(f"File content does not look like .{ext}")
                written += len(chunk)
                if written > limit:
                    raise PayloadTooLargeError(
                        f"File is larger than {limit // (1024 * 1024)} MB", details={"max_bytes": limit}
                    )
                out.write(chunk)
        if written == 0:
            raise UnsupportedMediaError("File is empty")
    except BaseException:
        target.unlink(missing_ok=True)  # never leave half-written or rejected files behind
        raise
    return relative.as_posix()


def save_generated(data: bytes, kind: str, ext: str) -> str:
    """Store a file the backend produced itself (spectrogram, heatmap). Returns the relative path."""
    relative = _new_relative_path(kind, ext)
    target = settings.media_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return relative.as_posix()


def resolve_media_path(relative: str) -> Path:
    """Turn a stored relative path into an absolute path, refusing anything outside media_dir."""
    media_root = settings.media_dir.resolve()
    if not relative or relative.startswith(("/", "\\")) or "\x00" in relative:
        raise NotFoundError("File not found")
    candidate = (media_root / relative).resolve()
    if not candidate.is_relative_to(media_root) or not candidate.is_file():
        raise NotFoundError("File not found")
    return candidate
