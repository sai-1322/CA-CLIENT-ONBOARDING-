"""Write the sample emails as real .eml files (sample_data/emails/*.eml).

Each file has a proper From, Subject, Message-ID and body, and the documents are attached
the way a mail program attaches them. Run after changing the sample attachments:
    python scripts/build_sample_emails.py
All names and numbers are dummy data.
"""
from __future__ import annotations

from email.message import EmailMessage
from email.utils import format_datetime
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ATTACH = ROOT / "sample_data" / "attachments"
UNSEEN = ROOT / "sample_data" / "unseen_layouts"
OUT = ROOT / "sample_data" / "emails"

SAMPLES = [
    ("01_rohan_itr.eml", "Email 1 | ITR filing with PAN and Aadhaar", "rohan@example.com", "Rohan Mehta",
     "Hi, I'm Rohan Mehta, need ITR filing for FY 2025-26. PAN ABCDE1234F, phone 9876500001.",
     [ATTACH / "sample_pan_rohan.png", ATTACH / "sample_aadhaar_rohan.png"]),
    ("02_sunita_gst.eml", "Email 2 | GST registration and returns", "sunita@example.com", "Sunita Traders",
     "Sunita Traders here. We need GST registration and monthly returns. GSTIN 27ABCDE1234F1Z5. Call 98765 00002.",
     [ATTACH / "sample_gst_sunita.png", ATTACH / "sample_bank_statement_sunita.pdf"]),
    ("03_amit_audit.eml", "Email 3 | Audit", "amit@example.com", "Amit Shah",
     "Please do my audit. I'm Amit Shah. PAN ABCDE12345.",
     [ATTACH / "sample_pan_amit_invalid.png"]),
    ("04_rohan_duplicate.eml", "Email 4 (duplicate) | PAN sent again", "rohan@example.com", "Rohan Mehta",
     "Sending my PAN again, ITR filing please.",
     [ATTACH / "sample_pan_rohan_blurry.png"]),
    ("05_rohan_wrong_document.eml", "Email 5 (wrong doc) | ID proof", "rohan@example.com", "Rohan Mehta",
     "Here is my ID proof for the ITR.",
     [ATTACH / "sample_wrong_document_electricity_bill.png"]),
    ("06_priya_new_layouts.eml", "Email 6 (new layouts) | ITR and GST for Nair Enterprises", "priya@example.com", "Priya Nair",
     "Hi, I'm Priya Nair. I need ITR filing and GST registration for Nair Enterprises. Phone 91234 56780.",
     [UNSEEN / "unseen_pan_permanent_account_number.png", UNSEEN / "unseen_aadhaar_aadhaar_no.png",
      UNSEEN / "unseen_gst_gstin_no.png", UNSEEN / "unseen_bank_name_of_account_holder.png"]),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for index, (filename, subject, sender, who, body, files) in enumerate(SAMPLES, start=1):
        msg = EmailMessage()
        msg["From"] = f"{who} <{sender}>"
        msg["To"] = "office@example.com"
        msg["Subject"] = subject
        msg["Date"] = format_datetime(datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc) + timedelta(minutes=index))
        msg["Message-ID"] = f"<sample-{index}@sample.absolute-demo.example>"
        msg.set_content(body + "\n\nAll values are dummy.\n")
        for path in files:
            kind = "application/pdf" if path.suffix == ".pdf" else "image/png"
            maintype, subtype = kind.split("/")
            msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)
        (OUT / filename).write_bytes(bytes(msg))
        print(f"wrote {filename} ({len(files)} attachment(s))")


if __name__ == "__main__":
    main()
