# Client Onboarding for a CA Office

A small, complete web app for a CA firm. It:

- **reads real email files (.eml)**: save an email from Outlook, Gmail, Apple Mail or Thunderbird and the app reads the sender, subject, body and attachments,
- **reads documents** (PAN, Aadhaar, GST certificate, bank statement, other) with real OCR (Tesseract), including blurry scans,
- **adds clients by hand**, and lets staff **type details in** when a file can't be read,
- **tracks every client** with a status, what is missing, and what needs checking,
- **drafts reminders** automatically when the app starts and every 24 hours,
- **never sends anything by itself**: a person approves each message, opens a WhatsApp or email link, presses send in their own app, and then confirms,
- keeps **six built-in test examples** (real .eml files with the expected result) and lets you **add your own**.

All sample data is dummy data. Nothing leaves your computer.

---

## 1. What you need

- **Python 3.10 or newer** (3.12 or 3.13 recommended). Check with `python --version` (Windows) or `python3 --version` (Mac/Linux).
- **Tesseract** (free text-reading program), recommended. Without it the app still runs, but it cannot read text inside uploaded files. See section 3.
- **Keep the project on your own drive** (for example `C:\absolute-onboarding` or your Home folder). Do not run it from a network drive.

---

## 2. Run it

### Visual Studio Code (recommended)

1. Install Python from python.org and tick **Add python.exe to PATH**. Install VS Code and its **Python** extension (Microsoft).
2. **File → Open Folder**, and choose the folder that contains `run.py`.
3. Press **Ctrl+Shift+P**, type **Python: Create Environment**, choose **Venv**, and pick the Python you installed.
4. Open a new terminal (**Terminal → New Terminal**) and type:
   ```
   pip install -r requirements.txt
   ```
   If `pip` is not recognised, type `python -m pip install -r requirements.txt`.
5. Click **▶ Run** on `run.py`, or type `python run.py`.
6. Your browser opens at **http://127.0.0.1:8000**. If it doesn't, open that address yourself. Press **Ctrl+C** in the terminal to stop.

### Windows (terminal)

Copy the project to `C:\absolute-onboarding` first (not a network drive), then:

```
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

If `py` is not recognised, use `python` instead. The `.venv\Scripts\python.exe` form does not need the activation script.

### Mac or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

### If port 8000 is busy

Windows (terminal): `$env:PORT=8001; python run.py`. Mac/Linux: `PORT=8001 python run.py`. Then open **http://127.0.0.1:8001**.

---

## 3. Turn on real reading of documents (Tesseract)

The app uses Tesseract automatically whenever it is installed.

- **Windows:** download the installer from the Tesseract project page (search "Tesseract at UB Mannheim"), run it, keep the default options, and restart VS Code or the terminal.
- **Mac:** `brew install tesseract poppler`
- **Linux (Ubuntu/Debian):** `sudo apt install tesseract-ocr poppler-utils`

PDFs also need `pdftoppm` (included with poppler).

**Without Tesseract** the app still runs. It then uses the text saved for the sample documents in `sample_data/ocr_cache.json`. Those saved results are **a shortcut for the sample pack only**. Any other file that is uploaded without Tesseract is reported as "no readable text", and you can type its details in instead. A reviewer should run it with Tesseract installed to see real reading.

---

## 4. Using the app

| Page | What you do there |
|---|---|
| **Dashboard** | Every client, their status, what is missing, open review items, and the automatic reminder check. |
| **Examples** | Run the six built-in test cases (real .eml files, with the expected result shown), or add and run your own. |
| **Intake** | Choose real **.eml files** to read, or drop them into `data/inbox` and press **Read inbox folder**. You can also type an email in by hand. |
| **Clients** | Search, and **+ New client** to add someone. You can type the details, or **Create from a photo**: add a photo of a PAN card, Aadhaar or GST certificate, the app proposes the details and suggests create, check, or disqualify. Click a client to open it. |
| **Client page** | Edit details, upload documents, type details in, read the checklist, record review decisions, approve messages, and mark the client onboarded. |
| **Review queue** | Every item that needs a human decision, with a box for what you checked on the original. |
| **Messages** | All drafts and their status. Approve, open a WhatsApp or email link, press send in your own app, then confirm. |
| **Outbox** | The record of messages a staff member confirmed as sent. |
| **How it works** | The rules in plain words. |

**Your name** (top right) is required for every decision. It is written in the activity log.

### Creating a client from a photo

1. Click **Clients → + New client**, then **Create from a photo**. Choose one or more photos.
2. The app reads them, including blurry ones, and shows the details it found: name, PAN, Aadhaar (masked), GSTIN, and a suggested service (you choose the service, because an ID card does not state it).
3. A recommendation appears in a coloured box, with the reasons:
   - **Create:** the name and identifier were read cleanly. Confirm to create the client and keep the photo.
   - **Check:** something was blurry, unread, or similar to an existing client. Type the missing details from the original, then create, or disqualify.
   - **Disqualify:** no usable document (for example, an electricity bill). Confirm to record the rejection; no client is created.
   - **Already exists:** a client with this PAN is on file. The app opens that client and creates nothing.
4. The app never decides for you. Every outcome needs a named staff member's decision, and every decision is written to the activity log.

### Typical day

1. Save a client's email as an `.eml` file and choose it on the **Intake** page (or drop it in `data/inbox`). The client record is created or linked, and every attachment is checked.
2. Read the **Review items** on the client page. For each one, check the original and type what you checked, then **Record decision**.
3. Read the drafted message in **Messages**. Edit it if you like, then click **Approve**.
4. Click **Open email with this text** or **Open WhatsApp with this text**. The message opens in your app. **Press send there yourself**, come back, tick **I have sent it myself**, and click **Record as sent**.
5. When every required document is accepted and no review item is open, click **Mark onboarded**.

---

## 5. The six built-in test examples

Open **Examples** and click **Run all built-in examples**. Each one is a real .eml file in `sample_data/emails/`.

| Example | What it tests | Expected result |
|---|---|---|
| **Email 1** | A normal ITR client with PAN and Aadhaar | New client Rohan Mehta. Both documents received, with checksum warnings to verify. Bank statement missing, so status is **Docs pending**. |
| **Email 2** | A GST client with a GST certificate and bank statement | New client Sunita Traders. The GSTIN carries Rohan's PAN, so an **identity conflict** is raised. Low-confidence bank holder name goes to review. |
| **Email 3** | An Audit client whose PAN is invalid | New client Amit Shah. The PAN is **rejected** with the reason. The client is asked for a correct copy. |
| **Email 4 (duplicate)** | Same sender as Email 1, blurry scan | The blurry scan is **enhanced and read**, not thrown away. Its PAN number is not trusted, so it is **held for staff to check**. Linked to Rohan. **No second record.** |
| **Email 5 (wrong doc)** | Same sender, electricity bill sent as ID proof | The electricity bill is **rejected** as proof, and the client is told why. |
| **Email 6 (new layouts)** | Documents in layouts the pack never used ("PAN No.", "Permanent Account Number", "Aadhaar No.", "GSTIN No.", "Name of account holder") | New client Priya Nair. All four documents are read. The bank holder name differs from the client name, so it is **flagged for a name check**. |

The same six cases are checked automatically by the test suite (section 7).

### Adding your own examples

On the **Examples** page, scroll to **Add more examples**: type a **title**, the **sender's email**, and the **email text**, optionally attach files, then **Save example**. Run it with **Run**. Running it again changes nothing. Examples are saved in `data/examples.json`.

### Reading your own .eml files

Save any email as `.eml` (Outlook: File → Save As → Outlook Email Message (.eml) or drag it to a folder; Gmail: open the email, ⋮ → Download message; Apple Mail: File → Save As; Thunderbird: File → Save As). Then either choose the file on **Intake**, or copy it into `data/inbox` and press **Read inbox folder**. Files that were already read are skipped.

---

## 6. How the checks work (plain words)

**Photo intake.** The same checks as email intake apply. A PAN that is already on file is never created twice. A name that matches an existing client but has a different PAN (or no PAN) is flagged, and staff must tick "create anyway" to confirm it is a different person. A blurry photo is read with enhancement. If the number cannot be read reliably, the app will not guess it; it asks staff to type it from the original.

1. **Reading the email.** The sender, subject, body and attachments are read from the .eml file. The subject part before "|" becomes the title. The email's Message-ID is its key, so the same email is never read twice.
2. **Quality first.** A blurry scan is **never rejected for being blurry**. It is deblurred and upscaled, then read with OCR. What comes out is handled as follows:
   - type and number read cleanly: accepted, marked "read from a blurry scan; verify";
   - type identified but number unreadable, or type not identifiable: **held as needs staff check**, with a review item. Staff type the number in from the original, using the same checks.
   - Nothing is guessed. An unreadable number is never filled in.
3. **Reading the text.** Tesseract reads each line and gives a confidence score.
4. **Finding the document type.** From words on the page. Several label wordings are accepted ("PAN:", "PAN No.", "Permanent Account Number"; "Aadhaar:", "Aadhaar No."; "GSTIN:", "GSTIN No."; "Account holder:", "Name of account holder:").
5. **Checking the numbers.**
   - PAN must be 5 letters, 4 digits, 1 letter. Otherwise rejected.
   - Aadhaar must be 12 digits. Its checksum and first digit are checked; a problem becomes a review item, not a silent pass.
   - GSTIN must match the GST format. Its check character is verified. Characters 3–12 are the PAN, which is cross-checked against clients.
6. **Low confidence goes to a human.** Any field under 85% confidence becomes a review item.
7. **Masking.** Aadhaar is stored and shown only as `XXXX XXXX 1234`. Bank account numbers keep only the last four digits.
8. **Identity.** A PAN match links to the existing client. The same email alone never merges two people: documents wait for staff confirmation, or a new client is created.
9. **Status is calculated, never typed.** New, Docs pending, Ready for review, Onboarded (only when nothing is open).
10. **Approval and sending.** Every message is a draft until a named person approves it. Editing an approved message removes the approval. The app builds a WhatsApp (`wa.me`) or email (`mailto:`) link for an approved draft, a person presses send in their own app, and then confirms. Only that confirmation is recorded as sent. **The app cannot see whether the message really went out**; the confirmation is the staff member's word.
11. **Reminders.** When the app starts, and again every 24 hours while it runs, it drafts reminders for clients who are past the reminder period (3 days in `config/settings.json`). A draft still needs approval, and nothing is sent.

---

## 7. Run the tests (proves the behaviour)

With the environment active (section 2), run:

```bash
python -m pytest -q
```

You should see **106 passed**. By default the tests use the saved OCR text, so they run the same on every machine. To run the document tests with real Tesseract, `tests/test_real_ocr.py` runs real reading whenever Tesseract is installed. To run **every** test on real Tesseract, set `OCR_ENGINE=tesseract` before running pytest (Windows PowerShell: `$env:OCR_ENGINE="tesseract"`; Mac/Linux: `OCR_ENGINE=tesseract python -m pytest -q`). This is slower: about 9 minutes on a typical laptop, against about 30 seconds on saved text.

### Failure cases and the test that checks each one

| Failure case in the brief | What should happen | Test |
|---|---|---|
| Invalid PAN (Email 3) | Rejected with the reason; client asked again | `test_brief_failure_cases.py::test_case_invalid_pan_...` |
| Blurry scan (Email 4) | Enhanced and read, not rejected for blur; number not guessed | `test_brief_failure_cases.py::test_case_blurry_scan_...` |
| Duplicate email (Email 4) | Linked to the existing client; no second record | `test_brief_failure_cases.py::test_case_duplicate_email_...` |
| Wrong document (Email 5) | Rejected with the reason; client told which documents are needed | `test_brief_failure_cases.py::test_case_wrong_document_...` |
| GSTIN with another client's PAN (Email 2) | Identity conflict raised for a human | `test_brief_failure_cases.py::test_case_gstin_...` |
| Low-confidence bank name (Email 2) | Sent to review | `test_brief_failure_cases.py::test_case_low_confidence_...` |
| Same mailbox, different PAN | Never merged into the other client | `test_brief_failure_cases.py::test_case_same_email_...` |
| Message sent without approval | Refused (403); outbox stays empty | `test_brief_failure_cases.py::test_case_message_cannot_be_sent_...` |
| Approved text edited afterwards | Approval removed; no link can be made | `test_brief_failure_cases.py::test_case_approved_text_...` |
| Onboarding with open items | Refused (409) | `test_brief_failure_cases.py::test_case_a_client_with_open_review_items_...` |
| Full Aadhaar number | Never stored in the database | `test_brief_failure_cases.py::test_case_full_aadhaar_...` |
| Reminder | A draft only; nothing sent | `test_brief_failure_cases.py::test_case_reminder_...` |
| Same .eml uploaded twice | Read once | `test_inbox_and_scheduler.py::test_the_same_eml_...` |
| Broken or non-email file | Refused with a reason, no crash | `test_inbox_and_scheduler.py::test_a_non_eml_file_...` and `test_emails.py` |
| Documents in new layouts | Read correctly | `test_unseen_layouts.py` |
| Automatic reminder check | Drafts for old clients, no duplicates, nothing sent | `test_inbox_and_scheduler.py::test_automatic_check_...` |

---

## 8. Where things are

```
app/            the program: email reading, checks, pipeline, workflow, approvals, scheduler, web API
static/         the web pages (HTML, CSS, JavaScript)
config/         settings.json (thresholds, reminder days and check interval, country code) and checklists.json
sample_data/
  emails/            the six built-in examples as real .eml files (with their attachments inside)
  attachments/       the sample document images and PDF
  unseen_layouts/    four documents in layouts the other samples do not use
  ocr_cache.json     saved OCR text, used only when Tesseract is not installed
