"""Browser voice channel: the same Session as text mode, spoken over a WebSocket with Pipecat.

Pipeline (one per browser tab):

    browser mic -> transport.input -> EchoGate -> Sarvam STT (saaras:v4, codemix)
        -> user aggregator (Silero VAD, speech-timeout turn end, half-duplex mute)
        -> Brain (Session.hear, no LLM) -> Sarvam TTS (bulbul:v4-flash) -> transport.output -> browser

Half duplex: laptop speakers leak the bot's voice into the mic and a plain WebSocket has no browser echo
cancellation, so the user is not heard while the bot speaks. Three layers enforce it: the browser sends
silence while it is playing, EchoGate zeroes mic audio while the bot speaks (plus a short tail), and
AlwaysUserMuteStrategy drops any turn frames the aggregator sees in that window.

Nothing here needs a key at import time; services are built per session in build_worker().
"""

import time

from fastapi import WebSocket
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    EndWorkerFrame,
    Frame,
    InputAudioRawFrame,
    LLMContextFrame,
    LLMContextUserTurnFrame,
    OutputTransportMessageFrame,
    OutputTransportMessageUrgentFrame,
    StartFrame,
    TTSSpeakFrame,
)
from pipecat.observers.user_bot_latency_observer import UserBotLatencyObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transcriptions.language import Language
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from pipecat.turns.user_mute import AlwaysUserMuteStrategy
from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.workers.runner import WorkerRunner

from app.browser_serializer import WIRE_RATE, BrowserSerializer
from app.flow import Session

STT_MODEL = "saaras:v4"
TTS_MODEL = "bulbul:v4-flash"
# Female voices accepted by bulbul:v4-flash (checked against the live API, 27 Nov 2026).
VOICES = {"hi": "kavya_hi_conversational", "en": "ishita_en_customer"}
LANGS = {"hi": Language.HI, "en": Language.EN}
# Recognition hints for the words a borrower uses about money.
KEYTERMS = ["हज़ार", "किस्त", "बीमा", "हफ्ते", "hazaar", "kisht", "bima", "hafta", "EMI"]

# Silence before a turn ends. Answers with numbers get longer ("pachaas ... hazaar") so they are not cut;
# yes/no answers end faster.
NUMBER_TIMEOUT = 0.9
YES_NO_TIMEOUT = 0.6
YES_NO_STATES = {"consent", "private", "final_consent"}

# Mic audio stays muted this long after the bot stops, so the tail of its voice is not heard as the user.
ECHO_TAIL_SECS = 0.25
SESSION_TIMEOUT_SECS = 300
MAX_SESSIONS = 4

_active = 0


class StateSpeechTimeout(SpeechTimeoutUserTurnStopStrategy):
    """Speech-timeout turn end whose timeout follows the Session state, read when each pause begins."""

    def __init__(self, session: Session) -> None:
        self._session = session
        super().__init__(user_speech_timeout=NUMBER_TIMEOUT)

    @property
    def _user_speech_timeout(self) -> float:  # read by the base class when it arms its timer
        return YES_NO_TIMEOUT if self._session.state in YES_NO_STATES else NUMBER_TIMEOUT

    @_user_speech_timeout.setter
    def _user_speech_timeout(self, value: float) -> None:
        pass  # fixed by state, not by the constructor


class EchoGate(FrameProcessor):
    """Replaces mic audio with silence while the bot speaks and for a short tail after."""

    def __init__(self, tail_secs: float = ECHO_TAIL_SECS) -> None:
        super().__init__()
        self._tail = tail_secs
        self._bot_speaking = False
        self._open_at = 0.0

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
            self._open_at = time.monotonic() + self._tail
        elif isinstance(frame, InputAudioRawFrame) and (self._bot_speaking or time.monotonic() < self._open_at):
            frame = InputAudioRawFrame(
                audio=bytes(len(frame.audio)), sample_rate=frame.sample_rate, num_channels=frame.num_channels
            )
        await self.push_frame(frame, direction)


