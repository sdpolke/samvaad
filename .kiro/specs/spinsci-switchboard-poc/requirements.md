# Requirements Document

## Introduction

This document specifies the requirements for a **Proof of Concept (PoC)** implementation of the
**SpinSci AI Virtual Switchboard** — an **inbound** phone switchboard and support agent for a
healthcare provider network. The PoC demonstrates end-to-end inbound calls that greet the caller,
determine business vs. after-hours behavior, authenticate the patient when required, resolve the
correct destination, and either transfer the caller or hang up — while speaking only mandated,
verbatim scripts and never revealing internal system behavior.

**This is an inbound support-team system, not an outbound calling campaign.** Inbound-specific
behavior (inbound entry/trigger, ANI-based caller lookup on the first turn, business-hours vs.
after-hours routing on the America/Chicago schedule, authentication gating before transfer,
verbatim caller scripts, silent phase transitions, and terminal transfer/hangup turns where only
the prescribed line is spoken) is first-class and specified in full.

**Workflow-graph framing.** This system MUST be modeled on top of the existing graph-based
workflow engine in this repository (`api/services/workflow/`), in which a workflow is a validated
directed graph of nodes (`startCall`, `agentNode`, `endCall`, `globalNode`, `trigger`, `webhook`,
`qa`) connected by edges that carry a `condition` and a `transition_speech`. Nodes carry prompts,
extraction variables (`extraction_variables`), tool references (`tool_uuids`), document references
(`document_uuids`), greeting configuration, and pre-call fetch. The Pipecat engine
(`api/services/pipecat/`) drives the conversation, and telephony providers
(`api/services/telephony/`) handle transfer and hangup. The five conversation phases and the shared
Call State Ledger map onto this model: **phases are node clusters**, the **ledger is the set of
extracted/gathered context variables** passed across the graph, **silent turns are agent nodes that
run tools but emit no speech**, **transition speech lives on edges**, and **backend connectors are
custom/MCP tools** referenced by nodes.

**Samvaad scope.** This PoC is built ON the in-repo Samvaad/Dograh workflow engine
(`api/services/workflow/`) itself. It MUST NOT introduce a dependency on any external Samvaad-integration
pipeline beyond that in-repo engine. The design MUST remain future-integration-friendly, keeping future
SpinSci expansion and any later broader Samvaad integration possible without rework (captured as a
non-functional requirement).

**External contracts.** SpinSci provides API schemas and integration contracts for backend services
separately, and provides the after-hours hotword keyword list separately (marked TBD). These are
treated as external integration contracts, and this document does not define their wire formats.

Traceability tags from the vendor document (`REQ-`, `GATE-`, `AC-`, `POC-`) are referenced in
requirements where helpful.

## Glossary

- **Switchboard**: The inbound SpinSci AI Virtual Switchboard orchestrator, modeled as a single workflow graph. Primary system actor in this document.
- **Workflow_Engine**: The repository's graph-based workflow engine (`api/services/workflow/`) that validates and executes the directed graph of nodes and edges.
- **Node_Cluster**: A group of workflow nodes implementing one conversation phase (Greeting, Business Hours, After Hours, Authentication, Routing).
- **Call_State_Ledger** (ledger): The single shared session record for a call, represented as the workflow's extracted/gathered context variables. Fields are listed in Requirement 15 (Appendix D of the vendor doc).
- **Conversation Phase** (phase): One of Greeting, Business Hours, After Hours, Authentication, Routing. Phases are invisible to the caller.
- **Phase Transition**: Movement between phases, modeled as traversal of a workflow edge carrying a `condition` and optional `transition_speech`.
- **Silent turn**: A conversation turn on which the Switchboard may run backend tools but emits no speech (an agent node with no spoken output / an edge with empty `transition_speech`).
- **ANI**: Automatic Number Identification — the caller's originating phone number, available at call start.
- **Internal intent** (`intent`): The ledger field classifying the caller's need (e.g., Scheduling, Referrals, Triage, Billing, mychart, Paging, Records, General, Directory, Hotword-Urgent).
- **Routing intent**: The destination string returned by routing intent resolution. It is NOT the same as the ledger `intent` (REQ-LEDGER-03).
- **after_hours**: A boolean set at call start from the America/Chicago business-hours schedule; controls business vs. after-hours behavior.
- **Business hours**: Monday–Friday 08:00–17:00, Saturday 08:00–12:00, Sunday closed, in America/Chicago.
- **Terminal action**: Transfer or hangup — ends the orchestration path.
- **Transfer message**: The single prescribed spoken line played when connecting the caller (Appendix E of the vendor doc).
- **appointment_action**: What the caller wants to do about an appointment: `create`, `cancel`, `reschedule`, `list`, or `confirm`.
- **visit_type**: Classification driving scheduling rules — `sick` or `wellness` — set in Scheduling Init for `create` only.
- **visit_reason**: Caller-stated reason for the visit, used to derive `visit_type`.
- **Scheduling_Init**: The first downstream scheduling segment after switchboard authentication; determines `visit_type` and reason for visit. Modeled as a downstream workflow segment/tool.
- **Scheduling_Engine** (SpinSci Scheduling Engine): The downstream system of record for scheduling logic — visit-type rules, provider availability, slot matching, booking, and locate/cancel/reschedule/list/confirm. Modeled as a downstream tool.
- **Scheduling agent**: The downstream agent for a specific specialty that collects visit type and hands off to the Scheduling_Engine.
- **hotword**: An after-hours urgent keyword (keyword list TBD from SpinSci) that triggers immediate silent routing to an urgent transfer line.
- **Restricted service**: An after-hours service (e.g., scheduling, referrals, triage) that is limited but may still connect the caller via an INFORM → ASK → wait → Auth → Route flow.
- **Path A / Path B / Path D / Path E**: Greeting script branches defined in Appendix C of the vendor doc.
- **Verbatim script**: A mandatory caller line whose wording MUST be reproduced exactly (Appendix C of the vendor doc).
- **Backend connector tool**: A workflow tool (custom or MCP) that wraps a SpinSci backend capability (patient lookup, directory lookup, FAQ/KB, DOB validation, identity verification, routing intent resolution, route metadata resolution, transfer, hangup, scheduling handoff, Scheduling_Engine).
- **Pre-call fetch**: The node capability that runs a data fetch before the node produces speech (used for the turn-1 ANI lookup).
- **Samvaad**: The in-repo Dograh workflow engine (`api/services/workflow/`) that is the substrate this PoC is built on. Distinct from a **Samvaad integration** — an external/broader integration pipeline beyond the in-repo engine — which is explicitly out of scope for this PoC.

