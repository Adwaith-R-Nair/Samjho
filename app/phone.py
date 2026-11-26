"""Real phone calls: place a Twilio call whose audio streams to /ws/twilio, and let the browser watch it live.

Flow: POST /api/call -> checks (kill switch, keys, judge token, consent, number, limits) -> Twilio calls.create
with TwiML <Connect><Stream url="wss://HOST/ws/twilio"> carrying a one-time token -> the callee answers ->
Twilio opens /ws/twilio -> the token is claimed (once, within TOKEN_TTL) -> the phone pipeline runs the same
Session as text mode -> every UI event is published to the WatchHub under the call's watch id -> the browser that
asked for the call follows it on /ws/watch?id=...

Nothing here needs a key at import time. Numbers are never logged in full (+91XXXXXX1234) and never stored raw.
"""

import asyncio
import hmac
import os
import re
import secrets
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from urllib.parse import urlparse

from fastapi import Request, WebSocket
from loguru import logger

from app.config import load_settings
from app.limits import CallLimiter

PHONE_RE = re.compile(r"^\+91[6-9]\d{9}$")
CALL_TIME_LIMIT = 300  # seconds, Twilio hangs up after this; a full session with repairs can pass 4 minutes
RING_TIMEOUT = 30  # seconds the phone rings before Twilio gives up
TOKEN_TTL = 120  # seconds from placing the call to its stream connecting
HISTORY_MAX = 500


class CallRefused(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def valid_number(number: str) -> bool:
    return bool(PHONE_RE.fullmatch(number or ""))


def mask(number: str) -> str:
    number = number or ""
    return number[:3] + "X" * max(0, len(number) - 7) + number[-4:] if len(number) > 7 else "X" * len(number)


def mask_sid(sid: str) -> str:
    return f"{sid[:2]}...{sid[-4:]}" if sid and len(sid) > 6 else "..."


def stream_url(public_base_url: str) -> str:
    """https://host[/prefix] -> wss://host[/prefix]/ws/twilio (http gives ws, for local tests only)."""
    u = urlparse(public_base_url.strip().rstrip("/"))
    scheme = "ws" if u.scheme == "http" else "wss"
    return f"{scheme}://{u.netloc}{u.path}/ws/twilio"


def build_twiml(url: str, token: str) -> str:
    from twilio.twiml.voice_response import Connect, VoiceResponse

    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=url).parameter(name="t", value=token)
    response.append(connect)
    return str(response)


def client_ip(request: Request) -> str:
    """The caller's IP. Behind a local Cloudflare tunnel every request comes from loopback, so trust the
    tunnel's CF-Connecting-IP (or X-Forwarded-For) only then."""
    host = request.client.host if request.client else "unknown"
    if host in ("127.0.0.1", "::1", "localhost"):
        fwd = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "").split(",")[0]
        if fwd.strip():
            return fwd.strip()
    return host


def twilio_client(account_sid: str, auth_token: str):
    from twilio.rest import Client

    return Client(account_sid, auth_token)


# ---- watch hub: in-process pub/sub keyed by watch id -----------------------------------------------------
@dataclass
class _Channel:
    created: float
    history: list[dict] = field(default_factory=list)
    queues: set = field(default_factory=set)
    closed: bool = False


class WatchHub:
    """Every event of a call, kept for late watchers and pushed to live ones."""

    def __init__(self, ttl: float = 3600) -> None:
        self._ttl = ttl
        self._channels: dict[str, _Channel] = {}

    def open(self, wid: str) -> None:
        now = time.time()
        for old in [w for w, c in self._channels.items() if now - c.created > self._ttl]:
            self.close(old)
            del self._channels[old]
        self._channels[wid] = _Channel(now)

    def exists(self, wid: str) -> bool:
        return wid in self._channels

    def publish(self, wid: str, ev: dict) -> None:
        ch = self._channels.get(wid)
        if not ch or ch.closed:
            return
        if len(ch.history) < HISTORY_MAX:
            ch.history.append(ev)
        for q in ch.queues:
            q.put_nowait(ev)

    def close(self, wid: str) -> None:
        ch = self._channels.get(wid)
        if not ch or ch.closed:
            return
        ch.closed = True
        for q in ch.queues:
            q.put_nowait(None)

    async def subscribe(self, wid: str) -> AsyncIterator[dict]:
        ch = self._channels.get(wid)
        if not ch:
            return
        # Snapshot and register with no await in between, so no event is lost or repeated.
        backlog, q = list(ch.history), asyncio.Queue()
        if not ch.closed:
            ch.queues.add(q)
        try:
            for ev in backlog:
                yield ev
            if ch.closed:
                return
            while (ev := await q.get()) is not None:
                yield ev
        finally:
            ch.queues.discard(q)


# ---- call desk: places calls and hands their streams to the pipeline --------------------------------------
@dataclass
class Pending:
    watch_id: str
    lang: str
    reservation: str
    masked: str
    created: float
    call_sid: str = ""


