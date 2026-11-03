"""Make dummy documents in layouts the sample pack never used.

They test that extraction is not tied to one exact layout: different labels ("PAN No.",
"Permanent Account Number", "Aadhaar No.", "GSTIN No.", "Name of account holder").
Every name and number is invented. Run once:  python scripts/build_unseen_samples.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import validators as v  # noqa: E402

OUT = ROOT / "sample_data" / "unseen_layouts"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _card(name: str, title: str, lines: list[str], header: str = "") -> Image.Image:
    image = Image.new("RGB", (1400, 900), "white")
    draw = ImageDraw.Draw(image)
    big = ImageFont.truetype(FONT_BOLD, 46)
    body = ImageFont.truetype(FONT, 40)
    draw.rectangle([40, 40, 1360, 860], outline="black", width=4)
    y = 80
    if header:
        draw.text((90, y), header, font=big, fill="black")
        y += 90
    draw.text((90, y), title, font=big, fill="black")
    y += 110
    for line in lines:
        draw.text((90, y), line, font=body, fill="black")
        y += 80
    return image


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # PAN card worded "Permanent Account Number", with "PAN No." as the label
    pan = "BCDPN5678K"  # 5 letters, 4 digits, 1 letter; 4th letter P = individual
    _card("pan", "Permanent Account Number Card",
          [f"Name: Priya Nair", f"PAN No.: {pan}", "Date of Birth: 14/03/1991"],
          header="INCOME TAX DEPARTMENT").save(OUT / "unseen_pan_permanent_account_number.png")

    # Aadhaar with "Aadhaar No." label and a number that passes the Verhoeff checksum
    base = "432109876543"[:11]
    aadhaar = base + v.verhoeff_check_digit(base)
    spaced = f"{aadhaar[:4]} {aadhaar[4:8]} {aadhaar[8:]}"
    _card("aadhaar", "Aadhaar No. Card",
          ["Name: Priya Nair", "Year of Birth: 1991", "Female", f"Aadhaar No.: {spaced}"],
          header="GOVERNMENT OF INDIA").save(OUT / "unseen_aadhaar_aadhaar_no.png")

    # GST certificate with "GSTIN No." label; state 29 (Karnataka); embeds Priya's PAN
    first14 = "29" + pan + "1Z"
    gstin = first14 + v.gstin_check_char(first14)
    _card("gst", "GST Registration Certificate",
          ["Legal Name: Nair Enterprises", f"GSTIN No.: {gstin}", "Registration Date: 01/07/2017"],
          ).save(OUT / "unseen_gst_gstin_no.png")

    # Bank statement header with "Name of account holder" and "Account No."
    _card("bank", "Account Statement",
          ["Name of account holder: Nair Enterprises", "Account No.: XXXXXX7788", "Period: Oct 2026"],
          ).save(OUT / "unseen_bank_name_of_account_holder.png")

    print(f"wrote {len(list(OUT.glob('*.png')))} images to {OUT}")
    print("PAN", pan, "| Aadhaar", aadhaar, "| GSTIN", gstin)


if __name__ == "__main__":
    main()
