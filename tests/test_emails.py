"""Real .eml email files: parsing, attachments, and the inbox."""
import email.message
from email.utils import format_datetime
from datetime import datetime, timezone

import pytest

from app.config import EMAIL_SAMPLES_DIR
from app.emails import load_samples, parse_eml
from app.errors import ActionError


def _eml(sender="Asha Rao <asha@example.com>", subject="ITR filing", body="Hi, I'm Asha Rao. Need ITR.",
         message_id="<test-1@example.test>", attach=None):
    msg = email.message.EmailMessage()
    msg["From"] = sender
    msg["To"] = "office@example.com"
    msg["Subject"] = subject
    msg["Date"] = format_datetime(datetime(2026, 11, 2, tzinfo=timezone.utc))
    msg["Message-ID"] = message_id
    msg.set_content(body)
    if attach:
        name, content = attach
        msg.add_attachment(content, maintype="application", subtype="octet-stream", filename=name)
    return bytes(msg)


def test_sample_pack_is_six_real_eml_files():
    files = sorted(p.name for p in EMAIL_SAMPLES_DIR.glob("*.eml"))
    assert len(files) == 6
    titles = [parse_eml(raw, name).title for name, raw in load_samples()]
    assert titles == ["Email 1", "Email 2", "Email 3", "Email 4 (duplicate)", "Email 5 (wrong doc)", "Email 6 (new layouts)"]


def test_sample_email_fields_are_read_from_the_headers_and_attachments():
    name, raw = load_samples()[1]
    email = parse_eml(raw, name)
    assert email.sender == "sunita@example.com"
    assert email.attachments == ["sample_gst_sunita.png", "sample_bank_statement_sunita.pdf"]
    assert all(a.content[:4] in (b"\x89PNG", b"%PDF") for a in email.contents)  # real file bytes
    assert "GSTIN 27ABCDE1234F1Z5" in email.body


def test_message_id_is_the_key_so_the_same_email_is_never_read_twice():
    assert parse_eml(_eml(message_id="<abc@x.test>")).key == "abc@x.test"


def test_email_without_message_id_gets_a_stable_key_from_its_content():
    raw = _eml(message_id="")
    assert parse_eml(raw).key == parse_eml(raw).key
    assert parse_eml(raw).key.startswith("file:")


def test_sender_name_and_address_are_separated():
    assert parse_eml(_eml(sender="Asha Rao <asha@example.com>")).sender == "asha@example.com"


def test_subject_before_bar_becomes_the_title():
    assert parse_eml(_eml(subject="Email 9 | Something")).title == "Email 9"
    assert parse_eml(_eml(subject="Plain subject")).title == "Plain subject"


def test_attachment_content_is_kept_intact():
    raw = _eml(attach=("notes.bin", b"\x00\x01binary"))
    email = parse_eml(raw)
    assert email.contents[0].name == "notes.bin" and email.contents[0].content == b"\x00\x01binary"


def test_attachment_names_are_reduced_to_a_plain_file_name():
    raw = _eml(attach=("../../etc/passwd.png", b"x"))
    assert parse_eml(raw).contents[0].name == "passwd.png"


def test_missing_or_bad_sender_is_refused_with_a_plain_reason():
    raw = b"Subject: no sender\n\nhello\n"
    with pytest.raises(ActionError) as err:
        parse_eml(raw, "no_sender.eml")
    assert "no valid From address" in err.value.message


def test_garbage_bytes_are_refused_without_crashing():
    with pytest.raises(ActionError):
        parse_eml(b"\xff\xfe not an email at all \x00", "junk.eml")


def test_oversized_file_is_refused():
    with pytest.raises(ActionError) as err:
        parse_eml(b"x" * (5 * 1024 * 1024 + 10), "huge.eml")
    assert "larger than 5 MB" in err.value.message
