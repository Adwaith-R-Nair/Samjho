"""Recording and replay checks with no keys: masking, timing, files, listing, path safety, the status gate."""

import asyncio
import json
import wave
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import recording
from app.flow import Session
from app.main import app
from app.recording import Recorder, mask_numbers


class Clock:
    def __init__(self) -> None:
        self.t = 500.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def rdir(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMJHO_REPLAY_DIR", str(tmp_path))
    return tmp_path


def recorded_session(clock: Clock) -> Recorder:
    session = Session(lang="hi")
    rec = Recorder(session, "browser", clock=clock)
    for ev in session.start():
        rec.event(ev)
    clock.t += 4.25
    for ev in session.hear("haan ji, mera number 98765 43210 hai"):
        rec.event(ev)
    clock.t += 1.0
    rec.event({"type": "latency", "turn": 1, "ms": 1040})
    rec.add_audio(b"\x01\x00" * 16000 * 6, 16000)  # 6 s at 16 kHz
    return rec


# ---- masking --------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text", ["+91 98765 43210", "9876543210", "09876543210", "+91-9876543210", "+919876543210", "call 98765-43210 now"]
)
def test_phone_numbers_are_masked(text):
    out = mask_numbers(text)
    assert "XXXXXX3210" in out and "98765" not in out


@pytest.mark.parametrize("text", ["50,000", "56940 rupees", "Rs 1,095", "52 weeks", "48410", "id a1b2c3d4e5f6"])
def test_amounts_and_ids_are_not_masked(text):
    assert mask_numbers(text) == text


def test_hashes_are_never_masked():
    seal = "ab" + "9876543210" + "cd" * 26
    assert mask_numbers({"seal_sha256": seal, "entries": [{"hash": seal}]}) == {
        "seal_sha256": seal,
        "entries": [{"hash": seal}],
    }


def test_masking_reaches_nested_record_entries():
    ev = {"type": "record", "record": {"entries": [{"kind": "heard", "text": "mera 9876543210"}]}}
    assert mask_numbers(ev)["record"]["entries"][0]["text"] == "mera XXXXXX3210"


# ---- recorder -------------------------------------------------------------------------------------------
def test_event_times_are_seconds_since_start():
    clock = Clock()
    rec = recorded_session(clock)
    times = [e["t"] for e in rec.events]
    assert times[0] == 0.0 and times == sorted(times)
    heard = next(e for e in rec.events if e["type"] == "heard")
    assert heard["t"] == 4.25 and heard["text"] == "haan ji, mera number XXXXXX3210 hai"
    assert rec.events[-1] == {"t": 5.25, "type": "latency", "turn": 1, "ms": 1040}
    assert all(isinstance(e["t"], float) for e in rec.events)


def test_restart_clock_lines_events_up_with_the_audio():
    clock = Clock()
    rec = Recorder(Session(), "browser", clock=clock)
    clock.t += 0.3
    rec.restart_clock()
    clock.t += 1.5
    rec.event({"type": "say", "text": "x"})
    assert rec.events[0]["t"] == 1.5


def test_save_writes_events_audio_and_manifest(tmp_path):
    rec = recorded_session(Clock())
    folder = rec.save(tmp_path)
    assert folder.name == f"{rec.started_at:%Y-%m-%d}_{rec.session.id}"
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for key in ("session_id", "lang", "channel", "started_at", "duration_s", "consent_text", "seal_sha256"):
        assert key in manifest
    assert manifest["right_first_answer"] == 0 and manifest["right_after_samjho"] == 0
    assert manifest["channel"] == "browser" and manifest["duration_s"] == 6.0
    assert manifest["consent_text"] == recording.CONSENT_TEXT
    lines = (folder / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x) for x in lines] == rec.events
    with wave.open(str(folder / "audio.wav")) as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getnframes() == 16000 * 6
    assert "9876543210" not in (folder / "events.jsonl").read_text(encoding="utf-8")


