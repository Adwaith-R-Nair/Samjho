// Samjho live session on the print: the five fact rings, leader lines to their rows, the number effect and the seal.
// web/app.js calls window.samjhoFx.{reset, fact, seal}; web/js/landing.js calls frame(view) every frame.
// The number effect (design E, "spoken into being"): when code checks an amount, the figure she said assembles
// out of grains of her voice inside the print, in the verdict colour, holds, then flies into its ring and row.
// It runs on one small 2D canvas only while a figure is on screen, and never under reduced motion.
(() => {
  const stage = window.samjhoStage;
  if (!stage) return;
  const field = stage.field;
  const reduced = stage.reduced;
  const G = window.gsap || null;
  const $ = (id) => document.getElementById(id);
  const animated = () => Boolean(G && !reduced && field.ok);

  const FACT_KEYS = ["cash_in_hand", "deductions", "instalment", "frequency", "total"];
  const RGB = { grey: [0.43, 0.41, 0.54], red: [1.0, 0.48, 0.42], amber: [1.0, 0.72, 0.3], green: [0.38, 0.89, 0.64], unclear: [1.0, 0.72, 0.3] };
  const CSSV = { green: "var(--green)", amber: "var(--amber)", red: "var(--red)", grey: "var(--ink-3)", unclear: "var(--amber)" };
  const HER = [255, 156, 194];
  const LIVE_UNWIND = 0.3;
  const FIRST = new Set(["green", "amber", "red", "grey"]);
  const firstSet = [false, false, false, false, false];

  // ---------------------------------------------------------------- overlay: leaders and the seal ring text
  const overlay = $("overlay");
  overlay.innerHTML =
    '<g id="leaders">' +
    [0, 1, 2, 3, 4].map((i) => `<path class="leader" id="leader${i}" pathLength="1" d=""/><circle class="leader-dot" id="leaderDot${i}" r="2.4" cx="-9" cy="-9"/><text class="leader-num" id="leaderNum${i}" x="-9" y="-9">${i + 1}</text>`).join("") +
    '</g><defs><path id="sealPath"/></defs><text class="seal-text" id="sealText" opacity="0"><textPath href="#sealPath" id="sealTextPath" startOffset="0"></textPath></text>';
  const rows = () => FACT_KEYS.map((k) => document.querySelector(`.fact[data-fact="${k}"]`));

  function frame(view) {
    const live = view === "live";
    overlay.style.display = live ? "" : "none";
    if (!live) return;
    overlay.setAttribute("viewBox", `0 0 ${innerWidth} ${innerHeight}`);
    const show = innerWidth >= 1000 && field.u.seal < 0.5;
    $("leaders").style.display = show ? "" : "none";
    if (show) {
      rows().forEach((li, i) => {
        const r = li.getBoundingClientRect();
        const p = field.ringPoint(i, Math.PI + (2 - i) * 0.1);
        const x1 = r.right + 4;
        const y1 = r.top + r.height / 2;
        $("leader" + i).setAttribute("d", `M${x1.toFixed(1)} ${y1.toFixed(1)}H${(x1 + 18).toFixed(1)}L${p.x.toFixed(1)} ${p.y.toFixed(1)}`);
        $("leaderNum" + i).setAttribute("x", (p.x - 10).toFixed(1));
        $("leaderNum" + i).setAttribute("y", (p.y - 6).toFixed(1));
        $("leaderDot" + i).setAttribute("cx", p.x.toFixed(1));
        $("leaderDot" + i).setAttribute("cy", p.y.toFixed(1));
      });
    }
    if (field.u.seal > 0.01) {
      // The seal text runs around the sealed ring, a little outside it.
      let d = "";
      for (let k = 0; k <= 96; k++) {
        const a = Math.PI / 2 - (k / 96) * Math.PI * 2;
        const p = field.ringPoint("seal", a);
        const dx = p.x - field.u.cx;
        const dy = p.y - field.u.cy;
        const len = Math.hypot(dx, dy) || 1;
        d += (k ? "L" : "M") + (p.x + (dx / len) * 12).toFixed(1) + " " + (p.y + (dy / len) * 12).toFixed(1);
      }
      $("sealPath").setAttribute("d", d);
    }
  }

  // A checked fact: its leader redraws from the row to the ring, in the verdict colour.
  function drawLeader(i, status) {
    const path = $("leader" + i);
    if (!animated() || !path) return;
    path.classList.add("hot");
    path.style.stroke = CSSV[status];
    G.fromTo(path, { strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 1.1, ease: "expo.out" });
    G.fromTo("#leaderDot" + i, { attr: { r: 7 } }, { attr: { r: 2.4 }, duration: 0.9, ease: "expo.out" });
    clearTimeout(path._t);
    path._t = setTimeout(() => {
      path.classList.remove("hot");
      path.style.stroke = "";
    }, 2200);
  }

  // ---------------------------------------------------------------- the number effect
  const cv = $("grains");
  const g = cv.getContext("2d");
  let dpr = 1;
  function sizeCanvas() {
    dpr = Math.min(devicePixelRatio || 1, 1.5);
    cv.width = Math.round(innerWidth * dpr);
    cv.height = Math.round(innerHeight * dpr);
  }
  sizeCanvas();
  addEventListener("resize", sizeCanvas);
  const small = () => matchMedia("(pointer: coarse)").matches || innerWidth < 760;
  const grainCount = () => (small() ? 1100 : 2600);
  if (document.fonts && document.fonts.load) {
    document.fonts.load('800 80px "Bodoni Moda"').catch(() => {});
    document.fonts.load('700 80px "Mukta"').catch(() => {});
  }

  // Rasterise the figure once on an offscreen canvas and pick n points inside it, each with a threshold that
  // runs left to right, so the figure is written in the order it is read.
  function sample(text, w, h, n, words) {
    const c = document.createElement("canvas");
    const W = Math.max(8, Math.round(w));
    const H = Math.max(8, Math.round(h));
    c.width = W;
    c.height = H;
    const x = c.getContext("2d", { willReadFrequently: true });
    const family = words ? '"Mukta", sans-serif' : '"Bodoni Moda", "Mukta", serif';
    let size = H * (words ? 0.7 : 0.86);
    x.font = `${words ? 700 : 800} ${size}px ${family}`;
    let m = x.measureText(text);
    if (m.width > W * 0.96) {
      size *= (W * 0.96) / m.width;
      x.font = `${words ? 700 : 800} ${size}px ${family}`;
      m = x.measureText(text);
    }
    const asc = m.actualBoundingBoxAscent || size * 0.7;
    const desc = m.actualBoundingBoxDescent || size * 0.2;
    const x0 = (W - m.width) / 2;
    x.fillStyle = "#fff";
    x.fillText(text, x0, (H - (asc + desc)) / 2 + asc);
    const data = x.getImageData(0, 0, W, H).data;
    const cand = [];
    for (let y = 0; y < H; y++) for (let xx = 0; xx < W; xx++) if (data[(y * W + xx) * 4 + 3] > 140) cand.push(xx, y);
    const out = new Float32Array(n * 3);
    const cn = cand.length / 2;
    if (!cn) return null;
    const span = Math.max(1, m.width);
    for (let j = 0; j < n; j++) {
      const p = Math.floor(Math.random() * cn);
      const px = cand[p * 2] + Math.random() - 0.5;
      out[j * 3] = px;
      out[j * 3 + 1] = cand[p * 2 + 1] + Math.random() - 0.5;
      out[j * 3 + 2] = Math.min(0.999, Math.max(0, ((px - x0) / span) * 0.85 + Math.random() * 0.15));
    }
    return out;
  }

  const queue = [];
  let cur = null;
  let raf = 0;
  const stats = { effects: 0, frames: 0, ms: 0 };
  const clamp = (v) => Math.max(0, Math.min(1, v));
  const smooth = (v) => {
    v = clamp(v);
    return v * v * (3 - 2 * v);
  };
  const expoOut = (v) => (v >= 1 ? 1 : 1 - Math.pow(2, -10 * v));
  const inOut = (v) => (v < 0.5 ? 4 * v * v * v : 1 - Math.pow(-2 * v + 2, 3) / 2);
  // Seconds: assemble, hold, fly. A queue (her teach-back checks four facts at once) plays a little faster.
  const A = 1.0;
  const H = 0.7;
  const F = 0.85;

  // Phones stack the print above the facts and the conversation: before a figure plays, the page brings the
  // print into view (it waits for that scroll), and once the queue is done it returns to the newest note.
  let scrolledForFx = false;
  function bringPrint() {
    if (innerWidth >= 1000 || !stage.pageTo) return 0;
    const spot = $("spotLive");
    const r = spot.getBoundingClientRect();
    if (r.top >= 40 && r.bottom <= innerHeight) return 0;
    stage.pageTo(spot, -72);
    scrolledForFx = true;
    return 750;
  }

  function begin(fx) {
    const delay = bringPrint();
    const u = field.u;
    const words = fx.words;
    const w = Math.min(u.scale * (words ? 1.8 : 1.6), innerWidth - 32);
    const h = Math.min(u.scale * (words ? 0.36 : 0.5), w * 0.42);
    const n = grainCount();
    const pts = sample(fx.text, w, h, n, words);
    if (!pts) return false;
    Object.assign(fx, { cx: u.cx, cy: u.cy, w, h, n, pts, t0: performance.now() + delay, speed: 1 + Math.min(0.8, queue.length * 0.3), arrived: false });
    // Her grains start on the print's outer voice lines and end on the fact's ring (some at its row on desktop).
    fx.s = new Float32Array(n * 2);
    fx.e = new Float32Array(n * 2);
    const row = innerWidth >= 1000 ? fx.row.getBoundingClientRect() : null;
    for (let k = 0; k < n; k++) {
      const a = Math.random() * Math.PI * 2;
      const r = u.scale * (1.0 + Math.random() * 0.5);
      fx.s[k * 2] = Math.cos(a) * r;
      fx.s[k * 2 + 1] = -Math.sin(a) * r * 1.12;
      if (row && k % 4 === 0) {
        fx.e[k * 2] = row.left + row.width * (0.1 + Math.random() * 0.8) - u.cx;
        fx.e[k * 2 + 1] = row.top + row.height * (0.2 + Math.random() * 0.6) - u.cy;
      } else {
        const p = field.ringPoint(fx.i, Math.random() * Math.PI * 2);
        fx.e[k * 2] = p.x - u.cx;
        fx.e[k * 2 + 1] = p.y - u.cy;
      }
    }
    stats.effects++;
    return true;
  }

  function next() {
    cur = null;
    while (queue.length) {
      const fx = queue.shift();
      if (begin(fx)) {
        cur = fx;
        break;
      }
      fx.onArrive();
    }
    if (cur) raf = requestAnimationFrame(tick);
    else {
      g.clearRect(0, 0, cv.width, cv.height);
      if (scrolledForFx) {
        scrolledForFx = false;
        setTimeout(() => !cur && window.samjhoShowLatestNote?.(), 500);
      }
    }
  }

  const buckets = [[], [], []];
  function tick(now) {
    const fx = cur;
    if (!fx) return;
    const t0 = performance.now();
    const t = ((now - fx.t0) / 1000) * fx.speed;
    if (t < 0) {
      raf = requestAnimationFrame(tick);
      return;
    }
    // The print may move under it (a phone scrolls the page): the figure stays on the print.
    const cx = field.u.cx;
    const cy = field.u.cy;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, innerWidth, innerHeight);
    // A dark pool behind the figure, so it reads against the ridges.
    const env = t < A ? smooth(t / 0.45) : t < A + H ? 1 : 1 - smooth((t - A - H) / (F * 0.55));
    if (env > 0.01) {
      const rad = fx.w * 0.6;
      const grd = g.createRadialGradient(cx, cy, 0, cx, cy, rad);
      grd.addColorStop(0, `rgba(13,11,22,${(0.86 * env).toFixed(3)})`);
      grd.addColorStop(0.55, `rgba(13,11,22,${(0.62 * env).toFixed(3)})`);
      grd.addColorStop(1, "rgba(13,11,22,0)");
      g.fillStyle = grd;
      g.fillRect(cx - rad, cy - rad, rad * 2, rad * 2);
    }
    const col = RGB[fx.status].map((v) => Math.round(v * 255));
    const ox = cx - fx.w / 2;
    const oy = cy - fx.h / 2;
    const sz = small() ? 1.7 : 2.0;
    buckets[0].length = buckets[1].length = buckets[2].length = 0;
    const X = fx.X || (fx.X = new Float32Array(fx.n));
    const Y = fx.Y || (fx.Y = new Float32Array(fx.n));
    const AL = fx.AL || (fx.AL = new Float32Array(fx.n));
    for (let k = 0; k < fx.n; k++) {
      const tx = ox + fx.pts[k * 3];
      const ty = oy + fx.pts[k * 3 + 1];
      let x;
      let y;
      let a;
      let mix;
      if (t < A + H) {
        const local = clamp((t - fx.pts[k * 3 + 2] * A * 0.55) / (A * 0.45));
        const e = expoOut(local);
        const sx = cx + fx.s[k * 2];
        const sy = cy + fx.s[k * 2 + 1];
        const wob = (1 - e) * 7;
        x = sx + (tx - sx) * e + Math.sin(t * 8 + k) * wob;
        y = sy + (ty - sy) * e + Math.cos(t * 7 + k * 1.3) * wob;
        a = 0.18 + 0.82 * e;
        mix = smooth((local - 0.35) / 0.5);
      } else {
        const f = clamp((t - A - H - (k % 9) * 0.012) / F);
        const e = inOut(f);
        x = tx + (cx + fx.e[k * 2] - tx) * e;
        y = ty + (cy + fx.e[k * 2 + 1] - ty) * e;
        a = 1 - smooth((f - 0.62) / 0.38);
        mix = 1;
      }
      X[k] = x;
      Y[k] = y;
      AL[k] = a;
      buckets[mix < 0.33 ? 0 : mix < 0.8 ? 1 : 2].push(k);
    }
    g.globalCompositeOperation = "lighter";
    for (let b = 0; b < 3; b++) {
      const m = b === 0 ? 0 : b === 1 ? 0.55 : 1;
      g.fillStyle = `rgb(${Math.round(HER[0] + (col[0] - HER[0]) * m)},${Math.round(HER[1] + (col[1] - HER[1]) * m)},${Math.round(HER[2] + (col[2] - HER[2]) * m)})`;
      const list = buckets[b];
      for (let j = 0; j < list.length; j++) {
        const k = list[j];
        if (AL[k] < 0.02) continue;
        g.globalAlpha = AL[k] * 0.9;
        g.fillRect(X[k] - sz / 2, Y[k] - sz / 2, sz, sz);
      }
    }
    g.globalAlpha = 1;
    g.globalCompositeOperation = "source-over";
    stats.frames++;
    stats.ms += performance.now() - t0;
    if (!fx.arrived && t > A + H + F * 0.7) {
      fx.arrived = true;
      fx.onArrive();
    }
    if (t > A + H + F + 0.05) next();
    else raf = requestAnimationFrame(tick);
  }

  // What she said, as a figure: an amount in rupees, or her own words for how often.
  function figureFor(ev) {
    if (ev.status === "unclear") return null;
    if (ev.fact !== "frequency" && typeof ev.said === "number" && ev.said > 0) return { text: "₹" + Math.round(ev.said).toLocaleString("en-IN"), words: false };
    const q = (ev.quote || "").trim();
    if (q && q.length <= 28) return { text: q, words: true };
    return null;
  }

  // ---------------------------------------------------------------- facts on the rings
  function ignite(i, status, animate) {
    const c = RGB[status] || RGB.grey;
    if (animate && animated()) {
      field.ripple(i, c);
      drawLeader(i, status);
      G.to(field.facts[i], { r: c[0], g: c[1], b: c[2], duration: 0.5, ease: "power2.out" });
      G.fromTo(field.facts[i], { a: 2.4 }, { a: 1, duration: 1.6, ease: "expo.out" });
      const li = rows()[i];
      li.classList.add("flash");
      setTimeout(() => li.classList.remove("flash"), 1400);
    } else {
      Object.assign(field.facts[i], { r: c[0], g: c[1], b: c[2], a: 1 });
      stage.refresh();
    }
  }

  // ev: the server's fact event. onArrive renders the row; with the effect it runs when the grains land.
  function fact(ev, { animate = true, onArrive = () => {} } = {}) {
    const i = FACT_KEYS.indexOf(ev.fact);
    if (i < 0) return onArrive();
    // The short arc at upper left keeps her first answer beside the ring's current verdict. It lights with
    // the ring, when her figure lands.
    let first = null;
    if (!firstSet[i] && FIRST.has(ev.status)) {
      firstSet[i] = true;
      const c = RGB[ev.status];
      first = { r: c[0], g: c[1], b: c[2], a: ev.status === "grey" ? 0.6 : 1 };
    }
    const land = (anim) => {
      onArrive();
      if (first) Object.assign(field.first[i], first);
      ignite(i, ev.status, anim);
    };
    const fig = animate && animated() ? figureFor(ev) : null;
    if (!fig) return land(animate);
    queue.push({ i, status: ev.status, row: rows()[i], ...fig, onArrive: () => land(true) });
    if (!cur) next();
  }

  // ---------------------------------------------------------------- seal
  let sealTl = null;
  const idle = () =>
    new Promise((res) => {
      const t0 = performance.now();
      const check = () => (!cur && !queue.length) || performance.now() - t0 > 9000 ? res() : setTimeout(check, 150);
      check();
    });

  async function seal(record, { animate = true } = {}) {
    const hash = record.seal_sha256 || "";
    $("scBefore").textContent = record.right_first_answer ?? 0;
    $("scAfter").textContent = record.right_after_samjho ?? 0;
    $("sealTextPath").textContent = `SEALED · SHA-256 ${hash.slice(0, 32)} ${hash.slice(32)} · मुहर · `;
    $("sealCenter").hidden = false;
    if (animate && animated()) {
      await idle();
      if (sealTl) sealTl.kill();
      const u = field.u;
      // The voice lines rewind, every ridge is drawn to one radius, then the ring breathes softly.
      sealTl = G.timeline()
        .to(u, { unwind: 0, duration: 1.1, ease: "power2.inOut" })
        .to(u, { seal: 1, duration: 4.2, ease: "power4.inOut" }, 0.4)
        .fromTo(u, { sealGlow: 0 }, { sealGlow: 1, duration: 0.7, ease: "power2.out" }, 4.1)
        .to(u, { sealGlow: 0.35, duration: 1.6, ease: "sine.inOut" }, 4.8)
        .to(u, { sealGlow: 0.6, duration: 2.4, ease: "sine.inOut", repeat: -1, yoyo: true }, 6.4)
        .fromTo("#sealText", { attr: { opacity: 0 } }, { attr: { opacity: 1 }, duration: 1.1 }, 4.0)
        .fromTo("#sealTextPath", { attr: { startOffset: "-45%" } }, { attr: { startOffset: "0%" }, duration: 2.6, ease: "expo.out" }, 4.0)
        .fromTo("#sealCenter", { autoAlpha: 0, scale: 0.86 }, { autoAlpha: 1, scale: 1, duration: 1.0, ease: "expo.out" }, 4.3);
    } else {
      Object.assign(field.u, { unwind: 0, seal: 1, sealGlow: 0.45 });
      $("sealText").setAttribute("opacity", "1");
      stage.refresh();
    }
  }

  // ---------------------------------------------------------------- reset (a new session, or a replay seek)
  function reset() {
    queue.length = 0;
    cur = null;
    cancelAnimationFrame(raf);
    g.clearRect(0, 0, cv.width, cv.height);
    if (sealTl) sealTl.kill();
    sealTl = null;
    if (G) {
      G.killTweensOf(field.u, "seal,sealGlow,unwind");
      G.killTweensOf(["#sealText", "#sealTextPath", "#sealCenter"]);
      field.facts.forEach((f) => G.killTweensOf(f));
    }
    Object.assign(field.u, { seal: 0, sealGlow: 0, rings: 1 });
    if (stage.view() === "live") field.u.unwind = LIVE_UNWIND;
    field.facts.forEach((f) => Object.assign(f, { r: RGB.grey[0], g: RGB.grey[1], b: RGB.grey[2], a: 0.32 }));
    field.first.forEach((f) => Object.assign(f, { r: 0, g: 0, b: 0, a: 0 }));
    firstSet.fill(false);
    $("sealText").setAttribute("opacity", "0");
    $("sealCenter").hidden = true;
    stage.refresh();
  }

  window.samjhoFx = { frame, fact, seal, reset, stats, busy: () => Boolean(cur || queue.length) };
})();
