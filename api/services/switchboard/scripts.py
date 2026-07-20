"""Verbatim caller scripts for the SpinSci Switchboard PoC (Appendix C / E).

This module is the switchboard's **verbatim script asset**. Every string below is
copied **byte-for-byte** from the vendor requirements document
(``SpinsciPoCRequirement/SpinSci Switchboard and Scheduling Requirements.md``),
Appendix C (caller scripts) and Appendix E (transfer / goodbye / error lines).

Fidelity rules (do not "clean up" any of these):

* Wording, punctuation, capitalization, and spacing are reproduced exactly as
  authored. In particular, Script 3′ deliberately uses a comma before "and"
  (``... do my best to help, and to ensure ...``) with **no period before**
  "and" — this is preserved on purpose (Requirement 18.4).
* Typographic punctuation is preserved as authored: curly apostrophes
  (``U+2019`` ``’``) and em dashes (``U+2014`` ``—``) — not ASCII substitutes.
* Runtime placeholder tokens are reproduced with their **exact authored syntax**,
  even where the source is internally inconsistent: ``{FirstName}`` (single
  braces) in Script 2′, ``{{caller_name}}`` (double braces) in Paths A/B, and
  ``{{FirstName}} {{LastName}}`` (double braces) in the name-confirm line. Do not
  normalize the brace style. The bracketed ``[digit N]`` / ``[symptom]`` tokens in
  the phone read-back and disambiguation lines are likewise preserved verbatim.

Besides the verbatim constants, this module owns the switchboard's **script
renderer and speech guards** (task 4.2): :func:`render` substitutes runtime
placeholder tokens into a verbatim line without altering any other character;
:func:`assert_no_internal_narration` rejects speech that leaks internal artifacts
(system names, JSON, UUIDs, Call State Ledger field names — Requirement 4.1); and
:func:`prescription_speech` produces prescription/pharmacy speech that never
emits a medication name (Requirements 4.2, 5.1, 11.4). All of these are pure and
side-effect-free so they are independently unit/property-testable. Routing selects
an Appendix E line by ledger intent (Requirement 10.5) using the constants here.

Design references:
- ``design.md`` → "Verbatim spoken line" framing and Requirements Traceability
- ``requirements.md`` → Requirement 18 (18.1, 18.2, 18.4), Requirement 17.4/17.5

Requirements: 18.1, 18.2, 17.4, 17.5.
"""

from __future__ import annotations

import re
from typing import Mapping, Optional

from api.services.switchboard.ledger import LEDGER_FIELD_NAMES

# ===========================================================================
# Appendix C — Caller scripts (all wording mandatory / verbatim)
# ===========================================================================

# --- Greeting --------------------------------------------------------------

#: ROUTING REQUEST — used standalone and in Scripts 3′, 4, 4′, Path B, Path D.
GREETING_ROUTING_REQUEST: str = (
    "To ensure your call is routed correctly, please provide the provider, "
    "specialty, or location you are trying to reach, along with the reason for "
    "your call today."
)

#: Script 4 — Standard in hours (no Step 0).
GREETING_SCRIPT_4_STANDARD_IN_HOURS: str = (
    "Thank you for calling SpinSci. This is SpinSci AI, your virtual assistant. "
    "To ensure your call is routed correctly, please provide the provider, "
    "specialty, or location you are trying to reach, along with the reason for "
    "your call today."
)

#: Script 3′ — After hours (after Step 0). NOTE: no period before "and" — the
#: comma-before-"and" form is intentional and must be preserved (Req 18.4).
GREETING_SCRIPT_3_PRIME_AFTER_HOURS: str = (
    "Our offices are currently closed, so options may be limited, but I’ll do my "
    "best to help, and to ensure your call is routed correctly, please provide "
    "the provider, specialty, or location you are trying to reach, along with the "
    "reason for your call today."
)

