"""End-to-end smoke test of the browser voice channel, with real Sarvam calls. Needs SARVAM_API_KEY.

It speaks for the user: each answer is synthesised with Sarvam TTS, then streamed in real time (20 ms PCM16
16 kHz frames, silence in between, like a live mic) over a real WebSocket to a local uvicorn server.

Session 1 (Hindi): agree, move on, then a wrong teach-back. Checks say, heard and fact events and bot audio,
and prints the latency of each turn.
Session 2 (Hindi): decline at the start. Checks the record event, that the goodbye is played out, and that the
server closes the socket cleanly.

    .venv/Scripts/python scripts/voice_smoke.py [--port 7861] [--save bot.wav] [--server-log server.log]

Not a CI test: CI has no keys.
"""

import argparse
import asyncio
import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import httpx
import websockets
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
RATE = 16000
CHUNK = 640  # 20 ms of PCM16 mono at 16 kHz
USER_VOICE = "rahul_hi_conversational"
# What the user says, in order: start, move on from the explanation, then a wrong teach-back.
TURNS = ["हाँ जी, शुरू कीजिए।", "आगे बढ़िए।", "पचास हज़ार हाथ में आएँगे।"]
DECLINE = ["नहीं, अभी नहीं करना।"]
QUIET_SECS = 1.5  # bot audio silent this long = bot finished talking


def synthesise(text: str, key: str) -> bytes:
    r = httpx.post(
        "https://api.sarvam.ai/text-to-speech",
        headers={"api-subscription-key": key},
        json={
            "text": text,
            "target_language_code": "hi-IN",
            "speaker": USER_VOICE,
            "model": "bulbul:v4-flash",
            "speech_sample_rate": RATE,
        },
        timeout=30,
    )
    r.raise_for_status()
    with wave.open(io.BytesIO(base64.b64decode(r.json()["audios"][0]))) as w:
        assert w.getframerate() == RATE and w.getnchannels() == 1 and w.getsampwidth() == 2
        return w.readframes(w.getnframes())


async def wait_for_server(port: int, proc: subprocess.Popen) -> None:
    async with httpx.AsyncClient() as c:
        for _ in range(120):
            if proc.poll() is not None:
                raise SystemExit("server exited early, see the server log")
            try:
                if (await c.get(f"http://127.0.0.1:{port}/healthz")).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.5)
    raise SystemExit("server did not start")


