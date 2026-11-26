// Samjho UI. One screen: start a session one of four ways, see each fact turn green or red as she speaks.

const $ = (id) => document.getElementById(id);
const STATUS_TEXT = {
  green: "Understood",
  amber: "Close, not exact",
  red: "Not what the loan says",
  grey: "Not said yet",
  unclear: "Lender will call to explain",
};
const FACT_NAMES = {
  cash_in_hand: "cash in hand",
  deductions: "deductions",
  instalment: "instalment",
  frequency: "how often",
  total: "total to repay",
};
const CASE_TEXT = {
  HOLD_REVIEW: "Held for the grievance officer: she reported a demand for extra money.",
  CALLBACK: "Callback booked: ",
};

let sessionId = null;

function lang() {
  return document.querySelector('input[name="lang"]:checked').value;
}

function fmt(value) {
  if (typeof value === "number") return "Rs " + Math.round(value).toLocaleString("en-IN");
  return value ?? "";
}

function bubble(who, main, sub) {
  const div = document.createElement("div");
  div.className = `bubble ${who}`;
  div.innerHTML = `<div class="main"></div>${sub ? '<div class="sub"></div>' : ""}`;
  div.querySelector(".main").textContent = main;
  if (sub) div.querySelector(".sub").textContent = sub;
  $("transcript").appendChild(div);
  div.scrollIntoView({ block: "end", behavior: "smooth" });
}

function note(text, kind = "") {
  const p = document.createElement("div");
  p.className = `event ${kind}`;
  p.textContent = text;
  $("events").appendChild(p);
}

function resetPanel() {
  $("transcript").innerHTML = "";
  $("events").innerHTML = "";
  $("record").hidden = true;
  document.querySelectorAll(".fact").forEach((li) => {
    li.className = "fact";
    li.querySelector(".said").textContent = "";
  });
}

function renderRecord(record) {
  const box = $("record");
  const facts = Object.entries(record.facts)
    .map(([k, f]) => `<li class="${f.status}"><b>${FACT_NAMES[k]}</b>: ${STATUS_TEXT[f.status]}${f.her_words ? ` (she said "${escapeHtml(f.her_words)}")` : ""}${f.explained_again ? `, explained again ${f.explained_again}x` : ""}</li>`)
    .join("");
  box.innerHTML = `
    <h3>Acknowledgement record</h3>
    <p>Consent: <b>${record.consent ?? "none"}</b>. Understood all five: <b>${record.understood_all ? "yes" : "no"}</b>.
       Extra money reported: <b>${record.extra_money_reported === null ? "not asked" : record.extra_money_reported ? "yes, held for review" : "no"}</b>.</p>
    <p class="score">Right on her first answer: <b>${record.right_first_answer} of 5</b>. Right after Samjho: <b>${record.right_after_samjho} of 5</b>.</p>
    <ul>${facts}</ul>
    <p class="seal">Seal (SHA-256 of the whole session log): <code>${record.seal_sha256}</code></p>
    <button type="button" id="download">Download record (JSON)</button>`;
  box.hidden = false;
  $("download").onclick = () => {
    const blob = new Blob([JSON.stringify(record, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `samjho-record-${record.session_id}.json`;
    a.click();
  };
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// Shared by every channel: text, browser voice, phone and replay all emit the same events.
function handleEvent(ev) {
  switch (ev.type) {
    case "say":
      bubble("bot", ev.text, lang() === "hi" ? ev.en : null);
      break;
    case "heard":
      bubble("user", ev.text);
      break;
    case "fact": {
      const li = document.querySelector(`.fact[data-fact="${ev.fact}"]`);
      li.className = `fact ${ev.status}`;
      const said = ev.quote ? `She said "${ev.quote}"${ev.said !== null && ev.fact !== "frequency" ? ` = ${fmt(ev.said)}` : ""}. ` : "";
      li.querySelector(".said").textContent = said + STATUS_TEXT[ev.status];
      break;
    }
    case "case":
      if (ev.case === "HOLD_REVIEW") note(CASE_TEXT.HOLD_REVIEW, "case");
      else if (ev.case === "CALLBACK") note(CASE_TEXT.CALLBACK + ev.detail, "case");
      else note(ev.detail || ev.case, "case"); // KEY_NOT_SET, BUSY and other notices
      break;
    case "record":
      renderRecord(ev.record);
      $("say").hidden = true;
      break;
    case "latency":
      note(`Turn ${ev.turn}: ${ev.ms} ms from end of speech to first reply audio`, "latency");
      break;
  }
}
window.samjhoHandleEvent = handleEvent;

async function post(url, body) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
  return res.json();
}

async function startText() {
  resetPanel();
  $("hint").hidden = false;
  const data = await post("/api/text/start", { lang: lang() });
  sessionId = data.session_id;
  data.events.forEach(handleEvent);
  $("say").hidden = false;
  $("sayText").focus();
}

$("say").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("sayText").value.trim();
  if (!text || !sessionId) return;
  $("sayText").value = "";
  try {
    const data = await post("/api/text/say", { session_id: sessionId, text });
    data.events.forEach(handleEvent);
  } catch (err) {
    note(err.message, "case");
  }
});

async function loadStatus() {
  const res = await fetch("/api/status");
  const status = await res.json();
  const modeNeeds = { browser: "voice", phone: "phone", text: "text", replay: "replay" };
  document.querySelectorAll(".tile").forEach((tile) => {
    const s = status[modeNeeds[tile.dataset.mode]];
    tile.disabled = !s.ready;
    tile.querySelector(".state").textContent = s.ready ? "" : s.reason;
  });
  const missing = Object.values(status).filter((s) => !s.ready).length;
  $("keys").textContent = missing
    ? "Some features are off because their keys are not set. Typing always works."
    : "All features available.";
}

document.querySelector('.tile[data-mode="text"]').addEventListener("click", () => startText().catch((e) => note(e.message, "case")));

// Browser voice (web/voice.js): the same events arrive over a WebSocket and go through handleEvent.
function startBrowserVoice() {
  resetPanel();
  sessionId = null;
  $("say").hidden = true;
  $("hint").hidden = false;
  return window.samjhoVoice.start(lang());
}
document.querySelector('.tile[data-mode="browser"]').addEventListener("click", () => startBrowserVoice().catch((e) => note(e.message, "case")));

loadStatus().catch(() => {
  $("keys").textContent = "Could not reach the server.";
});
