"""Image quality gate. Runs BEFORE OCR so a blurry scan is never 'read' and guessed at."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError

from app.config import SETTINGS

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


def blur_score(path: Path) -> float:
    """Variance of the Laplacian. Sharp text scores high; blurred text scores near zero."""
    img = Image.open(path).convert("L")
    if max(img.size) > 1600:
        img.thumbnail((1600, 1600))
    a = np.asarray(img, dtype=np.float64)
    lap = a[1:-1, 1:-1] * -4 + a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:]
    return float(lap.var())


def check_quality(path: Path) -> tuple[bool, float | None, str]:
    """Return (passed, score, reason). PDFs are not scored here; they go straight to OCR."""
    if path.suffix.lower() not in IMAGE_SUFFIXES:
        return True, None, ""
    try:
        score = blur_score(path)
    except (UnidentifiedImageError, OSError):
        return False, None, "file is not a readable image"
    if score < SETTINGS["blur_threshold"]:
        return False, score, "the scan is too blurry to read"
    return True, score, ""
