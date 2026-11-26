// Samjho UI. Reads which features are available and labels the ones that need a missing key.

async function loadStatus() {
  const res = await fetch("/api/status");
  const status = await res.json();
  const modeNeeds = { browser: "voice", phone: "phone", text: "text", replay: "replay" };
  document.querySelectorAll(".tile").forEach((tile) => {
    const need = modeNeeds[tile.dataset.mode];
    const s = status[need];
    tile.disabled = !s.ready;
    tile.querySelector(".state").textContent = s.ready ? "" : s.reason;
  });
  const missing = Object.values(status).filter((s) => !s.ready).length;
  document.getElementById("keys").textContent = missing
    ? "Some features are off because their keys are not set. Text mode and replay always work."
    : "All features available.";
}

loadStatus().catch(() => {
  document.getElementById("keys").textContent = "Could not reach the server.";
});