#: Script 2′ — Personalized in hours. Placeholder token authored as {FirstName}.
GREETING_SCRIPT_2_PRIME_PERSONALIZED: str = "Am I speaking with {FirstName}?"

#: Path A — personalized acknowledgment variant.
GREETING_PATH_A_PERSONALIZED: str = (
    "Hi {{caller_name}}, nice to meet you. Let me help you with that."
)

#: Path A — standard acknowledgment variant.
GREETING_PATH_A_STANDARD: str = "Let me help you with that."

#: Path B — personalized greeting that still requests routing information.
GREETING_PATH_B: str = (
    "Hi {{caller_name}}, nice to meet you. To ensure your call is routed "
    "correctly, please provide the provider, specialty, or location you are "
    "trying to reach, along with the reason for your call today."
)

#: Path D — non-personalized greeting that still requests routing information.
GREETING_PATH_D: str = (
    "No worries — I can still help you. To ensure your call is routed correctly, "
    "please provide the provider, specialty, or location you are trying to reach, "
    "along with the reason for your call today."
)

#: Path E — not-understood retry line.
GREETING_PATH_E: str = "I didn’t quite catch that. Could you repeat that for me?"

#: Medication line (never repeat the medication name).
GREETING_MEDICATION: str = "You’re calling about your prescription."

#: Goodbye retention line.
GREETING_GOODBYE_RETENTION: str = (
    "Before you go, is there anything else I can help you with?"
)

#: Hangup line.
GREETING_HANGUP: str = "Thank you for calling SpinSci. Goodbye."

# --- Business Hours --------------------------------------------------------

#: FAQ lookup prefix.
BH_FAQ_LOOKUP: str = "Let me check that for you."

#: Non-FAQ / non-first-directory lookup prefix.
BH_OTHER_LOOKUP: str = "One moment."

#: Directory close line.
BH_DIRECTORY_CLOSE: str = "Can I help with anything else before we end our call?"

#: Scheduling new/existing gate question.
BH_SCHEDULING_GATE: str = "Are you a new or existing patient?"

#: Directory/provider no-match "search trouble" line.
BH_SEARCH_TROUBLE: str = (
    "I’m having some trouble finding that. Would you like me to connect you with "
    "someone who can help?"
)

#: Business-hours first not-understood retry line.
BH_RETRY_1: str = (
    "I’m sorry, I didn’t catch that. How can I help you direct your call today?"
)

#: Business-hours second not-understood retry line.
BH_RETRY_2: str = (
    "I’m still having trouble understanding. Please tell me what you need help "
    "with — like scheduling, a nurse, or a provider."
)

#: List-cap continuation line.
BH_LIST_CAP: str = (
    "I have a few more as well. Would you like me to continue, or does one of "
    "those sound right?"
)

#: Business-hours goodbye retention line.
BH_GOODBYE_RETENTION: str = (
    "Before you go, is there anything else I can help you with?"
)

#: Business-hours closing line.
BH_CLOSING: str = "Thank you for calling SpinSci. Have a great day."

# --- After Hours -----------------------------------------------------------

#: Paging clarifier — option 1 (pick one).
AH_PAGING_CLARIFIER_OPTION_1: str = (
    "Just to route this correctly — are you calling from a hospital or medical "
    "facility, or are you the patient?"
)

#: Paging clarifier — option 2 (pick one).
AH_PAGING_CLARIFIER_OPTION_2: str = (
    "Are you a doctor or calling from a medical facility, or are you calling for "
    "yourself as the patient?"
)

#: Paging clarifier — option 3 (pick one).
AH_PAGING_CLARIFIER_OPTION_3: str = (
    "Are you staff calling about a patient, or are you calling for yourself?"
)

#: Paging clarifier options grouped in authored order ("pick one").
AH_PAGING_CLARIFIER_OPTIONS: tuple[str, str, str] = (
    AH_PAGING_CLARIFIER_OPTION_1,
    AH_PAGING_CLARIFIER_OPTION_2,
    AH_PAGING_CLARIFIER_OPTION_3,
)

