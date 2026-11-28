// Replay of a recorded, consented session: plays its audio and feeds its UI events to window.samjhoHandleEvent
// at the times they happened, so the transcript, fact chips and record appear in sync. Seeking re-renders.
// The recording plays through an AudioContext (made inside the click that opens it) into two AnalyserNodes,
// so the print and the voice notes move with it as in a live session. The file is one mono mix of both voices:
// the voice notes say whose turn it is (speaker()), which opens that voice's analyser. Its loudness envelope
// is also decoded once, so every voice note's waveform is the real recording, even after a seek.
(() => {
  let box = null;
  let list = [];
  let events = [];
  let next = 0;
  let timer = null;
  let audio = null;
  let wallStart = 0;
  let ctx = null;
  let an = null;
  let gates = null;
  let env = null; // { rate, data: Float32Array } loudness at 50 Hz, 0..1
  let loadId = 0;

  // Once per page, inside a user gesture: the <audio> element now plays through this graph.
  function graph() {
    if (ctx || !audio) return;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    ctx = new AC();
    const src = ctx.createMediaElementSource(audio);
    src.connect(ctx.destination);
    const sink = ctx.createGain();
    sink.gain.value = 0;
    sink.connect(ctx.destination);
    an = {};
    gates = {};
    for (const who of ["samjho", "her"]) {
      const a = ctx.createAnalyser();
      a.fftSize = 1024;
      a.smoothingTimeConstant = 0.5;
      a.minDecibels = -96;
      a.maxDecibels = -22;
      a.connect(sink);
      const g = ctx.createGain();
      g.gain.value = who === "samjho" ? 1 : 0;
      src.connect(g).connect(a);
      an[who] = a;
      gates[who] = g;
    }
  }

  function speaker(who) {
    if (!gates) return;
    gates.samjho.gain.setTargetAtTime(who === "her" ? 0 : 1, ctx.currentTime, 0.03);
    gates.her.gain.setTargetAtTime(who === "her" ? 1 : 0, ctx.currentTime, 0.03);
  }

  // Loudness envelope of the recording (no gesture needed: an OfflineAudioContext only decodes).
  async function loadEnvelope(url, id) {
    try {
      const OAC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
      const res = await fetch(url);
      if (!OAC || !res.ok) return;
      const buf = await new OAC(1, 1, 16000).decodeAudioData(await res.arrayBuffer());
      const d = buf.getChannelData(0);
      const hop = Math.round(buf.sampleRate / 50);
      const n = Math.ceil(d.length / hop);
      const data = new Float32Array(n);
      for (let i = 0; i < n; i++) {
        let s = 0;
        const a = i * hop;
        const b = Math.min(d.length, a + hop);
        for (let k = a; k < b; k++) s += d[k] * d[k];
        data[i] = Math.sqrt(s / Math.max(1, b - a));
      }
      const ref = Array.from(data).sort((x, y) => x - y)[Math.floor(n * 0.95)] || 1;
      for (let i = 0; i < n; i++) data[i] = Math.min(1, (data[i] / ref) * 0.85);
      if (id === loadId) env = { rate: 50, data };
    } catch (e) {
      /* no waveforms; the replay itself still plays */
    }
  }

  // n bars of the recording's loudness between s and e seconds (null until decoded).
  function envelope(s, e, n) {
    if (!env || !(e > s)) return null;
    const out = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const a = Math.floor((s + ((e - s) * i) / n) * env.rate);
      const b = Math.max(a + 1, Math.floor((s + ((e - s) * (i + 1)) / n) * env.rate));
      let m = 0;
      for (let k = a; k < b && k < env.data.length; k++) m = Math.max(m, env.data[k]);
      out[i] = m;
    }
    return out;
  }

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
      graph();
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
      const { t: at, ...ev } = events[next++];
      window.samjhoHandleEvent(ev, at);
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
    env = null;
    loadId++;
    if (an && window.samjhoField?.analysers.samjho === an.samjho) window.samjhoField.attach(null);
  }

  // Seek to t seconds (a voice note was tapped). The audio's seeked event re-renders the panel.
  function seek(t) {
    if (!events.length) return;
    t = Math.max(0, t);
    if (audio && !audio.hidden) {
      audio.currentTime = t;
      if (audio.paused) audio.play().catch(() => {});
    } else {
      wallStart = performance.now() - t * 1000;
      rerender(t);
    }
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
      if (ctx) {
        ctx.resume().catch(() => {});
        window.samjhoField?.attach(an);
      }
      loadEnvelope(audio.src, ++loadId);
      // Browsers may block autoplay; then the person presses play on the controls and the panel follows.
      audio.play().catch(() => {});
    } else {
      wallStart = performance.now();
    }
    timer = setInterval(() => dispatchUntil(now()), 50);
  }

  async function open() {
    ui();
    graph(); // inside the tile's click, so the recording may play
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

  window.samjhoReplay = {
    open,
    stop,
    seek,
    speaker,
    envelope,
    // The replay clock in seconds while one is loaded, else null.
    time: () => (events.length ? now() : null),
    // When she was speaking: before each of her recognised answers, by its length (the mix has no labels).
    herWindows: () =>
      events
        .filter((e) => e.type === "heard")
        .map((e) => {
          const words = String(e.text || "").trim().split(/\s+/).filter(Boolean).length;
          return [Math.max(0, e.t - (0.8 + words * 0.42)), e.t - 0.2];
        }),
    playing: () => Boolean(events.length && (audio.hidden || !audio.paused)),
  };
})();