## Requirements

### Requirement 1: Workflow-graph modeling of the switchboard

**User Story:** As a platform engineer, I want the switchboard modeled as a validated workflow graph on the existing engine, so that the five phases, shared state, and backend connectors reuse the repo's node/edge/tool primitives instead of a bespoke pipeline.

#### Acceptance Criteria

1. THE Switchboard SHALL be represented as a single directed workflow graph validated by the Workflow_Engine.
2. THE Switchboard SHALL implement each conversation phase (Greeting, Business Hours, After Hours, Authentication, Routing) as a Node_Cluster of one or more workflow nodes.
3. THE Switchboard SHALL model each Phase Transition as traversal of a workflow edge whose `condition` encodes the transition rule.
4. WHERE a Phase Transition speaks a line, THE Switchboard SHALL carry that line as the edge `transition_speech`.
5. WHERE a Phase Transition is silent, THE Switchboard SHALL leave the edge `transition_speech` empty.
6. THE Switchboard SHALL represent each Call_State_Ledger field as a workflow extraction or gathered-context variable.
7. THE Switchboard SHALL reference each backend connector capability as a workflow tool via node tool references.
8. THE Switchboard SHALL begin execution from an inbound entry node (inbound `startCall`/`trigger`), and SHALL NOT initiate outbound calls.

### Requirement 2: Single Call State Ledger for the whole call

**User Story:** As an orchestration designer, I want one shared ledger carried across all phases, so that state is consistent and facts are never lost between phases.

#### Acceptance Criteria

1. WHEN a call starts, THE Switchboard SHALL initialize exactly one Call_State_Ledger for that call. (REQ-ARCH-01)
2. WHEN a Phase Transition occurs, THE Switchboard SHALL pass the full Call_State_Ledger plus a call summary to the entered phase. (REQ-ARCH-01)
3. IF a Call_State_Ledger field is already populated, THEN THE Switchboard SHALL NOT ask the caller for that field again. (REQ-LEDGER-01, AC rule "Never re-ask")
4. THE Switchboard SHALL keep the ledger `intent` distinct from the Routing intent returned by routing intent resolution. (REQ-LEDGER-03)

### Requirement 3: Phase architecture and silent transitions

**User Story:** As a caller, I want the assistant to move between internal modules invisibly, so that the call feels like one continuous conversation.

#### Acceptance Criteria

1. THE Switchboard SHALL implement five phases in the order Greeting → (Business Hours or After Hours) → Authentication (when required) → Routing → terminal transfer or hangup. (REQ-ARCH-02)
2. THE Switchboard SHALL NOT tell the caller about phases, modules, or internal transitions. (REQ-ARCH-02)
3. WHEN transitioning to the Authentication phase, THE Switchboard SHALL emit no speech on that transition turn. (REQ-ARCH-04, AC-04)
4. WHEN transitioning to the Routing phase, THE Switchboard SHALL emit no speech on that transition turn. (REQ-ARCH-04, AC-04, POC-05)
5. WHERE the Greeting phase resolves via Path A, THE Switchboard SHALL be permitted to speak a single acknowledgment on the same turn as entering Business Hours or After Hours. (REQ-ARCH-04, AC-02)

### Requirement 4: Never narrate internals

**User Story:** As a caller, I want to hear natural language only, so that I never encounter system internals.

#### Acceptance Criteria

