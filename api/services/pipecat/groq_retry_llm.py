"""Groq LLM service with a bounded retry for transient function-call failures.

Groq's Llama models occasionally emit a malformed tool call that the Groq API
rejects with an HTTP 400 whose body reads "Failed to call a function. Please
adjust your prompt." (with a ``failed_generation`` payload). This is a
*stochastic* generation failure, not a deterministic request error: the same
context regenerated almost always produces a valid tool call on the next
attempt.

Without a retry, the base service catches the exception in
``BaseOpenAILLMService.process_frame`` and pushes a (non-fatal) ``ErrorFrame``.
Our pipeline's ``on_pipeline_error`` handler then ends the call, so a single bad
completion terminates the whole conversation mid-turn — exactly the failure seen
on multi-transition nodes (e.g. the switchboard Greeting Collect node, which
registers several transition functions at once).

This subclass retries **only** that specific failure and re-raises everything
else (auth, rate-limit, context-length, connection errors, etc.) unchanged, so
real errors are never masked and we never loop. The retry is safe because the
Groq 400 is returned before any content frames are produced (see
``BaseOpenAILLMService._process_context``), so re-running inference cannot
duplicate already-emitted speech.
"""

from __future__ import annotations

from loguru import logger

from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.services.groq.llm import GroqLLMService

#: Substrings identifying Groq's stochastic "could not produce a valid tool
#: call" generation failure. Matched case-insensitively against the exception
#: message so we do not depend on a specific SDK exception class.
_FUNCTION_CALL_GENERATION_ERROR_MARKERS: tuple[str, ...] = (
    "failed to call a function",
    "failed_generation",
)

#: Number of *extra* attempts after the first failure. One retry is sufficient
#: in practice and bounds the added latency/cost to a single extra completion.
_MAX_RETRIES: int = 1


def is_function_call_generation_error(exc: Exception) -> bool:
    """Return True if ``exc`` is Groq's retryable malformed-tool-call failure.

    Matches the exception message case-insensitively against
    :data:`_FUNCTION_CALL_GENERATION_ERROR_MARKERS`. Any other error (including
    other HTTP 400s such as context-length) returns False so it is not retried.
    """
    message = str(exc).lower()
    return any(marker in message for marker in _FUNCTION_CALL_GENERATION_ERROR_MARKERS)


class RetryingGroqLLMService(GroqLLMService):
    """``GroqLLMService`` that retries a rejected tool-call generation once.

    Overrides :meth:`_process_context` to catch the narrow "failed to call a
    function" generation error and re-run inference up to :data:`_MAX_RETRIES`
    times. All other exceptions propagate unchanged to the base
    ``process_frame`` handler, preserving existing error/timeout behavior.
    """

    async def _process_context(self, context: LLMContext) -> None:
        attempt = 0
        while True:
            try:
                await super()._process_context(context)
                return
            except Exception as exc:  # noqa: BLE001 - re-raised unless retryable
                if attempt >= _MAX_RETRIES or not is_function_call_generation_error(
                    exc
                ):
                    raise
                attempt += 1
                logger.warning(
                    "Groq rejected a tool-call generation ({}); retrying "
                    "completion (attempt {}/{})",
                    exc,
                    attempt,
                    _MAX_RETRIES,
                )


__all__ = [
    "RetryingGroqLLMService",
    "is_function_call_generation_error",
]
