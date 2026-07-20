"""Property test for empty hotword list matches nothing (task 8.2).

Covers Property 12 — Empty hotword list matches nothing (Requirement 10.5).

``detect_hotword`` (``api/services/switchboard/after_hours.py``) scans caller
speech for configured hotword keywords. When no hotwords are configured — an
explicit empty ``keywords=[]`` list, or ``keywords=None`` with nothing set via
:data:`~api.services.switchboard.config.AFTERHOURS_HOTWORDS_ENV_VAR` — there is
nothing to match against, so detection must always return ``None`` regardless
of what the caller said, even for utterances containing common urgent
words/phrases. This is what prevents the hotword silent-routing path
(:func:`~api.services.switchboard.after_hours.hotword_routing_decision`) from
ever firing when the feature is unconfigured.

Design references:
- ``design.md`` -> "Correctness Properties" -> "Property 12: Empty hotword
  list matches nothing"
- ``requirements.md`` -> Requirement 10.5

Requirements: 10.5.
"""

from __future__ import annotations

import os
from unittest import mock

from hypothesis import example, given, settings
from hypothesis import strategies as st

from api.services.switchboard.after_hours import (
    detect_hotword,
    hotword_routing_decision,
)
from api.services.switchboard.config import AFTERHOURS_HOTWORDS_ENV_VAR


# Feature: switchboard-frontend-enablement, Property 12: Empty hotword list matches nothing
@example(utterance="chest pain")
@example(utterance="stroke")
@example(utterance="help")
@example(utterance="emergency")
@example(utterance="bleeding")
@example(utterance="I can't breathe")
@example(utterance="")
@given(utterance=st.text())
@settings(max_examples=100)
def test_empty_hotword_list_matches_nothing(utterance: str) -> None:
    """No configured hotwords means no match, ever.

    **Validates: Requirements 10.5**

    With an explicit empty keyword list (``keywords=[]``), or with
    ``keywords=None`` and no hotwords configured via
    :data:`AFTERHOURS_HOTWORDS_ENV_VAR` (unset/empty), ``detect_hotword`` must
    always return ``None`` — including for utterances that contain common
    urgent words/phrases which would only ever match if explicitly configured
    as hotwords — and the hotword silent-routing decision must never fire.
    """
    # Explicit empty keyword list: nothing configured, nothing to match.
    assert detect_hotword(utterance, keywords=[]) is None
    assert hotword_routing_decision(utterance, keywords=[]) is None

    # keywords=None falls back to the configured (here: unconfigured) list.
    # Force the "no configured hotwords" case regardless of the ambient
    # environment by clearing the env var for the duration of this check.
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop(AFTERHOURS_HOTWORDS_ENV_VAR, None)
        assert detect_hotword(utterance, keywords=None) is None
        assert hotword_routing_decision(utterance, keywords=None) is None
