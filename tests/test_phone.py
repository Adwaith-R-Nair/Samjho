"""Phone channel checks with no keys and no network: Twilio is a fake."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import phone
from app.limits import CallLimiter
from app.main import app

GOOD = "+919876543210"
OWNER = "+919000000001"
SID = "CA" + "0" * 28 + "4321"


class Clock:
    def __init__(self) -> None:
        self.t = 1_000_000.0

    def __call__(self) -> float:
        return self.t


class FakeTwilio:
    def __init__(self, fail: Exception | None = None) -> None:
        self.made: list[dict] = []
        self.fail = fail
        self.calls = self

    def __call__(self, account_sid, auth_token):  # used as the client factory
        assert account_sid == "AC_test" and auth_token == "tok_test"
        return self

    def create(self, **kw):
        if self.fail:
            raise self.fail
        self.made.append(kw)
        return SimpleNamespace(sid=SID)


@pytest.fixture
def env(monkeypatch):
    values = {
        "SARVAM_API_KEY": "sk_test",
        "TWILIO_ACCOUNT_SID": "AC_test",
        "TWILIO_AUTH_TOKEN": "tok_test",
        "TWILIO_FROM_NUMBER": "+15550001111",
        "PUBLIC_BASE_URL": "https://demo.example.com",
        "CALLS_ENABLED": "true",
    }
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("JUDGE_TOKEN", raising=False)
    return monkeypatch


@pytest.fixture
def fake(monkeypatch):
    twilio = FakeTwilio()
    desk = phone.CallDesk(CallLimiter(owner_numbers=[OWNER]), phone.WatchHub(), client_factory=twilio)
    monkeypatch.setattr(phone, "_desk", desk)
    return SimpleNamespace(twilio=twilio, desk=desk)


def call(client, **body):
    payload = {"phone": GOOD, "consent": True, "lang": "hi", "k": ""} | body
    return client.post("/api/call", json=payload)


# ---- numbers, masking, TwiML ----------------------------------------------------------------------------
@pytest.mark.parametrize("n", ["+919876543210", "+916000000000", "+917123456789", "+918999999999"])
def test_valid_indian_mobiles(n):
    assert phone.valid_number(n)


@pytest.mark.parametrize(
    "n", ["9876543210", "+91987654321", "+9198765432101", "+915876543210", "+14155550123", "+91 9876543210", ""]
)
def test_invalid_numbers(n):
    assert not phone.valid_number(n)


def test_masking_never_shows_the_whole_number():
    assert phone.mask(GOOD) == "+91XXXXXX3210"
    assert phone.mask_sid(SID) == "CA...4321"


def test_twiml_streams_to_our_socket_with_the_token():
    url = phone.stream_url("https://demo.example.com/")
    assert url == "wss://demo.example.com/ws/twilio"
    xml = phone.build_twiml(url, "tok&en")
    assert '<Connect><Stream url="wss://demo.example.com/ws/twilio">' in xml
    assert '<Parameter name="t" value="tok&amp;en" />' in xml


# ---- limits ---------------------------------------------------------------------------------------------
def test_number_cooldown_and_daily_cap():
    clock = Clock()
    lim = CallLimiter(clock=clock, ip_per_hour=100, max_concurrent=100)
    rid, _ = lim.reserve(GOOD, "1.1.1.1")
    assert rid
    rid2, why = lim.reserve(GOOD, "2.2.2.2")
    assert rid2 is None and "recently" in why
    clock.t += 31 * 60
    assert lim.reserve(GOOD, "2.2.2.2")[0]
    clock.t += 31 * 60
    assert lim.reserve(GOOD, "3.3.3.3")[0]
    clock.t += 31 * 60
    rid4, why = lim.reserve(GOOD, "4.4.4.4")
    assert rid4 is None and "today" in why
    clock.t += 24 * 3600
    assert lim.reserve(GOOD, "4.4.4.4")[0]


def test_per_ip_limit():
    clock = Clock()
    lim = CallLimiter(clock=clock, max_concurrent=100)
    for i in range(3):
        assert lim.reserve(f"+91987654321{i}", "9.9.9.9")[0]
    rid, why = lim.reserve("+919876543219", "9.9.9.9")
    assert rid is None and "network" in why
    assert lim.reserve("+919876543219", "8.8.8.8")[0]
    clock.t += 3601
    assert lim.reserve("+919876543218", "9.9.9.9")[0]


def test_global_concurrency_release_and_ring_expiry():
    clock = Clock()
    lim = CallLimiter(clock=clock)
    a = lim.reserve("+919876543210", "1.1.1.1")[0]
    lim.reserve("+919876543211", "1.1.1.2")
    rid, why = lim.reserve("+919876543212", "1.1.1.3")
    assert rid is None and "already running" in why
    lim.release(a)
    assert lim.reserve("+919876543212", "1.1.1.3")[0]
    assert lim.active() == 2
    clock.t += 91  # nobody answered: ring holds expire
    assert lim.active() == 0


def test_answered_call_holds_its_slot():
    clock = Clock()
    lim = CallLimiter(clock=clock, max_concurrent=1)
    rid = lim.reserve(GOOD, "1.1.1.1")[0]
    lim.hold(rid, 300)
    clock.t += 200
    assert lim.reserve("+919876543211", "1.1.1.2")[0] is None
    lim.release(rid)
    assert lim.reserve("+919876543211", "1.1.1.2")[0]


def test_global_daily_cap():
    clock = Clock()
    lim = CallLimiter(clock=clock, max_concurrent=1000, ip_per_hour=1000, global_per_day=40)
    for i in range(40):
        assert lim.reserve(f"+9198765{i:05d}", "1.1.1.1")[0]
    rid, why = lim.reserve("+919999999999", "2.2.2.2")
    assert rid is None and "today" in why


def test_owner_numbers_skip_cooldowns_but_not_global_limits():
    clock = Clock()
    lim = CallLimiter(owner_numbers=[OWNER, ""], clock=clock, max_concurrent=100)
    for _ in range(6):
        assert lim.reserve(OWNER, "1.1.1.1")[0]
    lim2 = CallLimiter(owner_numbers=[OWNER], clock=clock, max_concurrent=1)
    lim2.reserve(GOOD, "1.1.1.1")
    assert lim2.reserve(OWNER, "1.1.1.1")[0] is None


def test_numbers_are_stored_only_as_salted_hashes():
    lim = CallLimiter()
    lim.reserve(GOOD, "1.1.1.1")
    assert GOOD not in repr(lim.__dict__)
    assert CallLimiter().key(GOOD) != lim.key(GOOD)  # salt differs per instance


# ---- /api/call ------------------------------------------------------------------------------------------
def test_call_refused_cleanly_without_twilio_keys(env, fake):
    for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER", "PUBLIC_BASE_URL"):
        env.delenv(k, raising=False)
    r = call(TestClient(app))
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert "TWILIO_ACCOUNT_SID" in detail and "PUBLIC_BASE_URL" in detail and "sk_test" not in detail
    assert fake.twilio.made == []


def test_kill_switch_is_read_per_request(env, fake):
    client = TestClient(app)
    env.setenv("CALLS_ENABLED", "false")
    r = call(client)
    assert r.status_code == 403 and "paused" in r.json()["detail"]
    env.setenv("CALLS_ENABLED", "true")
    assert call(client).status_code == 200


def test_judge_token_checked_when_set(env, fake):
    env.setenv("JUDGE_TOKEN", "letmein")
    client = TestClient(app)
    assert call(client, k="wrong").status_code == 403
    assert call(client, k="letmein").status_code == 200


def test_consent_and_number_are_required(env, fake):
    client = TestClient(app)
    assert call(client, consent=False).status_code == 400
    assert call(client, phone="+14155550123").status_code == 400
    assert fake.twilio.made == []


def test_call_placed_with_twiml_limits_and_watch_id(env, fake):
    r = call(TestClient(app), phone="+91 98765 43210", lang="en")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["call_id"] == "CA...4321" and body["to"] == "+91XXXXXX3210"
    (made,) = fake.twilio.made
    assert made["to"] == GOOD and made["from_"] == "+15550001111"
    assert made["time_limit"] == 300 and made["timeout"] == 30
    assert 'url="wss://demo.example.com/ws/twilio"' in made["twiml"]
    (token,) = list(fake.desk._pending)
    assert f'value="{token}"' in made["twiml"]
    assert fake.desk._pending[token].lang == "en"
    assert fake.desk.hub._channels[body["watch_id"]].history[0]["status"] == "ringing"


def test_twilio_error_releases_the_slot(env, fake):
    fake.twilio.fail = RuntimeError("boom")
    r = call(TestClient(app))
    assert r.status_code == 502 and "could not be placed" in r.json()["detail"]
    assert fake.desk.limiter.active() == 0 and fake.desk._pending == {}


def test_rate_limit_reported_as_429(env, fake):
    client = TestClient(app)
    assert call(client).status_code == 200
    r = call(client)
    assert r.status_code == 429 and "recently" in r.json()["detail"]


# ---- one-time token -------------------------------------------------------------------------------------
def _pending(desk, token="tok", sid=SID, created=None):
    rid = desk.limiter.reserve(GOOD, "1.1.1.1")[0]
    desk.hub.open("w1")
    desk._pending[token] = phone.Pending("w1", "hi", rid, "+91XXXXXX3210", created or desk._clock(), sid)


def test_token_claimed_once_for_its_own_call():
    desk = phone.CallDesk(CallLimiter(), phone.WatchHub())
    _pending(desk)
    assert desk.claim("nope", SID) is None
    assert desk.claim("tok", SID).watch_id == "w1"
    assert desk.claim("tok", SID) is None  # single use

    _pending(desk, token="tok2")
    assert desk.claim("tok2", "CA_other_call") is None
    assert desk.limiter.active() == 1  # the first claim still holds its call


def test_expired_token_rejected():
    clock = Clock()
    desk = phone.CallDesk(CallLimiter(clock=clock), phone.WatchHub(), clock=clock)
    _pending(desk)
    clock.t += phone.TOKEN_TTL + 1
    assert desk.claim("tok", SID) is None


def test_twilio_socket_rejects_a_bad_token(fake):
    _pending(fake.desk)
    client = TestClient(app)
    with client.websocket_connect("/ws/twilio") as ws:
        ws.send_text(json.dumps({"event": "connected", "protocol": "Call", "version": "1.0.0"}))
        ws.send_text(
            json.dumps(
                {
                    "event": "start",
                    "streamSid": "MZ1",
                    "start": {"streamSid": "MZ1", "callSid": SID, "customParameters": {"t": "forged"}},
                }
            )
        )
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_text()
        assert closed.value.code == 1008
    assert "tok" in fake.desk._pending  # the real token is untouched


# ---- watch hub ------------------------------------------------------------------------------------------
def test_hub_gives_late_watchers_the_backlog_then_live_events():
    async def scenario():
        hub = phone.WatchHub()
        hub.open("w")
        hub.publish("w", {"type": "say", "text": "a"})
        got = []

        async def watcher():
            async for ev in hub.subscribe("w"):
                got.append(ev["text"])

        task = asyncio.create_task(watcher())
        await asyncio.sleep(0)
        hub.publish("w", {"type": "heard", "text": "b"})
        hub.close("w")
        hub.publish("w", {"type": "say", "text": "after close"})
        await asyncio.wait_for(task, 1)
        return got

    assert asyncio.run(scenario()) == ["a", "b"]


def test_watch_socket_streams_a_call(fake):
    hub = fake.desk.hub
    hub.open("w9")
    hub.publish("w9", {"type": "call", "status": "connected"})
    hub.publish("w9", {"type": "heard", "text": "haan"})
    hub.close("w9")
    with TestClient(app).websocket_connect("/ws/watch?id=w9") as ws:
        assert ws.receive_json() == {"type": "call", "status": "connected"}
        assert ws.receive_json() == {"type": "heard", "text": "haan"}
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_watch_socket_unknown_call(fake):
    with TestClient(app).websocket_connect("/ws/watch?id=missing") as ws:
        assert ws.receive_json()["case"] == "WATCH_UNKNOWN"


# ---- phone pipeline pieces (app/voice.py) ---------------------------------------------------------------
def test_brain_publishes_to_the_hub_and_flags_amount_replies():
    from pipecat.frames.frames import OutputTransportMessageFrame, TTSSpeakFrame

    from app.flow import Session
    from app.voice import Brain

    published = []
    brain = Brain(Session(lang="hi"), publish=published.append)
    pushed = []

    async def capture(frame, direction=None):
        pushed.append(frame)

    brain.push_frame = capture
    asyncio.run(brain._emit(brain.session.start()))
    assert [e["type"] for e in published] == ["state", "say"]
    assert not any(isinstance(f, OutputTransportMessageFrame) for f in pushed)  # never sent to Twilio
    assert brain.critical is False  # the intro has no amounts: the caller may interrupt it

    asyncio.run(brain._on_turn("haan ji"))
    assert any(isinstance(f, TTSSpeakFrame) for f in pushed)
    assert brain.critical is True  # the explanation states amounts: the caller is muted while it plays


def test_critical_readout_mute_and_quiet_vad_start():
    from pipecat.frames.frames import BotStartedSpeakingFrame, BotStoppedSpeakingFrame, VADUserStartedSpeakingFrame

    from app.voice import CriticalReadoutMute, QuietVADStart

    brain = SimpleNamespace(critical=True)
    mute = CriticalReadoutMute(brain)
    assert asyncio.run(mute.process_frame(BotStartedSpeakingFrame())) is True
    brain.critical = False
    assert asyncio.run(mute.process_frame(VADUserStartedSpeakingFrame())) is False
    assert asyncio.run(mute.process_frame(BotStoppedSpeakingFrame())) is False

    start = QuietVADStart()
    started = []

    async def report(**kw):
        started.append(True)

    start.report_user_turn_started = report
    asyncio.run(start.process_frame(BotStartedSpeakingFrame()))
    asyncio.run(start.process_frame(VADUserStartedSpeakingFrame()))
    assert started == []  # while the bot speaks, words decide (MinWords), not voice activity
    asyncio.run(start.process_frame(BotStoppedSpeakingFrame()))
    asyncio.run(start.process_frame(VADUserStartedSpeakingFrame()))
    assert started == [True]


def test_phone_pipeline_builds_offline_at_8k():
    from pipecat.serializers.twilio import TwilioFrameSerializer

    from app.flow import Session
    from app.voice import PHONE, build_worker

    ser = TwilioFrameSerializer(
        "MZ1",
        call_sid=SID,
        account_sid="AC_test",
        auth_token="tok_test",
        params=TwilioFrameSerializer.InputParams(audio_in_sample_rate=8000, audio_out_sample_rate=8000),
    )
    ws = SimpleNamespace(headers={}, client_state=None, application_state=None)
    worker, brain = build_worker(ws, Session(), PHONE, ser, "sk_test", publish=lambda ev: None)
    assert PHONE.sample_rate == 8000 and not PHONE.half_duplex
    assert brain.session.state == "consent" and worker is not None
    with pytest.raises(ValueError):  # auto hang-up needs Twilio credentials: built only inside the call
        TwilioFrameSerializer("MZ1")


def test_refusals_offer_replay_only_when_one_exists(env, fake, tmp_path):
    env.setenv("SAMJHO_REPLAY_DIR", str(tmp_path))
    env.setenv("CALLS_ENABLED", "false")
    client = TestClient(app)
    detail = call(client).json()["detail"]
    assert detail.endswith("Typing still works.") and "replay" not in detail
    (tmp_path / "2026-11-28_abc").mkdir()
    (tmp_path / "2026-11-28_abc" / "manifest.json").write_text("{}")
    assert call(client).json()["detail"].endswith("Typing and replay still work.")