#: Restricted service (scheduling example) INFORM/ASK line.
AH_RESTRICTED_SERVICE_SCHEDULING: str = (
    "I’m sorry, our scheduling services are currently closed. You’re welcome to "
    "call back during business hours, or I can connect you to someone — though "
    "they won’t be from the specific office you’re calling about. Would you like "
    "me to do that?"
)

#: MyChart closed line.
AH_MYCHART_CLOSED: str = (
    "I’m sorry, MyChart support is currently closed. Please call back during "
    "business hours for live assistance."
)

#: Billing closed line.
AH_BILLING_CLOSED: str = (
    "I’m sorry, our billing department is currently closed. Please call back "
    "during business hours for billing assistance."
)

#: After-hours directory gate line.
AH_DIRECTORY_GATE: str = "Let me check that for you."

#: After-hours directory/provider no-match line.
AH_NO_MATCH: str = (
    "I wasn’t able to find a match. Would you like me to try a different search?"
)

#: After-hours live-connect offer line.
AH_LIVE_CONNECT_OFFER: str = (
    "Since our offices are currently closed, I can connect you to someone — "
    "though they won’t be from the specific office you’re calling about. Would "
    "you like me to do that?"
)

#: After-hours first not-understood retry line.
AH_RETRY_1: str = "I’m sorry, I didn’t catch that. How can I help you?"

#: After-hours second not-understood retry line.
AH_RETRY_2: str = (
    "I’m still having trouble understanding. Could you tell me what you need help "
    "with?"
)

#: After-hours follow-up — option 1.
AH_FOLLOW_UP_OPTION_1: str = "Is there anything else I can help with?"

#: After-hours follow-up — option 2.
AH_FOLLOW_UP_OPTION_2: str = (
    "Did that help, or is there anything else I can assist with?"
)

#: After-hours follow-up options grouped in authored order.
AH_FOLLOW_UP_OPTIONS: tuple[str, str] = (
    AH_FOLLOW_UP_OPTION_1,
    AH_FOLLOW_UP_OPTION_2,
)

# --- Authentication --------------------------------------------------------

#: ANI offer line.
AUTH_ANI_OFFER: str = (
    "I can use the phone number you’re calling from to look up your record. Is "
    "that okay?"
)

#: Phone request — provider caller.
AUTH_PHONE_PROVIDER: str = (
    "Could you please provide the phone number on file for the patient you’re "
    "calling about?"
)

#: Phone request — patient caller.
AUTH_PHONE_PATIENT: str = "Could you please provide the phone number for the patient?"

#: Phone read-back line. The [digit N] tokens are authored verbatim; the 3-3-4
#: period-grouping is mandated (Req 5.2, 9.9).
AUTH_PHONE_READBACK: str = (
    "I have [digit 1] [digit 2] [digit 3]. [digit 4] [digit 5] [digit 6]. "
    "[digit 7] [digit 8] [digit 9] [digit 10]. Is that correct?"
)

#: No-record line.
AUTH_NO_RECORD: str = (
    "I wasn’t able to find a record with that phone number. Could you try a "
    "different number?"
)

#: Date-of-birth request — patient caller.
AUTH_DOB_PATIENT: str = "Could you please provide your date of birth?"

#: Date-of-birth request — provider caller.
AUTH_DOB_PROVIDER: str = (
    "Could you please tell me the full date of birth of the patient you’re "
    "calling about?"
)

#: Name-confirm line. Placeholder tokens authored as {{FirstName}} {{LastName}}.
AUTH_NAME_CONFIRM: str = (
    "Can you confirm the full name for the patient is {{FirstName}} {{LastName}}?"
)

#: After-confirm line.
AUTH_AFTER_CONFIRM: str = "Thank you for confirming."

