"""Phone channel smoke test.

Live (needs a paid Twilio account and SARVAM_API_KEY, TWILIO_*, PUBLIC_BASE_URL, CALLS_ENABLED=true and
MY_PHONE_NUMBER in .env, plus the server running behind a public tunnel):

    .venv/Scripts/python -m uvicorn app.main:app --port 7860          # terminal 1
    cloudflared tunnel --url http://localhost:7860                     # terminal 2, put its https URL in
                                                                       # PUBLIC_BASE_URL and restart terminal 1
    .venv/Scripts/python scripts/call_smoke.py --server http://127.0.0.1:7860   # terminal 3

It asks the server to call MY_PHONE_NUMBER, then prints the call's live events (what the panel shows) until the
call ends. Answer the phone and talk to Samjho.

Simulated (needs only SARVAM_API_KEY): runs the server in this process with Twilio's REST API faked, then plays
Twilio's side of the Media Stream itself (mulaw 8 kHz, real-time 20 ms frames) with synthesised Hindi answers:

    .venv/Scripts/python scripts/call_smoke.py --simulate

Scenario: barge in on the intro (must interrupt), talk over the amounts (must be ignored), say "aage", then a
wrong teach-back (must be caught). Everything except the Twilio REST call and the phone network is real.
"""

import argparse
import asyncio
import audioop
import base64
import io
import json
import os
import re
import sys
import tempfile
import time
import wave
from pathlib import Path
from types import SimpleNamespace

import httpx
import websockets
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RATE = 8000
CHUNK = 160  # 20 ms of 8 kHz mono, one byte per mulaw sample
USER_VOICE = "rahul_hi_conversational"
QUIET_SECS = 1.5
BARGE_IN = "हाँ जी, शुरू कीजिए।"
TALK_OVER = "एक मिनट रुकिए, मुझे सोचने दीजिए।"
AAGE = "आगे बढ़िए।"
TEACH_BACK = "पचास हज़ार हाथ में आएँगे।"


def show(ev: dict) -> None:
    text = ev.get("text") or ev.get("status") or ev.get("state") or ev.get("fact") or ev.get("ms") or ev.get("case")
    print(f"  [panel] {ev['type']}: {str(text or '')[:90]}")


async def watch(base: str, wid: str, events: list[dict]) -> None:
    url = base.replace("http", "ws", 1) + f"/ws/watch?id={wid}"
    async with websockets.connect(url, max_size=None) as ws:
        async for msg in ws:
            ev = json.loads(msg)
            events.append(ev)
            show(ev)


# ---- live -----------------------------------------------------------------------------------------------
async def live(server: str, lang: str) -> int:
    number = os.getenv("MY_PHONE_NUMBER", "").strip()
    if not number:
        print("MY_PHONE_NUMBER not set")
        return 2
    async with httpx.AsyncClient(timeout=40) as c:
        r = await c.post(
            f"{server}/api/call",
            json={"phone": number, "consent": True, "lang": lang, "k": os.getenv("JUDGE_TOKEN", "")},
        )
    if r.status_code != 200:
        print(f"Refused ({r.status_code}): {r.json().get('detail')}")
        return 1
    data = r.json()
    print(f"Calling {data['to']} ({data['call_id']}). Answer the phone.")
    events: list[dict] = []
    await watch(server, data["watch_id"], events)
    lat = [e["ms"] for e in events if e["type"] == "latency"]
    print("heard:", [e["text"] for e in events if e["type"] == "heard"])
    print("latency per turn (ms):", lat)
    return 0 if any(e["type"] == "heard" for e in events) else 1


# ---- simulated ------------------------------------------------------------------------------------------
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
        pcm = w.readframes(w.getnframes())
    return audioop.lin2ulaw(pcm, 2)


class FakeTwilioRest:
    def __init__(self) -> None:
        self.made: list[dict] = []
        self.calls = self

    def create(self, **kw):
        self.made.append(kw)
        return SimpleNamespace(sid="CA" + "f" * 32)


