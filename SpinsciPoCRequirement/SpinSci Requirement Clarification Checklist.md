# SpinSci Requirement Clarification Checklist

| Version | 1.0 |
|---|---|
| **Date** | 2025-01-27 |
| **Purpose** | Joint product and technical workshop — resolve ambiguities before implementation |
| **Scope** | PoC, sandbox integration, and pilot readiness |
| **Source** | SpinSci Switchboard and Scheduling Requirements v2.1 |

---

## How to use this document

Each question targets a specific ambiguity, missing detail, or unstated dependency in the
requirements document. Questions are prioritized:

- **Blocker** — cannot begin or complete the affected workstream without a decision.
- **High** — can begin work with assumptions but risk rework if the answer differs.
- **Medium** — does not block implementation but affects pilot quality or operations.

Record decisions in the table at the bottom during the workshop. Questions that remain open
should be assigned an owner and due date.

---

## Blocker priority

### Q1. API contract delivery timeline

**Requirement ref:** REQ-ARCH-01, Integration capabilities table, Scheduling experience

**Question:** When will finalized API contracts (OpenAPI/schema definitions, sample
requests/responses, error codes, and rate limits) be available for every required backend
capability — patient lookup, directory, FAQ, DOB validation, identity verification, routing
intent resolution, route metadata resolution, transfer, hangup, scheduling handoff, and the
Scheduling Engine?

**Why it matters:** Implementation is scaffolded with mocks. Real integration cannot begin until
contracts are stable. Unstable contracts after sandbox work begins add 1–3 weeks.

**Owner:** SpinSci technical

---

### Q2. Scheduling Init and Engine ownership

**Requirement ref:** Scheduling experience, REQ-SCHED-06 through REQ-SCHED-14

**Question:** Which party owns the implementation of Scheduling Init (visit-type classification,
reason-for-visit collection, urgency screening) and the SpinSci Scheduling Engine API (provider
availability, slot search, booking, cancel, reschedule, list, confirm)? Is the vendor
responsible for the dialogue and decision logic of Scheduling Init, or does SpinSci provide it
as a downstream API?

**Why it matters:** The boundary between switchboard orchestration and scheduling backend
determines effort, testing surface, and where defects are resolved.

**Owner:** SpinSci product + technical

---

### Q3. Specialty-to-scheduling-agent mapping

**Requirement ref:** REQ-SCHED-01, REQ-SCHED-02, REQ-SCHED-03

**Question:** Which specialties are activated for scheduling in the PoC and pilot? What is the
exact mapping from specialty to scheduling agent? What is the approved behavior when a caller
requests a specialty that is not activated?

**Why it matters:** The switchboard must validate specialty before handoff. An incomplete mapping
causes runtime failures or incorrect routing during acceptance testing.

**Owner:** SpinSci product

---

### Q4. After-hours hotword catalog

**Requirement ref:** Vendor delivers / SpinSci provides, After Hours phase, Req 21 (TBD)

**Question:** What is the final list of hotword keywords? For each hotword, what urgency action
applies (immediate silent route, specific transfer destination, escalation to a live agent)?
When will this list be delivered?

**Why it matters:** Hotword detection is tested in POC-04 and AC-05. Without the catalog,
hotword QA cannot complete and the after-hours path cannot be fully accepted.

**Owner:** SpinSci product

---

### Q5. Telephony provider and transfer mechanism

**Requirement ref:** Integration capabilities — Transfer, Out of scope — low-level telephony wiring

**Question:** Which telephony provider and transfer mechanism (warm/cold/conference) will the
PoC and pilot use? Where does vendor responsibility end and SpinSci's telephony team begin?
Does "low-level telephony wiring out of scope" mean the vendor implements the transfer tool
against an existing provider API, or that a separate team provisions the carrier/SIP
infrastructure?

**Why it matters:** Transfer is exercised in nearly every acceptance scenario. A misunderstood
boundary blocks sandbox integration and pilot telephony testing.

**Owner:** SpinSci technical + telephony

---

### Q6. Routing destinations and metadata

**Requirement ref:** Appendix B, REQ-ROUTE-01, Integration capabilities — routing intent/metadata

**Question:** What are the authoritative routing intent strings, destination metadata payloads,
queue identifiers, and transfer phone numbers/SIP URIs for every route in Appendix B? Are these
static configuration or dynamically resolved per organization/location?

**Why it matters:** The sequential routing chain must use exact strings returned by the listing
API. Without authoritative values, routing and transfer acceptance tests cannot be validated.