#: Auth fail / refusal → route line.
AUTH_FAIL_ROUTE: str = "No problem. I’ll connect you now."

#: Pushback line.
AUTH_PUSHBACK: str = (
    "It helps us pull up your record. If you’d prefer, I can connect you without "
    "it."
)

#: Changed-request line.
AUTH_CHANGED_REQUEST: str = "Sure, let me get you to the right place for that."

#: After-hours DOB opener line.
AUTH_AFTER_HOURS_DOB_OPENER: str = (
    "Our offices are currently closed, so options may be limited, but I’ll do my "
    "best to help. Can you provide the patient’s date of birth?"
)

# --- Scheduling Init (downstream — not switchboard) ------------------------
# Appendix C also mandates these downstream Scheduling Init lines verbatim; they
# are consumed by the downstream scheduling segment (Requirements 13.3, 13.4),
# not by the switchboard clusters. Grouped here so all Appendix C verbatim text
# lives in one asset module.

#: Visit-reason question (when the reason is unknown).
SCHED_INIT_VISIT_REASON: str = "What is the reason for your visit today?"

#: Wellness + symptom disambiguation question. [symptom] token authored verbatim.
SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION: str = (
    "Just to make sure I schedule the right type of visit — are you looking for "
    "an annual wellness exam, or would you like to be seen for your [symptom]?"
)

#: Provider-unavailable-for-visit-type line. The vendor document defers the exact
#: wording to SpinSci ("SpinSci provides exact wording — offer alternative
#: provider at same location"), so no verbatim line exists yet.
SCHED_INIT_PROVIDER_UNAVAILABLE: Optional[str] = None


# ===========================================================================
# Appendix E — Transfer lines
# Used as the spoken transfer message. The Routing phase adds no other speech
# (Requirement 10.4). Selected by ledger intent (Requirement 10.5).
# ===========================================================================

#: Scheduling — new (general new-patient path).
E_SCHEDULING_NEW: str = (
    "Let me get you over to our scheduling department. One moment."
)

#: Scheduling — existing (hand off to Scheduling Init for specialty).
E_SCHEDULING_EXISTING: str = (
    "Let me connect you with our scheduling team for existing patients. One "
    "moment."
)

#: Triage transfer line.
E_TRIAGE: str = "Let me connect you with our nurse triage team. One moment."

#: Referrals transfer line.
E_REFERRALS: str = "Let me connect you with the referrals department. One moment."

#: Paging transfer line.
E_PAGING: str = "Let me connect you now. One moment."

#: Pharmacy transfer line (never speak medication names).
E_PHARMACY: str = (
    "Let me connect you with someone who can help with your medication. One "
    "moment."
)

#: Billing transfer line.
E_BILLING: str = "Let me get you over to the Billing department. One moment."

#: Records transfer line.
E_RECORDS: str = "Let me get you over to the Records department. One moment."

#: MyChart transfer line.
E_MYCHART: str = "Let me get you over to the My Chart department. One moment."

#: General transfer line.
E_GENERAL: str = "Let me connect you with someone who can help. One moment."

#: Hotword-Urgent transfer line (after-hours urgent path).
E_HOTWORD_URGENT: str = (
    "Let me connect you with someone who can help right away. One moment."
)

#: Switchboard / fallback line.
E_SWITCHBOARD_FALLBACK: str = "One moment while I connect you."

#: Switchboard (alternate) line.
E_SWITCHBOARD_ALT: str = "Let me connect you with someone who can help. One moment."

#: Transfer-error line.
E_TRANSFER_ERROR: str = (
    "I apologize for the inconvenience. Please try calling back shortly. Thank "
    "you for calling SpinSci."
)

#: Hangup line.
E_HANGUP: str = "Thank you for calling SpinSci. Goodbye."

