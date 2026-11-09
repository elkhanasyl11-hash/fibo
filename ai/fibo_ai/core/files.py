import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from fibo_ai.core.errors import FileTooLargeError

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_AUDIO_BYTES = 15 * 1024 * 1024  # 15 MB
MAX_PDF_BYTES = 50 * 1024 * 1024  # 50 MB

# Magic bytes signatures
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
PDF_MAGIC = b"%PDF"
RIFF_MAGIC = b"RIFF"
OGG_MAGIC = b"OggS"


def validate_file_size(file_bytes: bytes, max_bytes: int, label: str = "File") -> None:
    if len(file_bytes) > max_bytes:
        raise FileTooLargeError(
            f"{label} size {len(file_bytes)} exceeds limit of {max_bytes} bytes",
            details={"size_bytes": len(file_bytes), "max_bytes": max_bytes},
        )


def sniff_media_type(header: bytes) -> str:
    if header.startswith(PNG_MAGIC):
        return "image/png"
    if header.startswith(JPEG_MAGIC):
        return "image/jpeg"
    if header.startswith(PDF_MAGIC):
        return "application/pdf"
    if header.startswith(RIFF_MAGIC) and len(header) >= 12 and header[8:12] == b"WAVE":
        return "audio/wav"
    if header.startswith(OGG_MAGIC):
        return "audio/ogg"
    if header.startswith(b"ID3") or header.startswith(b"\xff\xfb") or header.startswith(b"\xff\xf3"):
        return "audio/mpeg"
    if len(header) >= 8 and header[4:8] == b"ftyp":
        return "audio/m4a"
    return "application/octet-stream"


@contextmanager
def temporary_file(suffix: str = "", content: bytes | None = None) -> Generator[Path, None, None]:
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        if content is not None:
            os.write(fd, content)
        os.close(fd)
        yield Path(path)
    finally:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


def strip_exif_if_image(image_bytes: bytes) -> bytes:
    # Basic EXIF stripping if Pillow is available, else pass through
    try:
        from io import BytesIO

        from PIL import Image

        img = Image.open(BytesIO(image_bytes))
        data = list(img.getdata())
        image_without_exif = Image.new(img.mode, img.size)
        image_without_exif.putdata(data)
        out_buf = BytesIO()
        fmt = img.format or "PNG"
        image_without_exif.save(out_buf, format=fmt)
        return out_buf.getvalue()
    except Exception:
        return image_bytes