async def simulate(port: int) -> int:
    key = os.getenv("SARVAM_API_KEY", "").strip()
    if not key:
        print("SARVAM_API_KEY not set: nothing to test")
        return 2
    os.environ.update(
        TWILIO_ACCOUNT_SID="AC_simulated",
        TWILIO_AUTH_TOKEN="simulated",
        TWILIO_FROM_NUMBER="+15550000000",
        PUBLIC_BASE_URL=f"http://127.0.0.1:{port}",
        CALLS_ENABLED="true",
    )
    os.environ.pop("JUDGE_TOKEN", None)

    from loguru import logger

    log_path = Path(tempfile.gettempdir()) / "samjho_call_smoke_server.log"
    logger.remove()
    logger.add(log_path, level="DEBUG", mode="w", encoding="utf-8")

    import uvicorn

    from app import phone
    from app.limits import CallLimiter
    from app.main import app

    rest = FakeTwilioRest()
    phone._desk = phone.CallDesk(CallLimiter(), phone.WatchHub(), client_factory=lambda sid, token: rest)

    print("Synthesising the caller's answers (8 kHz mulaw)...")
    audio = {t: synthesise(t, key) for t in (BARGE_IN, TALK_OVER, AAGE, TEACH_BACK)}

    server = uvicorn.Server(uvicorn.Config(app, port=port, log_level="warning"))
    serve = asyncio.create_task(server.serve())
    base = f"http://127.0.0.1:{port}"
    async with httpx.AsyncClient() as c:
        for _ in range(60):
            try:
                if (await c.get(base + "/healthz")).status_code == 200:
                    break
            except httpx.HTTPError:
                await asyncio.sleep(0.25)
        r = await c.post(base + "/api/call", json={"phone": "+919876543210", "consent": True, "lang": "hi"})
    assert r.status_code == 200, r.text
    wid = r.json()["watch_id"]
    twiml = rest.made[0]["twiml"]
    url = re.search(r'<Stream url="([^"]+)"', twiml).group(1)
    token = re.search(r'<Parameter name="t" value="([^"]+)"', twiml).group(1)
    print(f"Server log: {log_path}\nTwiML streams to {url}")

    events: list[dict] = []
    watcher = asyncio.create_task(watch(base, wid, events))
    st = {"last_audio": 0.0, "first_audio": 0.0, "clears": 0, "audio_bytes": 0}
    outbox: asyncio.Queue[bytes] = asyncio.Queue()
    sid = "MZ" + "e" * 32

    async with websockets.connect(url, max_size=None) as ws:
        await ws.send(json.dumps({"event": "connected", "protocol": "Call", "version": "1.0.0"}))
        await ws.send(
            json.dumps(
                {
                    "event": "start",
                    "sequenceNumber": "1",
                    "streamSid": sid,
                    "start": {
                        "streamSid": sid,
                        "callSid": "CA" + "f" * 32,
                        "accountSid": "AC_simulated",
                        "tracks": ["inbound"],
                        "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
                        "customParameters": {"t": token},
                    },
                }
            )
        )

        async def handset_mic() -> None:
            silence = audioop.lin2ulaw(bytes(CHUNK * 2), 2)
            next_t = time.monotonic()
            while True:
                data = outbox.get_nowait() if not outbox.empty() else silence
                payload = base64.b64encode(data).decode()
                await ws.send(json.dumps({"event": "media", "streamSid": sid, "media": {"payload": payload}}))
                next_t += 0.02
                await asyncio.sleep(max(0.0, next_t - time.monotonic()))

        async def handset_speaker() -> None:
            async for msg in ws:
                m = json.loads(msg)
                if m.get("event") == "media":
                    now = time.monotonic()
                    if not st["last_audio"] or now - st["last_audio"] > QUIET_SECS:
                        st["first_audio"] = now
                    st["last_audio"] = now
                    st["audio_bytes"] += len(base64.b64decode(m["media"]["payload"]))
                elif m.get("event") == "clear":
                    st["clears"] += 1
                    print("  [handset] clear: bot audio flushed (barge-in)")

        mic = asyncio.create_task(handset_mic())
        spk = asyncio.create_task(handset_speaker())

        async def say(text: str) -> None:
            print(f"-> caller: {text}")
            pcm = audio[text]
            for k in range(0, len(pcm), CHUNK):
                outbox.put_nowait(pcm[k : k + CHUNK].ljust(CHUNK, b"\xff"))
            while not outbox.empty():
                await asyncio.sleep(0.05)

        async def bot_speaking_for(secs: float, timeout: float = 30) -> None:
            start = time.monotonic()
            while time.monotonic() - start < timeout:
                await asyncio.sleep(0.05)
                now = time.monotonic()
                if st["last_audio"] and now - st["last_audio"] < 0.5 and now - st["first_audio"] >= secs:
                    return
            raise RuntimeError("bot did not start speaking")

        async def bot_quiet(timeout: float = 120) -> None:
            start = time.monotonic()
            while time.monotonic() - start < timeout:
                await asyncio.sleep(0.1)
                if st["last_audio"] and time.monotonic() - st["last_audio"] > QUIET_SECS:
                    return
            raise RuntimeError("bot never finished speaking")

        try:
            await bot_speaking_for(2.5)  # intro is playing
            await say(BARGE_IN)  # barge in: a reply with no amounts may be interrupted
            heard_before = sum(e["type"] == "heard" for e in events)
            while sum(e["type"] == "heard" for e in events) == heard_before:
                await asyncio.sleep(0.1)
            st["last_audio"] = 0.0
            await bot_speaking_for(3.0)  # the amounts are being read
            await say(TALK_OVER)  # must be ignored
            await bot_quiet()
            await say(AAGE)
            st["last_audio"] = 0.0
            await bot_quiet()
            await say(TEACH_BACK)
            st["last_audio"] = 0.0
            await bot_quiet()
            await ws.send(json.dumps({"event": "stop", "streamSid": sid}))
        finally:
            mic.cancel()
            spk.cancel()

    await asyncio.sleep(2)
    watcher.cancel()
    server.should_exit = True
    await serve

    heard = [e["text"] for e in events if e["type"] == "heard"]
    facts = [(e["fact"], e["status"], e.get("said")) for e in events if e["type"] == "fact"]
    lat = [(e["turn"], e["ms"]) for e in events if e["type"] == "latency"]
    print("\nheard:", heard)
    print("facts:", facts)
    print(f"bot audio to the handset: {st['audio_bytes'] / RATE:.1f} s; clears (barge-ins): {st['clears']}")
    print("latency per turn (server, end of speech to first bot audio):", lat)

    problems = []
    if st["clears"] < 1:
        problems.append("barge-in on the intro did not interrupt the bot")
    if len(heard) != 3:
        problems.append(f"expected 3 heard turns (barge-in, aage, teach-back), got {len(heard)}")
    if any("मिनट" in h or "रुक" in h or "minute" in h.lower() for h in heard):
        problems.append("talking over the amounts was heard; it should be muted")
    if not facts:
        problems.append("expected fact events")
    if not lat:
        problems.append("expected latency events")
    if not any(e.get("status") == "connected" for e in events):
        problems.append("watcher did not see the call connect")
    if problems:
        print("FAIL:", "; ".join(problems))
        return 1
    print("PASS")
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simulate", action="store_true", help="fake Twilio locally; needs only SARVAM_API_KEY")
    ap.add_argument("--server", default="http://127.0.0.1:7860", help="live mode: the running server")
    ap.add_argument("--port", type=int, default=7864, help="simulate mode: port for the in-process server")
    ap.add_argument("--lang", default="hi")
    args = ap.parse_args()
    load_dotenv(ROOT / ".env")
    if args.simulate:
        return await simulate(args.port)
    return await live(args.server.rstrip("/"), args.lang)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