#: Appendix E transfer/goodbye/error lines grouped by their vendor case label.
#: Keys are the Appendix E "Intent / case" labels exactly as authored; values are
#: the verbatim spoken lines. This is a pure organizational grouping — mapping a
#: resolved ledger intent onto a case is routing logic handled elsewhere.
APPENDIX_E_TRANSFER_LINES: dict[str, str] = {
    "Scheduling — new": E_SCHEDULING_NEW,
    "Scheduling — existing": E_SCHEDULING_EXISTING,
    "Triage": E_TRIAGE,
    "Referrals": E_REFERRALS,
    "Paging": E_PAGING,
    "Pharmacy": E_PHARMACY,
    "Billing": E_BILLING,
    "Records": E_RECORDS,
    "mychart": E_MYCHART,
    "General": E_GENERAL,
    "Hotword-Urgent": E_HOTWORD_URGENT,
    "Switchboard / fallback": E_SWITCHBOARD_FALLBACK,
    "Switchboard (alt)": E_SWITCHBOARD_ALT,
    "Transfer error": E_TRANSFER_ERROR,
    "Hangup": E_HANGUP,
}


# ===========================================================================
# Script renderer + speech guards (task 4.2)
# ===========================================================================
#
# These are the switchboard's pure, side-effect-free speech helpers. They do no
# I/O and never print; they operate purely on strings and the placeholder mapping
# they are given, which keeps them independently unit/property-testable and
# reusable from nodes/tools.


class SwitchboardSpeechError(Exception):
    """Base class for switchboard speech-safety violations."""


class NarrationGuardError(SwitchboardSpeechError):
    """Raised when caller-facing speech leaks an internal artifact.

    Signals a violation of Requirement 4.1 (never speak system names, JSON,
    UUIDs, or Call State Ledger field names). The message names the offending
    fragment so the caller of the guard can log/diagnose it.
    """


class MedicationLeakError(SwitchboardSpeechError):
    """Raised when speech would emit a medication name.

    Signals a violation of Requirements 4.2 / 11.4 (never repeat the medication
    name when referring to a prescription).
    """


# --- render ----------------------------------------------------------------


def _placeholder_token_forms(name: str) -> tuple[str, str, str]:
    """Return the three authored token spellings for a placeholder ``name``.

    ``scripts.py`` reproduces the vendor's (internally inconsistent) token syntax
    verbatim, so a single logical placeholder may appear as a double-brace token
    (``{{caller_name}}``, ``{{FirstName}}``), a single-brace token
    (``{FirstName}``), or a bracket token (``[digit 1]``, ``[symptom]``). A
    ``placeholders`` key therefore substitutes whichever of these three spellings
    of that key is present in the template.

    The token strings are built by literal concatenation (never an f-string /
    ``str.format``), so a ``name`` such as ``"digit 1"`` yields exactly
    ``"[digit 1]"`` without any format-string interpretation.
    """
    return ("{{" + name + "}}", "{" + name + "}", "[" + name + "]")


