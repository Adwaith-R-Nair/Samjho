"""Recording and replay of consented sessions, so a judge can watch a real person's session without a mic.

A recorded session is a folder replays/<UTC date>_<session id>/ with:
    events.jsonl   every UI event, one JSON object per line, with "t" = seconds since the session started
    audio.wav      the conversation, user and Samjho mixed to mono (16 kHz browser, 8 kHz phone)
    manifest.json  session_id, lang, channel, started_at, duration_s, consent_text, spoken_consent,
                   right_first_answer, right_after_samjho, seal_sha256

Anything that looks like a phone number is masked before it is written. No keys are ever part of an event.
SAMJHO_REPLAY_DIR overrides the folder (the smoke test writes synthetic sessions under scratch/, because
replays/ holds only real consented sessions).
"""

import json
import os
import re
import time
import wave
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "replays"
CONSENT_TEXT = "Save this session as a demo replay. The person speaking agrees to be recorded and shown."
REPLAY_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
# Indian mobiles with or without +91 / 0, spaces or dashes: 98765 43210, +91-9876543210, 09876543210.
# ASCII letters around it mean it is part of a hash or an id (the seal is hex), not a phone number.
_PHONE = re.compile(r"(?<![0-9A-Za-z+])(?:\+?91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?![0-9A-Za-z])")


def replay_dir() -> Path:
    custom = os.getenv("SAMJHO_REPLAY_DIR", "").strip()
    return Path(custom) if custom else DEFAULT_DIR


def mask_numbers(value):
    """Masks anything that looks like a phone number, keeping the last four digits, in any nested value."""
    if isinstance(value, str):
        return _PHONE.sub(lambda m: "XXXXXX" + re.sub(r"\D", "", m.group())[-4:], value)
    if isinstance(value, dict):
        return {k: mask_numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_numbers(v) for v in value]
    return value


class Recorder:
    """Collects a session's events (timed) and audio, and writes them as one replay folder at the end."""

    def __init__(self, session, channel: str, clock=time.monotonic) -> None:
        self.session = session
        self.channel = channel
        self._clock = clock
        self._t0 = clock()
        self.started_at = datetime.now(UTC)
        self.events: list[dict] = []
        self.audio: bytes = b""
        self.rate = 0

    def restart_clock(self) -> None:
        """Called when the audio recording starts, so event times line up with the audio."""
        self._t0 = self._clock()

    def event(self, ev: dict) -> None:
        self.events.append({"t": round(max(0.0, self._clock() - self._t0), 3), **mask_numbers(ev)})

    def add_audio(self, pcm: bytes, rate: int) -> None:
        self.audio += pcm
        self.rate = rate

    def save(self, root: Path | None = None) -> Path | None:
        """Writes the replay. Skipped when she never spoke (nothing worth replaying)."""
        if not any(e["type"] == "heard" for e in self.events):
            logger.info("Recording not saved: no user turn was heard")
            return None
        root = root or replay_dir()
        rid = f"{self.started_at:%Y-%m-%d}_{self.session.id}"
        folder = root / rid
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / "events.jsonl", "w", encoding="utf-8") as f:
            for ev in self.events:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        duration = self.events[-1]["t"]
        if self.audio and self.rate:
            with wave.open(str(folder / "audio.wav"), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(self.rate)
                w.writeframes(self.audio)
            duration = max(duration, len(self.audio) / 2 / self.rate)
        record = self.session.record()
        manifest = {
            "id": rid,
            "session_id": self.session.id,
            "lang": self.session.lang,
            "channel": self.channel,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "duration_s": round(duration, 1),
            "consent_text": CONSENT_TEXT,
            "spoken_consent": record.get("consent"),
            "right_first_answer": record.get("right_first_answer"),
            "right_after_samjho": record.get("right_after_samjho"),
            "seal_sha256": record.get("seal_sha256"),
            "has_audio": bool(self.audio),
        }
        (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Replay saved: {folder}")
        return folder


# ---- reading replays (the API) ----------------------------------------------------------------------
def list_replays(root: Path | None = None) -> list[dict]:
    root = root or replay_dir()
    if not root.is_dir():
        return []
    out = []
    for path in root.glob("*/manifest.json"):
        try:
            m = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        m["id"] = path.parent.name
        out.append(m)
    return sorted(out, key=lambda m: m.get("started_at", ""), reverse=True)


def has_replays(root: Path | None = None) -> bool:
    root = root or replay_dir()
    return root.is_dir() and any(root.glob("*/manifest.json"))


def replay_file(rid: str, name: str, root: Path | None = None) -> Path | None:
    """The file of one replay, or None. Only plain ids, only files inside the replay folder."""
    if not REPLAY_ID.fullmatch(rid or "") or name not in ("events.jsonl", "audio.wav", "manifest.json"):
        return None
    root = (root or replay_dir()).resolve()
    path = (root / rid / name).resolve()
    if path.parent.parent != root or not path.is_file():
        return None
    return path


def read_events(rid: str, root: Path | None = None) -> list[dict] | None:
    path = replay_file(rid, "events.jsonl", root)
    if not path:
        return None
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