class Brain(FrameProcessor):
    """Takes each finished user turn, runs it through the Session, sends the events and speaks the replies.

    The user aggregator broadcasts LLMContextUserTurnFrame (the turn's text) and then pushes LLMContextFrame
    to run an LLM. There is no LLM here: the text goes to Session.hear() and the context frame is dropped.
    """

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.turn = 0
        self._ending = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            await self.push_frame(frame, direction)
            await self._emit(self.session.start())
        elif isinstance(frame, LLMContextUserTurnFrame):
            if direction == FrameDirection.DOWNSTREAM and not frame.speculation:
                await self._on_turn(frame.text)
        elif isinstance(frame, LLMContextFrame):
            pass
        else:
            await self.push_frame(frame, direction)

    async def _on_turn(self, text: str) -> None:
        if self.session.done or self._ending:
            return
        self.turn += 1
        logger.info(f"Samjho voice turn {self.turn} [{self.session.state}]: {text!r}")
        await self._emit(self.session.hear(text))

    async def _emit(self, events: list[dict]) -> None:
        says = []
        for ev in events:
            # Not urgent on purpose: the TTS queues it behind any audio still playing, so events stay in order.
            await self.push_frame(OutputTransportMessageFrame(message=ev))
            if ev["type"] == "say" and ev["text"].strip():
                says.append(ev["text"].strip())
        if says:
            # One utterance per reply: separate TTS contexts make the bot "stop speaking" between lines,
            # which would unmute the user mid-reply and let a stray word cut the rest of the explanation.
            await self.push_frame(TTSSpeakFrame(" ".join(says), append_to_context=False))
        if self.session.done and not self._ending:
            self._ending = True
            # Downstream, so the goodbye is played out before the pipeline ends and the socket closes.
            await self.push_frame(EndWorkerFrame(reason="session complete"))


def build_worker(websocket: WebSocket, lang: str, api_key: str) -> tuple[PipelineWorker, Brain]:
    lang = lang if lang in VOICES else "hi"
    session = Session(lang=lang)

    transport = FastAPIWebsocketTransport(
        websocket,
        FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            serializer=BrowserSerializer(),
            session_timeout=SESSION_TIMEOUT_SECS,
        ),
    )
    stt = SarvamSTTService(
        api_key=api_key,
        mode="codemix",
        sample_rate=WIRE_RATE,
        keyterms=KEYTERMS,
        settings=SarvamSTTService.Settings(model=STT_MODEL, language=LANGS[lang]),
    )
    tts = SarvamTTSService(
        api_key=api_key,
        sample_rate=WIRE_RATE,
        settings=SarvamTTSService.Settings(model=TTS_MODEL, voice=VOICES[lang], language=LANGS[lang], pace=1.0),
    )
    vad = SileroVADAnalyzer(
        sample_rate=WIRE_RATE, params=VADParams(confidence=0.7, start_secs=0.2, stop_secs=0.2, min_volume=0.6)
    )
    aggregators = LLMContextAggregatorPair(
        LLMContext(),
        user_params=LLMUserAggregatorParams(
            vad_analyzer=vad,
            user_turn_strategies=UserTurnStrategies(stop=[StateSpeechTimeout(session)]),
            user_mute_strategies=[AlwaysUserMuteStrategy()],
            empty_user_turn=None,
        ),
    )
    brain = Brain(session)

    pipeline = Pipeline([transport.input(), EchoGate(), stt, aggregators.user(), brain, tts, transport.output()])

    latency = UserBotLatencyObserver()
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=WIRE_RATE, audio_out_sample_rate=WIRE_RATE, enable_metrics=True
        ),
        observers=[latency],
        enable_rtvi=False,
    )

    @latency.event_handler("on_latency_measured")
    async def on_latency(_observer, seconds: float) -> None:
        ms = round(seconds * 1000)
        logger.info(f"Samjho voice turn {brain.turn}: {ms} ms end of speech to first bot audio")
        await worker.queue_frame(
            OutputTransportMessageUrgentFrame(message={"type": "latency", "turn": brain.turn, "ms": ms})
        )

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(_transport, _ws) -> None:
        await worker.cancel(reason="browser disconnected")

    @transport.event_handler("on_session_timeout")
    async def on_timeout(_transport, _ws) -> None:
        await worker.cancel(reason="session timeout")

    return worker, brain


async def run_browser_session(websocket: WebSocket, lang: str, api_key: str) -> None:
    """Runs one spoken session on an accepted WebSocket until it ends or the browser leaves."""
    global _active
    if _active >= MAX_SESSIONS:
        await websocket.send_json({"type": "case", "case": "BUSY", "detail": "Too many live sessions, try again"})
        await websocket.close()
        return
    _active += 1
    try:
        worker, _ = build_worker(websocket, lang, api_key)
        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(worker)
        await runner.run()
    finally:
        _active -= 1