def render(template: str, placeholders: Mapping[str, str]) -> str:
    """Substitute runtime placeholder tokens into a verbatim script line.

    Only the tokens for keys present in ``placeholders`` are replaced; every other
    character of ``template`` is preserved byte-for-byte. This is what makes the
    renderer safe for the mandatory Appendix C/E lines: punctuation, curly
    apostrophes (``’``), em dashes (``—``), and Script 3′'s deliberate
    comma-before-"and" are never touched (Requirements 18.1, 18.3, 18.4).

    Token matching. For each ``placeholders`` key ``name`` the renderer looks for
    the three authored spellings ``{{name}}``, ``{name}``, and ``[name]`` (see
    :func:`_placeholder_token_forms`) and replaces any that occur. Matching and
    substitution are performed in a **single left-to-right pass** built from the
    literal (regex-escaped) token strings, with longer tokens tried first so a
    double-brace ``{{FirstName}}`` is consumed as a whole and never mis-read as a
    single-brace ``{FirstName}`` wrapped in stray braces.

    Literal substitution. Replacement values are inserted verbatim by a plain
    lookup function — they are **never** interpreted as format specifiers or
    regex, so a value like ``"{LastName}"`` or ``"$1"`` cannot trigger a second
    substitution or a regex-injection surprise. Because the scan is single-pass,
    an inserted value is never itself re-scanned for further tokens.

    Missing tokens. A token whose key is absent from ``placeholders`` is left
    untouched in the output. Callers that require every token to be filled before
    speaking (Requirement 18.3) should supply all keys and/or run
    :func:`assert_no_internal_narration` on the result — an unfilled
    ledger-derived token such as ``{{caller_name}}`` is itself an internal
    artifact and is rejected by that guard.

    Args:
        template: A verbatim script line (typically an Appendix C/E constant).
        placeholders: Mapping of placeholder name → literal replacement value.

    Returns:
        ``template`` with the provided placeholder tokens substituted and all
        other text preserved exactly.
    """
    if not placeholders:
        return template

    token_to_value: dict[str, str] = {}
    for name, value in placeholders.items():
        for token in _placeholder_token_forms(name):
            token_to_value[token] = value

    # Try longer tokens first so `{{X}}` wins over the `{X}` nested inside it.
    ordered_tokens = sorted(token_to_value, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(token) for token in ordered_tokens))

    # The replacement is a function returning the literal value, so placeholder
    # values are never interpreted as regex/format templates.
    return pattern.sub(lambda match: token_to_value[match.group(0)], template)


# --- narration guard (Requirement 4.1) -------------------------------------

#: UUID (any version/variant) — an internal identifier that must never be spoken.
_UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

#: A quoted JSON-style key immediately followed by a colon, e.g. ``"intent":``.
_JSON_KEY_PATTERN = re.compile(r"""["'][^"']+["']\s*:""")

#: Any snake_case identifier (a word containing an underscore). Fully-rendered
#: caller speech contains no underscores, so such a token is always an internal
#: system/ledger identifier (e.g. ``patient_lookup``, ``caller_name``) rather
#: than natural language.
_SNAKE_CASE_IDENTIFIER_PATTERN = re.compile(r"\b\w*_\w+\b")

#: Explicit internal system names that are not snake_case (so the identifier
#: pattern above would miss them). CamelCase is NOT flagged generically because
#: legitimate caller-facing brand words are CamelCase (``SpinSci``, ``MyChart``).
_SYSTEM_NAMES: frozenset[str] = frozenset({"CallStateLedger"})

#: Call State Ledger field names that read as machine identifiers, derived from
#: :data:`api.services.switchboard.ledger.LEDGER_FIELD_NAMES` (never duplicated
#: here) so the guard tracks the ledger definition. Only fields containing an
#: underscore are included: the remaining bare-word fields (``intent``,
#: ``specialty``, ``location``) are ordinary English words that appear in
#: mandatory Appendix C lines (e.g. the ROUTING REQUEST asks for the
#: "specialty, or location"), so flagging them would reject legitimate speech.
#: Those bare words only ever leak as artifacts inside JSON/structure, which the
#: JSON checks below already catch.
_LEDGER_FIELD_ARTIFACTS: frozenset[str] = frozenset(
    name for name in LEDGER_FIELD_NAMES if "_" in name
)


