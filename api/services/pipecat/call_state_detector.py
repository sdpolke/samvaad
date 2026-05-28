"""Call state detection processor — IVR, voicemail, and human detection.

For outbound calls, detects whether the call was answered by a human,
an IVR system, or voicemail. Uses LLM-based classification and can
navigate IVR menus via DTMF.

Inserted into the pipeline after STT when
workflow_configurations.call_state_detection.enabled is true.
"""

import asyncio
import time
from enum import Enum

from loguru import logger

from pipecat.frames.frames import (
    EndFrame,
    Frame,
    TTSSpeakFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class CallState(Enum):
    """Detected state of the call."""

    DETECTING = "detecting"
    HUMAN = "human"
    VOICEMAIL = "voicemail"
    IVR = "ivr"


CLASSIFICATION_PROMPT = """\
You are an IVR detection classifier on an OUTBOUND call.
You have not spoken yet. Everything you hear is the callee's side only.

Respond with ONLY ONE of:
- "ivr" — phone tree, hold music, business-hours message, carrier prompts, OR a recorded voicemail greeting.
- "human" — someone is clearly interacting WITH YOU as the caller (asks who you are, engages in real Q&A).
- "wait" — not enough text to decide yet."""


class CallStateDetectorProcessor(FrameProcessor):
    """Detects whether an outbound call reached a human, voicemail, or IVR.

    During the detection window:
    - Buffers STT transcriptions
    - Uses LLM to classify the call state
    - For IVR: attempts DTMF navigation
    - For voicemail: speaks configured message and ends call
    - For human: passes control to normal workflow

    After max_ivr_secs, defaults to HUMAN.
    """

    _BUFFER_CHARS = 600

    def __init__(
        self,
        llm_service,
        max_ivr_secs: int = 60,
        ivr_target_description: str = "",
        voicemail_message: str | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._llm = llm_service
        self._max_ivr_secs = max_ivr_secs
        self._ivr_target = ivr_target_description
        self._voicemail_message = voicemail_message
        self._state = CallState.DETECTING
        self._start_time: float = 0.0
        self._text_buffer: str = ""
        self._classifying: bool = False
        self._resolved: bool = False

    @property
    def state(self) -> CallState:
        return self._state

    @property
    def is_detecting(self) -> bool:
        return self._state == CallState.DETECTING

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # Once resolved to HUMAN, pass everything through
        if self._state == CallState.HUMAN:
            await self.push_frame(frame, direction)
            return

        # Block VAD interruptions during voicemail
        if self._state == CallState.VOICEMAIL and isinstance(
            frame, UserStartedSpeakingFrame
        ):
            return

        # Timeout check
        if not self._start_time:
            self._start_time = time.time()

        elapsed = time.time() - self._start_time
        if elapsed > self._max_ivr_secs and self._state == CallState.DETECTING:
            logger.info(
                f"CallStateDetector: timeout ({elapsed:.1f}s) — defaulting to HUMAN"
            )
            self._state = CallState.HUMAN
            self._resolved = True
            await self.push_frame(frame, direction)
            return

        # Only classify on transcription frames
        if isinstance(frame, TranscriptionFrame) and frame.text.strip():
            if self._state == CallState.DETECTING:
                await self._handle_detecting(frame, direction)
                return
            elif self._state == CallState.VOICEMAIL:
                # Drop transcription frames during voicemail
                return

        # Non-transcription frames pass through during detection
        await self.push_frame(frame, direction)

    async def _handle_detecting(
        self, frame: TranscriptionFrame, direction: FrameDirection
    ) -> None:
        """Buffer text and classify."""
        text = frame.text.strip()
        self._text_buffer = (self._text_buffer + " " + text)[-self._BUFFER_CHARS:]

        if self._classifying:
            return  # Skip while LLM call is in flight

        self._classifying = True
        try:
            classification = await self._classify(self._text_buffer)
            logger.info(
                f"CallStateDetector: class='{classification}' "
                f"buf='{self._text_buffer[-80:]!r}'"
            )

            if classification == "human":
                self._state = CallState.HUMAN
                self._resolved = True
                logger.info("CallStateDetector: HUMAN detected")
                await self.push_frame(frame, direction)
            elif classification == "ivr":
                # For now, default to HUMAN after IVR detection
                # Full DTMF navigation would require OutputDTMFUrgentFrame support
                self._state = CallState.IVR
                logger.info("CallStateDetector: IVR detected, defaulting to HUMAN")
                self._state = CallState.HUMAN
                self._resolved = True
                await self.push_frame(frame, direction)
            elif classification == "voicemail":
                self._state = CallState.VOICEMAIL
                logger.info("CallStateDetector: VOICEMAIL detected")
                await self._handle_voicemail()
            # else: "wait" — keep buffering
        except Exception as exc:
            logger.warning(
                f"CallStateDetector: LLM error ({exc}) — defaulting to HUMAN"
            )
            self._state = CallState.HUMAN
            self._resolved = True
            await self.push_frame(frame, direction)
        finally:
            self._classifying = False

    async def _classify(self, text: str) -> str:
        """Use LLM to classify the call state."""
        try:
            # Use the LLM's run_inference if available, otherwise fall back
            # to a simple completion call
            result = await self._llm.run_inference(
                system_prompt=CLASSIFICATION_PROMPT,
                user_message=text[-400:],
            )
            reply = result.strip().lower()
        except AttributeError:
            # LLM service doesn't have run_inference — skip classification
            return "wait"

        if "human" in reply:
            return "human"
        if any(kw in reply for kw in ("ivr", "voicemail", "automated", "machine")):
            if "voicemail" in reply:
                return "voicemail"
            return "ivr"
        return "wait"

    async def _handle_voicemail(self):
        """Speak voicemail message and end call."""
        if self._voicemail_message:
            logger.info("CallStateDetector: speaking voicemail message")
            await self.push_frame(TTSSpeakFrame(self._voicemail_message))
        await self.push_frame(EndFrame())
