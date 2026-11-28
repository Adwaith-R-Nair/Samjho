// Voice notes: each spoken line in the session gets a waveform made of the real audio.
//   Browser voice: Samjho's reply arrives as one audio stream for all its lines (web/voice.js reports each
//     scheduled chunk through audio(t0, t1)); the reply's time is split over its lines by length, and the line
//     being heard fills its bars from Samjho's AnalyserNode. Her note appears while she speaks (only when the
//     mic is open, half duplex) and fills from the mic's analyser; her recognised words fill it in after.
//   Replay: the recording's decoded envelope gives every note its bars, the replay clock lights them, the
//     voice whose turn it is gets the analyser, and tapping a note seeks the replay there.
//   Phone: no audio reaches the browser, so the print is driven from the call's events (Samjho speaking for
//     about as long as his lines take, then her turn), and the notes carry no waveform.
// Typing mode has no audio and no waveforms.
(() => {
  const SLOTS = 64;
  const PLAY_SVG = '<svg viewBox="0 0 14 14" aria-hidden="true"><path d="M3 1.8v10.4L12 7z"/></svg>';
  const clamp = (v) => Math.max(0, Math.min(1, v));
  const clock = (s) => {
    const r = Math.max(1, Math.round(s));
    return `${Math.floor(r / 60)}:${String(r % 60).padStart(2, "0")}`;
  };
  const td = new Float32Array(1024);

  let mode = null; // "voice" | "replay" | "phone" | "text"
  let notes = [];
  let group = null; // Samjho's current reply: { notes, start, end } (voice) or { notes, t0, closed } (replay)
  let her = null; // her note while she speaks (voice)
  let lastHer = null; // the envelope of her latest answer (the number effect's energy)
  let talkUntil = 0; // phone: Samjho is speaking until this time (s)
  let ended = false;
  let raf = 0;
  let replayWho = "";
  let herWins = null; // replay: [start, end] of her turns
  let frame = 0;

  function level(a) {
    if (!a || a.context.state !== "running") return 0;
    a.getFloatTimeDomainData(td);
    let s = 0;
    for (let i = 0; i < td.length; i++) s += td[i] * td[i];
    return Math.min(1, Math.sqrt(s / td.length) * 3.2);
  }

  // ---------------------------------------------------------------- one note's waveform
  function attach(li, who) {
    const seekable = mode === "replay";
    const b = document.createElement("div");
    b.className = "note-body";
    b.innerHTML =
      (seekable ? `<button type="button" class="note-play" aria-label="Play the replay from this line">${PLAY_SVG}</button>` : "") +
      '<canvas class="note-wave" aria-hidden="true"></canvas><span class="note-dur tnum"></span>';
    li.querySelector(".note-head").after(b);
    const n = { li, who, canvas: b.querySelector("canvas"), dur: b.querySelector(".note-dur"), bars: new Float32Array(SLOTS), progress: 0, s: 0, e: 0, chars: 1, samples: null };
    if (seekable) {
      b.querySelector(".note-play").onclick = () => window.samjhoReplay?.seek(n.s);
      n.canvas.addEventListener("click", (e) => {
        const r = n.canvas.getBoundingClientRect();
        window.samjhoReplay?.seek(n.s + clamp((e.clientX - r.left) / r.width) * (n.e - n.s));
      });
    }
    notes.push(n);
    draw(n);
    return n;
  }

  function resample(src, out) {
    out.fill(0);
    if (!src || !src.length) return out;
    for (let i = 0; i < out.length; i++) {
      const a = Math.floor((i * src.length) / out.length);
      const b = Math.max(a + 1, Math.floor(((i + 1) * src.length) / out.length));
      let m = 0;
      for (let k = a; k < b && k < src.length; k++) m = Math.max(m, src[k]);
      out[i] = m;
    }
    return out;
  }

  // Levels recorded with their audio-clock times, [t0, l0, t1, l1, ...], cut to this line's span.
  function fromSeries(n, out) {
    out.fill(0);
    const span = n.e - n.s;
    if (!(span > 0)) return out;
    const s = n.series;
    for (let i = 0; i < s.length; i += 2) {
      if (s[i] < n.s || s[i] >= n.e) continue;
      const k = Math.min(SLOTS - 1, Math.floor(((s[i] - n.s) / span) * SLOTS));
      if (s[i + 1] > out[k]) out[k] = s[i + 1];
    }
    return out;
  }

  function draw(n) {
    const c = n.canvas;
    const w = c.clientWidth || 200;
    const d = Math.min(2, devicePixelRatio || 1);
    if (c.width !== Math.round(w * d)) {
      c.width = Math.round(w * d);
      c.height = Math.round(32 * d);
    }
    const g = c.getContext("2d");
    const W = c.width;
    const H = c.height;
    const nb = Math.max(16, Math.floor(w / 5));
    const tmp = n.tmp || (n.tmp = new Float32Array(SLOTS));
    const src = n.samples ? resample(n.samples, tmp) : n.series ? fromSeries(n, tmp) : n.bars;
    const col = n.who === "samjho" ? "93,226,231" : "255,156,194";
    g.clearRect(0, 0, W, H);
    const bw = (W / nb) * 0.56;
    for (let i = 0; i < nb; i++) {
      const k = Math.min(SLOTS - 1, Math.floor((i / nb) * SLOTS));
      const v = Math.min(1, src[k] * 1.25);
      const h = Math.max(2.5 * d, v * (H - 4 * d));
      g.fillStyle = (i + 0.5) / nb <= n.progress ? `rgba(${col},1)` : `rgba(${col},0.34)`;
      const x = (i + 0.22) * (W / nb);
      g.beginPath();
      if (g.roundRect) g.roundRect(x, (H - h) / 2, bw, h, Math.min(bw / 2, h / 2));
      else g.rect(x, (H - h) / 2, bw, h);
      g.fill();
    }
    if (n.e > n.s) n.dur.textContent = clock(n.e - n.s);
    else if (n.samples) n.dur.textContent = clock(n.samples.length / 60);
  }

  // ---------------------------------------------------------------- browser voice
  function voiceTick() {
    const v = window.samjhoVoice;
    const an = v && v.analysers();
    const now = v && v.now();
    if (!an || now === null) return;
    const ls = level(an.samjho);
    if (group && group.start !== null) {
      // The reply's length grows while its audio streams in, so levels are kept with their times and each
      // line's bars are cut from them by its current share of the reply.
      if (now >= group.start && now <= group.end + 0.05) group.series.push(now, ls);
      const total = Math.max(0.01, group.end - group.start);
      const p = now - group.start;
      const chars = group.notes.reduce((a, n) => a + n.chars, 0) || 1;
      let acc = 0;
      for (const n of group.notes) {
        const a = (acc / chars) * total;
        const b = ((acc + n.chars) / chars) * total;
        acc += n.chars;
        n.s = group.start + a;
        n.e = group.start + b;
        n.series = group.series;
        const on = p >= a && p < b;
        const prog = clamp((p - a) / Math.max(0.01, b - a));
        if (on || prog !== n.progress) {
          n.progress = prog;
          draw(n);
        }
        n.li.classList.toggle("speaking", on);
      }
      // Her placeholder that never became words (a cough, noise) leaves when Samjho speaks again.
      if (her && her.n && p > 0 && her.startedBefore < group.start) dropHer();
    }
    if (v.micOpen()) {
      const lh = level(an.her);
      if (!her && lh > 0.09) her = { n: null, samples: [], startedBefore: now };
      if (her) {
        if (!her.n) {
          const li = window.samjhoMakeHerNote?.();
          if (!li) return;
          her.n = attach(li, "her");
          her.n.samples = her.samples;
          her.n.progress = 1;
        }
        her.samples.push(lh);
        if (her.samples.length > 1800) her.samples.splice(0, 600);
        if (frame % 3 === 0) draw(her.n);
      }
    }
  }

  function dropHer() {
    if (her && her.n) {
      her.n.li.remove();
      notes = notes.filter((n) => n !== her.n);
    }
    her = null;
  }

  // Her words arrived: the live note (if her voice was heard) becomes this answer, its bars trimmed to her voice.
  function claimHer() {
    if (mode !== "voice" || !her || !her.n) {
      her = null;
      return null;
    }
    const n = her.n;
    const s = her.samples;
    let a = 0;
    let b = s.length;
    while (a < b && s[a] < 0.05) a++;
    while (b > a && s[b - 1] < 0.05) b--;
    resample(s.slice(a, b), n.bars);
    n.samples = null;
    n.progress = 1;
    n.e = (b - a) / 60;
    n.s = 0;
    draw(n);
    lastHer = n.bars;
    her = null;
    return n.li;
  }

  // ---------------------------------------------------------------- replay
  function splitGroup(g, end) {
    const chars = g.notes.reduce((a, n) => a + n.chars, 0) || 1;
    let acc = g.t0;
    const span = Math.max(0.3, end - g.t0);
    for (const n of g.notes) {
      n.s = acc;
      acc += (n.chars / chars) * span;
      n.e = acc;
      n.bars = window.samjhoReplay?.envelope(n.s, n.e, SLOTS) || n.bars;
      n.needEnv = !window.samjhoReplay?.envelope(n.s, n.e, 1);
    }
  }

  function replayTick() {
    const r = window.samjhoReplay;
    const t = r && r.time();
    if (t === null || t === undefined) return;
    // Whose turn it is decides which analyser hears the recording.
    if (!herWins) herWins = r.herWindows ? r.herWindows() : [];
    let who = herWins.some(([a, b]) => t >= a && t < b) ? "her" : "samjho";
    for (const n of notes) {
      if (n.needEnv && frame % 15 === 0) {
        const env = r.envelope(n.s, n.e, SLOTS);
        if (env) {
          n.bars = env;
          n.needEnv = false;
          n.progress = -1;
        }
      }
      const prog = n.e > n.s ? clamp((t - n.s) / (n.e - n.s)) : 0;
      const on = t >= n.s && t < n.e;
      if (prog !== n.progress) {
        n.progress = prog;
        draw(n);
      }
      n.li.classList.toggle("speaking", on && r.playing());
    }
    if (who !== replayWho) {
      replayWho = who;
      r.speaker(who);
    }
  }

  // ---------------------------------------------------------------- phone
  function phoneTick() {
    const field = window.samjhoField;
    if (!field) return;
    const t = performance.now() / 1000;
    if (t < talkUntil) field.feed("samjho", 0.12 + 0.14 * (0.5 + 0.5 * Math.sin(t * 11)) * (0.5 + 0.5 * Math.sin(t * 2.7)));
    else if (!ended) field.feed("her", 0.04 + 0.03 * (0.5 + 0.5 * Math.sin(t * 1.6)));
  }

  function loop() {
    raf = requestAnimationFrame(loop);
    frame++;
    if (mode === "voice") voiceTick();
    else if (mode === "replay") replayTick();
    else if (mode === "phone") phoneTick();
  }

  // ---------------------------------------------------------------- the app's calls
  function reset() {
    notes = [];
    group = null;
    her = null;
    lastHer = null;
    talkUntil = 0;
    ended = false;
    replayWho = "";
    herWins = null;
  }

  function begin(m) {
    reset();
    mode = m;
    cancelAnimationFrame(raf);
    if (m !== "text") raf = requestAnimationFrame(loop);
  }

  // Samjho said a line (t: the replay time of the event, when replaying).
  function say(li, text, t) {
    const chars = Math.max(1, [...String(text || "")].length);
    if (mode === "phone") {
      const now = performance.now() / 1000;
      talkUntil = Math.max(now, talkUntil) + chars * 0.065 + 0.25;
      return;
    }
    if (mode !== "voice" && mode !== "replay") return;
    const n = attach(li, "samjho");
    n.chars = chars;
    if (mode === "voice") {
      if (!group) group = { notes: [], start: null, end: null, series: [] };
      group.notes.push(n);
    } else {
      if (!group || group.closed) group = { notes: [], t0: t || 0, closed: false };
      group.notes.push(n);
      // Until her answer closes this reply, its length is estimated from the text.
      splitGroup(group, group.t0 + group.notes.reduce((a, x) => a + x.chars, 0) * 0.075 + 0.4);
    }
  }

  // Her recognised words (after a live note, claimHer() already turned it into this note).
  function heard(li, text, t) {
    if (mode === "voice") {
      group = null;
      return;
    }
    if (mode !== "replay") return;
    const words = String(text || "").trim().split(/\s+/).filter(Boolean).length;
    const prevEnd = group ? group.t0 + 0.5 : 0;
    const start = Math.max(prevEnd, (t || 0) - (0.8 + words * 0.42));
    if (group && !group.closed) {
      splitGroup(group, start - 0.05);
      group.closed = true;
    }
    const n = attach(li, "her");
    n.s = start;
    n.e = Math.max(start + 0.3, (t || 0) - 0.2);
    n.bars = window.samjhoReplay?.envelope(n.s, n.e, SLOTS) || n.bars;
    n.needEnv = !window.samjhoReplay?.envelope(n.s, n.e, 1);
    lastHer = n.bars;
    draw(n);
  }

  // Browser voice: a chunk of Samjho's audio was scheduled from t0 to t1 (AudioContext time).
  function audio(t0, t1) {
    if (mode !== "voice") return;
    if (!group) group = { notes: [], start: null, end: null, series: [] };
    if (group.start === null) group.start = t0;
    group.end = t1;
  }

  window.samjhoNotes = {
    begin,
    reset,
    say,
    heard,
    claimHer,
    audio,
    end: () => (ended = true),
    lastHerEnvelope: () => lastHer,
  };
})();