def find_internal_narration(speech: str) -> Optional[str]:
    """Return a description of the first internal artifact in ``speech``, or None.

    Detects the artifact classes named by Requirement 4.1 in the **final rendered
    speech** (run this after :func:`render`, so a legitimately substituted value
    such as an actual caller name is plain text and does not trip the guard, while
    a raw ledger field name that leaked into speech does):

    * **UUIDs** — canonical 8-4-4-4-12 hexadecimal identifiers.
    * **JSON / structure** — curly braces, square brackets (also unfilled
      placeholder tokens such as ``{{caller_name}}`` / ``[digit 1]``), or a quoted
      ``"key":`` pair.
    * **Call State Ledger field names** — the underscored ledger identifiers from
      :data:`_LEDGER_FIELD_ARTIFACTS`.
    * **Other system names** — the explicit :data:`_SYSTEM_NAMES` and any other
      snake_case identifier (tool names, internal variables), which never occur in
      natural caller speech.

    Args:
        speech: The final caller-facing speech string to inspect.

    Returns:
        A short human-readable reason for the first artifact found, or ``None``
        when the speech is clean.
    """
    uuid_match = _UUID_PATTERN.search(speech)
    if uuid_match:
        return f"contains a UUID: {uuid_match.group(0)!r}"

    for char in ("{", "}", "[", "]"):
        if char in speech:
            return f"contains JSON/structure character {char!r}"

    json_key = _JSON_KEY_PATTERN.search(speech)
    if json_key:
        return f"contains a JSON-style key: {json_key.group(0)!r}"

    for name in _SYSTEM_NAMES:
        if re.search(rf"\b{re.escape(name)}\b", speech):
            return f"contains an internal system name: {name!r}"

    for field in _LEDGER_FIELD_ARTIFACTS:
        if re.search(rf"\b{re.escape(field)}\b", speech):
            return f"contains a Call State Ledger field name: {field!r}"

    identifier = _SNAKE_CASE_IDENTIFIER_PATTERN.search(speech)
    if identifier:
        return f"contains an internal identifier: {identifier.group(0)!r}"

    return None


def assert_no_internal_narration(speech: str) -> str:
    """Return ``speech`` unchanged, or raise if it leaks an internal artifact.

    Guard wrapper around :func:`find_internal_narration` enforcing Requirement 4.1
    on any caller-facing line before it is spoken. Returns the input so it can be
    used inline (``spoken = assert_no_internal_narration(render(...))``).

    Args:
        speech: The final caller-facing speech string.

    Returns:
        ``speech`` unchanged when it is free of internal artifacts.

    Raises:
        NarrationGuardError: If ``speech`` contains a system name, JSON, a UUID,
            or a Call State Ledger field name.
    """
    reason = find_internal_narration(speech)
    if reason is not None:
        raise NarrationGuardError(f"Speech {reason}: {speech!r}")
    return speech


# --- medication-name omission (Requirements 4.2, 5.1, 11.4) ----------------


def prescription_speech(
    medication_name: Optional[str] = None, *, transferring: bool = False
) -> str:
    """Return prescription/pharmacy speech that never names the medication.

    Produces caller-facing speech about a prescription/medication using the
    mandated verbatim wording rather than any generated line: the Greeting
    medication acknowledgment :data:`GREETING_MEDICATION` ("You’re calling about
    your prescription.") or, when handing the caller to the pharmacy queue, the
    Appendix E pharmacy transfer line :data:`E_PHARMACY` ("Let me connect you with
    someone who can help with your medication. One moment."). Neither line
    contains a medication name, satisfying Requirements 4.2 / 11.4 while staying
    concise and TTS-friendly (Requirement 5.1).

    ``medication_name`` is accepted only as *context* (what the caller is calling
    about); it is never inserted into the returned speech. When provided, it is
    used defensively to assert the chosen line does not contain it, so the
    omission guarantee holds even if the verbatim constants are ever edited.

    Args:
        medication_name: The medication the caller mentioned, if any. Used only to
            verify omission — never spoken.
        transferring: When ``True`` return the pharmacy transfer line; otherwise
            return the Greeting prescription acknowledgment.

    Returns:
        The verbatim prescription/pharmacy line, guaranteed free of the medication
        name.

    Raises:
        MedicationLeakError: If the selected line would contain ``medication_name``
            (only possible if the verbatim constants are changed to include it).
    """
    line = E_PHARMACY if transferring else GREETING_MEDICATION

    if medication_name is not None:
        needle = medication_name.strip()
        if needle and needle.lower() in line.lower():
            raise MedicationLeakError(
                f"Prescription speech would emit the medication name "
                f"{medication_name!r}: {line!r}"
            )

    return line