data/           created when you run the app: database, uploads, inbox folder, custom examples (safe to delete to reset)
tests/          the automated tests
scripts/        build_sample_emails.py, build_unseen_samples.py, build_ocr_cache.py (regenerate the samples)
run.py          starts the app
```

**To change the rules:** edit `config/checklists.json` (documents needed per service) or `config/settings.json` (blur threshold, confidence threshold, reminder days, reminder check hours, country code, firm name). Restart the app after editing.

**To start fresh:** click **Reset demo data** on the Intake page, or delete the `data` folder while the app is stopped.

---

## 9. Limitations (read this before relying on it)

- **Not for real client data yet.** This is a working prototype. There is no login, so anyone who can open the page can use it. Real use needs staff accounts, encrypted storage and an access log.
- **Email is read from saved .eml files.** The app does not connect to a mailbox (Gmail, Outlook 365) by itself. Staff save the email, or drop it in the inbox folder. Connecting to a mailbox is the next step.
- **Nothing is sent by the app.** A person opens the link and presses send in WhatsApp or their email app. Long emails may be cut short by some email programs, because `mailto:` links have a length limit.
- **The confirmation is trusted, not verified.** The app records "sent" when the staff member ticks the box. It cannot see the message leave.
- **Reading accuracy.** Tesseract is good on clean, printed, flat scans. It is weaker on photos, handwriting, tilted or shadowed pages, and some tables. Blurry scans are enhanced first, but enhancement cannot always recover digits. Those cases are held for staff, never guessed.
- **Checksums on the dummy data.** The sample Aadhaar and GSTIN do not pass real checksums, so the app flags them for verification instead of accepting them silently. Real documents normally pass.
- **Identity is by PAN and email.** It does not check against government records, and it does not match on name and phone alone. Name differences are flagged for review.
- **Reminders run only while the app is running.** If the computer is off, the check runs the next time the app starts.
- **Layouts are known label patterns.** The app reads the label wordings it has been given (section 6, step 4). A document with a new label word will be reported as unreadable or unknown, and staff can type it in. Adding a label is a one-line change in `app/extraction.py`.
- **Checklists are a starting point.** The document lists per service should be approved by the firm before use.

---

## 10. Versions tested

Python 3.13, FastAPI 0.162, Uvicorn 0.54, Pillow 12, NumPy 2.5, pytest 9, Tesseract 5.3. Other recent versions should work because `requirements.txt` sets minimum versions only.
