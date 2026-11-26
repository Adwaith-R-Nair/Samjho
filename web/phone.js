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

  function form() {
    if (box) return box;
    box = document.createElement("div");
    box.className = "phone-box";
    box.style.margin = "12px 0 0";
    box.innerHTML = `
      <form class="say phone-form" style="flex-wrap: wrap">
        <input name="phone" type="tel" inputmode="tel" autocomplete="tel" value="+91" aria-label="Indian mobile number"
               placeholder="+91 98765 43210" required>
        <button type="submit">Call me</button>
        <label class="muted" style="flex-basis: 100%; margin: 4px 0 0">
          <input name="consent" type="checkbox">
          I agree to receive one demo call from a +1 (US) number; it shows as an International Call.
        </label>
      </form>
      <p class="phone-status muted" hidden></p>`;
    box.querySelector("form").addEventListener("submit", (e) => {
      e.preventDefault();
      call().catch((err) => status(err.message));
    });
    const tiles = document.getElementById("tiles");
    tiles.parentNode.insertBefore(box, tiles.nextSibling);
    return box;
  }

  function status(text) {
    const p = form().querySelector(".phone-status");
    p.textContent = text;
    p.hidden = !text;
  }

  async function call() {
    const f = form().querySelector("form");
    const phone = f.phone.value.replace(/[\s-]/g, "");
    if (!/^\+91[6-9]\d{9}$/.test(phone)) throw new Error("Enter an Indian mobile number as +91 followed by 10 digits.");
    if (!f.consent.checked) throw new Error("Please tick the box to agree to receive the demo call.");
    const button = f.querySelector("button");
    button.disabled = true;
    status("Placing the call...");
    try {
      const res = await fetch("/api/call", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, consent: true, lang: window.samjhoLang(), k: accessCode() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      window.samjhoReset();
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
        status((STATUS[ev.status] || (() => ev.status))(ev));
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

  window.samjhoPhone = { open };
})();
