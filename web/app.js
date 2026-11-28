// Samjho UI. Two views: the landing (the story and the four start options) and the live session (voice-note
// transcript, five facts on the rings of her print, the sealed record). Every channel (text, browser voice,
// phone, replay) emits the same events and renders through handleEvent(). Visuals: web/js/landing.js (the
// print and the story) and web/js/livefx.js (rings, leaders, the number effect, the seal).

const $ = (id) => document.getElementById(id);
const STATUS_TEXT = {
  green: "Understood",
  amber: "Close, not exact",
  red: "Not what the loan says",
  grey: "Not said yet",
  unclear: "Lender will call to explain",
};
const FIRST_TEXT = {
  green: "understood",
  amber: "close, not exact",
  red: "not what the loan says",
  grey: "not said",
  "not asked": "not asked",
};
const FACT_KEYS = ["cash_in_hand", "deductions", "instalment", "frequency", "total"];
const FACT_NAMES = {
  cash_in_hand: "Cash in hand",
  deductions: "Deductions",
  instalment: "Instalment",
  frequency: "How often",
  total: "Total to repay",
};
const STAGES = {
  consent: "Asking to start",
  explain: "Explaining the loan",
  teachback: "She explains it back",
  check: "Explaining again what she missed",
  private: "A private question",
  final_consent: "Her final consent",
  done: "Sealed",
};
const CASES = {
  HOLD_REVIEW: { cls: "hold", text: () => "Held for the grievance officer: she reported a demand for extra money." },
  CALLBACK: { cls: "callback", text: (ev) => "Callback booked: " + (ev.detail || "") },
};
const MODE_TITLE = { browser: "Talking in the browser", phone: "Phone call", text: "Typing", replay: "Replay" };
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

let sessionId = null;
let mode = null;
const S = { facts: {}, latencies: [], cases: [], awaitingReply: false, turnNote: null, pendingMs: null, bulk: false, bulkT: 0 };

function lang() {
  return document.querySelector('input[name="lang"]:checked').value;
}

function fmt(value) {
  if (typeof value === "number") return "Rs " + Math.round(value).toLocaleString("en-IN");
  return value ?? "";
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
const isHindi = (s) => /[ऀ-ॿ]/.test(s || "");

// ---------------------------------------------------------------- the conversation, as voice notes
function addNote(who, text, en) {
  const typed = mode === "text";
  const li = document.createElement("li");
  li.className = `note ${who === "bot" ? "s" : "h"}${typed ? " typed" : ""}`;
  li.innerHTML =
    '<div class="note-head"><span class="who"></span><span class="meta"></span></div><p class="note-text"></p>' +
    (en ? '<p class="note-en"></p>' : "") +
    (typed ? '<span class="tag"></span>' : "");
  li.querySelector(".who").textContent = who === "bot" ? "Samjho" : "Her";
  const p = li.querySelector(".note-text");
  p.textContent = text;
  if (isHindi(text)) p.lang = "hi";
  if (en) li.querySelector(".note-en").textContent = en;
  if (typed) li.querySelector(".tag").textContent = who === "bot" ? "Text reply, no audio in typing mode" : "Typed";
  $("transcript").appendChild(li);
  const convo = li.closest(".convo");
  // Wide screens scroll the conversation column; phones scroll the page to the newest note, except while a
  // checked figure is playing on the print (web/js/livefx.js returns to the conversation afterwards).
  if (innerWidth >= 1000) convo.scrollTo({ top: convo.scrollHeight, behavior: S.bulk || reducedMotion ? "auto" : "smooth" });
  else if (!S.bulk && !window.samjhoFx?.busy()) showLatestNote();
  // Voice notes arrive on a spring from their speaker's side.
  if (window.gsap && !reducedMotion && !S.bulk) {
    const fromLeft = who === "bot";
    gsap.fromTo(li, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.35, ease: "power2.out" });
    gsap.fromTo(
      li,
      { x: fromLeft ? -36 : 36, y: 16, scale: 0.92, transformOrigin: fromLeft ? "0% 100%" : "100% 100%" },
      { x: 0, y: 0, scale: 1, duration: 1.1, ease: "elastic.out(1, 0.62)", clearProps: "transform" },
    );
  }
  return li;
}

