"""Groq LLM service with a bounded retry for transient tool-call failures.

Groq-hosted models (both the Llama family and gpt-oss) occasionally emit a bad
tool call that the Groq API rejects with an HTTP 400. Two *stochastic* variants
are seen in practice, and neither is a deterministic request error — the same
context regenerated almost always produces a valid tool call on the next attempt:

1. **Malformed generation** — body reads "Failed to call a function. Please
   adjust your prompt." (with a ``failed_generation`` payload). The model failed
   to produce a syntactically valid tool call at all.
2. **Hallucinated tool name** — body reads "attempted to call tool '<name>' which
   was not in request.tools". The model invented a function name that is not in
   the node's registered tool set (more likely on late turns with a large
   accumulated context, where a stale earlier tool name bleeds into the call).

Without a retry, the base service catches the exception in
``BaseOpenAILLMService.process_frame`` and pushes a (non-fatal) ``ErrorFrame``.
Our pipeline's ``on_pipeline_error`` handler then ends the call, so a single bad
completion terminates the whole conversation mid-turn — exactly the failure seen
on multi-transition nodes (e.g. the switchboard Greeting Collect node, which
registers several transition functions at once).

This subclass retries **only** those two stochastic failures and re-raises
everything else (auth, rate-limit, context-length, connection errors, and
deterministic tool-schema mismatches such as "parameters ... did not match
schema") unchanged, so real errors are never masked and we never loop. The retry
is safe because the Groq 400 is returned before any content frames are produced
(see ``BaseOpenAILLMService._process_context``), so re-running inference cannot
duplicate already-emitted speech.
"""

from __future__ import annotations

from loguru import logger

from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.services.groq.llm import GroqLLMService

#: Substrings identifying Groq's stochastic, retryable tool-call failures — a
#: malformed/failed generation, or a hallucinated tool name that was not in the
#: request's tool set. Matched case-insensitively against the exception message
#: so we do not depend on a specific SDK exception class. Deliberately excludes
#: deterministic tool-schema mismatches (e.g. "did not match schema"), which are
#: request bugs that would only fail again on retry.
_TOOL_CALL_ERROR_MARKERS: tuple[str, ...] = (
    "failed to call a function",
    "failed_generation",
    "not in request.tools",
)

#: Number of *extra* attempts after the first failure. Two keeps a hallucinated
#: tool name (which can recur on a re-run with the same context) from ending the
#: call while bounding the added latency/cost to at most two extra completions.
_MAX_RETRIES: int = 2


def is_function_call_generation_error(exc: Exception) -> bool:
    """Return True if ``exc`` is a Groq retryable, stochastic tool-call failure.

    Matches the exception message case-insensitively against
    :data:`_TOOL_CALL_ERROR_MARKERS` — i.e. a malformed/failed tool-call
    generation, or a hallucinated tool name not present in the request's tools.
    Any other error (auth, rate-limit, context-length, or a deterministic
    tool-schema mismatch) returns False so it is not retried.
    """
    message = str(exc).lower()
    return any(marker in message for marker in _TOOL_CALL_ERROR_MARKERS)


class RetryingGroqLLMService(GroqLLMService):
    """``GroqLLMService`` that retries a rejected, stochastic tool-call failure.

    Overrides :meth:`_process_context` to catch the narrow retryable tool-call
    errors identified by :func:`is_function_call_generation_error` (a
    malformed/failed generation, or a hallucinated tool name not in the request's
    tools) and re-run inference up to :data:`_MAX_RETRIES` times. All other
    exceptions propagate unchanged to the base ``process_frame`` handler,
    preserving existing error/timeout behavior.
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