1. THE Switchboard SHALL NOT speak system names, JSON, UUIDs, or Call_State_Ledger field names to the caller. (REQ-ARCH-05, AC-03)
2. WHEN referring to a prescription, THE Switchboard SHALL NOT repeat the medication name. (Appendix C — Medication)
3. THE Switchboard SHALL NOT name a specific clinical team that has not been confirmed. (Routing — "Switchboard" rule)
4. THE Switchboard SHALL NOT use "Triage" as a directory specialty and SHALL use a real specialty or provider for directory lookups. (Business Hours — Triage lookup)

### Requirement 5: TTS-friendly, concise speech

**User Story:** As a caller, I want short, clear spoken responses, so that the assistant is easy to understand over the phone.

#### Acceptance Criteria

1. THE Switchboard SHALL produce concise, TTS-friendly speech using short sentences. (REQ-ARCH-06)
2. WHERE the Switchboard speaks a sequence of digits, THE Switchboard SHALL use periods to introduce pauses between digit groups. (REQ-ARCH-06, Appendix C phone read-back)

### Requirement 6: Greeting phase

**User Story:** As an inbound caller, I want to be greeted and asked for what I need, so that my call can be routed correctly.

#### Acceptance Criteria

1. WHEN a call connects, THE Greeting phase SHALL perform a patient lookup on the caller ANI on turn 1 as a silent turn, using pre-call fetch bounded to 2 seconds, and SHALL emit no Switchboard-generated speech on turn 1. (REQ-ARCH pre-call, AC-01, POC-07)
2. WHEN turn 1 completes, THE Greeting phase SHALL set `greeting_ani_lookup_done` to true and SHALL set `greeting_ani_match_count` to the number of matched records. (Appendix D)
3. IF the turn-1 ANI lookup fails or exceeds its 2-second bound, THEN THE Greeting phase SHALL set `greeting_ani_lookup_done` to true, SHALL set `greeting_ani_match_count` to 0, and SHALL continue without a caller-facing error. (REQ-ARCH pre-call, POC-07)
4. THE Greeting phase SHALL play the pre-configured welcome audio from configuration rather than from Switchboard-generated text. (AC-01)
5. THE Greeting phase SHALL select the caller-facing greeting script (Scripts 4, 4′, 2′, 3′, Path B, Path D as applicable) based on `after_hours` and on whether the caller record was personalized, where personalized means `greeting_ani_match_count` equals 1. (Appendix C)
6. WHEN the caller's utterance contains at least one of an intent, specialty, provider, or specific request, THE Greeting phase SHALL follow Path A by speaking the acknowledgment ("Let me help you with that." or the personalized variant) and transitioning to Business Hours or After Hours on the same turn. (AC-02, Appendix C Path A)
7. WHEN the caller's utterance contains none of an intent, specialty, provider, or specific request, THE Greeting phase SHALL request the provider, specialty, or location plus the reason for the call using the mandated ROUTING REQUEST wording. (Appendix C)
8. THE Greeting phase SHALL treat the caller name alone as insufficient to hand off, and SHALL require an intent, specialty, provider, or specific request before handing off. (Greeting "Ready to hand off" rule)
9. WHERE the Greeting phase pre-fills `intent` before Business Hours continues, THE Switchboard SHALL carry that intent forward on the ledger. (REQ-ROUTE-02)
10. IF the caller's utterance is not understood, THEN THE Greeting phase SHALL speak the Path E line ("I didn't quite catch that. Could you repeat that for me?"). (Appendix C Path E)
11. IF the caller's utterance is not understood on 3 consecutive turns, THEN THE Greeting phase SHALL stop repeating the Path E line and SHALL fall back to the mandated ROUTING REQUEST wording. (Appendix C Path E)

### Requirement 7: Business Hours phase

**User Story:** As an in-hours caller, I want my intent classified and my destination confirmed, so that I reach the right department.

#### Acceptance Criteria

