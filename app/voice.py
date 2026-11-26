"""Spoken channels: the same Session as text mode, run by one Pipecat pipeline with two profiles.

    transport.input -> EchoGate -> Sarvam STT (saaras:v4, codemix)
        -> user aggregator (Silero VAD, speech-timeout turn end, profile's start and mute strategies)
        -> Brain (Session.hear, no LLM) -> Sarvam TTS (bulbul:v4-flash) -> transport.output

Browser (16 kHz, half duplex): laptop speakers leak the bot's voice into the mic and a plain WebSocket has no
echo cancellation, so the user is not heard while the bot speaks. The browser sends silence while it plays,
EchoGate zeroes mic audio while the bot speaks (plus a short tail), and AlwaysUserMuteStrategy drops turn frames
in that window. UI events go to the browser on the same socket as JSON.

Phone (8 kHz, Twilio Media Streams, barge-in): the handset cancels its own echo, so the caller may interrupt.
While the bot speaks, a turn starts only from a transcript of at least two words (so "haan" or "hmm" does not
cut it off), and the caller is muted outright (EchoGate and CriticalReadoutMute) while a reply that states
amounts is read out. UI events go to the watch hub (app/phone.py), never to Twilio.

Nothing here needs a key at import time; services are built per session.
"""

import asyncio
import inspect
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

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
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.serializers.base_serializer import FrameSerializer
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transcriptions.language import Language
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from pipecat.turns.user_mute import AlwaysUserMuteStrategy, BaseUserMuteStrategy
from pipecat.turns.user_start import MinWordsUserTurnStartStrategy, VADUserTurnStartStrategy
from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.workers.runner import WorkerRunner

from app.browser_serializer import WIRE_RATE, BrowserSerializer
from app.flow import Session
from app.recording import Recorder

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
# Words needed to interrupt the bot on the phone.
BARGE_IN_MIN_WORDS = 2
# A reply that states an amount ("... रुपये", "Rs 1,095", digits) is read without interruption.
_AMOUNT = re.compile(r"\d|रुपये|रुपए|\bRs\b")

_active = 0

Publish = Callable[[dict], Awaitable[None] | None]


@dataclass(frozen=True)
class Profile:
    name: str
    sample_rate: int
    half_duplex: bool


BROWSER = Profile("browser", WIRE_RATE, True)
PHONE = Profile("phone", 8000, False)


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


