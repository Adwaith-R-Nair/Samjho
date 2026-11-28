// Samjho landing: the living thumbprint and its four-chamber scroll story (design D).
// Owns the visuals only: the intro (one drop of ink), Lenis smooth scroll wired to GSAP ScrollTrigger, the
// pinned story, the pointer as a fingertip, and where the print sits in each view. web/app.js owns the views
// and calls window.samjhoStage.onView(view, opts) after switching. Everything degrades: no GSAP or reduced
// motion gives a plain stacked story and a still print; no WebGL2 gives an SVG print.
(() => {
  const $ = (id) => document.getElementById(id);
  const root = document.documentElement;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const G = window.gsap || null;
  if (G && window.ScrollTrigger) G.registerPlugin(ScrollTrigger);
  if (G && window.SplitText) G.registerPlugin(SplitText);
  if (!window.VoiceField) {
    root.classList.remove("intro-on");
    return;
  }

  const S = { view: "landing", tweening: 0, redraw: { p: 0 }, introActive: false };
  const LIVE_UNWIND = 0.3; // in a session the print's outer ridges are already voice
  const LIVE_INK = 0.5; // and it rests quieter behind the panels

  // ---------------------------------------------------------------- the field
  const field = new VoiceField($("field"), { reduced, fallbackSvg: $("fieldFallback") });
  window.samjhoField = field; // phase 3 attaches the session's AnalyserNodes: samjhoField.attach({samjho, her})

  function to(target, vars) {
    if (G && !reduced) {
      S.tweening++;
      const done = vars.onComplete;
      return G.to(target, {
        ...vars,
        onComplete() {
          S.tweening--;
          field.still();
          done && done();
        },
        onInterrupt() {
          S.tweening--;
        },
      });
    }
    const { duration, ease, delay, stagger, onComplete, onUpdate, overwrite, ...rest } = vars;
    Object.assign(target, rest);
    field.still();
    onComplete && onComplete();
    return null;
  }

  // Where the print sits: measured from a placeholder element in each view, so CSS owns the layout.
  function spotOf(el, live) {
    const r = el.getBoundingClientRect();
    const scale = live ? Math.min(r.width / 2 / 1.2, r.height / 2 / 1.36) : Math.min(r.width / 2 / 1.1, r.height / 2 / 1.3);
    let cy = r.top + r.height / 2;
    if (!live) cy = Math.max(cy, innerHeight * (innerWidth < 760 ? 0.3 : 0.45));
    return { cx: r.left + r.width / 2, cy, scale: Math.max(90, scale) };
  }
  function follow() {
    if (S.tweening) return;
    const live = S.view === "live";
    const t = spotOf(live ? $("spotLive") : $("spotLanding"), live);
    const u = field.u;
    if (Math.abs(u.cx - t.cx) + Math.abs(u.cy - t.cy) + Math.abs(u.scale - t.scale) > 0.5) {
      Object.assign(u, t);
      if (reduced || !field.ok) field.still();
    }
  }

  // ---------------------------------------------------------------- smooth scroll (Lenis) and pointer
  let lenis = null;
  if (G && window.ScrollTrigger && window.Lenis && !reduced) {
    lenis = new Lenis({ lerp: 0.085, smoothWheel: true, wheelMultiplier: 0.9 });
    lenis.on("scroll", ScrollTrigger.update);
    G.ticker.add((time) => lenis.raf(time * 1000));
    G.ticker.lagSmoothing(0);
  }
  const easeOut = (t) => (t === 1 ? 1 : 1 - Math.pow(2, -10 * t));
  function scrollToY(target, immediate) {
    // After a view switch the page height changed; Lenis must measure it before it can scroll there.
    if (lenis) lenis.resize();
    if (lenis) lenis.scrollTo(target, { immediate: !!immediate, duration: 1.6, easing: easeOut, force: true });
    else if (typeof target === "number") scrollTo(0, target);
    else document.querySelector(target)?.scrollIntoView();
  }
  function goStart(immediate) {
    scrollToY("#start", immediate);
    setTimeout(() => $("startTitle").focus({ preventScroll: true }), lenis && !immediate ? 1500 : 50);
  }
  document.querySelectorAll('a[href="#start"]').forEach((a) =>
    a.addEventListener("click", (e) => {
      e.preventDefault();
      goStart(false);
    }),
  );

  // The pointer is a fingertip: ridges bend away from it, light follows it, a tap leaves an ink ripple.
  let touchDown = false;
  if (!reduced) {
    addEventListener("pointermove", (e) => {
      if (e.pointerType === "mouse" || touchDown) field.setPointer(e.clientX, e.clientY, true);
    }, { passive: true });
    addEventListener("pointerdown", (e) => {
      if (e.pointerType !== "mouse") touchDown = true;
      field.setPointer(e.clientX, e.clientY, true);
      field.tap(e.clientX, e.clientY);
    }, { passive: true });
    const release = (e) => {
      if (e.pointerType !== "mouse") {
        touchDown = false;
        field.setPointer(e.clientX, e.clientY, false);
      }
    };
    addEventListener("pointerup", release, { passive: true });
    addEventListener("pointercancel", release, { passive: true });
    root.addEventListener("pointerleave", () => field.setPointer(field.mouse.x, field.mouse.y, false));
  }

  let lastY = scrollY;
  field.onFrame = () => {
    follow();
    // Scroll velocity: Lenis knows it; without Lenis, measure it.
    if (lenis) field.velIn = S.view === "landing" ? lenis.velocity : lenis.velocity * 0.4;
    else {
      field.velIn = (scrollY - lastY) * 0.8;
      lastY = scrollY;
    }
    if (S.view === "landing" && !S.introActive) {
      // Chamber 3 redraws the print ridge by ridge while its scroll segment plays.
      const rp = S.redraw.p;
      field.u.draw = rp > 0.001 && rp < 0.999 ? rp * 75 : 999;
    }
    if (S.view === "landing") {
      // The converging voice lines aim at the Talk button, which breathes with Samjho's level.
      const cta = $("storyCta");
      const r = cta.getBoundingClientRect();
      field.u.tx = r.left + r.width * 0.5;
      field.u.ty = r.top + r.height / 2;
      cta.style.setProperty("--pulse", (field.level.samjho * 0.9 + field.u.converge * 0.15).toFixed(3));
    }
  };
  addEventListener("resize", () => {
    follow();
    field.still();
    drawNote();
  });
  addEventListener(
    "scroll",
    () => {
      if (reduced || !field.ok) {
        follow();
        field.still();
      }
    },
    { passive: true },
  );

  const fmtRs = (v) => "Rs " + Math.round(v).toLocaleString("en-IN");

  // ---------------------------------------------------------------- chamber 3: her voice note
  // One real clip (Sarvam text-to-speech, an AI stand-in for the borrower), played by an <audio> element only
  // when pressed. Its bars and the print's tremble come from the clip's own loudness envelope (data-env), so no
  // AudioContext is opened on the landing.
  const note = {
    btn: $("herNotePlay"),
    audio: $("herNoteAudio"),
    canvas: $("herNoteWave"),
    dur: $("herNoteDur"),
    env: ($("herNoteWave")?.dataset.env || "").split(",").map(Number),
    raf: 0,
  };
  const PLAY_SVG = '<svg viewBox="0 0 14 14" aria-hidden="true"><path d="M3 1.8v10.4L12 7z"/></svg>';
  const STOP_SVG = '<svg viewBox="0 0 14 14" aria-hidden="true"><rect x="3" y="3" width="8" height="8" rx="1"/></svg>';
  const clock = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
  function noteProgress() {
    const a = note.audio;
    return a && a.duration > 0 ? Math.min(1, a.currentTime / a.duration) : 0;
  }
  function drawNote() {
    const c = note.canvas;
    if (!c || !note.env.length) return;
    const css = c.clientWidth || 240;
    const d = Math.min(2, devicePixelRatio || 1);
    if (c.width !== Math.round(css * d)) {
      c.width = Math.round(css * d);
      c.height = Math.round(36 * d);
    }
    const g = c.getContext("2d");
    const W = c.width;
    const H = c.height;
    const n = note.env.length;
    const p = note.audio && !note.audio.paused ? noteProgress() : 0;
    g.clearRect(0, 0, W, H);
    const bw = (W / n) * 0.56;
    for (let i = 0; i < n; i++) {
      const h = Math.max(2.5 * d, note.env[i] * (H - 4 * d));
      g.fillStyle = i / n < p ? "rgba(255,156,194,1)" : "rgba(255,156,194,0.42)";
      const x = (i + 0.22) * (W / n);
      g.beginPath();
      if (g.roundRect) g.roundRect(x, (H - h) / 2, bw, h, Math.min(bw / 2, h / 2));
      else g.rect(x, (H - h) / 2, bw, h);
      g.fill();
    }
  }
  function noteTick() {
    const p = noteProgress();
    const i = Math.min(note.env.length - 1, Math.floor(p * note.env.length));
    field.feed("her", (note.env[i] || 0) * 0.85);
    drawNote();
    if (!note.audio.paused) note.raf = requestAnimationFrame(noteTick);
  }
  function noteUI(playing) {
    note.btn.innerHTML = playing ? STOP_SVG : PLAY_SVG;
    note.btn.setAttribute("aria-pressed", String(playing));
    note.btn.setAttribute("aria-label", playing ? "Stop her answer" : "Play her answer, an AI stand-in voice");
  }
  function stopNote() {
    if (!note.audio) return;
    note.audio.pause();
    note.audio.currentTime = 0;
    cancelAnimationFrame(note.raf);
    noteUI(false);
    drawNote();
  }
  if (note.btn && note.audio) {
    note.btn.addEventListener("click", () => {
      if (!note.audio.paused) return stopNote();
      note.audio.currentTime = 0;
      note.audio.play().then(() => {
        noteUI(true);
        noteTick();
      }, () => noteUI(false));
    });
    note.audio.addEventListener("ended", stopNote);
    note.audio.addEventListener("loadedmetadata", () => (note.dur.textContent = clock(note.audio.duration)));
    drawNote();
  }

  // ---------------------------------------------------------------- the story
  // Four chambers of the print. Scrolling travels into the whorl (zoom, tunnel, parallax depth), smudges it,
  // redraws it ridge by ridge, lets her voice unwind it, and pulls the voice into the Talk button.
  let storyST = null;
  function buildStory() {
    const beats = [...document.querySelectorAll(".beat")];
    const heads = [...document.querySelectorAll("[data-split]")];
    const his = [...document.querySelectorAll("[data-split-hi]")];
    const hasSplit = Boolean(window.SplitText);
    // Latin headlines split to characters inside line masks; Devanagari only to words, so conjuncts and
    // vowel signs are never torn apart.
    const splits = hasSplit ? heads.map((h) => SplitText.create(h, { type: "lines,words,chars", mask: "lines", linesClass: "ln", wordsClass: "w", charsClass: "ch" })) : [];
    const hiSplits = hasSplit ? his.map((h) => SplitText.create(h, { type: "lines,words", mask: "lines", linesClass: "ln", wordsClass: "w" })) : [];
    const chars = (i) => (splits[i] ? splits[i].chars : []);
    const hiWords = (i) => (hiSplits[i] ? hiSplits[i].words : []);
    const rest = (b) => b.querySelectorAll(".beat-p, .beat-label, .beat-fact, .beat-note, .btn");

    // Beat 1 is revealed by the intro, not by scroll (different elements and properties, so they never fight).
    const words0 = splits[0] ? splits[0].words : [];
    const hiLines0 = hiSplits[0] ? hiSplits[0].lines : [];
    G.set(words0, { yPercent: 115 });
    G.set(hiLines0, { yPercent: 115 });
    G.set(rest(beats[0]), { clipPath: "inset(0% 0% 100% 0%)", yPercent: 30 });
    function revealFirst() {
      G.to(words0, { yPercent: 0, duration: 1.1, stagger: 0.06, ease: "expo.out" });
      G.to(hiLines0, { yPercent: 0, duration: 1.1, stagger: 0.1, ease: "expo.out", delay: 0.25 });
      G.to(rest(beats[0]), { clipPath: "inset(0% 0% 0% 0%)", yPercent: 0, duration: 0.9, ease: "expo.out", delay: 0.5 });
    }

    // Numbers that change their mind: 1,590 counts up, 50,000 is struck and counts down to 48,410.
    const numHand = $("numHand");
    const numCut = document.querySelector("[data-count]");
    const strike = document.querySelector(".beat-fact .strike");
    const hand = { v: 50000 };
    const cut = { v: 0 };
    numHand.textContent = fmtRs(50000);
    numCut.textContent = fmtRs(0);
    G.set(strike, { scaleX: 0 });

    const tl = G.timeline({
      defaults: { ease: "power2.out" },
      scrollTrigger: {
        trigger: "#story",
        start: "top top",
        end: "+=360%",
        pin: true,
        scrub: 1,
        // Leaving chamber 3 stops her voice note.
        onUpdate(self) {
          if ((self.progress < 0.43 || self.progress > 0.7) && note.audio && !note.audio.paused) stopNote();
        },
        onLeave: () => stopNote(),
      },
    });
    for (let i = 1; i < 4; i++) {
      const prev = beats[i - 1];
      const cur = beats[i];
      const off = { immediateRender: false };
      tl.fromTo(rest(prev), { autoAlpha: 1, y: 0, filter: "blur(0px)" }, { autoAlpha: 0, y: -24, filter: "blur(8px)", stagger: 0.02, duration: 0.22, ease: "power2.in", ...off }, i - 0.36);
      tl.fromTo(hiWords(i - 1), { yPercent: 0 }, { yPercent: -115, stagger: 0.015, duration: 0.24, ease: "power2.in", ...off }, i - 0.3);
      tl.fromTo(chars(i - 1), { yPercent: 0, rotate: 0 }, { yPercent: -115, stagger: 0.003, duration: 0.24, ease: "power2.in", ...off }, i - 0.28);
      tl.set(prev, { autoAlpha: 0 }, i + 0.02);
      tl.fromTo(cur, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.01 }, i - 0.14);
      tl.from(chars(i), { yPercent: 115, rotate: 4, stagger: 0.01, duration: 0.45, ease: "expo.out" }, i - 0.13);
      tl.from(hiWords(i), { yPercent: 115, stagger: 0.04, duration: 0.45, ease: "expo.out" }, i - 0.05);
      tl.from(rest(cur), { autoAlpha: 0, y: 26, filter: "blur(6px)", stagger: 0.06, duration: 0.4, ease: "expo.out" }, i + 0.04);
      // The print takes a breath of ink at every chamber door: a radial wash that carries the eye across.
      tl.fromTo(field.u, { wash: 0 }, { wash: 1, duration: 0.24, ease: "power2.out", immediateRender: false }, i - 0.3);
      tl.to(field.u, { wash: 0, duration: 0.4, ease: "power2.inOut" }, i - 0.06);
    }
    tl.to(cut, { v: 1590, duration: 0.2, ease: "power1.out", onUpdate: () => (numCut.textContent = fmtRs(cut.v)) }, 1.06)
      .to(strike, { scaleX: 1, duration: 0.14, ease: "power2.inOut" }, 1.2)
      .to(hand, { v: 48410, duration: 0.22, ease: "power2.out", onUpdate: () => (numHand.textContent = fmtRs(hand.v)) }, 1.26);
    tl.to("#scrollCue", { autoAlpha: 0, y: 10, duration: 0.15 }, 0.12);

    // Chamber 1 the whole print; dive into chamber 2 (close, smudged: pseudo consent); chamber 3 redraws in
    // clean ink ridge by ridge, then her voice unwinds it; chamber 4 is all voice, converging into the button.
    const u = field.u;
    tl.to(u, { zoom: 2.7, travel: 7, tunnel: 0.75, depth: 1, duration: 0.7, ease: "power3.inOut" }, 0.42)
      .to(u, { dim: 1, duration: 0.45, ease: "power2.inOut" }, 0.82)
      .to(u, { zoom: 1.45, travel: 15, tunnel: 0.3, dim: 0, duration: 0.7, ease: "power3.inOut" }, 1.45)
      .fromTo(S.redraw, { p: 0 }, { p: 1, duration: 0.55, ease: "power1.inOut", immediateRender: false }, 1.71)
      .to(u, { unwind: 0.6, duration: 0.6, ease: "power2.inOut" }, 2.05)
      .to(u, { unwind: 1, zoom: 0.95, tunnel: 0, depth: 0.25, travel: 21, duration: 0.7, ease: "power3.inOut" }, 2.55)
      // On a phone the funnel is short, so the lines bend toward the button rather than collapse into it.
      .to(u, { converge: innerWidth < 760 ? 0.35 : 1, depth: 0, duration: 0.8, ease: "power2.inOut" }, 3.35)
      .to({}, { duration: 0.4 }, 4.15);
    storyST = tl.scrollTrigger;

    // The start options title, revealed once when it enters.
    if (splits[4]) G.from(splits[4].chars, { yPercent: 115, stagger: 0.02, duration: 0.9, ease: "expo.out", scrollTrigger: { trigger: "#start", start: "top 70%" } });
    G.from(".start-hi", { autoAlpha: 0, y: 14, duration: 0.8, ease: "expo.out", scrollTrigger: { trigger: "#start", start: "top 70%" } });
    return { revealFirst };
  }

  // ---------------------------------------------------------------- intro
  // One drop of ink falls where the whorl will be; on impact the print inks in from it, ridge by ridge.
  // 1.4 s, skippable with the button, any key, a click or a tap.
  function runIntro(onReveal) {
    if (!root.classList.contains("intro-on") || !G) {
      root.classList.remove("intro-on");
      if (G && !reduced) G.to(field.u, { intro: 1, duration: 1.2, ease: "power2.out" });
      onReveal && onReveal();
      return;
    }
    const c = spotOf($("spotLanding"), false);
    Object.assign(field.u, c, { intro: 1, draw: 0 });
    if (lenis) lenis.stop();
    S.introActive = true;
    const drop = $("drop");
    const splash = $("splash");
    const chrome = [".top", ".story-copy"];
    drop.style.animation = "none";
    G.set(drop, { left: 0, top: 0, x: c.cx, y: c.cy });
    G.set(splash, { x: c.cx, y: c.cy });
    let revealed = false;
    const reveal = () => {
      if (revealed) return;
      revealed = true;
      onReveal && onReveal();
    };
    let tl = null;
    const skip = () => tl && tl.progress(1);
    const finish = () => {
      root.classList.remove("intro-on");
      G.set(chrome, { clearProps: "opacity" });
      field.u.draw = 999;
      S.introActive = false;
      reveal();
      if (lenis) lenis.start();
      removeEventListener("keydown", skip, true);
      removeEventListener("pointerdown", skip, true);
    };
    tl = G.timeline({ onComplete: finish });
    tl.fromTo(drop, { y: c.cy - Math.min(240, innerHeight * 0.3), opacity: 1, scaleX: 0.8, scaleY: 1.2 }, { y: c.cy, opacity: 1, scaleX: 0.85, scaleY: 1.25, duration: 0.42, ease: "power2.in" })
      .to(drop, { scaleX: 1.9, scaleY: 0.35, opacity: 0, duration: 0.2, ease: "power2.out" }, 0.42)
      .fromTo(splash, { scale: 0.5, opacity: 0.9 }, { scale: 11, opacity: 0, duration: 0.8, ease: "expo.out" }, 0.42)
      .fromTo(field.u, { draw: 0 }, { draw: 80, duration: 0.95, ease: "power2.inOut" }, 0.44)
      .to(chrome, { opacity: 1, duration: 0.5, ease: "power2.out" }, 0.9)
      .add(reveal, 0.85);
    $("introSkip").addEventListener("click", skip);
    addEventListener("keydown", skip, true);
    addEventListener("pointerdown", skip, true);
  }

  // ---------------------------------------------------------------- views (called by web/app.js)
  // live: the pin releases, the camera pulls back out of the print and it rests, half voice, behind the panels.
  // landing: the story comes back; opts.to = "start" returns to the start options, otherwise to the top.
  function onView(view, opts = {}) {
    const prev = S.view;
    S.view = view;
    $("topNote").textContent = view === "live" ? "Sample loan (synthetic): Rs 50,000, Rs 1,095 every week" : "Sample loan (synthetic). Synthetic people only.";
    if (view === "live") {
      stopNote();
      if (storyST) storyST.disable(true);
      scrollToY(0, true);
      field.u.draw = 999;
      const t = spotOf($("spotLive"), true);
      to(field.u, { ...t, unwind: LIVE_UNWIND, dim: 0, rings: 0, intro: LIVE_INK, zoom: 1, tunnel: 0, depth: 0, converge: 0, travel: 0, wash: 0, duration: 1.4, ease: "expo.inOut" });
      return;
    }
    if (prev === "live" && storyST) {
      storyST.enable();
      ScrollTrigger.refresh();
    }
    const t = spotOf($("spotLanding"), false);
    to(field.u, { ...t, unwind: 0, dim: 0, intro: 1, zoom: 1, tunnel: 0, depth: 0, converge: 0, travel: 0, duration: 1.0, ease: "expo.inOut" });
    if (opts.to === "start") goStart(true);
    else if (prev === "live") {
      scrollToY(0, true);
      if (storyST) storyST.scroll(storyST.start);
    } else scrollToY(0, false);
  }
  window.samjhoStage = { onView, field };

  // ---------------------------------------------------------------- debug (?debug=1): an fps readout only
  if (new URLSearchParams(location.search).get("debug") === "1") {
    const fps = document.createElement("span");
    fps.className = "debug-fps";
    fps.setAttribute("aria-hidden", "true");
    document.body.appendChild(fps);
    setInterval(() => {
      fps.textContent = field.ok ? (reduced ? "still frame" : `fps ${Math.round(field.fps())}, q ${field.q.toFixed(2)}, ${field.source}`) : "SVG fallback";
    }, 500);
  }

  // ---------------------------------------------------------------- boot
  Object.assign(field.u, spotOf($("spotLanding"), false));
  field.u.rings = 0;
  const boot = () => {
    if (G && !reduced && window.ScrollTrigger) {
      root.classList.add("js-story");
      Object.assign(field.u, spotOf($("spotLanding"), false));
      const story = buildStory();
      runIntro(story.revealFirst);
    } else {
      // Reduced motion or no GSAP: the story is a plain stacked read, the print a still, half-unwound frame.
      root.classList.remove("intro-on");
      Object.assign(field.u, { intro: 1, unwind: 0.5 });
      field.still();
    }
    field.start();
    field.still();
    if (location.hash === "#start") goStart(true);
  };
  // Fonts and the shader warm up under the intro; never wait more than 900 ms for fonts.
  const fontsReady = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
  Promise.race([fontsReady, new Promise((r) => setTimeout(r, 900))]).then(boot, boot);
})();
