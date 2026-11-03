from app.config import SAMPLE_ATTACHMENTS_DIR
from app.extraction import classify, extract_fields
from app.ocr import read_lines
from app.quality import check_quality


def test_sharp_scan_passes_quality_gate():
    passed, score, _ = check_quality(SAMPLE_ATTACHMENTS_DIR / "sample_pan_rohan.png")
    assert passed and score > 1000


def test_blurry_scan_fails_quality_gate_with_reason():
    passed, score, reason = check_quality(SAMPLE_ATTACHMENTS_DIR / "sample_pan_rohan_blurry.png")
    assert not passed and score < 100 and "blurry" in reason


def test_pdf_skips_image_quality_check():
    passed, score, _ = check_quality(SAMPLE_ATTACHMENTS_DIR / "sample_bank_statement_sunita.pdf")
    assert passed and score is None


def test_each_sample_document_is_classified_correctly():
    expected = {
        "sample_pan_rohan.png": "pan",
        "sample_aadhaar_rohan.png": "aadhaar",
        "sample_gst_sunita.png": "gst_certificate",
        "sample_bank_statement_sunita.pdf": "bank_statement",
        "sample_wrong_document_electricity_bill.png": "electricity_bill",
    }
    for name, doc_type in expected.items():
        assert classify(read_lines(SAMPLE_ATTACHMENTS_DIR / name, name)) == doc_type, name


def test_pan_fields_extracted_with_confidence():
    lines = read_lines(SAMPLE_ATTACHMENTS_DIR / "sample_pan_rohan.png", "sample_pan_rohan.png")
    fields = extract_fields("pan", lines)
    assert fields["pan"].value == "ABCDE1234F" and fields["name"].value == "ROHAN MEHTA"
    assert 0 < fields["pan"].confidence <= 1


def test_bank_holder_low_confidence_is_visible():
    lines = read_lines(SAMPLE_ATTACHMENTS_DIR / "sample_bank_statement_sunita.pdf", "sample_bank_statement_sunita.pdf")
    holder = extract_fields("bank_statement", lines)["account_holder"]
    assert holder.value == "SUNITA TRADERS" and holder.confidence < 0.85


def test_blank_text_is_unreadable_not_guessed():
    assert classify([]) == "unreadable"
    assert classify([{"text": "hello world", "conf": 0.9}]) == "unknown"
