"""Bounded, EXIF-safe image decoding through ffmpeg."""

import base64
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from fibo_ai.core.errors import FiboError
from fibo_ai.core.files import MAX_IMAGE_BYTES, sniff_media_type


@dataclass(frozen=True)
class ImageData:
    width: int
    height: int
    gray: NDArray[np.uint8]
    jpeg: bytes


def read_image_bytes(file_path: str | None, image_b64: str | None, shared_dir: Path) -> bytes:
    if bool(file_path) == bool(image_b64):
        raise FiboError("VALIDATION_ERROR", "Provide exactly one image input", 400)
    if image_b64:
        try:
            raw = base64.b64decode(image_b64, validate=True)
        except ValueError as exc:
            raise FiboError("UNSUPPORTED_MEDIA", "Image is not valid base64", 415) from exc
    else:
        candidate = Path(str(file_path))
        if not candidate.is_absolute():
            candidate = shared_dir / candidate
        resolved = candidate.resolve()
        root = shared_dir.resolve()
        if root not in resolved.parents:
            raise FiboError("INVALID_FILE_PATH", "Image must be inside FIBO_SHARED_DIR", 400)
        try:
            raw = resolved.read_bytes()
        except FileNotFoundError as exc:
            raise FiboError("FILE_NOT_FOUND", "Image was not found", 404) from exc
    if len(raw) > MAX_IMAGE_BYTES:
        raise FiboError("FILE_TOO_LARGE", "Image exceeds 10 MB", 413)
    if sniff_media_type(raw[:32]) not in {"image/png", "image/jpeg"}:
        raise FiboError("UNSUPPORTED_MEDIA", "Only PNG and JPEG images are supported", 415)
    return raw


def decode_image(raw: bytes, *, max_dimension: int = 1600) -> ImageData:
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:stream_tags=rotate:stream_side_data=rotation",
            "-of",
            "json",
            "pipe:0",
        ],
        input=raw,
        capture_output=True,
        check=False,
        timeout=10,
    )
    if probe.returncode:
        raise FiboError("UNSUPPORTED_MEDIA", "Image could not be decoded", 415)
    try:
        stream = json.loads(probe.stdout)["streams"][0]
        width, height = int(stream["width"]), int(stream["height"])
        rotation = 0.0
        for side_data in stream.get("side_data_list", []):
            if "rotation" in side_data:
                rotation = float(side_data["rotation"])
                break
        if not rotation and stream.get("tags", {}).get("rotate"):
            rotation = float(stream["tags"]["rotate"])
        if int(abs(rotation)) % 180 == 90:
            width, height = height, width
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise FiboError("UNSUPPORTED_MEDIA", "Image dimensions are unavailable", 415) from exc
    scale = min(1.0, max_dimension / max(width, height))
    scaled_w, scaled_h = max(1, round(width * scale)), max(1, round(height * scale))
    vf = f"scale={scaled_w}:{scaled_h}"
    gray_result = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            "pipe:0",
            "-vf",
            vf,
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "pipe:1",
        ],
        input=raw,
        capture_output=True,
        check=False,
        timeout=15,
    )
    jpeg_result = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            "pipe:0",
            "-vf",
            vf,
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "pipe:1",
        ],
        input=raw,
        capture_output=True,
        check=False,
        timeout=15,
    )
    expected = scaled_w * scaled_h
    if gray_result.returncode or len(gray_result.stdout) != expected or jpeg_result.returncode:
        raise FiboError("UNSUPPORTED_MEDIA", "Image could not be normalized", 415)
    gray = np.frombuffer(gray_result.stdout, dtype=np.uint8).reshape(scaled_h, scaled_w)
    return ImageData(width, height, gray, jpeg_result.stdout)


def laplacian_variance(gray: NDArray[np.uint8]) -> float:
    image = gray.astype(np.float32)
    laplacian = (
        -4.0 * image
        + np.roll(image, 1, axis=0)
        + np.roll(image, -1, axis=0)
        + np.roll(image, 1, axis=1)
        + np.roll(image, -1, axis=1)
    )
    return float(np.var(laplacian[1:-1, 1:-1])) if min(gray.shape) > 2 else 0.0
