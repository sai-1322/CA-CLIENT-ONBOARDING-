/* Client onboarding dashboard. Plain JavaScript, no build step. */
(function () {
  "use strict";

  const main = document.getElementById("main");
  const staffInput = document.getElementById("staff-name");
  const toastEl = document.getElementById("toast");

  // ---------- small helpers ----------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const STATUS_LABEL = { new: "New", docs_pending: "Docs pending", ready_for_review: "Ready for review", onboarded: "Onboarded" };
  const STATUS_CLASS = { new: "b-new", docs_pending: "b-pending", ready_for_review: "b-ready", onboarded: "b-done" };
  const badge = (status) => `<span class="badge ${STATUS_CLASS[status] || "b-grey"}">${esc(STATUS_LABEL[status] || status)}</span>`;

  const DOC_STATUS = {
    accepted: ["Accepted", "b-done"],
    accepted_needs_review: ["Accepted – verify", "b-warn"],
    held: ["Held – awaiting confirmation", "b-info"],
    rejected: ["Rejected", "b-bad"],
    needs_verification: ["Staff to check", "b-warn"],
  };
  const docBadge = (s) => `<span class="badge ${(DOC_STATUS[s] || ["?", "b-grey"])[1]}">${esc((DOC_STATUS[s] || [s])[0])}</span>`;

  const CHECK_STATE = {
    received: ["✓ Received", "b-done"],
    missing: ["✗ Missing", "b-bad"],
    rejected: ["✗ Rejected", "b-bad"],
    awaiting_confirmation: ["… Awaiting confirmation", "b-info"],
    needs_verification: ["⚠ Needs staff check", "b-warn"],
  };
  const checkBadge = (s) => `<span class="badge ${(CHECK_STATE[s] || ["?", "b-grey"])[1]}">${esc((CHECK_STATE[s] || [s])[0])}</span>`;

  const MSG_CLASS = { pending_approval: "b-pending", approved: "b-info", sent: "b-done", rejected: "b-bad", superseded: "b-grey" };
  const msgBadge = (s) => `<span class="badge ${MSG_CLASS[s] || "b-grey"}">${esc(s.replace(/_/g, " "))}</span>`;

  function toast(text, kind) {
    toastEl.textContent = text;
    toastEl.className = "toast" + (kind === "error" ? " error" : "");
    toastEl.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { toastEl.hidden = true; }, 4500);
  }

  async function api(method, url, body) {
    const options = { method, headers: {} };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    let response;
    try {
      response = await fetch(url, options);
    } catch (networkError) {
      throw new Error("Cannot reach the server. Is it still running?");
    }
    let data = null;
    try { data = await response.json(); } catch (_) { data = null; }
    if (!response.ok) {
      let message = "Request failed";
      if (data && typeof data.error === "string") message = data.error;
      else if (data && Array.isArray(data.detail)) message = data.detail.map((d) => d.msg).join("; ");
      else if (data && typeof data.detail === "string") message = data.detail;
      throw new Error(message);
    }
    return data;
  }

  // Staff name is remembered in this browser only (used for the audit log, not for security).
  function staffName() {
    try { return staffInput.value.trim(); } catch (_) { return ""; }
  }
  function requireStaff() {
    const name = staffName();
    if (!name) throw new Error("Type your name in the top-right box first. It is recorded in the audit log.");
    return name;
  }
  try {
    staffInput.value = localStorage.getItem("staffName") || "";
    staffInput.addEventListener("change", () => {
      try { localStorage.setItem("staffName", staffInput.value.trim()); } catch (_) { /* private mode */ }
    });
  } catch (_) { /* storage unavailable: still works, just not remembered */ }

  const fmtDate = (iso) => (iso ? String(iso).replace("T", " ").slice(0, 16) : "—");

  // ---------- pages ----------
  const pages = {
    async dashboard() {
      const clients = await api("GET", "/api/clients");
      const health = await api("GET", "/api/health");
      const [review, messages] = await Promise.all([api("GET", "/api/review"), api("GET", "/api/messages?status=pending_approval")]);
      const count = (s) => clients.filter((c) => c.status === s).length;
      const rows = clients.map((c) => `
        <tr class="clickable" data-action="open-client" data-id="${c.id}">
          <td><strong>${esc(c.code)}</strong></td>
          <td>${esc(c.name)}</td>
          <td>${esc(c.pan || "Needs review")}</td>
          <td>${esc(c.email)}</td>
          <td>${esc(c.service)}</td>
          <td>${badge(c.status)}</td>
          <td class="small-text">${c.missing.length ? esc(c.missing.join(", ")) : "—"}</td>
          <td>${c.open_review ? `<span class="badge b-warn">${c.open_review} open</span>` : "—"}</td>
        </tr>`).join("");
      main.innerHTML = `
        <h1>Dashboard</h1>
        <p class="muted">Live tracker. Statuses are calculated from the documents on file. Nothing is sent without staff approval.</p>
        <div class="grid-stats">
          <div class="stat"><div class="num">${clients.length}</div><div class="label">Clients</div></div>
          <div class="stat"><div class="num">${count("new") + count("docs_pending")}</div><div class="label">Docs pending</div></div>
          <div class="stat"><div class="num">${count("ready_for_review")}</div><div class="label">Ready for review</div></div>
          <div class="stat"><div class="num">${count("onboarded")}</div><div class="label">Onboarded</div></div>
          <div class="stat"><div class="num">${review.length}</div><div class="label">Open review items</div></div>
          <div class="stat"><div class="num">${messages.length}</div><div class="label">Drafts awaiting approval</div></div>
        </div>
        ${clients.length ? `<div class="table-wrap"><table>
          <thead><tr><th>ID</th><th>Client</th><th>PAN</th><th>Email</th><th>Service</th><th>Status</th><th>Missing</th><th>Review</th></tr></thead>
          <tbody>${rows}</tbody></table></div>`
          : `<div class="card"><p>No clients yet. Go to <a href="#intake">Intake</a> and load the sample emails.</p></div>`}
        <h2>Check reminders</h2>
        <div class="card">
          <p class="small-text">${health.reminder_check.enabled
            ? `The app checks for reminders when it starts and every 24 hours. Last check: ${health.reminder_check.last_run ? fmtDate(health.reminder_check.last_run) : "not yet"} (${health.reminder_check.last_drafts} draft(s) made). It only drafts them; nothing is sent.`
            : "Automatic reminder checks are switched off in this run. Use the button below."}</p>
          <p class="small-text">Clients still missing documents get a reminder <em>draft</em> once their last contact is older than the reminder period (3 days). Use the date to simulate time passing.</p>
          <div class="row">
            <input type="date" id="reminder-date" value="${new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10)}">
            <button class="auto" data-action="run-reminders">Check reminders</button>
          </div>
        </div>`;
    },

    async examples() {
      const items = await api("GET", "/api/examples");
      const rows = items.map((e) => `<tr>
        <td><strong>${esc(e.title)}</strong><div class="small-text">${esc(e.kind)} · from ${esc(e.sender)}</div></td>
        <td class="small-text">${esc(e.body)}<div>${esc(e.attachments.join(", ")) || "<em>no files</em>"}</div></td>
        <td class="small-text">${esc(e.expected) || "—"}</td>
        <td>${e.processed ? `<span class="badge b-done">Run</span>${e.client_id ? ` <a href="#clients/${e.client_id}">open client</a>` : ""}` : '<span class="badge b-grey">Not run</span>'}</td>
        <td><button class="small" data-action="run-example" data-key="${esc(e.key)}">${e.processed ? "Run again (no change)" : "Run"}</button></td>
      </tr>`).join("");
      main.innerHTML = `<h1>Examples</h1>
        <p class="muted">The six sample cases are the built-in test examples, with the result each one should produce. Add your own examples below and run them the same way. Running an example twice changes nothing.</p>
        <div class="row" style="margin-bottom:12px"><button class="auto" data-action="run-all-examples">Run all built-in examples</button></div>
        <div class="table-wrap"><table>
          <thead><tr><th>Example</th><th>Email and files</th><th>Expected result</th><th>Status</th><th></th></tr></thead>
          <tbody>${rows}</tbody></table></div>
        <h2>Add more examples</h2>
        <div class="card">
          <p class="small-text">Create a new scenario: a sender, the email text and any files (PDF or images). It is saved and can be run any time. Files are checked exactly like real intake.</p>
          <form id="example-form">
            <div class="two">
              <label class="field">Title *<input type="text" name="title" required placeholder="e.g. Shared family email, two PANs"></label>
              <label class="field">Sender email *<input type="email" name="sender" required placeholder="client@example.com"></label>
            </div>
            <label class="field">Email text<textarea name="body" placeholder="Hi, I'm … need ITR filing. PAN …"></textarea></label>
            <label class="field">Files (optional)<input type="file" name="files" multiple accept=".pdf,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff"></label>
            <button type="submit">Save example</button>
          </form>
        </div>`;
    },

    async intake() {
      const emails = await api("GET", "/api/sample-emails");
      const results = window.__emlResults || [];
      const resultRows = results.length ? `<div class="card"><h3>Last files read</h3><ul class="clean">${results.map((r) =>
        `<li><strong>${esc(r.file || r.email || "")}</strong>: ${esc((r.outcome || "").replace(/_/g, " "))}${r.reason ? ` <span class="small-text">${esc(r.reason)}</span>` : ""}${r.documents ? ` <span class="small-text">(${r.documents.length} attachment(s))</span>` : ""}</li>`).join("")}</ul></div>` : "";
      const rows = emails.map((e) => `
        <tr>
          <td><strong>${esc(e.key)}</strong><div class="small-text">${esc(e.file)} · ${esc(e.sender)}</div></td>
          <td class="small-text">${esc(e.body)}</td>
          <td class="small-text">${esc(e.attachments.join(", "))}</td>
          <td>${e.processed ? '<span class="badge b-done">Processed</span>' : '<span class="badge b-grey">Not yet</span>'}</td>
          <td><button class="small secondary" data-action="process-sample" data-index="${e.index}">${e.processed ? "Process again (no effect)" : "Process"}</button></td>
        </tr>`).join("");
      main.innerHTML = `
        <h1>Intake</h1>
        <p class="muted">Emails are read, attachments are checked, and a client record is created or linked. Processing the same email twice has no effect.</p>
        <div class="row" style="margin-bottom:12px">
          <button class="auto" data-action="load-demo">Load all 6 sample emails</button>
          <button class="auto secondary" data-action="reset">Reset demo data</button>
        </div>
        <div class="table-wrap"><table>
          <thead><tr><th>Email</th><th>Body</th><th>Attachments</th><th></th><th></th></tr></thead>
          <tbody>${rows}</tbody></table></div>
        ${resultRows}
        <h2>Read real email files (.eml)</h2>
        <div class="card">
          <p class="small-text">Save an email from Outlook, Gmail, Apple Mail or Thunderbird as an <strong>.eml</strong> file, then choose it here. The sender, subject, body and attachments are read from the file. Each email is read once.</p>
          <form id="eml-form">
            <label class="field">.eml files<input type="file" name="files" accept=".eml" multiple required></label>
            <button type="submit">Read email files</button>
          </form>
          <p class="small-text" style="margin-top:12px">Or drop .eml files into the inbox folder <code>data/inbox</code> and press the button below.</p>
          <button class="auto secondary" data-action="read-inbox">Read inbox folder</button>
        </div>
        <h2>Add an email by hand</h2>
        <div class="card">
          <p class="small-text">Files are checked the same way as the examples: a blurry scan is enhanced and read, and a file with no readable text is rejected with the reason shown.</p>
          <form id="intake-form">
            <div class="two">
              <label class="field">Sender email<input type="email" name="sender" required placeholder="client@example.com"></label>
              <label class="field">Attachments<input type="file" name="files" multiple></label>
            </div>
            <label class="field">Email text<textarea name="body" placeholder="Hi, I need ITR filing…"></textarea></label>
            <button type="submit">Process email</button>
          </form>
        </div>`;
    },

    async clients() {
      const clients = await api("GET", "/api/clients");
      const types = await api("GET", "/api/doc-types");
      const serviceOptions = ["ITR", "GST", "Audit"].map((x) => `<option>${x}</option>`).join("");
      const rows = clients.map((c) => `<tr class="clickable" data-action="open-client" data-id="${c.id}"
          data-search="${esc([c.code, c.name, c.pan, c.email, c.phone, c.service].join(" ").toLowerCase())}">
          <td>${esc(c.code)}</td><td>${esc(c.name)}</td><td>${esc(c.pan || "—")}</td><td>${esc(c.service)}</td>
          <td>${badge(c.status)}</td><td>${c.open_review || "—"}</td></tr>`).join("");
      main.innerHTML = `<h1>Clients</h1>
        <details class="card" ${clients.length ? "" : "open"}>
          <summary><strong>+ New client</strong></summary>
          <div class="card" style="margin-top:12px">
            <h3>Create from a photo</h3>
            <p class="small-text">Choose a photo of a PAN card, Aadhaar, or GST certificate (one or more). The app reads it and proposes the client details. It also suggests whether to create the client, check first, or disqualify. You make the final decision. Blurry photos are read too, and anything unclear is marked for you to check.</p>
            <form id="photo-form">
              <label class="field">Photos<input type="file" name="files" accept="image/*,.pdf" multiple required></label>
              <button type="submit">Read photo</button>
            </form>
            <div id="photo-preview"></div>
          </div>
          <form id="new-client-form" style="margin-top:12px">
            <div class="two">
              <label class="field">Full name *<input type="text" name="name" required minlength="2" placeholder="As on the PAN card"></label>
              <label class="field">Email<input type="email" name="email" placeholder="client@example.com"></label>
              <label class="field">Phone (10 digits)<input type="text" name="phone" inputmode="numeric"></label>
              <label class="field">PAN (optional, can be added later)<input type="text" name="pan" placeholder="ABCDE1234F"></label>
              <label class="field">Service<select name="service">${serviceOptions}</select></label>
            </div>
            <button type="submit">Create client</button>
            <p class="small-text">Your name at the top of the page is recorded for every new client.</p>
          </form>
        </details>
        <div class="row" style="margin:12px 0">
          <input type="search" id="client-search" placeholder="Search by name, PAN, email, phone or service">
          <span class="small-text auto" id="client-count">${clients.length} client(s)</span>
        </div>
        ${clients.length ? `<div class="table-wrap"><table>
          <thead><tr><th>ID</th><th>Name</th><th>PAN</th><th>Service</th><th>Status</th><th>Open review</th></tr></thead>
          <tbody id="client-rows">${rows}</tbody></table></div>`
          : '<div class="card"><p class="muted">No clients yet. Use “New client” above, or load the sample emails on the Intake page.</p></div>'}`;
      window.__docTypes = types;
    },

    async client(id) {
      if (!window.__docTypes) window.__docTypes = await api("GET", "/api/doc-types");
      const c = await api("GET", `/api/clients/${id}`);
      const reviewRows = c.review_items.filter((r) => r.status === "open");
      const onboardNote = c.status === "onboarded"
        ? `<div class="notice ok">Onboarded on ${esc(fmtDate(c.onboarded_at))}. Client record is locked.</div>`
        : c.can_onboard
          ? ""
          : `<div class="notice warn"><strong>Cannot onboard yet.</strong><ul class="clean">${c.onboard_blockers.map((b) => `<li>${esc(b)}</li>`).join("") || "<li>Required documents are not complete.</li>"}</ul></div>`;
      const drafts = c.messages.filter((m) => m.status === "pending_approval" || m.status === "approved");
      const sent = c.messages.filter((m) => m.status === "sent");
      main.innerHTML = `
        <p><a href="#clients">← All clients</a></p>
        <h1>${esc(c.code)} · ${esc(c.name)} ${badge(c.status)}</h1>
        <p class="muted">${esc(c.email)} · ${esc(c.phone || "no phone")} · ${esc(c.service)} · PAN ${esc(c.pan || "not confirmed")}</p>
        ${onboardNote}

        <div class="two">
          <div class="card">
            <h3>Client details <span class="small-text">(staff edits, validated)</span></h3>
            <label class="field">Name<input type="text" id="c-name" value="${esc(c.name)}"></label>
            <label class="field">PAN<input type="text" id="c-pan" value="${esc(c.pan || "")}" placeholder="ABCDE1234F"></label>
            <label class="field">Email<input type="email" id="c-email" value="${esc(c.email)}"></label>
            <label class="field">Phone (10 digits)<input type="text" id="c-phone" value="${esc(c.phone || "")}"></label>
            <label class="field">Service<select id="c-service">${["ITR", "GST", "Audit"].map((s) => `<option ${s === c.service ? "selected" : ""}>${s}</option>`).join("")}</select></label>
            <button data-action="save-client" data-id="${c.id}" ${c.status === "onboarded" ? "disabled" : ""}>Save details</button>
          </div>
          <div class="card">
            <h3>Onboarding</h3>
            <p class="small-text">Onboarding is a staff decision. It is only allowed when every required document is accepted and no review item is open.</p>
            <button data-action="onboard" data-id="${c.id}" ${c.can_onboard ? "" : "disabled"}>Mark onboarded</button>
            <h3 style="margin-top:16px">Document checklist</h3>
            <ul class="clean">${c.checklist.map((i) => `<li>${checkBadge(i.state)} ${esc(i.label)}${i.required ? "" : ' <span class="small-text">(if registered)</span>'}${i.reason ? `<div class="small-text">${esc(i.reason)}</div>` : ""}</li>`).join("")}</ul>
          </div>
        </div>

        <h2>Documents received</h2>
        ${c.documents.length ? `<div class="table-wrap"><table>
          <thead><tr><th>File</th><th>Type</th><th>Status</th><th>Details (masked)</th></tr></thead>
          <tbody>${c.documents.map((d) => `<tr>
            <td>${esc(d.filename)}<div class="small-text">from ${esc(d.source_email)}</div></td>
            <td>${esc(d.doc_label)}</td>
            <td>${docBadge(d.status)}${d.reason ? `<div class="small-text">${esc(d.reason)}</div>` : ""}</td>
            <td class="small-text">${Object.entries(d.fields).map(([k, f]) => `${esc(k)}: ${esc(f.value)} (${Math.round(f.confidence * 100)}%)`).join("<br>") || "—"}</td>
          </tr>`).join("")}</tbody></table></div>`
          : '<p class="muted">No documents yet.</p>'}

        <h2>Review items (${reviewRows.length} open)</h2>
        ${reviewRows.length ? reviewRows.map(reviewCard).join("") : '<p class="muted">Nothing open for this client.</p>'}

        <h2>Add documents to this client</h2>
        ${uploadPanels(c)}

        <h2>Messages</h2>
        ${drafts.map((m) => draftCard(m, c)).join("") || '<p class="muted">No drafts waiting. Drafts are created automatically when documents are missing.</p>'}
        ${sent.length ? `<h3>Sent (confirmed by staff)</h3><ul class="clean">${sent.map((m) => `<li>${esc(m.kind)} via ${esc(m.channel)} at ${esc(fmtDate(m.sent_at))} (approved by ${esc(m.approved_by)})</li>`).join("")}</ul>` : ""}

        <h2>Activity log</h2>
        <div class="card"><ul class="clean">${c.events.map((e) => `<li><span class="small-text">${esc(fmtDate(e.at))} · ${esc(e.actor)}</span><br>${esc(e.action)} — ${esc(e.detail)}</li>`).join("") || "<li>No activity</li>"}</ul></div>`;
    },

    async review() {
      const items = await api("GET", "/api/review");
      main.innerHTML = `<h1>Review queue</h1>
        <p class="muted">Things the system will not decide on its own: identity checks, checksum failures, low-confidence fields and conflicts. Check the original, then record your decision.</p>
        ${items.length ? items.map((i) => reviewCard(i)).join("") : '<div class="card"><p>Nothing to review. 🎉</p></div>'}`;
    },

    async messages() {
      const status = window.__msgFilter || "pending_approval";
      const msgs = await api("GET", `/api/messages?status=${encodeURIComponent(status)}`);
      const filters = ["pending_approval", "approved", "sent", "rejected", "superseded"];
      main.innerHTML = `<h1>Messages</h1>
        <p class="muted">Every outbound message is a draft until a named staff member approves it. Editing an approved draft removes the approval.</p>
        <div class="row" style="margin-bottom:12px">${filters.map((f) => `<button class="small ${f === status ? "" : "secondary"}" data-action="filter-messages" data-status="${f}">${f.replace(/_/g, " ")}</button>`).join("")}</div>
        ${msgs.length ? msgs.map((m) => `<div class="card">
          <div class="row"><strong>${esc(m.code)} · ${esc(m.client_name)}</strong> ${msgBadge(m.status)} <span class="small-text">${esc(m.kind)}</span></div>
          <pre class="msg">${esc(m.body)}</pre>
          ${m.status === "pending_approval" || m.status === "approved" ? `<div class="small-text">Open the <a href="#clients/${m.client_id}">client page</a> to edit or approve.</div>` : ""}
        </div>`).join("") : '<div class="card"><p class="muted">No messages with this status.</p></div>'}`;
    },

    async outbox() {
      const rows = await api("GET", "/api/outbox");
      main.innerHTML = `<h1>Outbox</h1>
        <div class="notice info"><strong>Record of sends.</strong> The app never sends a message itself. A row appears here only after a staff member approved the draft, opened the link, pressed send in their own app, and confirmed it.</div>
        ${rows.length ? `<div class="table-wrap"><table>
          <thead><tr><th>When</th><th>Client</th><th>Type</th><th>Channel</th><th>Recipient</th><th>Mode</th></tr></thead>
          <tbody>${rows.map((r) => `<tr><td>${esc(fmtDate(r.created_at))}</td><td>${esc(r.code)} ${esc(r.name)}</td><td>${esc(r.kind)}</td><td>${esc(r.channel)}</td><td>${esc(r.recipient)}</td><td><span class="badge b-info">${esc(r.mode)}</span></td></tr>`).join("")}</tbody></table></div>`
          : '<div class="card"><p class="muted">Nothing sent yet.</p></div>'}`;
    },

    how() {
      main.innerHTML = `<h1>How it works</h1>
        <div class="card"><ol class="steps">
          <li><strong>Intake:</strong> real .eml files are read for sender, subject, body and attachments. Each email (by its Message-ID) is read once.</li>
          <li><strong>Quality gate:</strong> a blurry scan is never rejected for being blurry. It is enhanced and read; a number that cannot be read is held for staff, and nothing is guessed.</li>
          <li><strong>Text recognition and extraction:</strong> the text is read line by line, and each value keeps its confidence. Values below 85% go to the review queue.</li>
          <li><strong>Checks:</strong> PAN, Aadhaar and GSTIN formats are validated. Checksum problems are flagged for staff, not silently accepted or silently rejected.</li>
          <li><strong>Identity:</strong> a PAN match links a client. A shared email alone never merges two records; documents wait for staff confirmation.</li>
          <li><strong>Checklist:</strong> required documents depend on the service (ITR, GST, Audit). Status is calculated from them.</li>
          <li><strong>Drafts:</strong> a message asking for missing or rejected documents is drafted automatically. Reminders are drafted after the set number of days.</li>
          <li><strong>Approval and sending:</strong> a named staff member approves every message, opens a WhatsApp or email link, presses send in their own app, and then confirms. Only then is it recorded as sent.</li>
          <li><strong>Onboarding:</strong> a staff member marks a client onboarded only when no required document is missing and no review item is open.</li>
        </ol></div>`;
    },
  };

  function typeOptions() {
    return (window.__docTypes || []).map((t) => `<option value="${esc(t.key)}">${esc(t.label)}</option>`).join("");
  }

  function uploadPanels(c) {
    return `<div class="two">
      <div class="card">
        <h3>Upload a file</h3>
        <form class="upload-form" data-client="${c.id}">
          <label class="field">What is this document?<select name="doc_type">${typeOptions()}</select></label>
          <label class="field">Name, only for “Other document” (e.g. Form 16)<input type="text" name="label"></label>
          <label class="field">File (PDF, PNG, JPG)<input type="file" name="files" multiple required
            accept=".pdf,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff"></label>
          <button type="submit">Upload and check</button>
          <p class="small-text">Blurry scans are enhanced and read, never thrown away. Anything that cannot be read reliably is held for staff to check. The wrong kind of document is rejected with the reason shown. Reading the text needs Tesseract (see README); without it, type the details in on the right.</p>
        </form>
      </div>
      <div class="card">
        <h3>Type the details in</h3>
        <form class="manual-form" data-client="${c.id}">
          <label class="field">Document<select name="doc_type">${typeOptions()}</select></label>
          <label class="field">Number (PAN, Aadhaar, GSTIN, or account number)<input type="text" name="number"></label>
          <label class="field">Name as printed on the document<input type="text" name="name"></label>
          <label class="field">Name, only for “Other document”<input type="text" name="label"></label>
          <button type="submit">Save details</button>
          <p class="small-text">The same checks run as for uploads. Aadhaar is stored masked, so only the last four digits are kept.</p>
        </form>
      </div>
    </div>`;
  }

  function reviewCard(item) {
    const ident = item.kind === "identity_confirmation";
    const clientLabel = item.client_name ? `${esc(item.code)} · ${esc(item.client_name)} — ` : "";
    const actions = ident
      ? `<select id="rv-action-${item.id}"><option value="confirm">Confirm: these documents belong to this client</option><option value="reject">Reject: not this client</option></select>`
      : `<input type="hidden" id="rv-action-${item.id}" value="resolve">`;
    return `<div class="card">
      <div class="small-text">${clientLabel}${esc(item.kind.replace(/_/g, " "))}</div>
      <p style="margin:6px 0">${esc(item.message)}</p>
      ${item.status === "resolved" ? `<div class="small-text">Resolved by ${esc(item.resolved_by)}: ${esc(item.resolution)}</div>` : `
      <div class="row">
        ${actions}
        <input type="text" id="rv-note-${item.id}" placeholder="${ident ? "Optional note" : "What you checked on the original (required)"}">
        <button class="auto" data-action="resolve-review" data-id="${item.id}">Record decision</button>
      </div>`}
    </div>`;
  }

  function draftCard(m, c) {
    const approved = m.status === "approved";
    return `<div class="card">
      <div class="row"><strong>${esc(m.kind.replace("_", " "))}</strong> ${msgBadge(m.status)} ${approved ? `<span class="small-text">approved by ${esc(m.approved_by)}</span>` : ""}</div>
      <label class="field">Subject<input type="text" id="m-subject-${m.id}" value="${esc(m.subject)}"></label>
      <label class="field">Email body<textarea id="m-body-${m.id}">${esc(m.body)}</textarea></label>
      <label class="field">WhatsApp version<textarea id="m-wa-${m.id}" style="min-height:80px">${esc(m.whatsapp_body)}</textarea></label>
      <div class="row">
        <button class="small secondary" data-action="save-draft" data-id="${m.id}" data-client="${c.id}">Save edits</button>
        <button class="small" data-action="approve-msg" data-id="${m.id}" data-client="${c.id}">Approve</button>
        <button class="small danger" data-action="reject-msg" data-id="${m.id}" data-client="${c.id}">Reject</button>
        <button class="small" data-action="open-link" data-id="${m.id}" data-channel="email" data-client="${c.id}" ${approved ? "" : "disabled"}>Open email with this text</button>
        <button class="small" data-action="open-link" data-id="${m.id}" data-channel="whatsapp" data-client="${c.id}" ${approved ? "" : "disabled"}>Open WhatsApp with this text</button>
      </div>
      ${approved ? `<div class="notice info">
        <p class="small-text">The link opens the message in WhatsApp or your email app. <strong>Press send there yourself.</strong> Then come back here and confirm.</p>
        <label class="row small-text"><input type="checkbox" id="m-confirm-${m.id}"> I have sent it myself</label>
        <div class="row"><button class="small" data-action="confirm-sent" data-id="${m.id}" data-channel="email" data-client="${c.id}">Record as sent (email)</button>
        <button class="small" data-action="confirm-sent" data-id="${m.id}" data-channel="whatsapp" data-client="${c.id}">Record as sent (WhatsApp)</button></div>
      </div>` : ""}
      <p class="small-text">Editing removes approval. Only an approved draft can be opened, and nothing is recorded as sent until a staff member confirms.</p>
    </div>`;
  }

  // ---------- photo reading ----------
  function renderPhoto(p) {
    const rec = p.recommendation;
    const tone = rec.action === "create" ? "info" : rec.action === "already_exists" ? "info" : "warn";
    const f = p.fields;
    const files = p.files.map((x) => `<li>${esc(x.name)}: ${esc(x.doc_type.replace(/_/g, " "))}, ${esc(x.status.replace(/_/g, " "))}${x.blurry ? " <strong>(blurry, read with enhancement)</strong>" : ""}${x.reason ? ` <span class="small-text">${esc(x.reason)}</span>` : ""}</li>`).join("");
    const similar = p.similar.length ? `<div class="notice warn small-text">Similar name already on file: ${p.similar.map((m) => `${esc(m.code)} ${esc(m.name)}`).join(", ")}.
      <label class="row"><input type="checkbox" id="photo-confirm-similar"> Create anyway: this is a different person</label></div>` : "";
    const existing = p.existing ? `<div class="notice info">Already exists: <a href="#clients/${p.existing.id}">${esc(p.existing.code)} ${esc(p.existing.name)}</a>. Open it instead.</div>` : "";
    const canCreate = rec.action !== "already_exists";
    return `<div class="card" style="margin-top:12px">
      <div class="notice ${tone}"><strong>${esc(rec.headline)}</strong>
        <ul class="clean small-text">${rec.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>
      <ul class="clean small-text">${files}</ul>
      ${existing}${similar}
      ${canCreate ? `<div class="two" style="margin-top:8px">
        <label class="field">Full name *<input type="text" id="photo-name" value="${esc(f.name || "")}"></label>
        <label class="field">PAN<input type="text" id="photo-pan" value="${esc(f.pan || "")}" placeholder="Type it from the original if it was not read"></label>
        <label class="field">Aadhaar (masked)<input type="text" value="${esc(f.aadhaar || "not read")}" disabled></label>
        <label class="field">GSTIN<input type="text" value="${esc(f.gstin || "not read")}" disabled></label>
        <label class="field">Service<select id="photo-service">${["ITR", "GST", "Audit"].map((x) => `<option ${x === f.service ? "selected" : ""}>${x}</option>`).join("")}</select></label>
        <label class="field">Email<input type="email" id="photo-email" value=""></label>
        <label class="field">Phone (10 digits)<input type="text" id="photo-phone" value="" inputmode="numeric"></label>
      </div>
      <div class="row" style="margin-top:8px">
        <button class="small" data-action="photo-create">${rec.action === "create" ? "Create client (suggested)" : "Create client"}</button>
        <button class="small danger" data-action="photo-disqualify">Disqualify this photo</button>
      </div>
      <label class="field small-text">Reason for disqualifying (optional)<input type="text" id="photo-note"></label>` : `<p class="small-text">No new client is created.</p>`}
    </div>`;
  }

  // ---------- actions ----------
  const handlers = {
    async "photo-create"() {
      const draft = window.__photo && window.__photo.draft_id;
      if (!draft) return toast("Read a photo first", "error");
      const body = {
        staff: requireStaff(),
        decision: "create",
        name: document.getElementById("photo-name").value,
        pan: document.getElementById("photo-pan").value,
        service: document.getElementById("photo-service").value,
        email: document.getElementById("photo-email").value,
        phone: document.getElementById("photo-phone").value,
        confirm_similar: !!(document.getElementById("photo-confirm-similar") || {}).checked,
      };
      const r = await api("POST", `/api/photo-intake/${draft}/decision`, body);
      window.__photo = null;
      if (r.outcome === "already_exists") toast(`Already exists as ${r.code}. Opened it instead.`);
      else toast(`Created ${r.code || "client"} from the photo`);
      location.hash = `#clients/${r.client_id}`;
    },
    async "photo-disqualify"() {
      const draft = window.__photo && window.__photo.draft_id;
      if (!draft) return;
      await api("POST", `/api/photo-intake/${draft}/decision`, {
        staff: requireStaff(), decision: "disqualify", note: document.getElementById("photo-note").value,
      });
      window.__photo = null;
      toast("Photo disqualified. No client was created.");
      pages.clients();
    },
    async "open-client"(el) { location.hash = `#clients/${el.dataset.id}`; },
    async "run-example"(el) {
      const r = await api("POST", `/api/examples/${encodeURIComponent(el.dataset.key)}/run`);
      toast(r.already_processed || r.outcome === "already_processed" ? "Already run. Nothing changed." : `Done: ${r.outcome.replace(/_/g, " ")}`);
      pages.examples();
    },
    async "run-all-examples"() {
      const r = await api("POST", "/api/demo/load");
      toast(`Ran ${r.processed.length} built-in examples`);
      pages.examples();
    },


    async "process-sample"(el) {
      const r = await api("POST", `/api/sample-emails/${el.dataset.index}/process`, { actor: staffName() || "intake" });
      toast(r.already_processed || r.outcome === "already_processed" ? "Already processed. Nothing changed." : `Processed: ${r.outcome.replace(/_/g, " ")}`);
      pages.intake();
    },
    async "load-demo"() {
      const r = await api("POST", "/api/demo/load");
      window.__emlResults = r.processed;
      toast(`Processed ${r.processed.length} sample emails`);
      pages.intake();
    },
    async "read-inbox"() {
      const r = await api("POST", "/api/intake/inbox");
      window.__emlResults = r.results;
      toast(r.files_found ? `Read ${r.files_found} file(s) from the inbox` : "The inbox folder is empty. Drop .eml files into data/inbox");
      pages.intake();
    },
    async reset() {
      if (!confirm("Delete all demo clients, documents, drafts and logs?")) return;
      await api("POST", "/api/demo/reset");
      toast("Demo data cleared");
      pages.intake();
    },
    async "run-reminders"() {
      const date = document.getElementById("reminder-date").value;
      const r = await api("POST", "/api/reminders/run", { staff: staffName() || "scheduler", as_of: date });
      toast(r.drafts_created.length ? `${r.drafts_created.length} reminder draft(s) created. Nothing sent.` : "No reminders due for that date");
      pages.dashboard();
    },
    async "save-client"(el) {
      const id = el.dataset.id;
      await api("PATCH", `/api/clients/${id}`, {
        staff: requireStaff(),
        name: document.getElementById("c-name").value,
        pan: document.getElementById("c-pan").value,
        email: document.getElementById("c-email").value,
        phone: document.getElementById("c-phone").value,
        service: document.getElementById("c-service").value,
      });
      toast("Details saved");
      render();
    },
    async onboard(el) {
      await api("POST", `/api/clients/${el.dataset.id}/onboard`, { staff: requireStaff() });
      toast("Client marked onboarded");
      render();
    },
    async "resolve-review"(el) {
      const id = el.dataset.id;
      const action = document.getElementById(`rv-action-${id}`).value;
      const note = document.getElementById(`rv-note-${id}`).value;
      await api("POST", `/api/review/${id}/resolve`, { staff: requireStaff(), action, note });
      toast("Decision recorded");
      render();
    },
    async "save-draft"(el) {
      const id = el.dataset.id;
      await api("PATCH", `/api/messages/${id}`, {
        staff: requireStaff(),
        subject: document.getElementById(`m-subject-${id}`).value,
        body: document.getElementById(`m-body-${id}`).value,
        whatsapp_body: document.getElementById(`m-wa-${id}`).value,
      });
      toast("Draft saved. Approval needed again.");
      render();
    },
    async "approve-msg"(el) {
      await api("POST", `/api/messages/${el.dataset.id}/approve`, { staff: requireStaff() });
      toast("Approved. You can now open it and send it.");
      render();
    },
    async "reject-msg"(el) {
      const note = prompt("Why is this draft rejected? (optional)") || "";
      await api("POST", `/api/messages/${el.dataset.id}/reject`, { staff: requireStaff(), note });
      toast("Draft rejected");
      render();
    },
    async "open-link"(el) {
      const r = await api("POST", `/api/messages/${el.dataset.id}/link`, { staff: requireStaff(), channel: el.dataset.channel });
      window.open(r.url, "_blank", "noopener");
      toast("Opened in your app. Press send there, then tick 'I have sent it' below.");
    },
    async "confirm-sent"(el) {
      const id = el.dataset.id;
      if (!document.getElementById(`m-confirm-${id}`).checked) {
        toast("Press send in your app first, then tick 'I have sent it'", "error");
        return;
      }
      const r = await api("POST", `/api/messages/${id}/send`, { staff: requireStaff(), channel: el.dataset.channel, confirmed: true });
      toast(`Recorded as sent via ${r.channel} by staff.`);
      render();
    },
    async "filter-messages"(el) {
      window.__msgFilter = el.dataset.status;
      pages.messages();
    },
  };

  document.addEventListener("click", async (event) => {
    const el = event.target.closest("[data-action]");
    if (!el || el.disabled) return;
    const handler = handlers[el.dataset.action];
    if (!handler) return;
    try {
      await handler(el);
    } catch (err) {
      toast(err.message || "Something went wrong", "error");
    }
  });

  document.addEventListener("input", (event) => {
    if (event.target.id !== "client-search") return;
    const needle = event.target.value.trim().toLowerCase();
    let shown = 0;
    document.querySelectorAll("#client-rows tr").forEach((row) => {
      const match = !needle || row.dataset.search.includes(needle);
      row.hidden = !match;
      if (match) shown += 1;
    });
    const counter = document.getElementById("client-count");
    if (counter) counter.textContent = needle ? `${shown} matching` : `${document.querySelectorAll("#client-rows tr").length} client(s)`;
  });

  document.addEventListener("submit", async (event) => {
    const form = event.target;
    if (!["new-client-form", "upload-form", "photo-form"].includes(form.id) && !form.classList.contains("upload-form") && !form.classList.contains("manual-form")) return;
    event.preventDefault();
    try {
      if (form.id === "photo-form") {
        const data = new FormData();
        data.append("staff", requireStaff());
        for (const file of form.files.files) data.append("files", file);
        const response = await fetch("/api/photo-intake", { method: "POST", body: data });
        let body = null;
        try { body = await response.json(); } catch (_) { /* not JSON */ }
        if (!response.ok) throw new Error((body && (body.error || body.detail)) || "Could not read the photo");
        window.__photo = body;
        document.getElementById("photo-preview").innerHTML = renderPhoto(body);
        toast("Photo read. Check the details, then decide.");
        return;
      }
      if (form.id === "new-client-form") {
        const d = Object.fromEntries(new FormData(form).entries());
        const created = await api("POST", "/api/clients", { ...d, staff: requireStaff() });
        toast(`Created ${created.code}`);
        location.hash = `#clients/${created.id}`;
      } else if (form.classList.contains("upload-form")) {
        const data = new FormData(form);
        data.append("staff", requireStaff());
        data.append("doc_type", form.doc_type.value);
        const response = await fetch(`/api/clients/${form.dataset.client}/documents`, { method: "POST", body: data });
        let body = null;
        try { body = await response.json(); } catch (_) { /* not JSON */ }
        if (!response.ok) throw new Error((body && (body.error || body.detail)) || "Upload failed");
        const last = body.documents[body.documents.length - 1];
        toast(last && last.status === "rejected" ? `Rejected: ${last.reason}` : "Uploaded and checked", last && last.status === "rejected" ? "error" : undefined);
        render();
      } else if (form.classList.contains("manual-form")) {
        const type = form.doc_type.value;
        const number = form.number.value.trim();
        const name = form.name.value.trim();
        const label = form.label.value.trim();
        let values;
        if (type === "pan") values = { pan: number, name };
        else if (type === "aadhaar") values = { aadhaar: number, name };
        else if (type === "gst_certificate") values = { gstin: number, name };
        else if (type === "bank_statement") values = { account_holder: name, account_number: number };
        else values = { label };
        await api("POST", `/api/clients/${form.dataset.client}/documents/manual`, { staff: requireStaff(), doc_type: type, values });
        toast("Details saved and checked");
        render();
      }
    } catch (err) {
      toast(err.message, "error");
    }
  });

  document.addEventListener("submit", async (event) => {
    if (event.target.id === "example-form") {
      event.preventDefault();
      const form = event.target;
      const data = new FormData(form);
      try {
        const response = await fetch("/api/examples", { method: "POST", body: data });
        let body = null;
        try { body = await response.json(); } catch (_) { /* not JSON */ }
        if (!response.ok) throw new Error((body && (body.error || body.detail)) || "Could not save the example");
        toast(`Saved “${body.title}”. Run it from the list.`);
        form.reset();
        pages.examples();
      } catch (err) {
        toast(err.message, "error");
      }
      return;
    }
    if (event.target.id === "eml-form") {
      event.preventDefault();
      const form = event.target;
      const data = new FormData();
      for (const file of form.files.files) data.append("files", file);
      try {
        const response = await fetch("/api/intake/eml", { method: "POST", body: data });
        let body = null;
        try { body = await response.json(); } catch (_) { /* not JSON */ }
        if (!response.ok) throw new Error((body && (body.error || body.detail)) || "Could not read the files");
        window.__emlResults = body.results;
        toast(`Read ${body.results.length} email file(s)`);
        pages.intake();
      } catch (err) {
        toast(err.message, "error");
      }
      return;
    }
    if (event.target.id !== "intake-form") return;
    event.preventDefault();
    const form = event.target;
    const data = new FormData();
    data.append("sender", form.sender.value.trim());
    data.append("body", form.body.value);
    for (const file of form.files.files) data.append("files", file);
    try {
      const response = await fetch("/api/intake", { method: "POST", body: data });
      let body = null;
      try { body = await response.json(); } catch (_) { /* not JSON */ }
      if (!response.ok) throw new Error((body && (body.error || body.detail)) || "Could not process the email");
      toast(`Processed: ${body.outcome.replace(/_/g, " ")}`);
      location.hash = `#clients/${body.client_id}`;
    } catch (err) {
      toast(err.message, "error");
    }
  });

  // ---------- routing ----------
  function setActiveNav(name) {
    document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === name));
  }

  async function render() {
    const hash = location.hash.replace(/^#/, "") || "dashboard";
    const [name, arg] = hash.split("/");
    const page = name === "clients" && arg ? "client" : name;
    setActiveNav(name === "clients" ? "clients" : page);
    try {
      if (page === "client") await pages.client(arg);
      else if (pages[page]) await pages[page](arg);
      else await pages.dashboard();
    } catch (err) {
      main.innerHTML = `<div class="notice warn">${esc(err.message)}</div>`;
    }
  }

  window.addEventListener("hashchange", render);
  render();
})();