def test_nothing_saved_when_she_never_spoke(tmp_path):
    session = Session()
    rec = Recorder(session, "browser")
    for ev in session.start():
        rec.event(ev)
    assert rec.save(tmp_path) is None and list(tmp_path.iterdir()) == []


# ---- listing, path safety, status gate, API -------------------------------------------------------------
def test_status_replay_gate_needs_a_manifest(rdir):
    client = TestClient(app)
    assert client.get("/api/status").json()["replay"]["ready"] is False
    (rdir / "stray.json").write_text("{}")  # the old layout no longer counts
    (rdir / "README.md").write_text("x")
    assert client.get("/api/status").json()["replay"]["ready"] is False
    recorded_session(Clock()).save()
    assert client.get("/api/status").json()["replay"]["ready"] is True


def test_listing_events_and_audio_over_the_api(rdir):
    old = recorded_session(Clock())
    old.started_at = old.started_at.replace(year=2025)
    old.save()
    new = recorded_session(Clock())
    new.save()
    client = TestClient(app)
    listed = client.get("/api/replays").json()
    assert [m["session_id"] for m in listed] == [new.session.id, old.session.id]  # newest first
    rid = listed[0]["id"]
    events = client.get(f"/api/replays/{rid}/events").json()
    assert events[0]["t"] == 0.0 and any(e["type"] == "heard" for e in events)
    audio = client.get(f"/api/replays/{rid}/audio")
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/wav"
    assert audio.content[:4] == b"RIFF"


@pytest.mark.parametrize("rid", ["..", "...", "a b", "x%2F..%2F..%2Fapp", "%2e%2e", "nope"])
def test_replay_api_rejects_unknown_and_unsafe_ids(rdir, rid):
    recorded_session(Clock()).save()
    client = TestClient(app)
    assert client.get(f"/api/replays/{rid}/events").status_code == 404
    assert client.get(f"/api/replays/{rid}/audio").status_code == 404


def test_replay_file_is_path_safe(tmp_path):
    folder = recorded_session(Clock()).save(tmp_path)
    rid = folder.name
    assert recording.replay_file(rid, "audio.wav", tmp_path) == (folder / "audio.wav").resolve()
    assert recording.replay_file(rid, "../../app/main.py", tmp_path) is None
    assert recording.replay_file("../" + rid, "audio.wav", tmp_path) is None
    assert recording.replay_file(rid, "secret.txt", tmp_path) is None
    assert recording.replay_file("C:\\Windows", "audio.wav", tmp_path) is None
    assert recording.read_events("..", tmp_path) is None


# ---- wiring: the pipeline's Brain records, the phone keeps the choice ------------------------------------
def test_brain_records_every_event_it_sends():
    from app.voice import Brain

    session = Session()
    rec = Recorder(session, "phone")
    published = []
    brain = Brain(session, publish=published.append, recorder=rec)

    async def swallow(frame, direction=None):
        pass

    brain.push_frame = swallow
    asyncio.run(brain._emit(session.start()))
    assert [e["type"] for e in rec.events] == [e["type"] for e in published] == ["state", "say"]


def test_phone_call_carries_the_recording_choice(monkeypatch):
    from app import phone
    from app.limits import CallLimiter

    for k, v in {
        "SARVAM_API_KEY": "sk",
        "TWILIO_ACCOUNT_SID": "AC",
        "TWILIO_AUTH_TOKEN": "tok",
        "TWILIO_FROM_NUMBER": "+15550001111",
        "PUBLIC_BASE_URL": "https://demo.example.com",
        "CALLS_ENABLED": "true",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("JUDGE_TOKEN", raising=False)
    rest = SimpleNamespace(create=lambda **kw: SimpleNamespace(sid="CA" + "1" * 32))
    desk = phone.CallDesk(CallLimiter(), phone.WatchHub(), client_factory=lambda a, b: SimpleNamespace(calls=rest))
    monkeypatch.setattr(phone, "_desk", desk)
    r = TestClient(app).post("/api/call", json={"phone": "+919876543210", "consent": True, "record": True})
    assert r.status_code == 200
    assert [p.record for p in desk._pending.values()] == [True]
