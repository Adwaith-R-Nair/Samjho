// VoiceField: one fullscreen WebGL2 fragment shader that draws a living thumbprint, and turns it into voice.
// Inputs per frame: amplitude and a 12-band spectrum for each voice, read from Web Audio AnalyserNodes
// (Samjho's and hers), plus choreography uniforms tweened by GSAP: unwind, seal, dim, rings, intro, centre.
// Raw WebGL2, no library: one triangle, one program, ~30 uniforms. Pauses when hidden or offscreen.
// Audio: attach({samjho, her}) with AnalyserNodes that live in the session's own AudioContext (web/voice.js);
// either may be null. With no running analyser the print breathes on a slow idle level, and feed(who, level)
// lets a page element (a voice note playing an <audio> clip) move it from a known loudness envelope.
(() => {
  const VERT = `#version 300 es
in vec2 a;
void main(){ gl_Position = vec4(a, 0.0, 1.0); }`;

  const FRAG = `#version 300 es
precision highp float;
out vec4 o;
uniform vec2 uRes;
uniform float uTime;
uniform vec2 uCenter;
uniform float uScale;
uniform float uCycles;
uniform float uUnwind;
uniform float uSeal;
uniform float uDim;
uniform float uRings;
uniform float uIntro;
uniform vec2 uAmp;
uniform float uSpeaker;
uniform float uSpec[12];
uniform vec4 uFact[5];
uniform vec4 uFirst[5];
uniform float uRingR[5];
uniform float uSealR;
uniform float uPx;
uniform float uZoom;
uniform float uWash;
uniform float uTravel;
uniform float uRot;
uniform float uDraw;
uniform float uTunnel;
uniform float uDepth;
uniform float uConverge;
uniform float uSealGlow;
uniform float uVel;
uniform vec3 uTarget;
uniform vec3 uMouse;
uniform vec4 uRip;
uniform vec3 uRipCol;
uniform vec4 uTap;

const vec3 BG = vec3(0.051, 0.043, 0.086);
const vec3 C_THUMB = vec3(0.56, 0.49, 1.0);
const vec3 C_SAMJHO = vec3(0.36, 0.88, 0.91);
const vec3 C_HER = vec3(1.0, 0.61, 0.76);
const vec3 C_SMUDGE = vec3(0.46, 0.44, 0.56);
const vec3 C_SEAL = vec3(0.78, 0.72, 1.0);

float hash(vec2 p){ p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float noise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}
float spec(float x){
  float f = clamp(x, 0.0, 1.0) * 10.999;
  int i = int(f);
  return mix(uSpec[i], uSpec[min(i + 1, 11)], fract(f));
}

void main(){
  vec2 fragRaw = vec2(gl_FragCoord.x, uRes.y - gl_FragCoord.y);
  vec2 frag = fragRaw;
  float t = uTime;
  float aS = uAmp.x, aH = uAmp.y;
  float amp = max(aS, aH);

  // A fingertip pressing the print: sample closer to the pointer, so ridges bend away from it.
  vec2 toM = frag - uMouse.xy;
  float md2 = dot(toM, toM) / (uScale * uScale);
  float press = uMouse.z * exp(-md2 / 0.04);
  frag -= toM * press * 0.3;
  // A tap leaves a soft ink ripple.
  float tapGlow = 0.0;
  if (uTap.w > 0.5) {
    vec2 tv = frag - uTap.xy;
    float tl = length(tv);
    float front = tl / uScale - uTap.z * 0.8;
    float rip = exp(-front * front * 110.0) * exp(-uTap.z * 1.7);
    frag += tv / (tl + 1.0) * rip * uScale * 0.03;
    tapGlow = rip;
  }

  vec2 p = (frag - uCenter) / (uScale * uZoom);
  p.y = -p.y;
  // Scroll velocity drags through the ink: a sideways ripple and a stretch along the scroll.
  p.y += uVel * 0.06 * sin(p.x * 3.6 + p.y * 1.7 + t * 2.5);
  p.y *= 1.0 + abs(uVel) * 0.16;

  // The print: a slightly tall oval, warped by low noise so the ridges wander like skin.
  vec2 wq = vec2(noise(p * 1.7 + 1.3), noise(p * 1.7 + 8.1)) - 0.5;
  vec2 w = p * vec2(1.0, 0.86) + wq * 0.16;
  float r0 = length(w);
  float spin = uRot * (1.0 - smoothstep(0.0, 1.4, r0));
  float th0 = atan(w.y, w.x);
  float th = th0 + spin;
  float s = uSeal;
  float rr = mix(r0, uSealR, s * 0.82);

  // Voice tremor on the ridges. Radius maps to frequency band: low tones shake the core, high the edge.
  float band = spec(r0 * 0.75);
  float tremS = aS * (0.25 + band) * 0.16 * sin(th * 7.0 - t * 15.0);
  float tremH = aH * (0.25 + band) * 0.34 * (noise(w * 2.6 + vec2(t * 0.6, -t * 2.3)) - 0.5) * 2.0;

  // Fact ripple: a wave that leaves a ring and travels outwards.
  float ripW = 0.0;
  if (uRip.w > 0.5) {
    float f = r0 - (uRip.x + uRip.y * 0.85);
    ripW = exp(-f * f * 260.0) * exp(-uRip.y * 1.3);
  }

  // Whorl: one continuous spiral. The tunnel term compresses the core so ridges stream past like a corridor.
  float swirl = (uUnwind * 2.6 - s * 3.2) * smoothstep(0.0, 1.5, r0);
  float rT = pow(max(rr, 1e-4), mix(1.0, 0.6, uTunnel));
  float whorlPh = rT * uCycles + (th + swirl) / 6.28318 + tremS + tremH - uTravel + ripW * 0.35;
  float archPh = (w.y * 0.92 + 0.36 * exp(-w.x * w.x * 1.5) - 0.08 * w.x) * uCycles * 1.04 - uTravel;
  float archK = smoothstep(1.0, 1.55, r0) * (1.0 - s) * (1.0 - uTunnel);
  float fp = mix(whorlPh, archPh, archK);
  float th2 = atan(-w.y, -w.x) + spin;
  float fp2 = mix(whorlPh + (th2 - th) / 6.28318, archPh, archK);

  // Sound-wave lines. Samjho: laminar harmonic sines. Her: wandering, breathy. At the end they converge.
  float x = p.x;
  float dx = x - uTarget.x;
  float reach = max(uTarget.z, 0.6);
  float conv = uConverge;
  float dS = 0.0;
  for (int i = 0; i < 4; i++) {
    float fi = float(i) + 1.0;
    dS += spec(fi / 5.0) * sin(x * 3.1 * fi - t * (2.6 + fi * 1.4) + fi * 1.7) * 0.12 / fi;
  }
  float dH = (noise(vec2(x * 1.5 - t * 0.8, p.y * 0.8 + t * 0.1)) - 0.5) * (0.22 + spec(0.2) * 0.5)
           + spec(0.45) * 0.1 * sin(x * 5.2 - t * 2.2 + noise(p * 2.0) * 3.0);
  float funnel = mix(1.0, 0.03 + 0.97 * smoothstep(0.0, reach * 1.05, dx), conv);
  float disp = mix(dS * (0.35 + aS * 2.4), dH * (0.35 + aH * 2.2), uSpeaker) * (0.45 + 1.1 * exp(-x * x * 0.45));
  disp *= mix(1.0, smoothstep(0.0, reach * 0.5, dx), conv);
  float lens = exp(-dot(p, p) * 0.9) * (1.0 - conv);
  float idle = (0.035 * sin(x * 2.2 - t * 0.55) + 0.02 * sin(x * 4.7 + t * 0.4)) * (1.0 - conv);
  float yy = p.y - uTarget.y * conv;
  float wavePh = (yy * (1.0 - 0.3 * lens) / funnel + disp + idle) * uCycles * 0.52 - uTravel * 0.12;

  // The unwinding front travels from the outside in. Her voice pushes it a little further while she speaks.
  float edge = mix(2.5, -0.4, uUnwind) - aH * 0.45 * min(1.0, uUnwind * 4.0);
  float m = smoothstep(edge - 0.3, edge + 0.3, r0) * (1.0 - s);
  // Chamber transitions: a radial wash ripples through every line.
  float wash = uWash * 0.45 * sin(r0 * 9.0 - uWash * 5.0);
  float ph = mix(fp, wavePh, m) + wash;
  float ph2 = mix(fp2, wavePh, m) + wash;

  float fw = max(min(fwidth(ph), fwidth(ph2)), 1e-4);
  float sd = (fract(ph) - 0.5) / fw;
  float dpx = abs(sd);
  float halfW = mix(0.5, 0.75, m) + amp * 0.45 + uDim * 0.9;
  float core = 1.0 - smoothstep(halfW, halfW + 1.2, dpx);
  // Chromatic edge: a red fringe on one side of each ridge, a blue one on the other, like wet ink catching light.
  float cR = 1.0 - smoothstep(halfW, halfW + 1.4, abs(sd - 0.9));
  float cB = 1.0 - smoothstep(halfW, halfW + 1.4, abs(sd + 0.9));
  vec3 chroma = mix(vec3(core), vec3(cR, core, cB), 0.42);
  float glow = exp(-dpx * mix(0.5, 0.35, uDim)) * 0.32;
  float dense = 1.0 - smoothstep(0.32, 0.55, fw);
  // Where lines get too dense to resolve they blend into their average ink, not into black.
  float avgInk = mix(0.12, 0.3, m);
  float L = (core + glow) * dense + avgInk * (1.0 - dense);
  vec3 Lc = (chroma + glow) * dense + avgInk * (1.0 - dense);

  // Ridge-by-ridge drawing: the spiral is inked along its own length, with a bright pen tip.
  float drawPh = rr * uCycles + th0 / 6.28318;
  float drawn = smoothstep(uDraw + 0.4, uDraw - 1.2, drawPh);
  float pen = exp(-pow((drawPh - uDraw) * 2.6, 2.0)) * (1.0 - step(139.0, uDraw));

  // Ink: uneven, pored, grainy, with a ragged edge.
  float ink = 0.6 + 0.55 * noise(p * 7.0 + 3.0);
  float pores = smoothstep(0.1, 0.26, noise(p * 34.0 + 5.0));
  float grain = 0.8 + 0.4 * hash(floor(fragRaw / (uPx * 1.5)));
  float thumbMask = 1.0 - smoothstep(1.32, 1.62, r0 + (noise(p * 4.2) - 0.5) * 0.16);
  float waveMask = (0.18 + 0.82 * exp(-yy * yy * 0.55)) * (1.0 - smoothstep(1.4, 3.2, abs(p.x) * 0.6 + abs(p.y) * 0.3));
  waveMask *= mix(1.0, smoothstep(-0.05, 0.35, dx), conv);

  vec3 thumbCol = mix(C_THUMB, C_SMUDGE, uDim);
  vec3 voiceCol = mix(C_SAMJHO, C_HER, uSpeaker);
  vec3 waveCol = mix(C_THUMB * 0.8, voiceCol, clamp(0.3 + amp * 1.8 + uUnwind * 0.25 + conv * 0.4, 0.0, 1.0));

  float bThumb = ink * mix(1.0, pores, 0.4) * grain * thumbMask * (0.62 + amp * 0.5) * (1.0 - uDim * 0.35) * drawn;
  float bWave = waveMask * (0.4 + amp * 1.25 + conv * 0.35) * mix(1.0, 0.55, uRings);
  vec3 col = thumbCol * Lc * bThumb * (1.0 - m) + waveCol * Lc * bWave * m;
  col += mix(C_THUMB, vec3(1.0), 0.4) * pen * L * thumbMask * 0.9 * (1.0 - m);

  // A deeper layer of ridges behind, moving slower: parallax depth while travelling into the print.
  if (uDepth > 0.01) {
    vec2 pb = p * 0.55;
    float phB = length(pb * vec2(1.0, 0.86) + wq * 0.1) * uCycles * 0.9 - uTravel * 0.42;
    float dB = abs(fract(phB) - 0.5) / max(fwidth(phB), 1e-4);
    float LB = (1.0 - smoothstep(0.6, 2.2, dB)) * 0.6 + exp(-dB * 0.45) * 0.4;
    col += C_THUMB * 0.5 * LB * uDepth * 0.4 * (1.0 - clamp(L * 1.5, 0.0, 1.0)) * (1.0 - smoothstep(1.2, 2.6, length(pb)));
  }

  // Five fact rings. Ring = now; a short arc at upper left = her first answer, kept beside it.
  float ringsOn = uRings * (1.0 - m);
  float rw = max(0.042, 7.0 * uPx / uScale);
  for (int i = 0; i < 5; i++) {
    float g = exp(-pow((r0 - uRingR[i]) / rw, 2.0));
    float arc = smoothstep(1.72, 1.8, th0) * (1.0 - smoothstep(2.62, 2.7, th0));
    vec4 c = mix(uFact[i], uFirst[i], arc * step(0.01, uFirst[i].a));
    float a = c.a * g * ringsOn;
    col = mix(col, c.rgb * (Lc * 1.25 + 0.1) * (0.8 + c.a * 0.4), clamp(a, 0.0, 1.0));
    col += c.rgb * a * 0.07;
  }
  col += uRipCol * ripW * 0.9 * (1.0 - m);

  // Seal: everything gathers into one ring, which then breathes with a slow glow.
  float sr = exp(-pow((r0 - uSealR) / (0.010 + uPx / uScale), 2.0));
  float sr2 = exp(-pow((r0 - uSealR + 0.055) / 0.006, 2.0)) * 0.5;
  col *= 1.0 - s * 0.78;
  col += C_SEAL * (sr + sr2) * s * 1.3;
  col += C_THUMB * exp(-pow((r0 - uSealR) / 0.08, 2.0)) * s * 0.12;
  col += C_SEAL * (exp(-pow((r0 - uSealR) / 0.13, 2.0)) * 0.5 + exp(-r0 * r0 * 3.0) * 0.12) * uSealGlow * s;

  // The converged voice gathers to a point of light at the button.
  col += voiceCol * exp(-length(p - uTarget.xy) * 5.0) * conv * (0.55 + amp * 0.8);

  // Light follows the pointer; a tap glows where it lands.
  float lightD = length(fragRaw - uMouse.xy) / uScale;
  float light = exp(-lightD * lightD / 0.3) * uMouse.z;
  col *= 1.0 + light * 0.55;
  col += C_THUMB * tapGlow * 0.35;

  col *= (1.0 + uWash * 0.4) * uIntro;
  // Ground: stamp pad with a faint skin and paper fibre, a breath of the speaker's colour, film grain.
  float fibre = noise(fragRaw / (uPx * 2.4)) - 0.5;
  vec3 bg = BG + fibre * 0.016 + voiceCol * 0.045 * amp * exp(-r0 * r0 * 0.8) + C_THUMB * 0.02 * exp(-r0 * r0 * 0.6) + C_THUMB * 0.035 * light;
  col = 1.0 - exp(-col * 1.35);
  vec3 outc = bg + col;
  outc += (hash(fragRaw + fract(t) * 91.0) - 0.5) * 0.018;
  o = vec4(outc, 1.0);
}`;

  // Same noise as the shader, so DOM annotations land exactly on a ring.
  const fract = (x) => x - Math.floor(x);
  function hash(x, y) {
    let px = fract(x * 123.34);
    let py = fract(y * 456.21);
    const d = px * (px + 45.32) + py * (py + 45.32);
    px += d;
    py += d;
    return fract(px * py);
  }
  function noise(x, y) {
    const ix = Math.floor(x);
    const iy = Math.floor(y);
    const fx = x - ix;
    const fy = y - iy;
    const ux = fx * fx * (3 - 2 * fx);
    const uy = fy * fy * (3 - 2 * fy);
    const a = hash(ix, iy);
    const b = hash(ix + 1, iy);
    const c = hash(ix, iy + 1);
    const d = hash(ix + 1, iy + 1);
    return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy;
  }
  function warpR(px, py) {
    const wx = px + (noise(px * 1.7 + 1.3, py * 1.7 + 1.3) - 0.5) * 0.16;
    const wy = py * 0.86 + (noise(px * 1.7 + 8.1, py * 1.7 + 8.1) - 0.5) * 0.16;
    return Math.hypot(wx, wy);
  }

  const RING_R = [0.3, 0.44, 0.58, 0.72, 0.86];
  const SEAL_R = 1.04;

  class VoiceField {
    constructor(canvas, { reduced = false, fallbackSvg = null } = {}) {
      this.canvas = canvas;
      this.reduced = reduced;
      this.fallbackSvg = fallbackSvg;
      // Choreography state, tweened by GSAP. zoom/travel/tunnel/depth carry the journey into the print,
      // draw inks the spiral ridge by ridge, converge pulls the voice lines into the Talk button (tx, ty).
      this.u = {
        unwind: 0, seal: 0, dim: 0, rings: 0, intro: reduced ? 1 : 0, cx: 0, cy: 0, scale: 300,
        zoom: 1, travel: 0, rot: 0, draw: 999, wash: 0, tunnel: 0, depth: 0, converge: 0, sealGlow: 0, tx: 0, ty: 0,
      };
      // Live inputs, integrated per frame: scroll velocity, pointer, tap ripple, fact ripple.
      this.velIn = 0;
      this.vel = 0;
      this.travelV = 0;
      this.rotV = 0;
      this.mouse = { x: -9999, y: -9999, s: 0, target: 0 };
      this.tapState = { x: 0, y: 0, age: 9, on: 0 };
      this.rip = { r: 0, age: 9, on: 0, col: [1, 1, 1] };
      this.facts = Array.from({ length: 5 }, () => ({ r: 0.43, g: 0.41, b: 0.54, a: 0 }));
      this.first = Array.from({ length: 5 }, () => ({ r: 0, g: 0, b: 0, a: 0 }));
      this.analysers = { samjho: null, her: null };
      this.level = { samjho: 0, her: 0 };
      this.ext = { samjho: 0, her: 0 };
      this.extAt = { samjho: -1e9, her: -1e9 };
      this.spec = { samjho: new Float32Array(12), her: new Float32Array(12) };
      this.mixSpec = new Float32Array(12);
      this.speaker = 0;
      this.source = "synthetic envelope";
      this.q = 1;
      this.frames = [];
      this.t0 = performance.now();
      this.running = false;
      this.hidden = document.hidden;
      this.offscreen = false;
      this.ok = this._init();
      if (!this.ok && fallbackSvg) this._drawFallback();
      addEventListener("resize", () => this.resize());
      document.addEventListener("visibilitychange", () => {
        this.hidden = document.hidden;
        this._sync();
      });
      if ("IntersectionObserver" in window) {
        new IntersectionObserver((es) => {
          this.offscreen = !es[0].isIntersecting;
          this._sync();
        }).observe(canvas);
      }
      canvas.addEventListener("webglcontextlost", (e) => {
        e.preventDefault();
        this.ok = false;
        this._sync();
      });
      canvas.addEventListener("webglcontextrestored", () => {
        this.ok = this._init();
        this._sync();
      });
    }

    _init() {
      const gl = this.canvas.getContext("webgl2", { antialias: false, alpha: false, depth: false, powerPreference: "high-performance" });
      if (!gl) return false;
      const sh = (type, src) => {
        const s = gl.createShader(type);
        gl.shaderSource(s, src);
        gl.compileShader(s);
        if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
        return s;
      };
      try {
        const prog = gl.createProgram();
        gl.attachShader(prog, sh(gl.VERTEX_SHADER, VERT));
        gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FRAG));
        gl.linkProgram(prog);
        if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
        gl.useProgram(prog);
        const buf = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, buf);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
        const loc = gl.getAttribLocation(prog, "a");
        gl.enableVertexAttribArray(loc);
        gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
        this.gl = gl;
        this.loc = {};
        ["uRes", "uTime", "uCenter", "uScale", "uCycles", "uUnwind", "uSeal", "uDim", "uRings", "uIntro", "uAmp", "uSpeaker", "uSpec", "uFact", "uFirst", "uRingR", "uSealR", "uPx",
          "uWash", "uZoom", "uTravel", "uRot", "uDraw", "uTunnel", "uDepth", "uConverge", "uSealGlow", "uVel", "uTarget", "uMouse", "uRip", "uRipCol", "uTap"].forEach(
          (n) => (this.loc[n] = gl.getUniformLocation(prog, n)),
        );
        gl.uniform1fv(this.loc.uRingR, RING_R);
        gl.uniform1f(this.loc.uSealR, SEAL_R);
        this.fa = new Float32Array(20);
        this.fb = new Float32Array(20);
        this.resize();
        return true;
      } catch (e) {
        console.warn("VoiceField: WebGL2 unavailable, using the SVG print.", e.message);
        return false;
      }
    }

    // analysers: {samjho, her}, either may be null; attach(null) detaches (the session's context closed).
    attach(analysers) {
      this.analysers = { samjho: (analysers && analysers.samjho) || null, her: (analysers && analysers.her) || null };
      const a = this.analysers.samjho || this.analysers.her;
      if (a) {
        this.td = new Float32Array(a.fftSize);
        this.fd = new Uint8Array(a.frequencyBinCount);
      }
    }

    // A level (0..1) for one voice from outside the audio graph, held until the next feed or for 250 ms.
    feed(who, level) {
      this.ext[who] = Math.max(0, Math.min(1, level || 0));
      this.extAt[who] = performance.now();
    }

    dpr() {
      const mobile = matchMedia("(pointer: coarse)").matches || innerWidth < 700;
      return Math.min(devicePixelRatio || 1, mobile ? 1 : 1.5) * this.q;
    }

    resize() {
      if (!this.gl) return;
      const d = this.dpr();
      const w = Math.round(innerWidth * d);
      const h = Math.round(innerHeight * d);
      if (this.canvas.width !== w || this.canvas.height !== h) {
        this.canvas.width = w;
        this.canvas.height = h;
        this.gl.viewport(0, 0, w, h);
      }
      if (this.reduced) this.render();
    }

    // Ring geometry for DOM annotations: point on ring i (or the seal ring) at angle a, in CSS px.
    ringPoint(i, a) {
      const R = i === "seal" ? SEAL_R : RING_R[i];
      let lo = 0;
      let hi = 2.2;
      const c = Math.cos(a);
      const s = Math.sin(a);
      for (let k = 0; k < 22; k++) {
        const mid = (lo + hi) / 2;
        if (warpR(c * mid, s * mid) < R) lo = mid;
        else hi = mid;
      }
      const d = (lo + hi) / 2;
      return { x: this.u.cx + c * d * this.u.scale, y: this.u.cy - s * d * this.u.scale };
    }

    _read(name) {
      const a = this.analysers[name];
      const spec = this.spec[name];
      let amp = 0;
      if (a && a.context.state === "running" && this.td && this.td.length === a.fftSize) {
        a.getFloatTimeDomainData(this.td);
        let sum = 0;
        for (let i = 0; i < this.td.length; i++) sum += this.td[i] * this.td[i];
        amp = Math.min(1, Math.sqrt(sum / this.td.length) * 2.3);
        a.getByteFrequencyData(this.fd);
        const hzPerBin = a.context.sampleRate / a.fftSize;
        for (let b = 0; b < 12; b++) {
          const f0 = 90 * Math.pow(6000 / 90, b / 12);
          const f1 = 90 * Math.pow(6000 / 90, (b + 1) / 12);
          const i0 = Math.max(1, Math.floor(f0 / hzPerBin));
          const i1 = Math.max(i0 + 1, Math.ceil(f1 / hzPerBin));
          let m = 0;
          for (let i = i0; i < i1 && i < this.fd.length; i++) m = Math.max(m, this.fd[i]);
          const v = Math.max(0, m / 255 - 0.18) / 0.82;
          spec[b] += (v - spec[b]) * 0.5;
        }
        this.source = "analyser";
      } else {
        // Idle: Samjho's lines breathe slowly, a calm 5 s cycle; hers rest. A fed level (a voice note's clip
        // envelope) takes over while it is fresh, with a soft vowel-like spectrum so the ridges tremble.
        const now = performance.now();
        const fresh = now - this.extAt[name] < 250 ? this.ext[name] : 0;
        const tsec = (now - this.t0) / 1000;
        const idle = name === "samjho" ? 0.03 + 0.03 * (0.5 + 0.5 * Math.sin(tsec * 1.25)) : 0;
        amp = Math.max(idle, fresh);
        for (let b = 0; b < 12; b++) {
          const shape = Math.exp(-Math.pow((b - 3.5 - Math.sin(tsec * 3 + b) * 1.2) / 3, 2));
          spec[b] += (shape * amp * 1.4 - spec[b]) * 0.3;
        }
        this.source = fresh ? "fed level" : "idle";
      }
      const prev = this.level[name];
      this.level[name] = prev + (amp - prev) * (amp > prev ? 0.55 : 0.12);
    }

    // Pointer as a fingertip on the print (CSS px). on=false lets the press fade out.
    setPointer(x, y, on) {
      this.mouse.x = x;
      this.mouse.y = y;
      this.mouse.target = on ? 1 : 0;
    }
    tap(x, y) {
      Object.assign(this.tapState, { x, y, age: 0, on: 1 });
    }
    // A ripple leaves fact ring i and travels outwards in its verdict colour.
    ripple(i, rgb) {
      Object.assign(this.rip, { r: RING_R[i], age: 0, on: 1, col: rgb });
    }

    _dynamics(dt) {
      const k = Math.min(1, dt * 60);
      const vin = Math.max(-1, Math.min(1, this.velIn / 38));
      this.vel += (vin - this.vel) * 0.08 * k;
      this.travelV += this.vel * 0.22 * k;
      this.rotV += this.vel * 0.05 * k;
      this.mouse.s += (this.mouse.target - this.mouse.s) * 0.07 * k;
      this.tapState.age += dt;
      if (this.tapState.age > 2.6) this.tapState.on = 0;
      this.rip.age += dt;
      if (this.rip.age > 2.4) this.rip.on = 0;
    }

    frame(now) {
      if (!this.ok) return;
      const dt = Math.min(0.05, (now - (this._lastF || now)) / 1000);
      this._lastF = now;
      this._dynamics(dt);
      this._read("samjho");
      this._read("her");
      const { samjho: s, her: h } = this.level;
      if (h > s + 0.03) this.speaker += (1 - this.speaker) * 0.12;
      else if (s > h + 0.03) this.speaker += (0 - this.speaker) * 0.12;
      for (let b = 0; b < 12; b++) this.mixSpec[b] = this.spec.samjho[b] * (1 - this.speaker) + this.spec.her[b] * this.speaker;
      this.render(now);
    }

    render(now = performance.now()) {
      const gl = this.gl;
      if (!gl) return;
      const L = this.loc;
      const d = this.canvas.width / innerWidth;
      gl.uniform2f(L.uRes, this.canvas.width, this.canvas.height);
      gl.uniform1f(L.uTime, this.reduced ? 14.0 : (now - this.t0) / 1000);
      gl.uniform2f(L.uCenter, this.u.cx * d, this.u.cy * d);
      gl.uniform1f(L.uScale, this.u.scale * d);
      gl.uniform1f(L.uPx, d);
      // Ridge spacing ~7.5 CSS px on a laptop, ~6 px on a phone-sized print.
      gl.uniform1f(L.uCycles, Math.max(16, Math.min(46, this.u.scale / (this.u.scale < 160 ? 6.2 : 7.4))));
      gl.uniform1f(L.uUnwind, this.u.unwind);
      gl.uniform1f(L.uSeal, this.u.seal);
      gl.uniform1f(L.uDim, this.u.dim);
      gl.uniform1f(L.uRings, this.u.rings);
      gl.uniform1f(L.uIntro, this.u.intro);
      gl.uniform2f(L.uAmp, this.reduced ? 0 : this.level.samjho, this.reduced ? 0 : this.level.her);
      gl.uniform1f(L.uSpeaker, this.speaker);
      gl.uniform1fv(L.uSpec, this.mixSpec);
      const u = this.u;
      const st = this.reduced ? 0 : 1;
      gl.uniform1f(L.uZoom, u.zoom);
      gl.uniform1f(L.uWash, u.wash);
      gl.uniform1f(L.uTravel, u.travel + this.travelV * st);
      gl.uniform1f(L.uRot, u.rot + this.rotV * st);
      gl.uniform1f(L.uDraw, u.draw);
      gl.uniform1f(L.uTunnel, u.tunnel);
      gl.uniform1f(L.uDepth, u.depth);
      gl.uniform1f(L.uConverge, u.converge);
      gl.uniform1f(L.uSealGlow, u.sealGlow);
      gl.uniform1f(L.uVel, this.vel * st);
      const zs = u.scale * u.zoom;
      gl.uniform3f(L.uTarget, (u.tx - u.cx) / zs, -(u.ty - u.cy) / zs, (innerWidth - u.tx) / zs);
      gl.uniform3f(L.uMouse, this.mouse.x * d, this.mouse.y * d, this.mouse.s * st);
      gl.uniform4f(L.uRip, this.rip.r, this.rip.age, 0, this.rip.on * st);
      gl.uniform3f(L.uRipCol, this.rip.col[0], this.rip.col[1], this.rip.col[2]);
      gl.uniform4f(L.uTap, this.tapState.x * d, this.tapState.y * d, this.tapState.age, this.tapState.on * st);
      for (let i = 0; i < 5; i++) {
        const f = this.facts[i];
        const g = this.first[i];
        this.fa.set([f.r, f.g, f.b, f.a], i * 4);
        this.fb.set([g.r, g.g, g.b, g.a], i * 4);
      }
      gl.uniform4fv(L.uFact, this.fa);
      gl.uniform4fv(L.uFirst, this.fb);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }

    _loop = (now) => {
      if (!this.running) return;
      const last = this._last || now;
      const dt = now - last;
      this._last = now;
      if (dt > 0 && dt < 250) {
        this.frames.push(dt);
        if (this.frames.length > 120) this.frames.shift();
        // Adaptive quality: if frames run long for a second, render fewer pixels.
        // The median ignores one-off stalls (font swap, clip decoding, GC); only a sustained slow GPU counts.
        if (this.frames.length === 120 && this.q > 0.6 && now - this.t0 > 4000) {
          const med = [...this.frames].sort((x, y) => x - y)[60];
          if (med > 21) {
            this.q = Math.max(0.6, this.q - 0.15);
            this.frames = [];
            this.resize();
          }
        }
      }
      this.frame(now);
      if (this.onFrame) this.onFrame(now);
      requestAnimationFrame(this._loop);
    };

    fps() {
      if (!this.frames.length) return 0;
      const n = Math.min(this.frames.length, 90);
      const s = this.frames.slice(-n);
      return 1000 / (s.reduce((a, b) => a + b, 0) / n);
    }

    start() {
      this.wanted = true;
      this._sync();
    }

    _sync() {
      const go = this.wanted && this.ok && !this.reduced && !this.hidden && !this.offscreen;
      if (go && !this.running) {
        this.running = true;
        this._last = 0;
        requestAnimationFrame(this._loop);
      } else if (!go) {
        this.running = false;
      }
    }

    // Reduced motion and fallback: draw one still frame whenever the state changes.
    still() {
      if (this.ok && this.reduced) this.render();
      if (!this.ok && this.fallbackSvg) this._drawFallback();
    }

    // No WebGL: an authored SVG print. Spiral ridges, the five rings in their verdict colours, the seal ring.
    _drawFallback() {
      const svg = this.fallbackSvg;
      svg.removeAttribute("hidden");
      this.canvas.hidden = true;
      const { cx, cy, scale } = this.u;
      const W = innerWidth;
      const H = innerHeight;
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
      const ridges = Math.round(Math.max(14, Math.min(34, scale / 9)));
      const toXY = (rr, a) => {
        const x = Math.cos(a) * rr;
        const y = (Math.sin(a) * rr) / 0.86;
        return [cx + x * scale + (noise(x * 1.7 + 1.3, y * 1.7) - 0.5) * 0.12 * scale, cy - y * scale];
      };
      let paths = "";
      const sealed = this.u.seal > 0.5;
      if (!sealed) {
        for (let k = 1; k < ridges * 1.45; k++) {
          let d = "";
          for (let j = 0; j <= 72; j++) {
            const a = (j / 72) * Math.PI * 2;
            const rr = (k - a / (Math.PI * 2)) / ridges;
            if (rr <= 0.02) continue;
            const [x, y] = toXY(rr, a);
            d += (d ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
          }
          const op = Math.max(0, 1 - Math.max(0, k / ridges - 1.05) * 2.2);
          paths += `<path d="${d}" fill="none" stroke="#8E7CFF" stroke-opacity="${(0.55 * op).toFixed(2)}" stroke-width="1.3"/>`;
        }
      }
      if (this.u.rings > 0.5 || sealed) {
        this.facts.forEach((f, i) => {
          if (f.a < 0.05) return;
          const rx = RING_R[i] * scale;
          const col = `rgb(${(f.r * 255) | 0},${(f.g * 255) | 0},${(f.b * 255) | 0})`;
          paths += `<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${rx / 0.86}" fill="none" stroke="${col}" stroke-width="${sealed ? 1.5 : 5}" stroke-opacity="${sealed ? 0.4 : 0.9}"/>`;
        });
      }
      if (sealed) paths += `<ellipse cx="${cx}" cy="${cy}" rx="${SEAL_R * scale}" ry="${(SEAL_R * scale) / 0.86}" fill="none" stroke="#C9C0FF" stroke-width="2.5"/>`;
      svg.innerHTML = paths;
    }
  }

  VoiceField.RING_R = RING_R;
  VoiceField.SEAL_R = SEAL_R;
  window.VoiceField = VoiceField;
})();
