"""Samjho web server: serves the one-screen UI and the API it talks to."""

import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import load_settings
from app.flow import Session

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
REPLAY_DIR = Path(__file__).resolve().parent.parent / "replays"
SESSION_TTL = 30 * 60
MAX_SESSIONS = 200

app = FastAPI(title="Samjho", docs_url=None, redoc_url=None)
_sessions: dict[str, tuple[float, Session]] = {}


def _prune() -> None:
    now = time.time()
    for sid in [sid for sid, (t, _) in _sessions.items() if now - t > SESSION_TTL]:
        del _sessions[sid]
    while len(_sessions) > MAX_SESSIONS:
        del _sessions[min(_sessions, key=lambda sid: _sessions[sid][0])]


class StartIn(BaseModel):
    lang: str = "hi"


class SayIn(BaseModel):
    session_id: str
    text: str


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/api/status")
def status() -> dict:
    result = load_settings().status()
    has_replay = REPLAY_DIR.is_dir() and any(REPLAY_DIR.glob("*.json"))
    result["replay"] = {"ready": has_replay, "reason": "" if has_replay else "No recorded test session added yet"}
    return result


@app.post("/api/text/start")
def text_start(body: StartIn) -> dict:
    _prune()
    session = Session(lang=body.lang)
    _sessions[session.id] = (time.time(), session)
    return {"session_id": session.id, "events": session.start()}


@app.post("/api/text/say")
def text_say(body: SayIn) -> dict:
    found = _sessions.get(body.session_id)
    if not found:
        raise HTTPException(404, "session expired, start again")
    session = found[1]
    _sessions[body.session_id] = (time.time(), session)
    return {"events": session.hear(body.text[:500]), "done": session.done}


@app.websocket("/ws/browser")
async def ws_browser(websocket: WebSocket, lang: str = "hi") -> None:
    """Browser voice: PCM16 16 kHz audio both ways, UI events as JSON. See app/voice.py."""
    await websocket.accept()
    key = load_settings().sarvam_api_key
    if not key:
        await websocket.send_json({"type": "case", "case": "KEY_NOT_SET", "detail": "SARVAM_API_KEY not set"})
        await websocket.close()
        return
    from app.voice import run_browser_session  # imported here so text mode starts without loading Pipecat

    await run_browser_session(websocket, lang, key)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
