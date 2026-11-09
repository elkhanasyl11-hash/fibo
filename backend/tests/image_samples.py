"""Synthetic test photos (no real images in the repository)."""

import cv2
import numpy as np


def tool_image(seed: int = 0) -> np.ndarray:
    """A sharp 'tool' picture: grey background, a bright blade with many fine edges and lines."""
    rng = np.random.default_rng(seed)
    image = np.full((480, 640, 3), 120, np.uint8)
    cv2.rectangle(image, (120, 160), (520, 320), (200, 200, 200), -1)
    for _ in range(40):
        x1, y1, x2, y2 = (int(v) for v in rng.integers(0, 640, 4))
        cv2.line(image, (x1, y1 % 480), (x2, y2 % 480), (30, 30, 30), 2)
    for y in range(170, 320, 12):
        cv2.line(image, (130, y), (510, y), (90, 90, 90), 1)
    return image


def damaged(image: np.ndarray, size: float) -> np.ndarray:
    """Black 'chip' covering roughly `size` (0..1) of the picture."""
    out = image.copy()
    h, w = out.shape[:2]
    half_w, half_h = int(w * np.sqrt(size) / 2), int(h * np.sqrt(size) / 2)
    cv2.rectangle(out, (w // 2 - half_w, h // 2 - half_h), (w // 2 + half_w, h // 2 + half_h), (0, 0, 0), -1)
    return out


def blurred(image: np.ndarray) -> np.ndarray:
    return cv2.GaussianBlur(image, (0, 0), 8)


def jpeg(image: np.ndarray) -> bytes:
    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
    assert ok
    return data.tobytes()
