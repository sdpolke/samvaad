"""Goodbye phrase detection processor.

Monitors transcription frames for configured goodbye phrases and triggers
call termination when detected. Inserted into the pipeline after STT when
workflow_configurations.goodbye_detection.enabled is true.
"""

from loguru import logger

from pipecat.frames.frames import (
    EndFrame,
    Frame,
    TTSSpeakFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class GoodbyeDetectorProcessor(FrameProcessor):
    """Detects goodbye phrases in transcription and triggers call termination.

    Performs case-insensitive substring matching against transcription text.
    Once triggered, emits either an EndFrame (end_call action) or a farewell
    TTSSpeakFrame followed by EndFrame (prompt_goodbye action).
    """

    def __init__(
        self,
        phrases: list[str],
        action: str = "end_call",
        farewell_message: str = "Thank you for your time. Goodbye!",
        **kwargs,
    ):
        super().__init__(**kwargs)
        # Store lowercase for case-insensitive matching
        self._phrases = [p.lower().strip() for p in phrases if p.strip()]
        self._action = action
        self._farewell_message = farewell_message
        self._triggered = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame) and not self._triggered:
            text_lower = frame.text.lower().strip()
            if not text_lower:
                await self.push_frame(frame, direction)
                return

            for phrase in self._phrases:
                if phrase in text_lower:
                    logger.info(
                        f"Goodbye phrase detected: '{phrase}' in '{frame.text}'"
                    )
                    self._triggered = True
                    # Still push the transcription frame so it's logged
                    await self.push_frame(frame, direction)
                    await self._handle_detection()
                    return

        await self.push_frame(frame, direction)

    async def _handle_detection(self):
        """Handle goodbye detection based on configured action."""
        if self._action == "end_call":
            await self.push_frame(EndFrame())
        elif self._action == "prompt_goodbye":
            # Speak farewell message, then end
            await self.push_frame(TTSSpeakFrame(self._farewell_message))
            # EndFrame will be pushed after TTS completes via idle monitor or
            # the pipeline's natural completion flow
