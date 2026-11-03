# Step by step: set it up, run it, and show it

Read this top to bottom. Each step says what to do and what you should see.
Everything uses dummy data. Nothing is sent anywhere.

---

## Part 1: Get the project ready (one time)

**Step 1. Install Python.**
Get Python 3.12 or 3.13 from python.org. On the first installer screen, tick **Add python.exe to PATH**.
Check: `python --version` (or `py --version` on Windows) shows 3.10 or higher.
If it says "not recognized", reinstall Python and tick the PATH box.

**Step 2. Install VS Code and its Python extension.**
Install VS Code. Open it, click the Extensions icon on the left, search **Python** (by Microsoft), click **Install**.

**Step 3. Put the project on your own drive.**
Unzip `absolute-onboarding.zip` somewhere on your computer, for example `C:\absolute-onboarding` or your Downloads folder.
Do **not** run it from a network drive (`Z:` or `\\server\...`). Python cannot set up its private space there.
You should see folders named `app`, `static`, `config`, `tests`, `sample_data`, and files named `run.py` and `README.md`.
If you see a folder inside a folder with the same name, open the inner one, the one that contains `run.py`.

**Step 4. (Recommended) Install Tesseract, the text reader.**
- Windows: search "Tesseract UB Mannheim", install it with the default options, and restart VS Code.
- Mac: `brew install tesseract poppler`
- Linux: `sudo apt install tesseract-ocr poppler-utils`

Without Tesseract the app still runs, but it reads only the saved text for the sample documents. Install it for the recording.

**Step 5. Open the project in VS Code.**
**File → Open Folder** → the folder that contains `run.py`.

**Step 6. Create the environment and install the parts.**
1. Press **Ctrl+Shift+P**, type **Python: Create Environment**, choose **Venv**, and pick the Python from Step 1 (not one from Inkscape or another program).
2. Open a new terminal (**Terminal → New Terminal**). The line should begin with `(.venv)`.
3. Type and press Enter:
   ```
   pip install -r requirements.txt
   ```
   If `pip` is not recognised, type `python -m pip install -r requirements.txt`.
4. Wait for "Successfully installed". It takes one to two minutes.

If it fails, see the troubleshooting table at the end.

---

## Part 2: Check that it works (about 1 minute)

**Step 7. Run the tests.** In the same terminal:
```
python -m pytest -q
```
Expected: `106 passed`. If a test fails, do not continue. Send me the test name.

---

## Part 3: Start the app

**Step 8. Start it.** Click **▶ Run** at the top right of `run.py`, or type:
```
python run.py
```
Your browser opens at http://127.0.0.1:8000. If it doesn't, open that address yourself.
To stop it, click the terminal and press **Ctrl + C**.

---

## Part 4: Use it (the order to follow)

**Step 9. Load the six built-in examples.**
Click **Examples** in the left menu, then **Run all built-in examples**.
You should see four clients on the Dashboard: Rohan Mehta, Sunita Traders, Amit Shah and Priya Nair.
The six examples are real `.eml` email files in `sample_data/emails`.

**Step 10. Read the tracker.**
Click **Dashboard**. Each client has a status:
- *Docs pending*: something is still missing.
- *Ready for review*: every required document is in, but review items may be open.
- *Onboarded*: a staff member has marked it done.

**Step 11. Open Rohan and handle the review items.**
Click **Rohan Mehta**. Look at **Review items**. For each one, type what you checked on the original in the box,
then click **Record decision**. You cannot mark a client onboarded while any item is open.

**Step 12. Approve a message and send it the safe way.**
Scroll to **Messages**. The app has written a message asking for the missing bank statement.
1. Read it, edit it if you want, then click **Approve** (your name is required at the top right).
2. Click **Open email with this text**. Your email app opens with the message filled in.
3. Press **send in your email app** yourself.
4. Back in the app, tick **I have sent it myself**, then click **Record as sent (email)**.
5. Open **Outbox**. The record is there, marked as confirmed by staff.

The app never sends anything itself. You can say so in the interview.

**Step 13. Read your own email file.**
Click **Intake**, then under **Read real email files (.eml)** choose a `.eml` file from `sample_data/emails`
(or any `.eml` you saved from your own mail program). Press **Read email files**.
The sender, subject, body and attachments are read from the file. Reading the same file again does nothing.
Or copy an `.eml` file into the `data` → `inbox` folder, then press **Read inbox folder**.

