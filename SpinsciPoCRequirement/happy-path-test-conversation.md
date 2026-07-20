# SpinSci Switchboard — Happy-Path Test Conversation

A turn-by-turn script for manually testing the switchboard end-to-end over a
WebRTC call. Read the **Caller says** lines aloud; check what SpinSci AI says
against the **AI says (expected)** lines.

Scenario: **POC-01 — Scheduling, existing patient, in business hours.** An
existing patient calls during business hours to book an appointment with a
specialty. This path exercises every switchboard phase:

> Greeting → Business Hours (intent classify → scheduling gate) → Authentication → Routing → transfer

## Prerequisites

- Test the workflow **"SpinSci Switchboard (routing-fix)" (workflow id 24)** — the
  latest fixed snapshot. Older snapshots (workflow 9, 22) have known bugs.
- Call during **business hours** (America/Chicago, Mon–Fri 8:00 AM–5:00 PM or
  Sat 8:00 AM–12:00 PM) so `after_hours = false` and the in-hours scripts play.
- Connectors run against their **mock backends** in dev (patient lookup,
  directory, identity), so any reasonable phone number / DOB will be accepted.

Notation: lines marked **[verbatim]** are mandatory Appendix C / E wording and
should match word-for-word. Lines marked *[dynamic]* are generated and only
need to match in intent. Italic *(internal)* notes are what's happening behind
the scenes — the caller never hears these.

---

## The conversation

### Turn 1 — Greeting (welcome + routing request)

*(internal: turn 1 is silent except the welcome; a patient lookup runs on the
calling number via pre-call fetch — no speech about it.)*

**AI says (expected) [verbatim]:**
> Thank you for calling SpinSci. This is SpinSci AI, your virtual assistant. To ensure your call is routed correctly, please provide the provider, specialty, or location you are trying to reach, along with the reason for your call today.

**Caller says:**
> Hi, I'd like to schedule an appointment with cardiology.

*(internal: this gives a routing signal — intent = Scheduling,
appointment_action = create, specialty = Cardiology. Greeting takes **Path A**
and hands off to Business Hours on the same turn.)*

### Turn 2 — Path A acknowledgment → Business Hours

**AI says (expected) [verbatim]:**
> Let me help you with that.

*(internal: silent transition into Business Hours → BH Intent Classify. The
classifier confirms intent = Scheduling with appointment_action = create, so it
moves to the Scheduling Gate.)*

### Turn 3 — Scheduling gate (new vs existing)

**AI says (expected) [verbatim]:**
> Are you a new or existing patient?

**Caller says:**
> I'm an existing patient.

*(internal: patient_status = existing. An existing scheduling request requires
authentication before routing, so the switchboard silently enters the
Authentication phase. There is no spoken line on this transition.)*

### Turn 4 — Authentication (verify before routing)

*(internal: the exact prompts can vary — the agent may offer to use the calling
number (ANI) first, then ask for date of birth, then confirm the name. Answer
naturally. Expected mandated lines below.)*

**AI says (expected) [verbatim, one of the phone prompts]:**
> I can use the phone number you're calling from to look up your record. Is that okay?

**Caller says:**
> Yes, that's fine.

**AI says (expected) [verbatim]:**
> Could you please provide your date of birth?

**Caller says:**
> January 5th, 1985.

**AI says (expected) [verbatim, name confirm — name comes from the record]:**
> Can you confirm the full name for the patient is {{FirstName}} {{LastName}}?

*(the name is filled from the looked-up record; in dev the mock returns a
placeholder such as "Mock Patient", so expect that name rather than your own.)*

**Caller says:**
> Yes, that's me.

**AI says (expected) [verbatim]:**
> Thank you for confirming.

*(internal: patient_verified = Success. Silent transition to Routing — no filler,
no "one moment" before the transfer line.)*

### Turn 5 — Routing → transfer (terminal)

*(internal: routing resolves the destination silently. Because this is an
existing-patient scheduling request, the caller is handed off to the scheduling
team for the specialty. Only the transfer line is spoken.)*

**AI says (expected) [verbatim]:**
> Let me connect you with our scheduling team for existing patients. One moment.

*(internal: downstream, Scheduling Init would ask the visit reason to set
visit_type (sick vs wellness) and the Scheduling Engine would offer slots — that
is a separate layer from the switchboard and may or may not continue in this
PoC build. Reaching this transfer line is switchboard success.)*

---

## What "pass" looks like (acceptance checkpoints)

| Check | Requirement | Pass criteria |
|---|---|---|
| Turn 1 is silent apart from the welcome | AC-01 | No system names/JSON; welcome + routing request only |
| Path A acknowledgment on the same turn as handoff | AC-02 | "Let me help you with that." then Business Hours |
| No internal narration | AC-03 | Never hear field names, JSON, tool names, or UUIDs |
| Auth and Routing transitions are silent | AC-04 / AC-07 | No filler between confirming identity and the transfer line |
| Scheduling asks new/existing before auth | AC-10 | "Are you a new or existing patient?" is asked |
| Specialty captured before handoff | AC-14 | Cardiology carried through; routes to the scheduling handoff |
| Transfer line only on the terminal turn | AC-08 | Exactly the Appendix E line, nothing extra |
| Correct appointment_action | AC-21 | Classified as `create` (not defaulted) |

---

## Tips for staying on the happy path

- Give the **specialty and the reason together** on your first reply (e.g.
  "schedule with cardiology") so Greeting can take Path A immediately.
- If the agent asks you to repeat or says it didn't catch you, speak a clear
  short phrase like "Cardiology appointment, please."
- Answer the new/existing question with a plain **"existing"** to trigger the
  authentication → scheduling handoff path.
- Any plausible phone/DOB works against the dev mocks; you don't need a real
  record.

## Quick variations to try next (still happy paths)

- **Records (skips auth):** first reply "I need my medical records." Expect no
  new/existing question, no auth, and a direct transfer:
  "Let me get you over to the Records department. One moment." (POC-02, AC-09)
- **Cancel (manage action):** first reply "I need to cancel my cardiology
  appointment." Expect appointment_action = cancel, **no** new/existing
  question, straight to authentication, then the existing-scheduling handoff.
  (POC-14, AC-20)
- **General help (unsure caller):** first reply "I'm not sure who I need to talk
  to." Expect **no** "I didn't catch that" loop — the agent should treat you as
  General and connect you: "Let me connect you with someone who can help. One
  moment." (validates the routing-fix)