1. WHILE `after_hours` is false, THE Business Hours phase SHALL classify the caller's `intent` from caller speech into a defined `intent` value before selecting a destination. (REQ-ROUTE-01)
2. WHEN the first provider/directory lookup on a turn occurs in Business Hours, THE Business Hours phase SHALL perform it as a silent turn without spoken filler. (GATE-LOOKUP-SPEECH exception, AC-13)
3. WHEN performing an FAQ lookup, THE Business Hours phase SHALL speak "Let me check that for you." and invoke the lookup on the same turn. (GATE-LOOKUP-SPEECH, Appendix C)
4. WHEN performing a non-FAQ, non-first-directory lookup, THE Business Hours phase SHALL speak "One moment." and invoke the lookup on the same turn. (GATE-LOOKUP-SPEECH, Appendix C)
5. WHEN `intent` is Scheduling and `appointment_action` is `create` and `patient_status` is null, THE Business Hours phase SHALL ask "Are you a new or existing patient?" before initiating authentication or routing. (AC-10, Appendix C)
6. WHEN `intent` is Scheduling, THE Business Hours phase SHALL set `appointment_action` from the caller's speech to one of: create, cancel, reschedule, list, or confirm. (REQ-SCHED-00, AC-21)
7. IF the caller expressed cancel, reschedule, list, or confirm, THEN THE Business Hours phase SHALL NOT set `appointment_action` to `create`. (REQ-SCHED-00, AC-21)
8. WHEN `appointment_action` is cancel, reschedule, list, or confirm, THE Business Hours phase SHALL treat the caller as an existing patient, skip the new/existing question, and proceed to Authentication after `specialty` is confirmed. (REQ-SCHED-00b, AC-21)
9. WHERE `intent` is Scheduling for an existing patient, THE Business Hours phase SHALL require a populated and confirmed `specialty` before handoff. (REQ-SCHED-01, AC-14)
10. WHEN `intent` is Records, THE Business Hours phase SHALL skip authentication and transition directly to Routing as a silent turn without spoken filler. (AC-09, POC-02)
11. IF the Business Hours phase cannot classify the caller's `intent` from caller speech, THEN THE Business Hours phase SHALL speak the Retry 1 wording on the first such failure and the Retry 2 wording on the second such failure. (Appendix C, POC-08)
12. IF the Business Hours phase still cannot classify `intent` after two spoken retries, THEN on the third consecutive failure THE Business Hours phase SHALL transition to Routing as a silent turn without spoken filler. (Retry policy, POC-08)
13. IF a directory or provider search returns no matching record, THEN THE Business Hours phase SHALL speak the "Search trouble" line offering to connect the caller. (Appendix C)

### Requirement 8: After Hours phase

**User Story:** As an after-hours caller, I want appropriate handling of limited services and urgent needs, so that I get help or a callback path even when offices are closed.

#### Acceptance Criteria

1. WHILE `after_hours` is true, THE After Hours phase SHALL handle the caller using after-hours behavior. (REQ-ARCH-03)
2. WHEN the caller requests a restricted service, THE After Hours phase SHALL inform the caller of the service limitation and SHALL ask whether to connect them before performing Authentication or Routing. (After Hours restricted services, POC-03)
3. WHEN a hotword is detected from the caller (patient), THE After Hours phase SHALL transition to Routing as a silent turn, SHALL set `patient_verified` to N/A, and SHALL use the urgent transfer line. (AC-05, POC-04, Appendix E Hotword-Urgent)
4. WHEN the caller requests Billing, THE After Hours phase SHALL speak the mandated "Billing closed" line and SHALL NOT perform an in-hours billing transfer. (Appendix C, Route matrix)
5. WHEN the caller requests MyChart, THE After Hours phase SHALL speak the mandated "MyChart closed" line and SHALL NOT perform an in-hours MyChart transfer. (Appendix C, Route matrix)
6. IF the caller is not understood, THEN THE After Hours phase SHALL speak the after-hours Retry 1 line on the first failure and the after-hours Retry 2 line on the second failure. (Appendix C, POC-08)
7. IF the caller is still not understood after two spoken retries, THEN THE After Hours phase SHALL transition to Routing on the third failure as a silent turn. (Retry policy, POC-08)
8. WHEN paging clarification is needed after hours, THE After Hours phase SHALL ask one of the mandated paging clarifier lines and SHALL set `caller_is_provider` and `ah_intent_selection` accordingly. (Appendix C, Appendix D)
9. IF the caller confirms the connection request for a restricted service, THEN THE After Hours phase SHALL proceed to Authentication and then to Routing. (After Hours restricted services, POC-03)
10. IF the caller declines the connection request for a restricted service, THEN THE After Hours phase SHALL NOT perform Authentication or Routing and SHALL end the restricted-service flow. (After Hours restricted services, POC-03)
11. IF no intelligible connect decision is received within 10 seconds of asking whether to connect the caller for a restricted service, THEN THE After Hours phase SHALL treat the request as declined and SHALL NOT perform Authentication or Routing. (After Hours restricted services, POC-03)

### Requirement 9: Authentication phase and auth gating

**User Story:** As a security-conscious operator, I want patients verified before routing for protected intents, so that calls are connected only after identity handling.

#### Acceptance Criteria

