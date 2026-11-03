"""Regenerate sample_data/ocr_cache.json by running real Tesseract OCR on the sample documents.

Covers sample_data/attachments and sample_data/unseen_layouts.

Run this only if you change the sample files. Requires Tesseract (and pdftoppm for the PDF).
    python scripts/build_ocr_cache.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import ocr  # noqa: E402
from app.config import OCR_CACHE_PATH, SAMPLE_ATTACHMENTS_DIR, SAMPLE_DIR  # noqa: E402
from app.quality import check_quality  # noqa: E402


def main() -> None:
    cache: dict[str, dict] = {}
    files = sorted(SAMPLE_ATTACHMENTS_DIR.iterdir()) + sorted((SAMPLE_DIR / "unseen_layouts").iterdir())
    for path in files:
        if path.suffix.lower() == ".pdf":
            with tempfile.TemporaryDirectory() as tmp:
                lines: list[dict] = []
                for page in ocr._pdf_to_pngs(path, Path(tmp)):
                    lines.extend(ocr._tesseract_tsv_lines(page))
        else:
            lines = ocr._tesseract_tsv_lines(path)
        cache[path.name] = {"lines": lines}
        passed, _score, _why = check_quality(path)
        if not passed:  # blurry scans also get the enhanced reading, stored alongside
            cache[path.name]["enhanced_lines"] = ocr.enhanced_tesseract_lines(path)
        print(f"{path.name}: {len(lines)} lines")
    OCR_CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    print(f"wrote {OCR_CACHE_PATH}")


if __name__ == "__main__":
    main()