async def converse(port: int, texts: list[str], utterances: list[bytes]) -> dict:
    events: list[dict] = []
    bot_audio = bytearray()
    st = {"last_audio": 0.0, "speech_end": None, "client_latency": [], "audio_after_record": 0, "closed": None}
    outbox: asyncio.Queue[bytes] = asyncio.Queue()

    async with websockets.connect(f"ws://127.0.0.1:{port}/ws/browser?lang=hi", max_size=None) as ws:

        async def mic() -> None:
            # A live mic never stops: real-time 20 ms frames, speech when queued, silence otherwise.
            silence = bytes(CHUNK)
            next_t = time.monotonic()
            while True:
                data = silence
                if not outbox.empty():
                    data = outbox.get_nowait()
                    if outbox.empty():
                        st["speech_end"] = time.monotonic() + 0.02
                await ws.send(data)
                next_t += 0.02
                await asyncio.sleep(max(0.0, next_t - time.monotonic()))

        async def speaker() -> None:
            try:
                async for msg in ws:
                    if isinstance(msg, bytes):
                        now = time.monotonic()
                        if st["speech_end"] is not None:
                            st["client_latency"].append(round((now - st["speech_end"]) * 1000))
                            st["speech_end"] = None
                        bot_audio.extend(msg)
                        st["last_audio"] = now
                        if any(e["type"] == "record" for e in events):
                            st["audio_after_record"] += len(msg)
                    else:
                        ev = json.loads(msg)
                        events.append(ev)
                        show = ev.get("text") or ev.get("state") or ev.get("fact") or ev.get("ms") or ev.get("case") or ""
                        print(f"  <- {ev['type']}: {str(show)[:90]}")
                st["closed"] = "clean"
            except websockets.ConnectionClosed as e:
                st["closed"] = f"error {e}"

        mic_task = asyncio.create_task(mic())
        spk_task = asyncio.create_task(speaker())

        async def bot_finished(timeout: float = 120) -> None:
            start = time.monotonic()
            while time.monotonic() - start < timeout:
                await asyncio.sleep(0.1)
                if spk_task.done():
                    return
                if st["last_audio"] and time.monotonic() - st["last_audio"] > QUIET_SECS:
                    return
            raise RuntimeError("bot never finished speaking")

        try:
            await bot_finished()
            for text, pcm in zip(texts, utterances):
                print(f"-> user: {text} ({len(pcm) / 2 / RATE:.2f} s of speech)")
                st["last_audio"] = 0.0
                for k in range(0, len(pcm), CHUNK):
                    outbox.put_nowait(pcm[k : k + CHUNK].ljust(CHUNK, b"\0"))
                while not outbox.empty():
                    await asyncio.sleep(0.05)
                await bot_finished()
            await asyncio.sleep(1.0)
        finally:
            mic_task.cancel()
            if not spk_task.done():
                spk_task.cancel()

    return {
        "events": events,
        "bot_audio": bytes(bot_audio),
        "client_latency": st["client_latency"],
        "audio_after_record_secs": st["audio_after_record"] / 2 / RATE,
        "closed": st["closed"],
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7861)
    ap.add_argument("--save", help="write the bot audio of session 1 to this WAV file")
    ap.add_argument("--server-log", default=str(Path(tempfile.gettempdir()) / "samjho_voice_smoke_server.log"))
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    key = os.getenv("SARVAM_API_KEY", "").strip()
    if not key:
        print("SARVAM_API_KEY not set: nothing to test")
        return 2

    print("Synthesising the user's answers with Sarvam TTS...")
    answers = [synthesise(t, key) for t in TURNS]
    decline = [synthesise(t, key) for t in DECLINE]

    log = open(args.server_log, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(args.port), "--log-level", "info"],
        cwd=ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    try:
        await wait_for_server(args.port, proc)
        print(f"Server up on :{args.port} (log: {args.server_log})")
        print("\nSession 1: agree, move on, wrong teach-back")
        one = await converse(args.port, TURNS, answers)
        print("\nSession 2: decline at the start")
        two = await converse(args.port, DECLINE, decline)
    finally:
        proc.terminate()
        proc.wait(10)
        log.close()

    events = one["events"]
    kinds = [e["type"] for e in events]
    heard = [e["text"] for e in events if e["type"] == "heard"]
    facts = [(e["fact"], e["status"], e.get("said")) for e in events if e["type"] == "fact"]
    server_latency = [(e["turn"], e["ms"]) for e in events if e["type"] == "latency"]
    audio_secs = len(one["bot_audio"]) / 2 / RATE

    print("\nSession 1")
    print("  heard:", heard)
    print("  facts:", facts)
    print(f"  bot audio received: {audio_secs:.1f} s")
    print("  latency per turn (server, end of speech to first bot audio):", server_latency)
    print("  latency per turn (client, last speech frame sent to first audio byte back):", one["client_latency"])
    print("Session 2")
    print("  heard:", [e["text"] for e in two["events"] if e["type"] == "heard"])
    print(f"  goodbye audio after the record event: {two['audio_after_record_secs']:.1f} s; socket: {two['closed']}")

    if args.save:
        with wave.open(args.save, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(one["bot_audio"])

    problems = []
    if kinds.count("say") < 3:
        problems.append("expected say events")
    if len(heard) < len(TURNS):
        problems.append(f"expected {len(TURNS)} heard events, got {len(heard)}")
    if "fact" not in kinds:
        problems.append("expected fact events after the teach-back")
    if audio_secs < 5:
        problems.append("expected bot audio")
    if len(server_latency) < len(TURNS):
        problems.append("expected a latency event per turn")
    if not any(e["type"] == "record" for e in two["events"]):
        problems.append("session 2: expected a record event after declining")
    if two["audio_after_record_secs"] < 1.0:
        problems.append("session 2: goodbye was not played before closing")
    if two["closed"] != "clean":
        problems.append(f"session 2: socket not closed cleanly by the server ({two['closed']})")
    if problems:
        print("FAIL:", "; ".join(problems))
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