// Phones: bring the newest note's bottom into view, above the sticky answer box.
function showLatestNote() {
  const li = $("transcript").lastElementChild;
  if (!li || innerWidth >= 1000 || document.body.dataset.view !== "live") return;
  const r = li.getBoundingClientRect();
  const room = $("say").hidden ? 24 : 96;
  if (r.bottom <= innerHeight - room && r.top >= 64) return;
  const y = scrollY + r.bottom - innerHeight + room;
  if (window.samjhoStage?.pageTo) window.samjhoStage.pageTo(y);
  else scrollTo({ top: y, behavior: reducedMotion ? "auto" : "smooth" });
}
window.samjhoShowLatestNote = showLatestNote;

function note(text, kind = "", badge = null) {
  const p = document.createElement("p");
  p.className = `event ${kind}${badge === "hold" ? " is-hold" : ""}`;
  if (badge) {
    const b = document.createElement("span");
    b.className = `case-badge ${badge}`;
    b.textContent = badge === "hold" ? "HOLD_REVIEW" : "CALLBACK";
    p.appendChild(b);
  }
  p.appendChild(document.createTextNode(text));
  $("events").appendChild(p);
}

// ---------------------------------------------------------------- status line
function setStatus(text) {
  $("status").textContent = text;
}
function setStage(state) {
  $("stageText").textContent = STAGES[state] || "Starting";
}
function setPill(kind) {
  $("pill").className = `pill is-${kind}`;
  $("pillText").textContent = kind === "sealed" ? "SEALED" : kind === "replay" ? "REPLAY" : "LIVE";
}
function setReply(ms) {
  S.latencies.push(ms);
  const sorted = [...S.latencies].sort((a, b) => a - b);
  const med = sorted[Math.floor(sorted.length / 2)];
  $("replyTime").innerHTML = `Reply <b class="tnum">${(ms / 1000).toFixed(2)} s</b>, median <span class="tnum">${(med / 1000).toFixed(2)} s</span> over ${S.latencies.length} turn${S.latencies.length === 1 ? "" : "s"}`;
}
function markReply(li, ms) {
  li.querySelector(".meta").innerHTML = `replied in <b class="tnum">${(ms / 1000).toFixed(2)} s</b>`;
}

// ---------------------------------------------------------------- facts
function resetFacts() {
  FACT_KEYS.forEach((k) => {
    S.facts[k] = { first: null, firstQuote: null, firstSaid: null, now: "grey", quote: null, said: null, again: 0, count: 0 };
    renderFact(k);
  });
}
function saidText(k, quote, said) {
  if (!quote) return "";
  return `"<span class="q">${escapeHtml(quote)}</span>"${said !== null && said !== undefined && k !== "frequency" ? ` = ${fmt(said)}` : ""}`;
}
// "First" keeps her first answer (the first verdict code gave, as the record counts it) beside "Now".
function renderFact(k) {
  const f = S.facts[k];
  const li = document.querySelector(`.fact[data-fact="${k}"]`);
  li.className = `fact ${f.now}`;
  const showFirst = f.first && f.count > 1;
  li.querySelector(".f-first").innerHTML = showFirst
    ? `First: ${f.firstQuote ? saidText(k, f.firstQuote, f.firstSaid) + ", " : ""}<span class="v-${f.first}">${FIRST_TEXT[f.first]}</span>`
    : "";
  li.querySelector(".f-now").innerHTML = `${showFirst ? "Now: " : ""}${f.quote ? saidText(k, f.quote, f.said) + ". " : ""}<b>${STATUS_TEXT[f.now] || f.now}</b>${f.again ? `, explained again ${f.again}x` : ""}`;
}
function onFact(ev) {
  const f = S.facts[ev.fact];
  if (!f) return;
  f.count++;
  if (!f.first && ["green", "amber", "red", "grey"].includes(ev.status)) {
    f.first = ev.status;
    f.firstQuote = ev.quote;
    f.firstSaid = ev.said;
  }
  Object.assign(f, { now: ev.status, quote: ev.quote, said: ev.said, again: ev.round || 0 });
  // With the number effect the row updates when her figure lands on it; otherwise at once.
  if (window.samjhoFx) window.samjhoFx.fact(ev, { animate: !S.bulk, onArrive: () => renderFact(ev.fact) });
  else renderFact(ev.fact);
}

