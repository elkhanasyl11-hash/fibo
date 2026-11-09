"""Fibo Vision: is this phone photo good enough to judge? (plain image maths, no AI)

  sharpness   variance of the Laplacian of the grey image. The Laplacian responds to edges; a
              blurred photo has weak edges, so the variance is low. Below FIBO_PHOTO_MIN_SHARPNESS
              -> "blurry".
  brightness  mean grey level 0..255: below the minimum -> "too dark", above the maximum ->
              "overexposed".
The image is first scaled so its longer side is 1024 px, so phone resolution does not change the
numbers. A rejected photo never reaches the LLM; the operator is asked to retake it.
"""

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from app.core.config import settings

ANALYSIS_SIDE = 1024
REASON_TEXT_RU = {
    "blurry": "фото размытое",
    "too_dark": "фото слишком тёмное",
    "overexposed": "фото пересвечено",
    "unreadable": "файл не читается как изображение",
}


@dataclass
class PhotoQuality:
    ok: bool
    sharpness: float
    brightness: float
    reasons: list[str] = field(default_factory=list)

    @property
    def text_ru(self) -> str:
        return ", ".join(REASON_TEXT_RU[r] for r in self.reasons)


def load_grey(path: Path) -> np.ndarray | None:
    """Grey image scaled to ANALYSIS_SIDE on its longer side; None if it cannot be decoded."""
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None
    scale = ANALYSIS_SIDE / max(image.shape)
    if scale < 1:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return image


def check_quality(path: Path) -> PhotoQuality:
    grey = load_grey(path)
    if grey is None:
        return PhotoQuality(False, 0.0, 0.0, ["unreadable"])
    sharpness = float(cv2.Laplacian(grey, cv2.CV_64F).var())
    brightness = float(grey.mean())
    reasons = []
    if sharpness < settings.photo_min_sharpness:
        reasons.append("blurry")
    if brightness < settings.photo_min_brightness:
        reasons.append("too_dark")
    elif brightness > settings.photo_max_brightness:
        reasons.append("overexposed")
    return PhotoQuality(not reasons, round(sharpness, 1), round(brightness, 1), reasons)


def pixel_difference(reference: Path, current: Path) -> float | None:
    """Mean absolute grey-level difference (0..255) after resizing both to 256x256.

    A rough, deterministic hint passed to the vision model (and used by the mock): 0 = identical,
    small = same scene, large = very different. It is NOT a defect measure on its own.
    """
    first, second = load_grey(reference), load_grey(current)
    if first is None or second is None:
        return None
    size = (256, 256)
    return round(float(np.abs(cv2.resize(first, size).astype(float) - cv2.resize(second, size)).mean()), 2)
