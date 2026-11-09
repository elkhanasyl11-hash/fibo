"""Small deterministic patch-memory anomaly detector used when anomalib is unavailable.

The fallback uses frozen hand-crafted local appearance descriptors (RGB, local contrast,
and horizontal/vertical gradients) rather than a pretrained ResNet. It is an engineering
fallback, not a claim of benchmark-equivalent PatchCore performance.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image

GRID = 8
INPUT_SIZE = 128


def patch_features(image_bytes: bytes) -> NDArray[np.float32]:
    image = (
        Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((INPUT_SIZE, INPUT_SIZE), Image.Resampling.BILINEAR)
    )
    rgb = np.asarray(image, dtype=np.float32) / 255.0
    gray = rgb.mean(axis=2)
    grad_x = np.pad(np.abs(np.diff(gray, axis=1)), ((0, 0), (0, 1)))
    grad_y = np.pad(np.abs(np.diff(gray, axis=0)), ((0, 1), (0, 0)))
    features: list[list[float]] = []
    cell = INPUT_SIZE // GRID
    for row in range(GRID):
        for col in range(GRID):
            y0, x0 = row * cell, col * cell
            region = rgb[y0 : y0 + cell, x0 : x0 + cell]
            gray_region = gray[y0 : y0 + cell, x0 : x0 + cell]
            features.append(
                [
                    *region.mean(axis=(0, 1)).tolist(),
                    float(gray_region.std()),
                    float(grad_x[y0 : y0 + cell, x0 : x0 + cell].mean()),
                    float(grad_y[y0 : y0 + cell, x0 : x0 + cell].mean()),
                ]
            )
    return np.asarray(features, dtype=np.float32)


def patch_distances(features: NDArray[np.float32], memory: NDArray[np.float32]) -> NDArray[np.float32]:
    # Chunked squared distances keep CPU memory bounded, even for a larger memory bank.
    output = np.empty(features.shape[0], dtype=np.float32)
    memory_norm = np.sum(memory * memory, axis=1)
    for start in range(0, features.shape[0], 128):
        chunk = features[start : start + 128]
        distances = np.sum(chunk * chunk, axis=1, keepdims=True) + memory_norm[None, :] - 2.0 * chunk @ memory.T
        output[start : start + len(chunk)] = np.sqrt(np.maximum(distances.min(axis=1), 0.0))
    return output.reshape(GRID, GRID)


@dataclass
class PatchMemory:
    memory: NDArray[np.float32]
    threshold: float

    @classmethod
    def fit(
        cls,
        train_features: list[NDArray[np.float32]],
        validation_features: list[NDArray[np.float32]],
        *,
        coreset_size: int = 512,
        threshold_quantile: float = 0.99,
    ) -> PatchMemory:
        if not train_features or not validation_features:
            raise ValueError("PatchMemory needs normal training and validation images")
        all_patches = np.vstack(train_features).astype(np.float32)
        count = min(coreset_size, len(all_patches))
        rng = np.random.default_rng(42)
        selected = np.sort(rng.choice(len(all_patches), count, replace=False))
        memory = all_patches[selected]
        validation_scores = [
            float(np.quantile(patch_distances(features, memory), 0.99)) for features in validation_features
        ]
        return cls(memory, float(np.quantile(validation_scores, threshold_quantile)))

    def score(self, image_bytes: bytes) -> tuple[float, NDArray[np.float32]]:
        heatmap = patch_distances(patch_features(image_bytes), self.memory)
        return float(np.quantile(heatmap, 0.99)), heatmap


def heatmap_png(image_bytes: bytes, heatmap: NDArray[np.float32]) -> bytes:
    source = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    resized = (
        np.asarray(
            Image.fromarray(np.uint8(np.clip(heatmap / max(float(heatmap.max()), 1e-8), 0, 1) * 255)).resize(
                source.size, Image.Resampling.BILINEAR
            ),
            dtype=np.float32,
        )
        / 255.0
    )
    color = np.zeros((*resized.shape, 3), dtype=np.float32)
    color[..., 0] = resized
    color[..., 1] = np.maximum(0.0, 1.0 - np.abs(resized * 2.0 - 1.0))
    overlay = np.asarray(source, dtype=np.float32) * 0.55 + color * 255.0 * 0.45
    output = io.BytesIO()
    Image.fromarray(np.uint8(np.clip(overlay, 0, 255))).save(output, format="PNG")
    return output.getvalue()


def top_bbox(heatmap: NDArray[np.float32], fraction: float = 0.15) -> list[float]:
    threshold = float(np.quantile(heatmap, 1.0 - fraction))
    rows, cols = np.where(heatmap >= threshold)
    if not len(rows):
        return [0.0, 0.0, 1.0, 1.0]
    return [
        round(float(rows.min() / GRID), 4),
        round(float(cols.min() / GRID), 4),
        round(float((rows.max() + 1) / GRID), 4),
        round(float((cols.max() + 1) / GRID), 4),
    ]