1. THE Authentication phase SHALL follow the flow phone number → read-back → patient lookup → date of birth → identity validation → Routing. (Authentication flow)
2. WHEN `intent` requires authentication and `patient_status` is not `new` and `patient_verified` is null, THE Switchboard SHALL block transfer and routing intent resolution until `patient_verified` becomes Success, Fail, or N/A. (GATE-AUTH, AC rule, POC-10)
3. THE Switchboard SHALL require authentication when `intent` is Scheduling, Referrals, Triage, Billing, mychart, Paging, Directory, Pharmacy, or General AND the patient is not new. (REQ-AUTH-01)
4. THE Switchboard SHALL skip authentication for Records, and for Scheduling with a new patient, while still routing before any transfer. (REQ-AUTH-01, AC-09, POC-01c)
5. WHERE `intent` is Billing, MyChart, Paging, Directory, Pharmacy, or General, THE Switchboard SHALL default `patient_status` to existing and SHALL NOT ask new/existing. (REQ-AUTH-01 "Default to existing")
6. WHEN a prior ANI patient lookup was already completed in Greeting (`greeting_ani_lookup_done` is true), THE Authentication phase SHALL reuse that result and SHALL NOT repeat the ANI lookup. (Authentication ANI reuse)
7. IF the caller refuses or fails authentication, THEN THE Authentication phase SHALL speak "No problem. I'll connect you now." and route on the same turn, and SHALL NOT hang up for refusal alone. (AC-11, POC-06, Appendix C)
8. IF the caller changes their request during Authentication, THEN THE Authentication phase SHALL speak "Sure, let me get you to the right place for that." and return to Business Hours or After Hours, and SHALL NOT go straight to Routing. (AC-06, POC-09, Appendix C)
9. WHEN reading a phone number back to the caller, THE Authentication phase SHALL use the mandated phone read-back format with digits grouped 3, 3, then 4 and separated by periods. (Appendix C phone read-back)
10. IF no patient record is found for a provided phone number, THEN THE Authentication phase SHALL speak the "No record" line and ask for a different number. (Appendix C)
11. WHEN identity validation runs, THE Authentication phase SHALL set `patient_verified` to Success only when the provided date of birth matches the record, and SHALL set `patient_verified` to Fail otherwise. (Authentication flow)
12. IF the caller cannot provide a matching phone number after 3 attempts, THEN THE Authentication phase SHALL route the caller without hanging up for the failure alone. (Authentication flow, AC-11)

### Requirement 10: Routing phase

**User Story:** As an operator, I want routing resolved silently and transfers spoken with only the prescribed line, so that callers hear a clean, professional handoff.

#### Acceptance Criteria

1. WHILE resolving a destination in the Routing phase, THE Routing phase SHALL emit zero speech tokens, including no filler, acknowledgment, or stall phrases. (GATE-LOOKUP-SPEECH exception, AC-07, POC-05)
2. THE Routing phase SHALL complete route listing for the department before initiating route metadata resolution, and SHALL NOT issue metadata resolution concurrently with route listing. (Routing chain)
3. THE Routing phase SHALL resolve route metadata using the exact Routing intent string returned by route listing, and SHALL NOT fabricate a Routing intent string. (Routing chain, REQ-LEDGER-03)
4. WHEN performing a terminal transfer or hangup, THE Routing phase SHALL speak only the prescribed transfer or goodbye line and SHALL emit no other Switchboard speech on that turn. (GATE-TRANSFER-SPEECH, AC-08)
5. THE Routing phase SHALL select the transfer message from Appendix E by the ledger `intent`. (Routing transfer message, Appendix E)
6. THE Routing phase SHALL NOT use stall phrases such as "Hang tight." on terminal turns. (Appendix E "Forbidden in Routing phase")
7. WHILE `after_hours` is false, THE Routing phase SHALL NOT use after-hours switchboard routing mode. (GATE-AH-SPEC, AC-12)
8. WHILE `after_hours` is true and resolving post-authentication routing, THE Routing phase SHALL use after-hours switchboard routing mode rather than the caller's real specialty for routing resolution, except for the hotword immediate path. (GATE-AH-SPEC)
9. WHERE `intent` is Directory and the caller only wants information, THE Routing phase SHALL be permitted to end the call with a goodbye rather than transfer. (Route matrix, Directory)
10. IF a transfer fails, THEN THE Routing phase SHALL speak the mandated transfer-error line. (Appendix E Transfer error)

### Requirement 11: Routing logic per intent

**User Story:** As an operator, I want each intent routed with the correct auth and destination behavior, so that the PoC covers the full route matrix.

#### Acceptance Criteria

1. THE Switchboard SHALL implement the routing logic in the vendor Route matrix for all PoC scenarios. (REQ-ROUTE-01, Appendix B)
2. WHEN `intent` is Referrals, Triage, Pharmacy, Billing, mychart, or General, THE Switchboard SHALL require authentication and then route. (Route matrix)
3. WHEN `intent` is Paging, THE Switchboard SHALL set `caller_is_provider` and route, using the paging path appropriate to whether the caller is a provider or a patient. (Route matrix, After Hours)
4. WHEN `intent` is Pharmacy, THE Switchboard SHALL NOT speak medication names. (Route matrix Pharmacy, Appendix C)
5. WHEN the caller requests lab results, THE Switchboard SHALL route to General rather than Records. (Route matrix Records/General note)
6. THE Switchboard SHALL provide a Fallback route resolved in the Routing phase for cases with no matched destination. (Route matrix Fallback, Appendix E Switchboard/fallback)

### Requirement 12: Appointment action classification and management

**User Story:** As a caller, I want to create, cancel, reschedule, list, or confirm appointments, so that I can manage my care by phone.

#### Acceptance Criteria