__all__ = [
    # Appendix C — Greeting
    "GREETING_ROUTING_REQUEST",
    "GREETING_SCRIPT_4_STANDARD_IN_HOURS",
    "GREETING_SCRIPT_3_PRIME_AFTER_HOURS",
    "GREETING_SCRIPT_2_PRIME_PERSONALIZED",
    "GREETING_PATH_A_PERSONALIZED",
    "GREETING_PATH_A_STANDARD",
    "GREETING_PATH_B",
    "GREETING_PATH_D",
    "GREETING_PATH_E",
    "GREETING_MEDICATION",
    "GREETING_GOODBYE_RETENTION",
    "GREETING_HANGUP",
    # Appendix C — Business Hours
    "BH_FAQ_LOOKUP",
    "BH_OTHER_LOOKUP",
    "BH_DIRECTORY_CLOSE",
    "BH_SCHEDULING_GATE",
    "BH_SEARCH_TROUBLE",
    "BH_RETRY_1",
    "BH_RETRY_2",
    "BH_LIST_CAP",
    "BH_GOODBYE_RETENTION",
    "BH_CLOSING",
    # Appendix C — After Hours
    "AH_PAGING_CLARIFIER_OPTION_1",
    "AH_PAGING_CLARIFIER_OPTION_2",
    "AH_PAGING_CLARIFIER_OPTION_3",
    "AH_PAGING_CLARIFIER_OPTIONS",
    "AH_RESTRICTED_SERVICE_SCHEDULING",
    "AH_MYCHART_CLOSED",
    "AH_BILLING_CLOSED",
    "AH_DIRECTORY_GATE",
    "AH_NO_MATCH",
    "AH_LIVE_CONNECT_OFFER",
    "AH_RETRY_1",
    "AH_RETRY_2",
    "AH_FOLLOW_UP_OPTION_1",
    "AH_FOLLOW_UP_OPTION_2",
    "AH_FOLLOW_UP_OPTIONS",
    # Appendix C — Authentication
    "AUTH_ANI_OFFER",
    "AUTH_PHONE_PROVIDER",
    "AUTH_PHONE_PATIENT",
    "AUTH_PHONE_READBACK",
    "AUTH_NO_RECORD",
    "AUTH_DOB_PATIENT",
    "AUTH_DOB_PROVIDER",
    "AUTH_NAME_CONFIRM",
    "AUTH_AFTER_CONFIRM",
    "AUTH_FAIL_ROUTE",
    "AUTH_PUSHBACK",
    "AUTH_CHANGED_REQUEST",
    "AUTH_AFTER_HOURS_DOB_OPENER",
    # Appendix C — Scheduling Init (downstream)
    "SCHED_INIT_VISIT_REASON",
    "SCHED_INIT_WELLNESS_SYMPTOM_DISAMBIGUATION",
    "SCHED_INIT_PROVIDER_UNAVAILABLE",
    # Appendix E — Transfer lines
    "E_SCHEDULING_NEW",
    "E_SCHEDULING_EXISTING",
    "E_TRIAGE",
    "E_REFERRALS",
    "E_PAGING",
    "E_PHARMACY",
    "E_BILLING",
    "E_RECORDS",
    "E_MYCHART",
    "E_GENERAL",
    "E_HOTWORD_URGENT",
    "E_SWITCHBOARD_FALLBACK",
    "E_SWITCHBOARD_ALT",
    "E_TRANSFER_ERROR",
    "E_HANGUP",
    "APPENDIX_E_TRANSFER_LINES",
    # Renderer + speech guards (task 4.2)
    "SwitchboardSpeechError",
    "NarrationGuardError",
    "MedicationLeakError",
    "render",
    "find_internal_narration",
    "assert_no_internal_narration",
    "prescription_speech",
]
