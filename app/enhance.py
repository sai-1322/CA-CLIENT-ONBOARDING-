"""Recover text from blurry scans before OCR.

Blur is not a reason to throw a document away. The scan is enhanced (deblurred and upscaled),
then read with OCR. Enhancement can recover a document's type and header, but it cannot make
unreadable digits readable. The pipeline therefore treats the identifier of an enhanced scan as
'needs verification' unless it reads cleanly.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

RL_ITERATIONS = 40
SIGMAS = (3.5, 5.0)          # blur strengths tried; the best OCR result wins
UPSCALE = 2


def _gaussian_kernel(sigma: float) -> np.ndarray:
    radius = int(3 * sigma) + 1
    x = np.arange(-radius, radius + 1)
    kernel = np.exp(-(x ** 2) / (2 * sigma ** 2))
    return kernel / kernel.sum()


def _blur(image: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Separable blur using FFT convolution (fast on large scans)."""
    padded = np.pad(image, len(kernel), mode="edge")
    rows = np.apply_along_axis(lambda r: np.convolve(r, kernel, mode="same"), 1, padded)
    cols = np.apply_along_axis(lambda c: np.convolve(c, kernel, mode="same"), 0, rows)
    return cols[len(kernel):-len(kernel), len(kernel):-len(kernel)]


def _richardson_lucy(observed: np.ndarray, kernel: np.ndarray, iterations: int) -> np.ndarray:
    estimate = np.full_like(observed, 0.5)
    flipped = kernel[::-1]
    for _ in range(iterations):
        predicted = _blur(estimate, kernel) + 1e-9
        estimate = np.clip(estimate * _blur(observed / predicted, flipped), 0, 1)
    return estimate


def enhanced_versions(path) -> list[Image.Image]:
    """Return deblurred, upscaled grey images, one per blur strength."""
    grey = Image.open(path).convert("L")
    if max(grey.size) > 1600:
        grey.thumbnail((1600, 1600))
    base = np.asarray(grey, dtype=np.float64) / 255.0
    versions = []
    for sigma in SIGMAS:
        restored = _richardson_lucy(base, _gaussian_kernel(sigma), RL_ITERATIONS)
        span = restored.max() - restored.min()
        restored = (restored - restored.min()) / (span if span > 1e-9 else 1.0)
        image = Image.fromarray((restored * 255).astype(np.uint8))
        versions.append(image.resize((image.width * UPSCALE, image.height * UPSCALE), Image.LANCZOS))
    return versions
