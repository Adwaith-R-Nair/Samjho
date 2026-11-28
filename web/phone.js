// Real phone call: a small form asks for an Indian mobile number and consent, POST /api/call places the call,
// and /ws/watch streams the call's UI events (the same ones text and browser voice emit) into this page.
(() => {
  const STATUS = {
    ringing: (ev) => `Calling ${ev.to || "your phone"}. It shows as an International Call from a +1 (US) number.`,
    connected: () => "Call connected. Speak on the phone; this panel follows the call live.",
    ended: () => "Call ended.",
    not_answered: () => "The call was not answered.",
  };

  let box = null;
  let watch = null;
  let recordNote = "";

  // The access code arrives once in the shared link (?k=...) and is kept for this tab.
  const params = new URLSearchParams(location.search);
  try {
    if (params.get("k")) sessionStorage.setItem("samjho_k", params.get("k"));
  } catch (e) {
    /* storage blocked: the code is read from the URL each time */
  }
  function accessCode() {
    try {
      return sessionStorage.getItem("samjho_k") || params.get("k") || "";
    } catch (e) {
      return params.get("k") || "";
    }
  }

  // The form is in the page (#phoneForm, start options); its errors show under it (#phoneErr).
  function form() {
    if (box) return box;
    box = document.getElementById("phoneForm");
    box.addEventListener("submit", (e) => {
      e.preventDefault();
      call().catch((err) => formNote(err.message, true));
    });
    return box;
  }

  function formNote(text, isError) {
    const p = document.getElementById("phoneErr");
    p.textContent = text;
    p.hidden = !text;
    p.classList.toggle("is-note", !isError);
  }

  // Once the call is placed, its status follows in the session view (#callStatus).
  function status(text) {
    const p = document.getElementById("callStatus");
    p.textContent = text;
    p.hidden = !text;
  }

  async function call() {
    const f = form();
    const phone = f.phone.value.replace(/[\s-]/g, "");
    if (!/^\+91[6-9]\d{9}$/.test(phone)) throw new Error("Enter an Indian mobile number as +91 followed by 10 digits.");
    if (!f.consent.checked) throw new Error("Please tick the box to agree to receive the demo call.");
    // Only with the consent box ticked: the person answering agrees to be recorded and shown as a demo replay.
    const record = Boolean(document.getElementById("recordConsent")?.checked);
    const button = f.querySelector("button");
    button.disabled = true;
    formNote("Placing the call...", false);
    try {
      const res = await fetch("/api/call", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, consent: true, lang: window.samjhoLang(), k: accessCode(), record }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      window.samjhoReset();
      formNote("", false);
      recordNote = record ? "Recording for a demo replay. " : "";
      status(recordNote + "Placing the call...");
      window.samjhoShowSession("phone");
      follow(data.watch_id);
    } finally {
      button.disabled = false;
    }
  }

  function follow(id) {
    if (watch) watch.close();
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/watch?id=${encodeURIComponent(id)}`);
    watch = ws;
    ws.onmessage = (msg) => {
      const ev = JSON.parse(msg.data);
      if (ev.type === "call") {
        const live = ev.status === "ringing" || ev.status === "connected";
        status((live ? recordNote : "") + (STATUS[ev.status] || (() => ev.status))(ev));
        return;
      }
      window.samjhoHandleEvent(ev);
    };
    ws.onclose = () => {
      if (watch === ws) watch = null;
    };
  }

  function open() {
    form().hidden = false;
    form().querySelector("input[name=phone]").focus();
  }
  form();

  window.samjhoPhone = { open };
})();
