"""Text recognition with two engines.

* "cache"     (default) - reads pre-computed OCR lines from sample_data/ocr_cache.json.
                          Works on any machine with no extra software. Used for the sample pack.
* "tesseract" - runs the real Tesseract OCR engine if it is installed (set OCR_ENGINE=tesseract).

Both return the same shape: a list of {"text": str, "conf": float 0..1}, one entry per line.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.config import OCR_CACHE_PATH, SETTINGS

MAX_PDF_PAGES = 5


class OCRError(Exception):
    """Raised when the OCR engine itself cannot run (not when a document is unreadable)."""


def _cache_lines(filename: str, key: str = "lines") -> list[dict]:
    if not OCR_CACHE_PATH.exists():
        return []
    cache = json.loads(OCR_CACHE_PATH.read_text(encoding="utf-8"))
    return cache.get(filename, {}).get(key, [])


def _tesseract_tsv_lines(image_path: Path, psm: int | None = None) -> list[dict]:
    if shutil.which("tesseract") is None:
        raise OCRError("Tesseract is not installed. Install it, or use OCR_ENGINE=cache.")
    command = ["tesseract", str(image_path), "stdout"]
    if psm is not None:
        command += ["--psm", str(psm)]
    result = subprocess.run(
        command + ["tsv"],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise OCRError(f"Tesseract failed: {result.stderr.strip()[:200]}")
    grouped: dict[tuple, dict] = {}
    for row in result.stdout.splitlines()[1:]:
        parts = row.split("\t")
        if len(parts) < 12 or parts[0] != "5":  # level 5 = word rows
            continue
        text, conf = parts[11].strip(), float(parts[10])
        if not text or conf < 0:
            continue
        key = (parts[2], parts[3], parts[4])  # block, paragraph, line
        group = grouped.setdefault(key, {"words": [], "confs": []})
        group["words"].append(text)
        group["confs"].append(conf)
    lines = []
    for group in grouped.values():
        lines.append({
            "text": " ".join(group["words"]),
            "conf": round(sum(group["confs"]) / len(group["confs"]) / 100, 3),
        })
    return lines


def _pdf_to_pngs(pdf_path: Path, out_dir: Path) -> list[Path]:
    if shutil.which("pdftoppm") is None:
        raise OCRError("pdftoppm is not installed, so PDF pages cannot be rendered for OCR.")
    prefix = out_dir / "page"
    subprocess.run(
        ["pdftoppm", "-r", "200", "-png", "-l", str(MAX_PDF_PAGES), str(pdf_path), str(prefix)],
        capture_output=True, timeout=120, check=False,
    )
    return sorted(out_dir.glob("page*.png"))


def active_engine() -> str:
    """'auto' uses Tesseract when it is installed, otherwise the sample cache."""
    engine = SETTINGS["ocr_engine"]
    if engine == "auto":
        return "tesseract" if shutil.which("tesseract") else "cache"
    return engine


def _score(lines: list[dict]) -> float:
    """Prefer the enhancement that gives the most confident text."""
    return sum(line["conf"] for line in lines if len(line["text"]) >= 3)


def enhanced_tesseract_lines(path: Path) -> list[dict]:
    """Deblur and upscale a blurry image, OCR each version, keep the best one."""
    from app.enhance import enhanced_versions
    best: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        for index, image in enumerate(enhanced_versions(path)):
            out = Path(tmp) / f"enhanced_{index}.png"
            image.save(out)
            lines = _tesseract_tsv_lines(out, psm=6)  # uniform text block: suits blurred scans
            if _score(lines) > _score(best):
                best = lines
    return best


def read_enhanced_lines(path: Path, filename: str) -> list[dict]:
    """OCR for a blurry scan: enhanced reading. Empty list means nothing could be recovered."""
    if active_engine() == "cache":
        return _cache_lines(filename, key="enhanced_lines")
    if active_engine() == "tesseract" and path.suffix.lower() != ".pdf":
        return enhanced_tesseract_lines(path)
    return []


def read_lines(path: Path, filename: str) -> list[dict]:
    """Return OCR lines for a document. Empty list means 'no readable text'."""
    engine = active_engine()
    if engine == "cache":
        return _cache_lines(filename)
    if engine == "tesseract":
        if path.suffix.lower() == ".pdf":
            with tempfile.TemporaryDirectory() as tmp:
                lines: list[dict] = []
                for page in _pdf_to_pngs(path, Path(tmp)):
                    lines.extend(_tesseract_tsv_lines(page))
                return lines
        return _tesseract_tsv_lines(path)
    raise OCRError(f"Unknown OCR engine '{engine}'. Use 'cache' or 'tesseract'.")