**Step 14. Add a new client from a photo (optional, shows the new feature).**
Click **Clients → + New client**, then under **Create from a photo** choose a photo of a PAN card or Aadhaar (try `sample_data/unseen_layouts/unseen_pan_permanent_account_number.png`), and click **Read photo**.
✅ Check: the app shows the name and PAN it found, and a suggestion such as "Suggest create". Click **Create client (suggested)**.
Then try a blurry photo (`sample_data/attachments/sample_pan_rohan_blurry.png`). The app says to check the original and type the details in, and it does not guess the number.

**Step 15. Add a new client by hand.**
Click **Clients**, open **+ New client**. Type a name, email, phone and service, then **Create client**.

**Step 16. Upload documents to that client.**
On the client page, under **Add documents to this client**:
- Choose the document type (PAN card, Aadhaar, and so on).
- Pick a file and click **Upload and check**.
- A wrong file is rejected with the reason shown. A blurry scan is enhanced and read, or held for a staff check.

**Step 17. Or type the details in.**
In **Type the details in**, choose the document, type the number and the name as printed, then **Save details**.
Invalid numbers are refused with a clear message.

**Step 18. Add your own example.**
Click **Examples**, scroll to **Add more examples**. Type a title, a sender email and the email text.
Optionally attach a file. Click **Save example**, then **Run** on it.

**Step 19. Search.**
Click **Clients** and type a name, PAN or phone in the search box. The list filters as you type.

**Step 20. Mark a client onboarded.**
Only possible when every required document is in and no review item is open.
Click **Mark onboarded** on the client page.

---

## Part 5: Show it in an interview (about 3 minutes)

Record the screen with captions if you can (Windows: Game Bar with Win+G, or any screen recorder).

1. (20 sec) Say: "It is a CA client onboarding tool. It reads email files and documents, checks them, tracks each client, and never sends anything without a named person approving it and pressing send."
2. (30 sec) **Intake** → choose `sample_data/emails/01_rohan_itr.eml`. Show the sender and attachments read from the file. Then **Examples → Run all built-in examples**. Go to **Dashboard** and point at the statuses.
3. (40 sec) Failure cases, in order:
   - **Email 3**: invalid PAN rejected, with the reason shown.
   - **Email 4**: blurry scan enhanced and read; the PAN number is held, not guessed. No second Rohan record.
   - **Email 5**: electricity bill rejected as proof.
   - **Email 6**: four documents in new layouts read correctly.
4. (30 sec) Open **Rohan Mehta**. Show the review items and one decision. Approve the draft, open the email link, and tick **I have sent it myself**. Show the **Outbox**.
5. (20 sec) Show the **Examples** page: the six expected results, and that the tests check them (`python -m pytest -q`, 106 passed).
6. (20 sec) End with the limits: no login yet, the app does not connect to a mailbox, the confirmation is the staff member's word, and reading depends on Tesseract and scan quality.

---

## If something goes wrong

| What you see | What to do |
|---|---|
| "python is not recognised" or "pip is not recognised" | Reinstall Python and tick **Add python.exe to PATH**. Or use `python -m pip install -r requirements.txt`. |
| "ensurepip ... returned non-zero exit status 1" | The project is on a network drive. Move it to your own drive, delete the `.venv` folder, and repeat Step 6. |
| "No module named 'uvicorn'" when you press Run | The packages are not installed in the Python VS Code is using. Repeat Step 6 and make sure the terminal shows `(.venv)`. |
| pip install shows "SSL: CERTIFICATE_VERIFY_FAILED" or builds `cmake` | The Python on your PATH is an old one, often from Inkscape. Install Python 3.12 or 3.13 and recreate `.venv` with it (Step 6). |
| "Port 8000 is already in use" | Run `PORT=8001 python run.py` (Windows: `$env:PORT=8001; python run.py`), then open port 8001. |
| Uploads say "no readable text" | Install Tesseract (Step 4), or type the details in instead. |
| "not a readable email file" or "no valid From address" | The file is not a saved email. Save it again as `.eml` from your mail program. |
| A test fails | Note the test name and send it to me. |
| Browser shows an error in a red box | Read it: it says what to fix. Nothing is lost. |

To start with empty data, stop the app and delete the `data` folder. Then run it again.
