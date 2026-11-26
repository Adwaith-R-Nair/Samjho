"""Wire format between the browser and the voice pipeline.

Browser to server: binary messages are raw PCM16 mono audio at 16 kHz (little endian). Text messages are
ignored (the browser ends a session by closing the socket).

Server to browser: binary messages are PCM16 mono 16 kHz audio to play, in order and without gaps. Text
messages are JSON objects that are exactly our UI events (say, heard, fact, case, record, state, latency),
plus {"type": "clear"} when queued audio must be dropped (only after an interruption).
"""

import json

from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
    OutputTransportMessageFrame,
    OutputTransportMessageUrgentFrame,
)
from pipecat.serializers.base_serializer import FrameSerializer

WIRE_RATE = 16000


class BrowserSerializer(FrameSerializer):
    """PCM16 16 kHz audio both ways as binary, UI events out as JSON text."""

    def __init__(self) -> None:
        super().__init__(
            FrameSerializer.InputParams(audio_in_sample_rate=WIRE_RATE, audio_out_sample_rate=WIRE_RATE)
        )

    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, OutputAudioRawFrame):
            if frame.sample_rate == WIRE_RATE and frame.num_channels == 1:
                return frame.audio
            return await self._resample_audio_out(frame)
        if isinstance(frame, (OutputTransportMessageFrame, OutputTransportMessageUrgentFrame)):
            if self.should_ignore_frame(frame) or not isinstance(frame.message, dict):
                return None
            return json.dumps(frame.message, ensure_ascii=False)
        if isinstance(frame, InterruptionFrame):
            await self._reset_audio_out()
            return json.dumps({"type": "clear"})
        return None

    async def deserialize(self, data: str | bytes) -> Frame | None:
        if not isinstance(data, (bytes, bytearray)) or len(data) < 2:
            return None
        audio = bytes(data[: len(data) - len(data) % 2])
        rate = self._sample_rate or WIRE_RATE
        if rate != WIRE_RATE:
            audio = await self._resample_audio_in(audio)
        return InputAudioRawFrame(audio=audio, sample_rate=rate, num_channels=1)