class CallDesk:
    def __init__(
        self,
        limiter: CallLimiter,
        hub: WatchHub,
        client_factory: Callable = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.limiter = limiter
        self.hub = hub
        self._client_factory = client_factory
        self._clock = clock
        self._pending: dict[str, Pending] = {}

    async def place(self, number: str, consent: bool, lang: str, k: str, ip: str) -> dict:
        s = load_settings()
        if not s.calls_enabled:
            raise CallRefused(403, "Phone calls are paused by the owner. Typing and replay still work.")
        missing = [
            name
            for name, value in [
                ("SARVAM_API_KEY", s.sarvam_api_key),
                ("TWILIO_ACCOUNT_SID", s.twilio_account_sid),
                ("TWILIO_AUTH_TOKEN", s.twilio_auth_token),
                ("TWILIO_FROM_NUMBER", s.twilio_from_number),
                ("PUBLIC_BASE_URL", s.public_base_url),
            ]
            if not value
        ]
        if missing:
            raise CallRefused(503, "Phone calls are not set up: " + ", ".join(missing) + " not set.")
        if s.judge_token and not hmac.compare_digest((k or "").encode(), s.judge_token.encode()):
            raise CallRefused(403, "This link needs its access code to place calls. Typing and replay still work.")
        if consent is not True:
            raise CallRefused(400, "Please tick the box to agree to receive the demo call.")
        if not valid_number(number):
            raise CallRefused(400, "Enter an Indian mobile number as +91 followed by 10 digits.")
        rid, reason = self.limiter.reserve(number, ip)
        if not rid:
            logger.info(f"Call to {mask(number)} refused: {reason}")
            raise CallRefused(429, reason)

        token = secrets.token_urlsafe(24)
        wid = secrets.token_urlsafe(12)
        lang = lang if lang in ("hi", "en") else "hi"
        pending = Pending(wid, lang, rid, mask(number), self._clock())
        self._pending[token] = pending
        self.hub.open(wid)
        twiml = build_twiml(stream_url(s.public_base_url), token)
        factory = self._client_factory or twilio_client
        try:
            client = factory(s.twilio_account_sid, s.twilio_auth_token)
            call = await asyncio.to_thread(
                client.calls.create,
                to=number,
                from_=s.twilio_from_number,
                twiml=twiml,
                time_limit=CALL_TIME_LIMIT,
                timeout=RING_TIMEOUT,
            )
        except Exception as e:  # Twilio errors carry a readable message and never the credentials
            self._pending.pop(token, None)
            self.limiter.release(rid)
            self.hub.close(wid)
            reason = getattr(e, "msg", None) or e.__class__.__name__
            logger.warning(f"Twilio refused the call to {mask(number)}: {reason}")
            raise CallRefused(502, f"The call could not be placed: {reason}") from None
        pending.call_sid = getattr(call, "sid", "") or ""
        logger.info(f"Calling {mask(number)} ({mask_sid(pending.call_sid)}), lang {lang}")
        self.hub.publish(wid, {"type": "call", "status": "ringing", "to": pending.masked})
        asyncio.get_running_loop().call_later(TOKEN_TTL, self._expire, token)
        return {"ok": True, "watch_id": wid, "call_id": mask_sid(pending.call_sid), "to": pending.masked}

    def _expire(self, token: str) -> None:
        pending = self._pending.pop(token, None)
        if pending:  # never answered (or the stream never reached us)
            self.limiter.release(pending.reservation)
            self.hub.publish(pending.watch_id, {"type": "call", "status": "not_answered"})
            self.hub.close(pending.watch_id)

    def claim(self, token: str, call_sid: str | None = None) -> Pending | None:
        """One use per token, within TOKEN_TTL, and for the call it was issued to."""
        pending = self._pending.pop(token or "", None)
        if not pending:
            return None
        if self._clock() - pending.created > TOKEN_TTL:
            self._expire_now(pending)
            return None
        if pending.call_sid and call_sid and not hmac.compare_digest(pending.call_sid, call_sid):
            self._expire_now(pending)
            return None
        return pending

    def _expire_now(self, pending: Pending) -> None:
        self.limiter.release(pending.reservation)
        self.hub.close(pending.watch_id)

    async def run_stream(self, websocket: WebSocket) -> None:
        """Handles Twilio's Media Stream WebSocket (already accepted)."""
        from pipecat.runner.utils import parse_telephony_websocket

        try:
            transport_type, call_data = await parse_telephony_websocket(websocket)
        except Exception as e:
            logger.warning(f"Twilio stream: bad handshake ({e.__class__.__name__})")
            await websocket.close(code=1008)
            return
        body = call_data.get("body") or {}
        call_sid = call_data.get("call_id") or ""
        pending = self.claim(body.get("t", ""), call_sid) if transport_type == "twilio" else None
        if not pending:
            logger.warning(f"Twilio stream rejected: unknown or used token ({mask_sid(call_sid)})")
            await websocket.close(code=1008)
            return

        s = load_settings()
        wid = pending.watch_id
        self.limiter.hold(pending.reservation, CALL_TIME_LIMIT + 60)
        self.hub.publish(wid, {"type": "call", "status": "connected"})
        try:
            from app.voice import run_phone_session

            await run_phone_session(
                websocket,
                lang=pending.lang,
                stream_sid=call_data.get("stream_id") or "",
                call_sid=call_sid,
                sarvam_key=s.sarvam_api_key,
                account_sid=s.twilio_account_sid,
                auth_token=s.twilio_auth_token,
                publish=lambda ev: self.hub.publish(wid, ev),
                time_limit=CALL_TIME_LIMIT,
            )
        except Exception as e:
            logger.exception(f"Phone session {mask_sid(call_sid)} failed: {e.__class__.__name__}")
        finally:
            self.limiter.release(pending.reservation)
            self.hub.publish(wid, {"type": "call", "status": "ended"})
            self.hub.close(wid)


_desk: CallDesk | None = None


def owner_numbers() -> list[str]:
    return [os.getenv(n, "").strip() for n in ("MY_PHONE_NUMBER", "SUPERVISOR_PHONE_NUMBER")]


def desk() -> CallDesk:
    global _desk
    if _desk is None:
        _desk = CallDesk(CallLimiter(owner_numbers=owner_numbers()), WatchHub())
    return _desk