1. WHEN `intent` is Scheduling, THE Business Hours phase SHALL set `appointment_action` to one of `create`, `cancel`, `reschedule`, `list`, or `confirm` from caller speech. (REQ-SCHED-00, AC-21)
2. WHEN `appointment_action` is `cancel`, `reschedule`, `list`, or `confirm`, THE Switchboard SHALL treat the caller as an existing patient, SHALL NOT ask new/existing, and SHALL require authentication after `specialty` is confirmed. (REQ-SCHED-00b, AC-20, AC-22)
3. WHEN `appointment_action` is `create`, THE Switchboard SHALL ask new/existing when `patient_status` is unknown, and only for `create` SHALL a visit type be required downstream. (REQ-SCHED-03, AC-10, AC-16)
4. THE Switchboard SHALL collect `specialty` (and `location`/`provider_name` when needed) for every `appointment_action` before handoff, and SHALL NOT collect `visit_type` on the switchboard. (Responsibility split, REQ-SCHED-05, AC-16)
5. WHERE `appointment_action` is `cancel` or `reschedule` and the caller identifies which visit, THE Switchboard SHALL capture `existing_appointment_date` on the ledger. (Appendix D, REQ-SCHED-10)
6. WHEN routing an existing-patient Scheduling call, THE Switchboard SHALL, after authentication, hand off to Scheduling_Init for the ledger `specialty`, which invokes the Scheduling_Engine. (REQ-SCHED-02, REQ-SCHED-03, AC-14, AC-22)
7. WHEN routing a new-patient `create` Scheduling call, THE Switchboard SHALL route to the general new-patient intake path rather than the specialty scheduling agent. (REQ-SCHED-03, AC-15, POC-01c)
8. WHEN handing off a Scheduling call, THE Switchboard SHALL pass the full Call_State_Ledger including `specialty`, `location`, `provider_name`, `appointment_action`, verification status, and call summary. (REQ-SCHED-04)

### Requirement 13: Scheduling Init (downstream visit-type determination)

**User Story:** As a scheduling caller, I want the right type of visit determined before booking, so that I am matched to a suitable provider and slot.

#### Acceptance Criteria

1. THE Switchboard SHALL model Scheduling_Init as a downstream workflow segment/tool invoked after switchboard authentication for Scheduling handoffs. (Responsibility split)
2. WHEN `appointment_action` is `create`, THE Scheduling_Init SHALL set `visit_type` to `sick` or `wellness` before invoking the Scheduling_Engine. (REQ-SCHED-06, AC-17)
3. WHEN the visit reason is unknown, THE Scheduling_Init SHALL ask "What is the reason for your visit today?" (Appendix C Scheduling Init)
4. WHEN the caller mentions both a wellness keyword and a specific symptom, THE Scheduling_Init SHALL ask the mandated wellness-vs-symptom disambiguation question before setting `visit_type`. (REQ-SCHED-07, AC-19, POC-12, Appendix C)
5. WHEN the disambiguation answer is a wellness exam, THE Scheduling_Init SHALL set `visit_type` to `wellness`; WHEN the answer is the symptom visit, THE Scheduling_Init SHALL set `visit_type` to `sick`; WHEN both are indicated, THE Scheduling_Init SHALL set `visit_type` to `wellness`. (REQ-SCHED-07)
6. IF the call summary or conversation already contains a clear visit reason, THEN THE Scheduling_Init SHALL map it directly and SHALL NOT ask for the reason again. (REQ-SCHED-08)
7. WHEN `appointment_action` is `cancel`, `reschedule`, `list`, or `confirm`, THE Scheduling_Init SHALL NOT ask sick vs. wellness and SHALL pass `appointment_action` and ledger context directly to the Scheduling_Engine. (REQ-SCHED-09, AC-20)

### Requirement 14: SpinSci Scheduling Engine (downstream availability and booking)

**User Story:** As a scheduling caller, I want provider availability checked and slots offered or my appointment managed, so that I complete my scheduling task.

#### Acceptance Criteria

1. THE Switchboard SHALL model the Scheduling_Engine as a downstream tool invoked by Scheduling_Init. (Responsibility split)
2. THE Scheduling_Engine SHALL receive at minimum `specialty`, verified patient/`patient_id`, and `appointment_action` for all actions, `visit_type` for `create`, and `location`/`provider_name`/`existing_appointment_date` when known. (REQ-SCHED-10)
3. WHEN handling a `create` or `reschedule`, THE Scheduling_Engine SHALL determine provider availability for the given `visit_type`, `specialty`, and `location`, and SHALL return bookable openings. (REQ-SCHED-11, REQ-SCHED-13, AC-18)
4. WHEN the preferred provider is unavailable for the visit type, THE Scheduling_Engine SHALL offer alternative providers at the same location and SHALL NOT re-ask facts already collected. (REQ-SCHED-12, AC-18, POC-13)
5. WHEN handling a `cancel`, THE Scheduling_Engine SHALL locate the target appointment using patient record, `specialty`, and optional `existing_appointment_date`, and SHALL complete cancellation. (REQ-SCHED-09b, POC-14)
6. WHEN handling a `reschedule`, THE Scheduling_Engine SHALL locate the appointment, present alternative slots, and complete the reschedule. (REQ-SCHED-09c, POC-11)
7. WHEN handling a `list`, THE Scheduling_Engine SHALL retrieve upcoming appointments for the patient in the relevant specialty and return them for read-back. (REQ-SCHED-09d, REQ-SCHED-13b, POC-15)
8. WHEN handling a `confirm`, THE Scheduling_Engine SHALL retrieve the appointment and return date, time, provider, and location for read-back. (REQ-SCHED-09e, REQ-SCHED-13b, POC-16)
9. IF urgent symptoms are detected during sick-visit handling, THEN THE Scheduling_Engine or Scheduling_Init SHALL escalate per SpinSci urgency rules before continuing self-service booking. (REQ-SCHED-14)
10. IF the `specialty` is not activated for scheduling in SpinSci's catalog, THEN THE Switchboard SHALL inform the caller and offer an alternate path. (POC note)

