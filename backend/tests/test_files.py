"""File storage: allow-lists, magic bytes, size limit, stored path shape, path-traversal guard."""

import io
import re

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.core.config import settings
from app.core.errors import NotFoundError, PayloadTooLargeError, UnsupportedMediaError
from app.storage import files

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
OGG = b"OggS" + b"\x00" * 100


def upload(data: bytes, filename: str, content_type: str) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(data), filename=filename, headers=Headers({"content-type": content_type})
    )


async def test_valid_photo_is_stored_under_uuid_name(started_app):
    relative = await files.save_upload(upload(PNG, "../../evil name.png", "image/png"), kind="photo")
    assert re.fullmatch(r"photo/\d{4}/\d{2}/[0-9a-f]{32}\.png", relative)
    assert "evil" not in relative
    assert (settings.media_dir / relative).read_bytes() == PNG


async def test_voice_ogg_is_accepted(started_app):
    relative = await files.save_upload(upload(OGG, "voice.oga", "audio/ogg"), kind="voice")
    assert relative.startswith("voice/") and relative.endswith(".oga")


@pytest.mark.parametrize(
    ("data", "filename", "content_type"),
    [
        (PNG, "photo.exe", "image/png"),  # extension not allowed
        (PNG, "photo.png", "application/x-msdownload"),  # MIME not allowed
        (b"MZ\x90\x00" + b"\x00" * 100, "photo.png", "image/png"),  # content is not a PNG
        (PNG, "noextension", "image/png"),
        (b"", "empty.png", "image/png"),
    ],
)
async def test_rejected_uploads_leave_no_file(started_app, data, filename, content_type):
    before = set(settings.media_dir.rglob("*.*"))
    with pytest.raises(UnsupportedMediaError):
        await files.save_upload(upload(data, filename, content_type), kind="photo")
    assert set(settings.media_dir.rglob("*.*")) == before


async def test_too_large_upload_is_rejected_and_deleted(started_app):
    before = set(settings.media_dir.rglob("*.*"))
    big = PNG + b"\x00" * 5000
    with pytest.raises(PayloadTooLargeError):
        await files.save_upload(upload(big, "big.png", "image/png"), kind="photo", max_bytes=1000)
    assert set(settings.media_dir.rglob("*.*")) == before


@pytest.mark.parametrize(
    "evil",
    ["../test.db", "../../etc/passwd", "photo/../../test.db", "/etc/passwd", "", "photo\x00.png", "photo"],
)
def test_path_traversal_is_refused(started_app, evil):
    with pytest.raises(NotFoundError):
        files.resolve_media_path(evil)


def test_symlink_out_of_media_is_refused(started_app, tmp_root):
    secret = tmp_root / "secret.txt"
    secret.write_text("top secret")
    link = settings.media_dir / "link.txt"
    link.symlink_to(secret)
    with pytest.raises(NotFoundError):
        files.resolve_media_path("link.txt")


async def test_media_endpoint_serves_files_and_blocks_traversal(client, tmp_root):
    relative = await files.save_upload(upload(PNG, "a.png", "image/png"), kind="photo")
    ok = await client.get(f"/api/v1/media/{relative}")
    assert ok.status_code == 200 and ok.content == PNG
    assert ok.headers["content-type"] == "image/png"

    # %2e%2e%2f = "../" — encoded so the HTTP client does not normalise it away before sending.
    for path in ["..%2f..%2ftest.db", "%2e%2e/%2e%2e/test.db", "photo/%2e%2e%2f%2e%2e%2f..%2ftest.db"]:
        response = await client.get(f"/api/v1/media/{path}")
        assert response.status_code == 404, path
        assert response.json()["error"]["code"] == "not_found"
