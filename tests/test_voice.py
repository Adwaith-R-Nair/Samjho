"""Browser voice channel checks that need no keys and no network (the live test is scripts/voice_smoke.py)."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.browser_serializer import BrowserSerializer
from app.flow import Session
from app.main import app


def run(coro):
    return asyncio.run(coro)


def test_serializer_audio_in_is_pcm16_at_16k():
    pcm = bytes(range(256)) * 5  # 1280 bytes = 40 ms
    frame = run(BrowserSerializer().deserialize(pcm))
    assert type(frame).__name__ == "InputAudioRawFrame"
    assert frame.audio == pcm and frame.sample_rate == 16000 and frame.num_channels == 1


def test_serializer_ignores_text_and_odd_bytes_from_browser():
    ser = BrowserSerializer()
    assert run(ser.deserialize('{"type": "hello"}')) is None
    assert run(ser.deserialize(b"\x01")) is None
    assert len(run(ser.deserialize(b"\x01\x02\x03")).audio) == 2


def test_serializer_audio_out_and_json_events():
    from pipecat.frames.frames import (
        OutputAudioRawFrame,
        OutputTransportMessageFrame,
        OutputTransportMessageUrgentFrame,
        StartFrame,
    )

    ser = BrowserSerializer()
    pcm = b"\x10\x00\x20\x00" * 160
    assert run(ser.serialize(OutputAudioRawFrame(audio=pcm, sample_rate=16000, num_channels=1))) == pcm

    ev = {"type": "say", "text": "नमस्ते", "hi": "नमस्ते", "en": "Hello"}
    out = run(ser.serialize(OutputTransportMessageFrame(message=ev)))
    assert isinstance(out, str) and json.loads(out) == ev and "नमस्ते" in out
    lat = {"type": "latency", "turn": 1, "ms": 900}
    assert json.loads(run(ser.serialize(OutputTransportMessageUrgentFrame(message=lat)))) == lat

    assert run(ser.serialize(OutputTransportMessageFrame(message={"label": "rtvi-ai", "type": "x"}))) is None
    assert run(ser.serialize(StartFrame())) is None


def test_ws_browser_refuses_politely_without_key(monkeypatch):
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    with TestClient(app).websocket_connect("/ws/browser?lang=hi") as ws:
        assert ws.receive_json() == {"type": "case", "case": "KEY_NOT_SET", "detail": "SARVAM_API_KEY not set"}
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_turn_timeout_follows_session_state():
    from app.voice import NUMBER_TIMEOUT, YES_NO_TIMEOUT, StateSpeechTimeout

    session = Session()
    strategy = StateSpeechTimeout(session)
    assert session.state == "consent" and strategy._user_speech_timeout == YES_NO_TIMEOUT
    session.state = "teachback"
    assert strategy._user_speech_timeout == NUMBER_TIMEOUT
    session.state = "final_consent"
    assert strategy._user_speech_timeout == YES_NO_TIMEOUT


def test_brain_sends_events_speaks_one_utterance_and_ends_when_done():
    from pipecat.frames.frames import EndWorkerFrame, OutputTransportMessageFrame, TTSSpeakFrame

    from app.voice import Brain

    brain = Brain(Session(lang="hi"))
    pushed = []

    async def capture(frame, direction=None):
        pushed.append(frame)

    brain.push_frame = capture

    run(brain._emit(brain.session.start()))
    says = [f for f in pushed if isinstance(f, TTSSpeakFrame)]
    events = [f.message for f in pushed if isinstance(f, OutputTransportMessageFrame)]
    assert len(says) == 1 and "समझो" in says[0].text
    assert [e["type"] for e in events] == ["state", "say"]

    pushed.clear()
    run(brain._on_turn("nahi, abhi nahi"))
    kinds = [type(f).__name__ for f in pushed]
    events = [f.message for f in pushed if isinstance(f, OutputTransportMessageFrame)]
    assert events[0] == {"type": "heard", "text": "nahi, abhi nahi"}
    assert any(e["type"] == "record" for e in events)
    assert kinds.count("TTSSpeakFrame") == 1 and isinstance(pushed[-1], EndWorkerFrame)
    assert brain.turn == 1 and brain.session.done

    pushed.clear()
    run(brain._on_turn("haan"))  # nothing after the session is sealed
    assert pushed == []


def test_a_latency_reading_older_than_the_turn_is_dropped():
    from app.voice import plausible_latency

    # First real call: the clock started at "hello" during the greeting and read 16.4 s, though the
    # reply came 0.28 s after the turn was handed over.
    assert not plausible_latency(16.393, last_turn_at=100.0, now=100.28)
    assert plausible_latency(1.354, last_turn_at=100.0, now=100.25)
    assert not plausible_latency(0.5, last_turn_at=None, now=5.0)  # greeting, no turn yet