**Owner:** SpinSci technical

---

### Q7. Scheduling Engine sandbox availability

**Requirement ref:** REQ-SCHED-10 through REQ-SCHED-14, POC-01/01b/11/12/13/14/15/16

**Question:** Will a functional sandbox of the Scheduling Engine be available for integration
testing — including provider availability queries, slot search, booking confirmation, cancel,
reschedule, list, and confirm responses? What test data (patients, providers, appointments) will
be seeded?

**Why it matters:** Eight of the eighteen acceptance scenarios exercise the Engine. Without a
working sandbox, integration testing is blocked and defect resolution is delayed.

**Owner:** SpinSci technical

---

### Q8. Acceptance scenario count confirmation

**Requirement ref:** POC acceptance — Minimum test scenarios

**Question:** The document lists POC-01 through POC-16, but POC-01 has two additional variants
(POC-01b: existing sick, POC-01c: new in-hours). Does acceptance require passing 16 or 18
discrete scenario executions? Are there additional unlisted scenarios implied by the "Optional
detailed edge-case annexes"?

**Why it matters:** Test harness design, effort estimation, and acceptance sign-off criteria
depend on the exact scenario count.

**Owner:** SpinSci product

---

## High priority

### Q9. Transfer destination for unverified callers

**Requirement ref:** REQ-AUTH-01, GATE-AUTH, AC-11, POC-06

