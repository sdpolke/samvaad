"""Pydantic schemas for BDR workflow configuration extensions.

These schemas validate the new workflow_configurations keys added for
BDR-calling integration: tts_expression, vad_config, goodbye_detection,
call_state_detection, and callback_scheduling.
"""

from typing import Optional

from pydantic import BaseModel, field_validator


class TTSExpressionConfig(BaseModel):
    """TTS expressiveness settings for Cartesia."""

    emotion: Optional[str] = None
    speed: float = 1.0

    @field_validator("speed")
    @classmethod
    def speed_in_range(cls, v: float) -> float:
        if v < 0.5 or v > 2.0:
            raise ValueError("speed must be between 0.5 and 2.0")
        return v


class VADConfig(BaseModel):
    """Voice Activity Detection tuning parameters."""

    confidence: float = 0.5
    start_secs: float = 0.2
    stop_secs: float = 0.8
    min_volume: float = 0.6

    @field_validator("confidence", "min_volume")
    @classmethod
    def zero_to_one(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError("Must be between 0.0 and 1.0")
        return v

    @field_validator("start_secs", "stop_secs")
    @classmethod
    def non_negative(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError("Must be >= 0.0")
        return v


class GoodbyeDetectionConfig(BaseModel):
    """Goodbye phrase detection configuration."""

    enabled: bool = False
    phrases: list[str] = ["goodbye", "bye", "not interested"]
    action: str = "end_call"  # "end_call" or "prompt_goodbye"

    @field_validator("phrases")
    @classmethod
    def at_least_one_phrase(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one phrase is required")
        return v

    @field_validator("action")
    @classmethod
    def valid_action(cls, v: str) -> str:
        if v not in ("end_call", "prompt_goodbye"):
            raise ValueError("action must be 'end_call' or 'prompt_goodbye'")
        return v


class CallStateDetectionConfig(BaseModel):
    """Call state detection (IVR/voicemail/human) configuration."""

    enabled: bool = False
    max_ivr_secs: int = 60
    ivr_target_description: str = ""
    voicemail_message: Optional[str] = None
    use_workflow_llm: bool = False
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None


class CallbackSchedulingConfig(BaseModel):
    """Callback scheduling tool configuration."""

    enabled: bool = False
