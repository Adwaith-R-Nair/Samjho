// Browser voice channel. Mic -> 16 kHz PCM16 binary frames over /ws/browser; the server sends back PCM16
// 16 kHz audio (played gaplessly) and JSON UI events (passed to window.samjhoHandleEvent).
// Half duplex: while Samjho's voice is playing, and for a short tail after, the mic sends silence, so laptop
// speakers do not feed her own voice back as the borrower's answer.
(() => {
  const RATE = 16000;
  const TAIL = 0.3; // seconds of mic silence after playback ends (room echo, output latency)
  const CUSHION = 0.12; // playback lead after a gap, absorbs network jitter

  let ws = null;
  let ctx = null;
  let stream = null;
  let micNode = null;
  let playHead = 0;
  let sources = [];
  let finished = false;
  let refused = false;
  let statusEl = null;
  let lastStatus = "";

  function ui() {
    if (statusEl) return statusEl;
    statusEl = document.createElement("div");
    statusEl.className = "voice-status";
    statusEl.style.margin = "10px 0 0";
    statusEl.hidden = true;
    statusEl.innerHTML =
      '<strong class="voice-rec" hidden style="color: var(--red)">Recording for a demo replay. </strong>' +
      '<span class="voice-text muted"></span> <button type="button" class="voice-end">End</button>';
    statusEl.querySelector(".voice-end").onclick = () => stop("Session ended.");
    const tiles = document.getElementById("tiles");
    tiles.parentNode.insertBefore(statusEl, tiles.nextSibling);
    return statusEl;
  }

  function status(text, live = true) {
    if (text === lastStatus) return;
    lastStatus = text;
    const el = ui();
    el.hidden = false;
    el.querySelector(".voice-text").textContent = text;
    el.querySelector(".voice-end").hidden = !live;
  }

  function botAudible() {
    return ctx !== null && ctx.currentTime < playHead + TAIL;
  }

  function play(buffer) {
    const pcm = new Int16Array(buffer);
    if (!pcm.length || !ctx) return;
    const samples = new Float32Array(pcm.length);
    for (let i = 0; i < pcm.length; i++) samples[i] = pcm[i] / 32768;
    const audio = ctx.createBuffer(1, samples.length, RATE);
    audio.copyToChannel(samples, 0);
    const src = ctx.createBufferSource();
    src.buffer = audio;
    src.connect(ctx.destination);
    const now = ctx.currentTime;
    if (playHead < now) playHead = now + CUSHION;
    src.start(playHead);
    playHead += audio.duration;
    sources.push(src);
    src.onended = () => {
      sources = sources.filter((s) => s !== src);
    };
  }

  function clearPlayback() {
    sources.forEach((s) => {
      try {
        s.stop();
      } catch (e) {
        /* already stopped */
      }
    });
    sources = [];
    playHead = 0;
  }

  function onMessage(msg) {
    if (typeof msg.data !== "string") {
      play(msg.data);
      return;
    }
    const ev = JSON.parse(msg.data);
    if (ev.type === "clear") {
      clearPlayback();
      return;
    }
    if (ev.type === "record") finished = true;
    if (ev.type === "case" && (ev.case === "KEY_NOT_SET" || ev.case === "BUSY")) {
      finished = true;
      refused = true;
      status(ev.detail, false);
    }
    window.samjhoHandleEvent(ev);
  }

  function onMic(e) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const speaking = botAudible();
    ws.send(speaking ? new ArrayBuffer(e.data.byteLength) : e.data);
    if (!finished) status(speaking ? "Samjho is speaking. Your mic is paused." : "Listening. Speak now.");
  }

  function recording(on) {
    ui().querySelector(".voice-rec").hidden = !on;
  }

  async function start(lang) {
    if (ws) stop();
    // Only with the consent box ticked: the person speaking agrees to be recorded and shown as a demo replay.
    const record = Boolean(document.getElementById("recordConsent")?.checked);
    finished = false;
    refused = false;
    lastStatus = "";
    // Created inside the click so the browser lets it play sound.
    ctx = new AudioContext();
    status("Asking for your microphone...");
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    await ctx.audioWorklet.addModule("/static/mic-worklet.js");
    const source = ctx.createMediaStreamSource(stream);
    micNode = new AudioWorkletNode(ctx, "samjho-mic");
    micNode.port.onmessage = onMic;
    source.connect(micNode);
    // Keep the worklet pulled by the graph without making the mic audible.
    const mute = ctx.createGain();
    mute.gain.value = 0;
    micNode.connect(mute).connect(ctx.destination);

    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/browser?lang=${encodeURIComponent(lang)}&record=${record ? 1 : 0}`);
    recording(record);
    ws.binaryType = "arraybuffer";
    status("Connecting...");
    ws.onmessage = onMessage;
    ws.onclose = () => {
      const done = finished;
      release();
      if (done) {
        if (!refused) status("Session complete.", false);
      } else {
        status("Disconnected. Click the tile to start again.", false);
      }
    };
    ws.onerror = () => status("Could not reach the voice server.", false);
  }

  function release() {
    recording(false);
    if (stream) stream.getTracks().forEach((t) => t.stop());
    if (micNode) micNode.port.onmessage = null;
    // Let queued audio (the goodbye) finish before closing the audio context.
    const c = ctx;
    const wait = c ? Math.max(0, (playHead - c.currentTime) * 1000) + 300 : 0;
    if (c) setTimeout(() => c.close().catch(() => {}), wait);
    ws = null;
    stream = null;
    micNode = null;
    ctx = null;
    sources = [];
    playHead = 0;
  }

  function stop(message) {
    const socket = ws;
    finished = true;
    if (socket) {
      socket.onclose = null;
      socket.close();
    }
    clearPlayback();
    release();
    if (message) status(message, false);
  }

  window.samjhoVoice = { start, stop };
})();