**Question:** After authentication failure or refusal, the caller is still connected ("No
problem. I'll connect you now."). Where exactly is the caller transferred — the originally
intended destination, a general switchboard queue, or a specific fallback? What patient context
(if any) may be included in the transfer payload for an unverified caller?

**Why it matters:** Incorrect transfer destinations for unverified callers could expose PHI or
route callers to the wrong team.

**Owner:** SpinSci product + security

---

### Q10. Multiple ANI matches

**Requirement ref:** Greeting phase, Authentication phase, Appendix D — greeting_ani_match_count

**Question:** When ANI lookup returns multiple patient matches (count > 1), what is the expected
behavior? Should the switchboard ask the caller to identify themselves, present options, or
proceed without personalization? How many phone-number retry attempts are allowed before
routing without verification?

**Why it matters:** The greeting personalization path and Script 2' depend on exactly one match.
Multi-match behavior is unspecified and affects both greeting and authentication flows.

**Owner:** SpinSci product

---

### Q11. Business-hours edge cases

**Requirement ref:** Session and schedule, REQ-ARCH-03

**Question:** Are closing times inclusive or exclusive (does a call arriving at exactly 17:00
count as business hours)? Are holidays or emergency closures supported, and if so, is the
calendar configurable at runtime or hardcoded for the PoC?

**Why it matters:** Edge-case scheduling logic affects after-hours gating. Holiday support
requires a configurable calendar rather than a static function.

**Owner:** SpinSci product

---

### Q12. Welcome audio and the "no system names" rule

**Requirement ref:** REQ-ARCH-05, Greeting phase — welcome audio, AC-03

**Question:** The configured welcome audio says "This is SpinSci AI, your virtual assistant."
Is "SpinSci AI" an approved exception to REQ-ARCH-05 ("SpinSci AI never speaks system names")?
Or does REQ-ARCH-05 refer only to internal technical system names (JSON, UUIDs, ledger fields)
and not the product's caller-facing brand name?

**Why it matters:** Verbatim fidelity testing (Property 23, AC-03) must know whether "SpinSci
AI" in the welcome is a violation or an intentional brand reference.

**Owner:** SpinSci product

---

### Q13. Directory: information-only versus connection

**Requirement ref:** Appendix B — Directory row, Business Hours phase

**Question:** What determines whether a Directory call ends in an information-only goodbye
versus a live transfer? Is it caller intent ("just looking for a phone number" vs. "connect me
to Dr. Smith"), or a directory-record attribute? When does Directory require authentication
(the table says "If connecting")?

**Why it matters:** The routing graph must model two terminal paths (goodbye vs. transfer) and
conditionally gate authentication, but the decision criteria are not defined.

**Owner:** SpinSci product

---

### Q14. Appointment disambiguation for manage actions

**Requirement ref:** REQ-SCHED-09b, REQ-SCHED-09c, REQ-SCHED-09d, REQ-SCHED-09e

**Question:** When a patient has multiple upcoming appointments in the same specialty, how
should the Engine identify the target appointment for cancel, reschedule, or confirm? Should it
ask the caller to select, use the nearest upcoming appointment, or rely on
`existing_appointment_date` from the ledger? What happens if no matching appointment is found?

**Why it matters:** Ambiguous appointment selection leads to incorrect cancellations or
rescheduling. The no-match path is untested without a defined behavior.

**Owner:** SpinSci product + technical

---

### Q15. Cancel/reschedule confirmation and atomicity

**Requirement ref:** REQ-SCHED-09b, REQ-SCHED-09c

**Question:** Must cancel and reschedule actions receive explicit caller confirmation before
committing? For reschedule, if a new slot is booked but the old appointment cancellation fails,
what is the expected state — rollback the new booking, keep both, or escalate to a live agent?

**Why it matters:** Healthcare scheduling errors are costly. Without an explicit confirmation
and failure-handling contract, the pilot risks appointment data integrity issues.

**Owner:** SpinSci product + technical

---

### Q16. Urgency escalation rules and fallback

**Requirement ref:** REQ-SCHED-14, After Hours — Restricted services

**Question:** What exact symptoms or keyword patterns trigger urgency escalation during
sick-visit scheduling? Where should urgent calls route — nurse triage, emergency line, or live
agent? If the escalation destination is unavailable or the caller declines, should scheduling
resume or should the call end?

**Why it matters:** Urgency handling in a healthcare context is safety-critical. Incorrect
routing or silent failure could have patient-safety implications.

**Owner:** SpinSci product + clinical

---

## Medium priority

### Q17. API failure behavior

**Requirement ref:** Integration capabilities, Error Handling (implied)

**Question:** For each backend API (patient lookup, directory, identity, routing, scheduling),
what is the expected caller-facing behavior on timeout, 5xx error, rate limit, or malformed
response? Should the switchboard retry silently, inform the caller, or route to a fallback? Are
there idempotency requirements for booking and cancellation calls?

**Why it matters:** Unspecified failure behavior leads to inconsistent caller experience during
pilot. Idempotency gaps risk duplicate bookings or cancellations.

**Owner:** SpinSci technical

---

### Q18. Latency targets

**Requirement ref:** Greeting phase (2s ANI bound), Integration capabilities

**Question:** Beyond the 2-second ANI lookup bound, are there latency targets or SLAs for
directory lookup, authentication, route resolution, Scheduling Engine slot search, and
transfer initiation? What is the maximum acceptable end-to-end silence between caller speech
and system response?

**Why it matters:** Latency budgets determine timeout configuration, retry strategy, and whether
"One moment" speech should be inserted before slow operations.

**Owner:** SpinSci technical + product

---

### Q19. PHI, logging, and data retention

**Requirement ref:** Security (implied), pilot operations

**Question:** What PHI may be logged, recorded, or stored during the pilot? Must call
transcripts be retained or purged? Are there masking requirements for DOB, phone numbers, or
patient IDs in operational logs? What retention period applies?

**Why it matters:** Healthcare telephony handles sensitive data. Incorrect logging or retention
can violate HIPAA or organizational policy and block pilot approval.

**Owner:** SpinSci security + compliance

---

### Q20. Configuration ownership for pilot operations

**Requirement ref:** SpinSci provides separately, Session and schedule, Appendix C/E

**Question:** Who owns ongoing configuration changes to scripts, business-hours schedule,
hotword catalog, specialty mappings, routing destinations, and transfer lines during the pilot?
Is there an approval workflow, or can SpinSci operations update configuration independently?

**Why it matters:** Configuration changes after acceptance can invalidate verbatim-speech tests
or routing behavior. A clear change-management process prevents pilot regressions.

**Owner:** SpinSci operations + product

---

## Decision capture table

| # | Priority | Decision | Owner | Due date | Notes |
|---|---|---|---|---|---|
| Q1 | Blocker | | | | |
| Q2 | Blocker | | | | |
| Q3 | Blocker | | | | |
| Q4 | Blocker | | | | |
| Q5 | Blocker | | | | |
| Q6 | Blocker | | | | |
| Q7 | Blocker | | | | |
| Q8 | Blocker | | | | |
| Q9 | High | | | | |
| Q10 | High | | | | |
| Q11 | High | | | | |
| Q12 | High | | | | |
| Q13 | High | | | | |
| Q14 | High | | | | |
| Q15 | High | | | | |
| Q16 | High | | | | |
| Q17 | Medium | | | | |
| Q18 | Medium | | | | |
| Q19 | Medium | | | | |
| Q20 | Medium | | | | |