### Requirement 15: Call State Ledger fields

**User Story:** As an orchestration designer, I want the ledger fields defined as workflow context variables, so that state maps precisely onto the workflow engine.

#### Acceptance Criteria

1. THE Switchboard SHALL maintain the following Call_State_Ledger fields as workflow context variables: `caller_name`, `intent`, `patient_status` (null/new/existing), `provider_name`, `specialty`, `scan_type`, `location`, `department_name`, `department_id`, `selected_id`, `patient_verified` (null/Success/Fail/N/A), `appointment_action`, `existing_appointment_date`, `visit_type`, `visit_reason`, `preferred_provider_id`, `preferred_date`, `caller_is_provider`, `patient_id`, `after_hours`, `greeting_ani_lookup_done`, `greeting_ani_match_count`, and `ah_intent_selection`. (Appendix D)
2. THE Switchboard SHALL normalize `specialty` when a specialty is required. (Appendix D)
3. THE Switchboard SHALL store `selected_id` as a numeric record identifier only. (Appendix D)
4. IF a ledger field is already populated, THEN THE Switchboard SHALL NOT re-ask the caller for it. (REQ-LEDGER-01)

### Requirement 16: Backend connector tools

**User Story:** As an integration engineer, I want each backend capability exposed as a workflow tool, so that nodes invoke SpinSci services through the engine's tool mechanism.

#### Acceptance Criteria

1. THE Switchboard SHALL expose backend connector tools for: patient lookup by ANI or confirmed phone, provider/directory lookup, FAQ/knowledge-base lookup, date-of-birth validation, identity verification, routing intent resolution, route metadata resolution, transfer, hangup, scheduling agent handoff, and the Scheduling_Engine. (Integration capabilities)
2. THE Switchboard SHALL treat the SpinSci-provided API schemas and integration contracts as external integration contracts and SHALL NOT hardcode wire formats not provided by those contracts. (SpinSci provides separately)
3. WHEN performing a transfer, THE transfer tool payload SHALL include destination, call summary, verification status, and the spoken transfer message when telephony transfer applies. (Transfer payload)
4. THE Switchboard SHALL invoke transfer and hangup through the repository telephony providers (`api/services/telephony/`). (Workflow-graph framing)

### Requirement 17: Session and schedule configuration

**User Story:** As an operator, I want business hours and defaults configured to the correct timezone, so that after-hours behavior triggers correctly.

#### Acceptance Criteria

1. THE Switchboard SHALL evaluate business hours in the America/Chicago timezone. (Session and schedule)
2. THE Switchboard SHALL treat business hours as Monday–Friday 08:00–17:00 and Saturday 08:00–12:00, and SHALL treat Sunday as closed. (Session and schedule)
3. WHEN a call starts, THE Switchboard SHALL set `after_hours` from the America/Chicago schedule, and SHALL keep it authoritative unless the Business Hours phase corrects a misroute to After Hours. (REQ-ARCH-03)
4. THE Switchboard SHALL use "Thank you for calling SpinSci. Goodbye." as the default hangup line. (Session and schedule)
5. THE Switchboard SHALL use "One moment while I connect you." as the default transfer fallback line. (Session and schedule)

### Requirement 18: Verbatim caller script fidelity

**User Story:** As a compliance reviewer, I want mandatory caller lines reproduced exactly, so that the PoC meets SpinSci's scripting requirements.

#### Acceptance Criteria

1. THE Switchboard SHALL reproduce every mandatory Appendix C caller line verbatim, changing only runtime placeholders such as `{{caller_name}}` and `{FirstName}`. (Appendix C, Rule 10)
2. WHEN speaking a transfer message, THE Switchboard SHALL reproduce the Appendix E line for the resolved case verbatim. (Appendix E)
3. THE Switchboard SHALL fill runtime placeholders in mandatory scripts with ledger values before speaking. (Appendix C)
4. THE Switchboard SHALL preserve the exact punctuation of mandatory scripts, including the no-period-before-"and" form of Script 3′. (Appendix C Script 3′)

