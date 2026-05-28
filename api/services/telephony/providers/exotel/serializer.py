"""Exotel WebSocket frame serializer for Pipecat.

Exotel's Voicebot applet streams audio over WebSocket using JSON messages
with base64-encoded Linear PCM (16-bit, 8 kHz, mono). This serializer
translates between Exotel's protocol and Pipecat's internal frame format.

Exotel → Bot events:
  - connected  : WebSocket handshake confirmed
  - start      : Audio streaming begins (contains stream_sid, call_sid, etc.)
  - media      : Base64-encoded PCM audio chunk
  - dtmf       : DTMF tone detected
  - mark       : Developer-defined marker
  - stop       : Stream ended
  - clear      : Reset session context

Bot → Exotel events:
  - media      : Base64-encoded PCM audio to play to the caller
"""

import base64
import json

from loguru import logger

from pipecat.frames.frames import (
    AudioRawFrame,
    Frame,
    InputAudioRawFrame,
    InterruptionFrame,
    StartFrame,
)
from pipecat.serializers.base_serializer import FrameSerializer


class ExotelFrameSerializer(FrameSerializer):
    """Serialize/deserialize Exotel Voicebot WebSocket messages.

    Exotel sends 16-bit Linear PCM at 8 kHz mono, base64-encoded in JSON.
    Unlike Twilio (which uses μ-law), Exotel uses raw PCM — so no codec
    conversion is needed when the pipeline also runs at 8 kHz.
    """

    class InputParams(FrameSerializer.InputParams):
        sample_rate: int = 8000

    def __init__(self, params: InputParams | None = None):
        super().__init__(params or ExotelFrameSerializer.InputParams())
        self._stream_sid: str = ""
        self._call_sid: str = ""
        self._sample_rate: int = self._params.sample_rate

    @property
    def stream_sid(self) -> str:
        return self._stream_sid

    @property
    def call_sid(self) -> str:
        return self._call_sid

    async def setup(self, frame: StartFrame):
        """Initialize with pipeline configuration."""
        self._sample_rate = self._params.sample_rate or frame.audio_in_sample_rate

    async def deserialize(self, data: str | bytes) -> Frame | None:
        """Convert an incoming Exotel WebSocket message into a Pipecat frame."""
        try:
            message = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Exotel: received non-JSON message, ignoring")
            return None

        event_type = message.get("event", "")

        if event_type == "connected":
            logger.info("Exotel: WebSocket connected")
            return None

        elif event_type == "start":
            start_data = message.get("start", {})
            self._stream_sid = start_data.get(
                "stream_sid", message.get("stream_sid", self._stream_sid)
            )
            self._call_sid = start_data.get("call_sid", "")
            media_format = start_data.get("media_format", {})
            logger.info(
                f"Exotel: stream started — stream_sid={self._stream_sid} "
                f"call_sid={self._call_sid} format={media_format}"
            )
            return None

        elif event_type == "media":
            media_data = message.get("media", {})
            payload = media_data.get("payload", "")
            if not payload:
                return None
            audio_bytes = base64.b64decode(payload)
            return InputAudioRawFrame(
                audio=audio_bytes,
                sample_rate=self._sample_rate,
                num_channels=1,
            )

        elif event_type == "dtmf":
            dtmf_data = message.get("dtmf", {})
            digit = dtmf_data.get("digit", "")
            logger.info(f"Exotel: DTMF digit received: {digit}")
            return None

        elif event_type == "clear":
            logger.info("Exotel: clear event — interrupting current output")
            return InterruptionFrame()

        elif event_type == "stop":
            stop_data = message.get("stop", {})
            reason = stop_data.get("reason", "unknown")
            logger.info(f"Exotel: stream stopped — reason={reason}")
            return None

        elif event_type == "mark":
            mark_data = message.get("mark", {})
            logger.debug(f"Exotel: mark event — {mark_data.get('name', '')}")
            return None

        else:
            logger.debug(f"Exotel: unhandled event type '{event_type}'")
            return None

    async def serialize(self, frame: Frame) -> str | bytes | None:
        """Convert a Pipecat frame into an Exotel WebSocket message."""
        if isinstance(frame, InterruptionFrame):
            return json.dumps({
                "event": "clear",
                "stream_sid": self._stream_sid,
            })
        elif isinstance(frame, AudioRawFrame):
            payload = base64.b64encode(frame.audio).decode("utf-8")
            return json.dumps({
                "event": "media",
                "stream_sid": self._stream_sid,
                "media": {
                    "payload": payload,
                },
            })

        return None
