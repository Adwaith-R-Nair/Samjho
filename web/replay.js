// Replay of a recorded, consented session: plays its audio and feeds its UI events to window.samjhoHandleEvent
// at the times they happened, so the transcript, fact chips and record appear in sync. Seeking re-renders.
(() => {
  let box = null;
  let list = [];
  let events = [];
  let next = 0;
  let timer = null;
  let audio = null;
  let wallStart = 0;

  function ui() {
    if (box) return box;
    box = document.createElement("div");
    box.className = "replay-box";
    box.style.margin = "12px 0 0";
    box.innerHTML = `
      <div class="replay-pick" hidden>
        <label class="muted">Recorded session:
          <select class="replay-select"></select>
        </label>
        <button type="button" class="replay-play">Play</button>
      </div>
      <p class="replay-badge" hidden style="color: var(--amber); font-weight: 700; margin: 8px 0"></p>
      <audio class="replay-audio" controls preload="auto" hidden style="width: 100%"></audio>`;
    box.querySelector(".replay-play").onclick = () => {
      const m = list[box.querySelector(".replay-select").selectedIndex];
      if (m) play(m).catch((e) => badge(e.message));
    };
    audio = box.querySelector(".replay-audio");
    audio.addEventListener("seeked", () => {
      if (events.length) rerender(audio.currentTime);
    });
    // Shown in the session view, above the conversation.
    const host = document.getElementById("sessionStatus");
    if (host) host.appendChild(box);
    else {
      const tiles = document.getElementById("tiles");
      tiles.parentNode.insertBefore(box, tiles.nextSibling);
    }
    return box;
  }

  function badge(text) {
    const p = ui().querySelector(".replay-badge");
    p.textContent = text;
    p.hidden = !text;
  }

  function label(m) {
    const date = (m.started_at || "").slice(0, 10);
    const lang = m.lang === "en" ? "English" : "Hindi";
    const score = m.right_first_answer == null ? "" : `, ${m.right_first_answer}/5 right first, ${m.right_after_samjho}/5 after`;
    return `${date}, ${m.channel === "phone" ? "phone call" : "browser"}, ${lang}, ${Math.round(m.duration_s || 0)} s${score}`;
  }

  function now() {
    return audio && !audio.hidden ? audio.currentTime : (performance.now() - wallStart) / 1000;
  }

  function dispatchUntil(t) {
    while (next < events.length && events[next].t <= t) {
      const { t: _t, ...ev } = events[next++];
      window.samjhoHandleEvent(ev);
    }
  }

  function rerender(t) {
    window.samjhoReset();
    next = 0;
    dispatchUntil(t);
  }

  function stop() {
    if (timer) clearInterval(timer);
    timer = null;
    if (audio) {
      audio.pause();
      audio.removeAttribute("src");
      audio.hidden = true;
    }
    events = [];
    next = 0;
  }

  async function play(m) {
    stop();
    window.samjhoReset();
    const res = await fetch(`/api/replays/${encodeURIComponent(m.id)}/events`);
    if (!res.ok) throw new Error("This replay could not be loaded.");
    events = await res.json();
    const date = (m.started_at || "").slice(0, 10);
    badge(`REPLAY of a real consented session, recorded ${date}. Not live.`);
    if (m.has_audio) {
      audio.src = `/api/replays/${encodeURIComponent(m.id)}/audio`;
      audio.hidden = false;
      // Browsers may block autoplay; then the person presses play on the controls and the panel follows.
      audio.play().catch(() => {});
    } else {
      wallStart = performance.now();
    }
    timer = setInterval(() => dispatchUntil(now()), 50);
  }

  async function open() {
    ui();
    const res = await fetch("/api/replays");
    list = res.ok ? await res.json() : [];
    if (!list.length) {
      badge("No recorded session yet.");
      return;
    }
    const pick = box.querySelector(".replay-pick");
    const select = box.querySelector(".replay-select");
    select.innerHTML = "";
    list.forEach((m) => {
      const opt = document.createElement("option");
      opt.textContent = label(m);
      select.appendChild(opt);
    });
    pick.hidden = list.length < 2;
    if (list.length === 1) await play(list[0]);
  }

  // Starting any other session stops the replay first, so its events never mix into a live panel.
  document.getElementById("tiles").addEventListener(
    "click",
    (e) => {
      const tile = e.target.closest(".tile");
      if (tile && tile.dataset.mode !== "replay") {
        stop();
        if (box) badge("");
      }
    },
    true,
  );

  window.samjhoReplay = { open, stop };
})();