### Requirement 19: Workflow-engine substrate and future extensibility (non-functional)

**User Story:** As an architect, I want this PoC built on the in-repo Samvaad/Dograh workflow engine without adding a dependency on an external Samvaad-integration pipeline, so that the PoC ships on the existing engine while future SpinSci expansion and any later broader Samvaad integration remain possible without rework.

#### Acceptance Criteria

1. THE Switchboard SHALL be implemented on the in-repo Samvaad/Dograh workflow engine (`api/services/workflow/`). (User constraint)
2. THE Switchboard SHALL NOT introduce a dependency on any external Samvaad-integration pipeline beyond the in-repo workflow engine. (User constraint)
3. THE Switchboard design SHALL remain behind the workflow-graph and tool boundaries so that future SpinSci expansion and any later broader Samvaad integration are possible without rework. (User constraint)

### Requirement 20: PoC acceptance scenarios

**User Story:** As a PoC sponsor, I want the minimum test scenarios demonstrable end to end, so that the PoC can be signed off.

#### Acceptance Criteria

1. WHEN an existing patient requests a primary-care wellness appointment, THE Switchboard SHALL authenticate, hand off to Scheduling_Init, set `visit_type` to `wellness`, and the Scheduling_Engine SHALL offer slots. (POC-01)
2. WHEN an existing patient requests a sick visit, THE Switchboard SHALL authenticate, hand off to Scheduling_Init, set `visit_type` to `sick`, and the Scheduling_Engine SHALL offer slots or an alternative provider. (POC-01b)
3. WHEN a new patient requests to schedule in hours, THE Switchboard SHALL skip authentication and route to the general new-patient intake path. (POC-01c, AC-15)
4. WHEN a caller requests Records in hours, THE Switchboard SHALL skip authentication, route silently, and speak the Records transfer line. (POC-02, AC-09)
5. WHEN a caller requests a restricted service after hours and agrees to connect, THE Switchboard SHALL run the INFORM/ASK script, authenticate, and use after-hours routing. (POC-03)
6. WHEN a hotword is detected after hours, THE Switchboard SHALL route silently, set `patient_verified` to N/A, and speak the urgent transfer line. (POC-04, AC-05)
7. WHEN authentication completes, THE Switchboard SHALL emit zero speech between authentication completion and the transfer line. (POC-05, AC-07)
8. WHEN the caller refuses authentication, THE Switchboard SHALL speak "No problem. I'll connect you now." and transfer rather than hang up. (POC-06, AC-11)
9. WHEN a call cold-starts, THE Switchboard SHALL be silent on turn 1, play welcome audio, and branch on turn 2. (POC-07, AC-01)
10. WHEN the caller fails to be understood twice, THE Switchboard SHALL speak two retries and then route silently on the third turn. (POC-08)
11. WHEN the caller changes their request during authentication, THE Switchboard SHALL speak "Sure, let me get you to the right place for that." and return to Business Hours or After Hours. (POC-09, AC-06)
12. WHEN an intent requires authentication, THE Switchboard SHALL lock transfer and routing resolution until verification resolves. (POC-10, AC rule GATE-AUTH)
13. WHEN an existing patient requests a reschedule, THE Switchboard SHALL confirm specialty, authenticate, hand off to Scheduling_Init without a visit type, and the Scheduling_Engine SHALL locate the appointment and offer new slots. (POC-11)
14. WHEN a caller says they need a physical because a body part hurts, THE Scheduling_Init SHALL ask the wellness-vs-sick disambiguation before setting `visit_type`. (POC-12, AC-19)
15. WHEN the Scheduling_Engine reports the preferred provider cannot see the patient for the visit type, THE scheduling agent SHALL offer an alternative provider at the same location without re-asking the visit reason or discharge date. (POC-13, AC-18)
16. WHEN a caller cancels an appointment, THE Switchboard SHALL set `appointment_action` to `cancel`, authenticate, and the Scheduling_Engine SHALL cancel the matched appointment. (POC-14)
17. WHEN a caller asks what appointments they have, THE Switchboard SHALL set `appointment_action` to `list`, authenticate, and the Scheduling_Engine SHALL list upcoming visits for the specialty. (POC-15)
18. WHEN a caller confirms an appointment, THE Switchboard SHALL set `appointment_action` to `confirm`, authenticate, and the Scheduling_Engine SHALL read back the appointment details. (POC-16)

### Requirement 21: After-hours hotword keyword list (external dependency)

**User Story:** As a QA engineer, I want the hotword behavior configurable pending the keyword list, so that the PoC is ready when SpinSci supplies the list.

#### Acceptance Criteria

1. THE Switchboard SHALL read the after-hours hotword keyword list from configuration rather than hardcoding it. (TBD dependency)
2. WHERE the hotword keyword list has not been provided by SpinSci, THE Switchboard SHALL allow hotword detection to be configured later without code changes. (TBD dependency)
3. WHEN a configured hotword matches after hours, THE After Hours phase SHALL trigger the urgent silent-routing path defined in Requirement 8. (POC-04)