// ---------------------------------------------------------------- the sealed record
function renderRecord(record) {
  const box = $("record");
  const hold = record.extra_money_reported === true;
  const callback = S.cases.includes("CALLBACK");
  const badges =
    (hold ? '<span class="case-badge hold">HOLD_REVIEW</span>' : "") +
    (callback ? '<span class="case-badge callback">CALLBACK</span>' : "") +
    (!hold && !callback ? '<span class="case-badge">NO CASE OPENED</span>' : "");
  const firsts = record.first_answer || {};
  const facts = FACT_KEYS.map((k) => {
    const f = (record.facts || {})[k];
    const first = FIRST_TEXT[firsts[k]] || firsts[k] || "not asked";
    if (!f) return `<li class="v-grey"><span><b>${FACT_NAMES[k]}</b>: not checked. First answer: ${first}.</span></li>`;
    return `<li class="v-${f.status}"><span><b>${FACT_NAMES[k]}</b>: ${STATUS_TEXT[f.status] || f.status}${f.her_words ? ` (she said "${escapeHtml(f.her_words)}")` : ""}${f.explained_again ? `, explained again ${f.explained_again}x` : ""}. First answer: ${first}.</span></li>`;
  }).join("");
  const first = record.right_first_answer;
  const after = record.right_after_samjho;
  const questions = (record.questions_for_lender || []).length;
  const hash = record.seal_sha256 || "";
  box.innerHTML = `
    <div class="rec-head"><h2 id="recTitle">Sealed record</h2><span>${badges}</span></div>
    ${hold ? '<p class="rec-p" style="color: var(--red)">Held for the grievance officer: she reported a demand for extra money.</p>' : ""}
    <p class="score">Right on her first answer: <b class="s1${first === 5 ? " ok" : ""}">${first} of 5</b>. Right after Samjho: <b class="s2${after < 5 ? " short" : ""}">${after} of 5</b>.</p>
    <p class="rec-p">Consent: <b>${escapeHtml(record.consent ?? "none")}</b>. Understood all five: <b>${record.understood_all ? "yes" : "no"}</b>.
       Extra money reported: <b>${record.extra_money_reported === null || record.extra_money_reported === undefined ? "not asked" : hold ? "yes, held for review" : "no"}</b>.${questions ? ` Questions for the lender: <b>${questions}</b>.` : ""}</p>
    <ul class="rec-list">${facts}</ul>
    <div class="seal-hash"><span>Seal: SHA-256 of the whole session log</span><code>${(hash.match(/.{1,16}/g) || []).join(" ")}</code></div>
    <div class="rec-actions"><button type="button" class="btn btn-voice" id="download"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>Download record (JSON)</button></div>
    <p class="verify">Verify offline: <code>python scripts/verify_record.py samjho-record-${escapeHtml(record.session_id)}.json</code></p>`;
  box.hidden = false;
  $("download").onclick = () => {
    const blob = new Blob([JSON.stringify(record, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `samjho-record-${record.session_id}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  };
}

function resetPanel() {
  $("transcript").innerHTML = "";
  $("events").innerHTML = "";
  $("record").hidden = true;
  $("record").innerHTML = "";
  $("replyTime").textContent = "";
  Object.assign(S, { latencies: [], cases: [], awaitingReply: false, turnNote: null, pendingMs: null });
  setStage(null);
  setPill(mode === "replay" ? "replay" : "live");
  resetFacts();
  window.samjhoFx?.reset();
  // Events handled in the same task as a reset (a replay seek re-renders everything at once) are not animated.
  S.bulk = true;
  clearTimeout(S.bulkT);
  S.bulkT = setTimeout(() => (S.bulk = false), 0);
}

// Shared by every channel: text, browser voice, phone and replay all emit the same events.
function handleEvent(ev) {
  switch (ev.type) {
    case "say": {
      const en = ev.en && ev.en !== ev.text ? ev.en : null;
      const li = addNote("bot", ev.text, en);
      // The reply time belongs to the first line Samjho says after she spoke.
      if (S.awaitingReply) {
        S.awaitingReply = false;
        S.turnNote = li;
        if (S.pendingMs !== null) markReply(li, S.pendingMs);
        S.pendingMs = null;
      }
      break;
    }
    case "heard":
      addNote("user", ev.text, null);
      S.awaitingReply = true;
      S.turnNote = null;
      S.pendingMs = null;
      break;
    case "fact":
      onFact(ev);
      break;
    case "state":
      setStage(ev.state);
      if (ev.state === "done" && mode !== "replay") setPill("sealed");
      break;
    case "case": {
      const known = CASES[ev.case];
      if (known) {
        S.cases.push(ev.case);
        note(known.text(ev), "case", known.cls);
      } else note(ev.detail || ev.case, "case"); // KEY_NOT_SET, BUSY and other notices
      break;
    }
    case "record":
      renderRecord(ev.record);
      $("say").hidden = true;
      window.samjhoFx?.seal(ev.record, { animate: !S.bulk });
      break;
    case "latency":
      setReply(ev.ms);
      if (S.turnNote) markReply(S.turnNote, ev.ms);
      else S.pendingMs = ev.ms;
      break;
  }
}
window.samjhoHandleEvent = handleEvent;

// ---------------------------------------------------------------- views
function showView(view, opts = {}) {
  if (document.body.dataset.view === view && !opts.to) return;
  document.body.dataset.view = view;
  $("live").hidden = view !== "live";
  window.samjhoStage?.onView(view, opts);
  if (view === "live") $("liveTitle").focus({ preventScroll: true });
}

// Every channel starts here: name the mode, clear the status line, show the session.
function begin(m) {
  mode = m;
  $("liveTitle").textContent = MODE_TITLE[m] || "Session";
  $("phoneForm").hidden = true;
  $("recNote").hidden = true;
  $("voiceEnd").hidden = true;
  setStatus("");
  setPill(m === "replay" ? "replay" : "live");
  $("hint").hidden = !(m === "browser" || m === "text");
  showView("live");
}

async function post(url, body) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
  return res.json();
}

async function startText() {
  begin("text");
  resetPanel();
  setStatus("Typing mode: Samjho's replies arrive as text. Type her answer below.");
  const data = await post("/api/text/start", { lang: lang() });
  sessionId = data.session_id;
  data.events.forEach(handleEvent);
  $("say").hidden = false;
  $("sayText").focus({ preventScroll: true });
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
  // Only an option that is off for want of a key earns this line; Replay off just means no session yet,
  // and its own reason already says so.
  const keyOff = ["voice", "phone"].some((k) => status[k] && !status[k].ready);
  $("keys").textContent = keyOff ? "Some options are off because their keys are not set on this server. Typing always works." : "";
  $("keys").hidden = !keyOff;
}

document.querySelector('.tile[data-mode="text"]').addEventListener("click", () => startText().catch((e) => note(e.message, "case")));

// Browser voice (web/voice.js): the same events arrive over a WebSocket and go through handleEvent.
function startBrowserVoice() {
  begin("browser");
  resetPanel();
  sessionId = null;
  $("say").hidden = true;
  return window.samjhoVoice.start(lang());
}
document.querySelector('.tile[data-mode="browser"]').addEventListener("click", () => startBrowserVoice().catch((e) => note(e.message, "case")));

// Real phone call (web/phone.js) and replays (web/replay.js) reset the panel through this.
window.samjhoLang = lang;
window.samjhoReset = () => {
  resetPanel();
  sessionId = null;
  $("say").hidden = true;
};
document.querySelector('.tile[data-mode="phone"]').addEventListener("click", () => window.samjhoPhone.open());
// Once the call is placed, the session view follows it.
window.samjhoShowSession = (m) => begin(m);

// Leaving the session (New session, or the Samjho mark) ends a browser voice session and stops a replay,
// so the mic is never left open behind the landing. A phone call carries on; its phone hangs up on its own.
function leaveSession(to) {
  if (document.body.dataset.view === "live") {
    if (window.samjhoVoice?.active()) window.samjhoVoice.stop("Session ended.");
    window.samjhoReplay?.stop();
  }
  showView("landing", { to });
}
$("newSession").addEventListener("click", () => leaveSession("start"));
document.querySelectorAll('[data-go="landing"]').forEach((a) =>
  a.addEventListener("click", (e) => {
    e.preventDefault();
    leaveSession("top");
  }),
);

// Replay of a recorded consented session (web/replay.js): its events go through handleEvent in time with its audio.
document.querySelector('.tile[data-mode="replay"]').addEventListener("click", () => {
  begin("replay");
  setStatus("Playing a recorded session. Pause or seek with the player; the panel follows.");
  window.samjhoReplay.open().catch((e) => note(e.message, "case"));
});

resetFacts();
loadStatus().catch(() => {
  $("keys").hidden = false;
  $("keys").textContent = "Could not reach the server.";
});