class QuietVADStart(VADUserTurnStartStrategy):
    """Starts a turn on voice activity only while the bot is silent; while it speaks, words decide (MinWords)."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._bot_speaking = False

    async def process_frame(self, frame: Frame) -> None:
        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
        elif not self._bot_speaking:
            await super().process_frame(frame)


class CriticalReadoutMute(BaseUserMuteStrategy):
    """Mutes the caller while the bot reads a reply that states amounts (Brain.critical)."""

    def __init__(self, brain: "Brain") -> None:
        super().__init__()
        self._brain = brain
        self._bot_speaking = False

    async def process_frame(self, frame: Frame) -> bool:
        await super().process_frame(frame)
        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
        return self._bot_speaking and self._brain.critical


class EchoGate(FrameProcessor):
    """Replaces mic audio with silence while the bot speaks and for a short tail after.

    With `only_if`, it gates only while that returns True (phone: replies that state amounts), so muted speech
    never reaches the STT buffer and cannot leak into the next turn's transcript.
    """

    def __init__(self, tail_secs: float = ECHO_TAIL_SECS, only_if: Callable[[], bool] | None = None) -> None:
        super().__init__()
        self._tail = tail_secs
        self._only_if = only_if
        self._bot_speaking = False
        self._open_at = 0.0

    def _closed(self) -> bool:
        if self._only_if is not None and not self._only_if():
            return False
        return self._bot_speaking or time.monotonic() < self._open_at

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
            self._open_at = time.monotonic() + self._tail
        elif isinstance(frame, InputAudioRawFrame) and self._closed():
            frame = InputAudioRawFrame(
                audio=bytes(len(frame.audio)), sample_rate=frame.sample_rate, num_channels=frame.num_channels
            )
        await self.push_frame(frame, direction)


class Brain(FrameProcessor):
    """Takes each finished user turn, runs it through the Session, sends the events and speaks the replies.

    The user aggregator broadcasts LLMContextUserTurnFrame (the turn's text) and then pushes LLMContextFrame
    to run an LLM. There is no LLM here: the text goes to Session.hear() and the context frame is dropped.

    Events go to `publish` when given (phone: the watch hub), otherwise down the pipeline to the browser.
    With a recorder (consented demo replay), every event is also kept with its time.
    """

    def __init__(self, session: Session, publish: Publish | None = None, recorder: Recorder | None = None) -> None:
        super().__init__()
        self.session = session
        self.recorder = recorder
        self.turn = 0
        self.critical = False
        self._publish = publish
        self._ending = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            await self.push_frame(frame, direction)
            # Off the event loop: Session may call Gemini, and audio must keep flowing meanwhile.
            await self._emit(await asyncio.to_thread(self.session.start))
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
        # Off the event loop: a question can take up to 3 s (Gemini), audio and the serializer keep flowing.
        await self._emit(await asyncio.to_thread(self.session.hear, text))

    async def send_event(self, ev: dict) -> None:
        if self.recorder is not None:
            self.recorder.event(ev)
        if self._publish is None:
            # Not urgent on purpose: the TTS queues it behind any audio still playing, so events stay in order.
            await self.push_frame(OutputTransportMessageFrame(message=ev))
        else:
            result = self._publish(ev)
            if inspect.isawaitable(result):
                await result

    async def _emit(self, events: list[dict]) -> None:
        says = []
        for ev in events:
            await self.send_event(ev)
            if ev["type"] == "say" and ev["text"].strip():
                says.append(ev["text"].strip())
        if says:
            self.critical = any(_AMOUNT.search(s) for s in says)
            # One utterance per reply: separate TTS contexts make the bot "stop speaking" between lines,
            # which would unmute the user mid-reply and let a stray word cut the rest of the explanation.
            await self.push_frame(TTSSpeakFrame(" ".join(says), append_to_context=False))
        if self.session.done and not self._ending:
            self._ending = True
            # Downstream, so the goodbye is played out before the pipeline ends (and the phone hangs up).
            await self.push_frame(EndWorkerFrame(reason="session complete"))


def build_worker(
    websocket: WebSocket,
    session: Session,
    profile: Profile,
    serializer: FrameSerializer,
    api_key: str,
    publish: Publish | None = None,
    session_timeout: int = SESSION_TIMEOUT_SECS,
    recorder: Recorder | None = None,
) -> tuple[PipelineWorker, Brain]:
    lang = session.lang
    rate = profile.sample_rate
    transport = FastAPIWebsocketTransport(
        websocket,
        FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
            session_timeout=session_timeout,
        ),
    )
    stt = SarvamSTTService(
        api_key=api_key,
        mode="codemix",
        sample_rate=rate,
        keyterms=KEYTERMS,
        settings=SarvamSTTService.Settings(model=STT_MODEL, language=LANGS[lang]),
    )
    tts = SarvamTTSService(
        api_key=api_key,
        sample_rate=rate,
        settings=SarvamTTSService.Settings(model=TTS_MODEL, voice=VOICES[lang], language=LANGS[lang], pace=1.0),
    )
    vad = SileroVADAnalyzer(
        sample_rate=rate, params=VADParams(confidence=0.7, start_secs=0.2, stop_secs=0.2, min_volume=0.6)
    )
    brain = Brain(session, publish, recorder)

    if profile.half_duplex:
        strategies = UserTurnStrategies(stop=[StateSpeechTimeout(session)])
        mutes: list[BaseUserMuteStrategy] = [AlwaysUserMuteStrategy()]
    else:
        strategies = UserTurnStrategies(
            start=[QuietVADStart(), MinWordsUserTurnStartStrategy(min_words=BARGE_IN_MIN_WORDS)],
            stop=[StateSpeechTimeout(session)],
        )
        mutes = [CriticalReadoutMute(brain)]
    aggregators = LLMContextAggregatorPair(
        LLMContext(),
        user_params=LLMUserAggregatorParams(
            vad_analyzer=vad,
            user_turn_strategies=strategies,
            user_mute_strategies=mutes,
            empty_user_turn=None,
        ),
    )

    gate = EchoGate() if profile.half_duplex else EchoGate(tail_secs=0.0, only_if=lambda: brain.critical)
    head = [transport.input(), gate]
    tail = []
    if recorder is not None:
        # After the output, so it hears both sides: the user's audio as it came in, Samjho's as it was sent.
        audio = AudioBufferProcessor(sample_rate=rate, num_channels=1, auto_start_recording=True)

        @audio.event_handler("on_recording_started")
        async def on_recording_started(_processor) -> None:
            recorder.restart_clock()

        @audio.event_handler("on_audio_data")
        async def on_audio_data(_processor, pcm: bytes, sample_rate: int, _channels: int) -> None:
            recorder.add_audio(pcm, sample_rate)

        tail = [audio]
    pipeline = Pipeline([*head, stt, aggregators.user(), brain, tts, transport.output(), *tail])

    latency = UserBotLatencyObserver()
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(audio_in_sample_rate=rate, audio_out_sample_rate=rate, enable_metrics=True),
        observers=[latency],
        enable_rtvi=False,
    )

    @latency.event_handler("on_latency_measured")
    async def on_latency(_observer, seconds: float) -> None:
        ms = round(seconds * 1000)
        logger.info(f"Samjho {profile.name} turn {brain.turn}: {ms} ms end of speech to first bot audio")
        ev = {"type": "latency", "turn": brain.turn, "ms": ms}
        if publish is None:
            if recorder is not None:
                recorder.event(ev)
            await worker.queue_frame(OutputTransportMessageUrgentFrame(message=ev))
        else:
            await brain.send_event(ev)

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(_transport, _ws) -> None:
        await worker.cancel(reason="client disconnected")

    @transport.event_handler("on_session_timeout")
    async def on_timeout(_transport, _ws) -> None:
        await worker.cancel(reason="session timeout")

    return worker, brain


async def run_worker(worker: PipelineWorker) -> None:
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()


async def save_recording(recorder: Recorder | None) -> None:
    if recorder is not None:
        try:
            await asyncio.to_thread(recorder.save)
        except Exception as e:
            logger.exception(f"Could not save the replay: {e.__class__.__name__}")


async def run_browser_session(websocket: WebSocket, lang: str, api_key: str, record: bool = False) -> None:
    """Runs one spoken session on an accepted WebSocket until it ends or the browser leaves.

    record=True only when the person speaking ticked the consent box to be saved as a demo replay.
    """
    global _active
    if _active >= MAX_SESSIONS:
        await websocket.send_json({"type": "case", "case": "BUSY", "detail": "Too many live sessions, try again"})
        await websocket.close()
        return
    _active += 1
    try:
        session = Session(lang=lang if lang in VOICES else "hi", recording=bool(record))
        recorder = Recorder(session, "browser") if record else None
        worker, _ = build_worker(websocket, session, BROWSER, BrowserSerializer(), api_key, recorder=recorder)
        try:
            await run_worker(worker)
        finally:
            await save_recording(recorder)
    finally:
        _active -= 1


async def run_phone_session(
    websocket: WebSocket,
    *,
    lang: str,
    stream_sid: str,
    call_sid: str,
    sarvam_key: str,
    account_sid: str,
    auth_token: str,
    publish: Publish,
    time_limit: int,
    record: bool = False,
) -> Session:
    """Runs one spoken session on a Twilio Media Stream; hangs up when the session ends."""
    from pipecat.serializers.twilio import TwilioFrameSerializer

    serializer = TwilioFrameSerializer(
        stream_sid,
        call_sid=call_sid,
        account_sid=account_sid,
        auth_token=auth_token,
        params=TwilioFrameSerializer.InputParams(
            audio_in_sample_rate=PHONE.sample_rate, audio_out_sample_rate=PHONE.sample_rate, auto_hang_up=True
        ),
    )
    session = Session(lang=lang if lang in VOICES else "hi", recording=bool(record))
    recorder = Recorder(session, "phone") if record else None
    worker, _ = build_worker(
        websocket,
        session,
        PHONE,
        serializer,
        sarvam_key,
        publish=publish,
        session_timeout=time_limit + 30,
        recorder=recorder,
    )
    try:
        await run_worker(worker)
    finally:
        await save_recording(recorder)
    return session
