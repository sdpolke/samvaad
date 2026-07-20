# Implementation Plan: SpinSci AI Virtual Switchboard PoC

## Overview

This plan implements the SpinSci AI Virtual Switchboard PoC as a single validated Samvaad/Dograh
workflow graph on the in-repo engine (`api/services/workflow/`), driven by Pipecat
(`api/services/pipecat/`) with telephony providers (`api/services/telephony/`). It targets
**Python** with **Hypothesis** for property-based tests, matching repo conventions
(design.md → Testing Strategy).

The build order deliberately extracts the deterministic, pure decision logic the design calls out
(schedule evaluator, ledger reducer + `should_ask`, script renderer, phone formatter, appointment
classifier, auth-gate, routing-chain sequencer, visit-type resolver) as independently testable
units **first**, covers them with property-based tests (Properties 1–33), and only then wires them
into the workflow graph clusters, tools, downstream scheduling segments, and end-to-end PoC
scenarios.

New code lives under `api/services/switchboard/` (pure logic + graph builders + connector tools);
tests live under `api/tests/switchboard/`. Verbatim scripts (Appendix C/E) are referenced from the
vendor document (`SpinsciPoCRequirement/`) and copied byte-for-byte into asset constants — never
rewritten.

**External-dependency notes:** two areas are blocked on SpinSci and are scaffolded with mocks so
the PoC is ready when contracts arrive — (a) the backend wire contracts (Req 16.2) and (b) the
after-hours hotword keyword list (Req 21, TBD). Tasks that depend on those are annotated
**[DEFERRED — SpinSci contract]** and are implemented against mocks/config only.

## Tasks

- [x] 1. Scaffold switchboard package, Call State Ledger, and schedule/session config
  - [x] 1.1 Create `api/services/switchboard/` package and the Call State Ledger model
    - Create package `__init__.py` and `ledger.py`
    - Define the ledger as a typed model (Pydantic/dataclass) with all 23 Appendix D fields:
      `caller_name`, `intent`, `patient_status`, `provider_name`, `specialty`, `scan_type`,
      `location`, `department_name`, `department_id`, `selected_id`, `patient_verified`,
      `appointment_action`, `existing_appointment_date`, `visit_type`, `visit_reason`,
      `preferred_provider_id`, `preferred_date`, `caller_is_provider`, `patient_id`, `after_hours`,
      `greeting_ani_lookup_done`, `greeting_ani_match_count`, `ah_intent_selection`
    - Map each field to its `VariableType` (string/number/boolean); enforce `selected_id` numeric-only
      and `specialty` normalization hook
    - _Requirements: 1.6, 2.1, 15.1, 15.2, 15.3_
  - [x] 1.2 Implement schedule/session configuration module (`config.py`)
    - Encode America/Chicago business-hours schedule (Mon–Fri 08:00–17:00, Sat 08:00–12:00, Sun closed)
    - Provide default hangup line "Thank you for calling SpinSci. Goodbye." and default transfer
      fallback line "One moment while I connect you."
    - Provide a config-driven hotword keyword list loader (empty/placeholder list, no hardcoding)
    - **[DEFERRED — SpinSci contract]** hotword keyword values are supplied later via config, no code change (Req 21.2)
    - _Requirements: 17.1, 17.2, 17.4, 17.5, 21.1, 21.2_
  - [x] 1.3 Write unit tests for config loading and config-driven hotword behavior
    - Assert default lines and schedule constants; assert hotword list is read from config, not hardcoded
    - _Requirements: 17.4, 17.5, 21.1, 21.2_

- [x] 2. Implement the after-hours schedule evaluator
  - [x] 2.1 Implement `is_after_hours(dt_local) -> bool` in `schedule.py`
    - Pure function over an America/Chicago local datetime using the Req 17 schedule; set `after_hours` at call start
    - _Requirements: 17.1, 17.2, 17.3_
  - [x] 2.2 Write property test for the schedule evaluator
    - **Property 1: Business-hours schedule evaluation**
    - Generators must cover DST boundaries, week edges, and all of Sunday
    - **Validates: Requirements 17.1, 17.2, 17.3**
    - Tag: `Feature: spinsci-switchboard-poc, Property 1: Business-hours schedule evaluation`

- [x] 3. Implement the ledger reducer, never-re-ask predicate, and intent separation
  - [x] 3.1 Implement full-carry reducer, `should_ask(field, ledger)`, and routing-intent separation in `ledger.py`
    - Reducer carries the full ledger across every transition (no field dropped/reset)
    - `should_ask` returns false whenever the target field is already populated
    - Keep `ledger.intent` immutable w.r.t. routing intent (routing intent is a separate transient value)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 15.4_
  - [x] 3.2 Write property test for full-carry ledger
    - **Property 2: Ledger carried in full across transitions**
    - **Validates: Requirements 2.1, 2.2**
    - Tag: `Feature: spinsci-switchboard-poc, Property 2: Ledger carried in full across transitions`
  - [x] 3.3 Write property test for never-re-ask
    - **Property 3: Never re-ask a populated field**
    - Generators cover empty and fully-populated ledgers across all 23 fields
    - **Validates: Requirements 2.3, 15.4**
    - Tag: `Feature: spinsci-switchboard-poc, Property 3: Never re-ask a populated field`
  - [x] 3.4 Write property test for intent vs routing-intent separation
    - **Property 4: Ledger intent is distinct from routing intent**
    - **Validates: Requirements 2.4**
    - Tag: `Feature: spinsci-switchboard-poc, Property 4: Ledger intent is distinct from routing intent`

- [x] 4. Implement verbatim script assets and the script renderer
  - [x] 4.1 Create `scripts.py` with Appendix C/E verbatim lines as constants
    - Copy each mandatory Appendix C caller line and Appendix E transfer/goodbye/error line byte-for-byte
      from `SpinsciPoCRequirement/` (do not rewrite); preserve Script 3′ no-period-before-"and" punctuation
    - Include placeholder tokens (`{{caller_name}}`, `{FirstName}`) exactly as authored
    - _Requirements: 18.1, 18.2, 17.4, 17.5_
  - [x] 4.2 Implement `render(template, placeholders)` plus narration/medication guards
    - Substitute only placeholders; add a guard rejecting system names/JSON/UUIDs/ledger field names in output;
      add a helper that omits medication names from prescription speech
    - _Requirements: 18.3, 4.1, 4.2, 5.1_
  - [x] 4.3 Write property test for render fidelity
    - **Property 23: Verbatim script render fidelity**
    - **Validates: Requirements 18.1, 18.3, 18.4**
    - Tag: `Feature: spinsci-switchboard-poc, Property 23: Verbatim script render fidelity`
  - [x] 4.4 Write verbatim fidelity example test against Appendix C/E
    - Assert each rendered mandatory line equals the vendor text exactly, including Script 3′ punctuation
    - _Requirements: 18.1, 18.2, 18.4_
  - [x] 4.5 Write property test for no internal narration
    - **Property 24: No internal narration in any emitted speech**
    - **Validates: Requirements 4.1, 3.2**
    - Tag: `Feature: spinsci-switchboard-poc, Property 24: No internal narration in any emitted speech`
  - [x] 4.6 Write property test for medication-name omission
    - **Property 25: Medication names are never spoken**
    - **Validates: Requirements 4.2, 11.4**
    - Tag: `Feature: spinsci-switchboard-poc, Property 25: Medication names are never spoken`

- [x] 5. Implement the phone read-back formatter
  - [x] 5.1 Implement 3-3-4 period-grouped formatter and digit extractor in `phone.py`
    - Format a 10-digit number grouped 3, 3, then 4 separated by periods; provide inverse digit extraction
    - _Requirements: 5.2, 9.9_
  - [x] 5.2 Write property test for the phone read-back round-trip
    - **Property 17: Phone read-back format round-trips**
    - **Validates: Requirements 5.2, 9.9**
    - Tag: `Feature: spinsci-switchboard-poc, Property 17: Phone read-back format round-trips`

- [x] 6. Implement Greeting-phase pure logic
  - [x] 6.1 Implement `select_greeting`, `ready_to_handoff`, turn-1 post-state builder, and Path E retry machine in `greeting.py`
    - `select_greeting(after_hours, greeting_ani_match_count)` returns the Appendix C script; personalized ⇔ count == 1
    - `ready_to_handoff(ledger)` true only with intent/specialty/provider/specific-request (name alone insufficient)
    - Turn-1 builder sets `greeting_ani_lookup_done=true` and `greeting_ani_match_count` (0 on fail/timeout), no error
    - Path E state machine: repeat Path E on failures 1 and 2, fall back to ROUTING REQUEST wording on the 3rd
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.7, 6.9, 6.10, 6.11_
  - [x] 6.2 Write property test for greeting turn-1 post-state
    - **Property 6: Greeting turn 1 is silent with a well-defined post-state**
    - Generators cover match(s)/no-match/failure/2s-timeout
    - **Validates: Requirements 6.1, 6.2, 6.3**
    - Tag: `Feature: spinsci-switchboard-poc, Property 6: Greeting turn 1 is silent with a well-defined post-state`
  - [x] 6.3 Write property test for greeting script selection
    - **Property 7: Greeting script selection**
    - **Validates: Requirements 6.4**
    - Tag: `Feature: spinsci-switchboard-poc, Property 7: Greeting script selection`
  - [x] 6.4 Write property test for name-alone insufficiency
    - **Property 8: Name alone is insufficient to hand off**
    - **Validates: Requirements 6.7**
    - Tag: `Feature: spinsci-switchboard-poc, Property 8: Name alone is insufficient to hand off`
  - [x] 6.5 Write property test for Path E repeat-then-fallback
    - **Property 9: Path E repeats then falls back on the third failure**
    - **Validates: Requirements 6.9, 6.10**
    - Tag: `Feature: spinsci-switchboard-poc, Property 9: Path E repeats then falls back on the third failure`

- [x] 7. Checkpoint - Ensure all pure-logic foundation tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement Business-Hours-phase pure logic
  - [x] 8.1 Implement the appointment_action classifier mapping in `business_hours.py`
    - Map caller speech to exactly one of create/cancel/reschedule/list/confirm; never default to create
      when caller expressed cancel/reschedule/list/confirm
    - _Requirements: 7.6, 7.7, 12.1_
  - [x] 8.2 Write property test for appointment-action classification
    - **Property 11: Appointment-action classification never defaults to create**
    - Generators cover all five appointment_action values
    - **Validates: Requirements 7.6, 7.7, 12.1**
    - Tag: `Feature: spinsci-switchboard-poc, Property 11: Appointment-action classification never defaults to create`
  - [x] 8.3 Implement lookup-speech prefix rules in `business_hours.py`
    - Empty prefix for first provider/directory lookup on a turn; "Let me check that for you." for FAQ;
      "One moment." otherwise; lookup invoked same turn
    - _Requirements: 7.2, 7.3, 7.4_
  - [x] 8.4 Write property test for lookup-speech prefix rules
    - **Property 10: Lookup speech prefix rules**
    - **Validates: Requirements 7.2, 7.3, 7.4**
    - Tag: `Feature: spinsci-switchboard-poc, Property 10: Lookup speech prefix rules`
  - [x] 8.5 Implement manage-action consequences and the BH classification-retry machine in `business_hours.py`
    - Manage actions set `patient_status=existing`, skip new/existing, require confirmed `specialty` before auth,
      and set no `visit_type`; Records skips auth (silent to Routing)
    - Retry: Retry-1 line on first failure, Retry-2 on second, silent ToRouting on third
    - _Requirements: 7.5, 7.8, 7.10, 7.11, 7.12, 7.13, 12.2, 13.7_
  - [x] 8.6 Write property test for manage-action consequences
    - **Property 12: Manage-action consequences**
    - **Validates: Requirements 7.8, 12.2, 13.7**
    - Tag: `Feature: spinsci-switchboard-poc, Property 12: Manage-action consequences`

- [x] 9. Implement Authentication-phase pure logic
  - [x] 9.1 Implement the auth-gate decision (auth matrix) in `auth.py`
    - Require auth for Scheduling(existing)/Referrals/Triage/Billing/mychart/Paging/Directory/Pharmacy/General
      when not new; skip for Records and new-patient create (still route); default `patient_status=existing`
      for Billing/MyChart/Paging/Directory/Pharmacy/General; block transfer + route_metadata until
      `patient_verified` ∈ {Success, Fail, N/A}
    - _Requirements: 9.2, 9.3, 9.4, 9.5, 11.2_
  - [x] 9.2 Write property test for the authentication gate
    - **Property 13: Authentication gate before transfer/routing resolution (GATE-AUTH)**
    - Generators cover every intent in the auth matrix
    - **Validates: Requirements 9.2, 9.3, 9.4, 9.5, 11.2**
    - Tag: `Feature: spinsci-switchboard-poc, Property 13: Authentication gate before transfer/routing resolution`
  - [x] 9.3 Implement ANI-reuse guard, fail/refusal-connects, changed-request routing, and DOB verification in `auth.py`
    - Reuse ANI result when `greeting_ani_lookup_done` is true (no repeat lookup)
    - Refusal/failure/attempt-exhaustion → next terminal is transfer (never hangup for refusal alone)
    - Changed request → next node is Business/After Hours, never Routing
    - DOB match ⇒ `patient_verified=Success`, else `Fail`
    - _Requirements: 9.1, 9.6, 9.7, 9.8, 9.10, 9.11, 9.12_
  - [x] 9.4 Write property test for ANI non-repeat in Authentication
    - **Property 14: ANI lookup is not repeated in Authentication**
    - **Validates: Requirements 9.6**
    - Tag: `Feature: spinsci-switchboard-poc, Property 14: ANI lookup is not repeated in Authentication`
  - [x] 9.5 Write property test for fail/refusal-still-connects
    - **Property 15: Authentication failure or refusal still connects**
    - **Validates: Requirements 9.7, 9.12**
    - Tag: `Feature: spinsci-switchboard-poc, Property 15: Authentication failure or refusal still connects`
  - [x] 9.6 Write property test for changed-request return
    - **Property 16: Changed request returns to Business/After Hours**
    - **Validates: Requirements 9.8**
    - Tag: `Feature: spinsci-switchboard-poc, Property 16: Changed request returns to Business/After Hours`
  - [x] 9.7 Write property test for DOB-determined verification
    - **Property 18: DOB-match determines verification**
    - **Validates: Requirements 9.11**
    - Tag: `Feature: spinsci-switchboard-poc, Property 18: DOB-match determines verification`

- [x] 10. Checkpoint - Ensure Business Hours and Authentication logic tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement Routing-phase pure logic
  - [x] 11.1 Implement the sequential routing-chain sequencer and zero-speech invariant checker in `routing.py`
    - `routing_intent_resolution` (route listing) must complete before `route_metadata_resolution`, which is
      called with the exact returned string (never fabricated, never concurrent); zero speech during resolution
    - _Requirements: 10.1, 10.2, 10.3_
  - [x] 11.2 Write property test for zero-speech resolution
    - **Property 19: Routing resolution emits zero speech**
    - **Validates: Requirements 10.1**
    - Tag: `Feature: spinsci-switchboard-poc, Property 19: Routing resolution emits zero speech`
  - [x] 11.3 Write property test for the sequential exact-string chain
    - **Property 20: Routing chain is sequential and uses the exact string**
    - **Validates: Requirements 10.2, 10.3**
    - Tag: `Feature: spinsci-switchboard-poc, Property 20: Routing chain is sequential and uses the exact string`
  - [x] 11.4 Implement terminal-line selection, AH routing-mode gating, lab→General, new-patient intake, and fallback in `routing.py`
    - Terminal turn speaks only the Appendix E line by ledger `intent` (or goodbye/transfer-error); no stall phrases
    - After-hours routing mode iff `after_hours` and post-auth non-hotword path; lab results → General;
      new-patient create → general intake path; provide a Fallback route
    - _Requirements: 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10, 11.5, 11.6, 12.7_
  - [x] 11.5 Write property test for terminal-turn line-only
    - **Property 21: Terminal turn speaks only the prescribed line**
    - **Validates: Requirements 10.4, 10.5, 10.6, 18.2**
    - Tag: `Feature: spinsci-switchboard-poc, Property 21: Terminal turn speaks only the prescribed line`
  - [x] 11.6 Write property test for after-hours routing-mode gating
    - **Property 22: After-hours routing mode gating (GATE-AH-SPEC)**
    - **Validates: Requirements 10.7, 10.8**
    - Tag: `Feature: spinsci-switchboard-poc, Property 22: After-hours routing mode gating`
  - [x] 11.7 Write property test for lab-results routing
    - **Property 26: Lab results route to General**
    - **Validates: Requirements 11.5**
    - Tag: `Feature: spinsci-switchboard-poc, Property 26: Lab results route to General`
  - [x] 11.8 Write property test for new-patient create routing
    - **Property 27: New-patient create routes to general intake**
    - **Validates: Requirements 12.7**
    - Tag: `Feature: spinsci-switchboard-poc, Property 27: New-patient create routes to general intake`

- [x] 12. Implement After-Hours-phase pure logic
  - [x] 12.1 Implement restricted-service connect decision, hotword path, and Billing/MyChart-closed in `after_hours.py`
    - Restricted INFORM → ASK → wait ≤10s: proceed to Auth+Route iff caller agreed; decline/timeout ends flow
    - Hotword → silent Routing, `patient_verified=N/A`, Hotword-Urgent line
    - Billing/MyChart → mandated closed line, no in-hours transfer; paging clarifier sets
      `caller_is_provider`/`ah_intent_selection`; Retry-1/Retry-2 then silent ToRouting on third
    - _Requirements: 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11_
  - [x] 12.2 Write property test for restricted-service connect decision
    - **Property 31: After-hours restricted-service connect decision**
    - **Validates: Requirements 8.2, 8.9, 8.10, 8.11**
    - Tag: `Feature: spinsci-switchboard-poc, Property 31: After-hours restricted-service connect decision`
  - [x] 12.3 Write property test for the hotword path
    - **Property 32: After-hours hotword path**
    - **Validates: Requirements 8.3**
    - Tag: `Feature: spinsci-switchboard-poc, Property 32: After-hours hotword path`
  - [x] 12.4 Write property test for Billing/MyChart closed
    - **Property 33: After-hours Billing/MyChart are closed**
    - **Validates: Requirements 8.4, 8.5**
    - Tag: `Feature: spinsci-switchboard-poc, Property 33: After-hours Billing/MyChart are closed`

- [x] 13. Implement Scheduling pure logic (visit-type resolution and engine input)
  - [x] 13.1 Implement visit-type resolver, never-set guard, and engine-input completeness in `scheduling.py`
    - `create`: wellness signal→wellness, symptom→sick, both→wellness; ask reason/disambiguation when needed;
      switchboard clusters never set/ask `visit_type`; engine payload includes specialty + verified patient_id +
      appointment_action for all actions, `visit_type` iff create, and location/provider/existing_appointment_date when known
    - _Requirements: 12.4, 12.8, 13.2, 13.5, 13.6, 14.2_
  - [x] 13.2 Write property test for visit-type resolution/disambiguation
    - **Property 28: Visit-type resolution and disambiguation**
    - Generators cover wellness/symptom/both cases
    - **Validates: Requirements 13.2, 13.5**
    - Tag: `Feature: spinsci-switchboard-poc, Property 28: Visit-type resolution and disambiguation`
  - [x] 13.3 Write property test for switchboard never setting visit type
    - **Property 29: Switchboard never sets or asks visit type**
    - **Validates: Requirements 12.4**
    - Tag: `Feature: spinsci-switchboard-poc, Property 29: Switchboard never sets or asks visit type`
  - [x] 13.4 Write property test for scheduling-engine input completeness
    - **Property 30: Scheduling Engine input completeness**
    - Generators cover all five appointment_action values
    - **Validates: Requirements 14.2, 12.8**
    - Tag: `Feature: spinsci-switchboard-poc, Property 30: Scheduling Engine input completeness`

- [x] 14. Checkpoint - Ensure Routing, After Hours, and Scheduling logic tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Implement backend connector tools with per-cluster scoping and mocks
  - [x] 15.1 Implement the 11 connector tools as workflow tools in `switchboard/tools/`
    - Implement `patient_lookup`, `directory_lookup`, `faq_kb`, `dob_validation`, `identity_verify`,
      `routing_intent_resolution`, `route_metadata_resolution`, `transfer`, `hangup`,
      `scheduling_handoff`, `scheduling_engine` with switchboard-side input/output contracts and mock backends
    - **[DEFERRED — SpinSci contract]** bind to credential/endpoint + field mapping; do not hardcode SpinSci wire formats (Req 16.2)
    - _Requirements: 16.1, 16.2_
  - [x] 15.2 Wire the `transfer` and `hangup` tools to the telephony providers
    - Invoke `transfer_call(destination, ...)`/hangup via `api/services/telephony/`; transfer payload carries
      destination + call summary + verification status + spoken transfer message
    - _Requirements: 16.3, 16.4_
  - [x] 15.3 Write integration tests (1–3) for telephony transfer/hangup wiring
    - Assert `transfer_call`/hangup invoked with correct payload against a fake provider
    - _Requirements: 16.3, 16.4_
  - [x] 15.4 Write integration tests (1–3) for the mocked SpinSci connector contracts
    - Exercise lookup/verify/routing tools against mocked wire contracts
    - _Requirements: 16.1, 16.2_

- [x] 16. Build the five phase node clusters and wire pure logic into the graph
  - [x] 16.1 Build the Greeting cluster (nodes + edges)
    - `trigger`→`startCall` inbound entry with 2s `pre_call_fetch` ANI lookup (silent turn 1), config-driven
      welcome audio, `select_greeting`, Path A same-turn ack edge, Path E loop edge with ROUTING REQUEST fallback
    - _Requirements: 1.2, 1.3, 1.4, 3.5, 6.1, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11_
  - [x] 16.2 Build the Business Hours cluster (nodes + edges)
    - Intent classify, lookup nodes with speech rules, scheduling gate (new/existing, specialty confirm),
      Records silent-skip edge, retry edges, Search-trouble line; Triage never used as a directory specialty
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.9, 7.10, 7.13, 4.4, 11.1, 11.3, 11.4, 12.3, 12.5_
  - [x] 16.3 Build the After Hours cluster (nodes + edges)
    - Restricted INFORM/ASK/wait node, hotword silent-route edge, Billing/MyChart closed nodes,
      paging clarifier node, retry edges; hotword list read from config
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 21.3_
  - [x] 16.4 Build the Authentication cluster (nodes + edges)
    - phone → read-back → patient_lookup → DOB → identity → Routing; silent entry edge;
      changed-request edges back to Business/After Hours; no-record + 3-attempt route edges
    - _Requirements: 9.1, 3.3, 9.7, 9.8, 9.10, 9.12_
  - [x] 16.5 Build the Routing cluster (nodes + edges)
    - Zero-speech resolve node, sequential `routing_intent_resolution`→`route_metadata_resolution`,
      terminal transfer/hangup nodes (Appendix E line only), Directory info-only goodbye, transfer-error line
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.9, 10.10, 3.4_
  - [x] 16.6 Implement the silent-transition classifier (`transitions.py`) and apply to silent edges
    - Classify silent triggers (normal auth entry, Records skip, new-create skip, retry-3, hotword) and set
      `transition_speech` empty on those edges
    - _Requirements: 1.5, 3.3, 3.4, 7.10, 8.3_
  - [x] 16.7 Write property test for the silent-transition invariant
    - **Property 5: Silent-transition invariant**
    - **Validates: Requirements 3.3, 3.4, 1.5, 7.10, 8.3**
    - Tag: `Feature: spinsci-switchboard-poc, Property 5: Silent-transition invariant`
  - [x] 16.8 Apply per-cluster tool scoping (gate-by-scoping)
    - Attach `tool_uuids` per cluster; `transfer` and `route_metadata_resolution` exist only on Routing nodes
      so no transfer/metadata can occur before Routing
    - _Requirements: 1.7, 9.2_
  - [x] 16.9 Add the global-node persona and TTS rules
    - Never speak system names/JSON/UUIDs/ledger field names; never repeat medication names; never name an
      unconfirmed team; short sentences + period-grouped digits; `add_global_prompt=false` on verbatim nodes
    - _Requirements: 4.1, 4.2, 4.3, 5.1, 5.2_

- [x] 17. Build the Scheduling Init and Scheduling Engine downstream segments
  - [x] 17.1 Build Scheduling Init + Scheduling Engine downstream node segments
    - After auth, `scheduling_handoff` passes the full ledger; Init sets `visit_type` for create only
      (reason/disambiguation), skips sick/wellness for manage actions; Engine handles
      create/reschedule availability + alternatives, cancel/list/confirm, urgency escalation, and
      specialty-not-activated fallback
    - **[DEFERRED — SpinSci contract]** Scheduling Engine runs against a mock until SpinSci delivers schemas
    - _Requirements: 12.6, 12.7, 12.8, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9, 14.10_
  - [x] 17.2 Write integration tests (1–3) for the mocked Scheduling Engine contracts
    - Cover create/reschedule availability + alternative-without-re-ask, cancel, list, confirm against a mock engine
    - _Requirements: 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9_

- [x] 18. Assemble the full switchboard graph and validate it
  - [x] 18.1 Assemble the complete graph from all clusters in `switchboard/graph.py`
    - Single directed graph from inbound entry, ledger fields as context variables, node tool references,
      edges carrying condition + transition_speech; no outbound dial
    - _Requirements: 1.1, 1.8, 2.1, 2.2, 3.1, 19.1, 19.2, 19.3_
  - [x] 18.2 Write a `WorkflowGraph` validation smoke test
    - Assert the assembled graph validates (single start node, ≤1 global node, edge cardinality, referential
      integrity); assert connector tools are registered and scoped to the correct clusters
    - _Requirements: 1.1, 1.7_

- [x] 19. Checkpoint - Ensure the graph builds, validates, and all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 20. Write the PoC acceptance-scenario end-to-end tests (POC-01..16)
  - [x] 20.1 E2E: existing wellness/sick and new-patient create (POC-01/01b/01c)
    - Drive the graph with scripted turns; assert auth→Init→visit_type→Engine slots and new-create general intake
    - _Requirements: 20.1, 20.2, 20.3_
  - [x] 20.2 E2E: Records in hours (POC-02)
    - _Requirements: 20.4_
  - [x] 20.3 E2E: after-hours restricted service, agree to connect (POC-03)
    - _Requirements: 20.5_
  - [x] 20.4 E2E: after-hours hotword (POC-04)
    - _Requirements: 20.6_
  - [x] 20.5 E2E: zero speech between auth completion and transfer (POC-05)
    - _Requirements: 20.7_
  - [x] 20.6 E2E: auth refusal still connects (POC-06)
    - _Requirements: 20.8_
  - [x] 20.7 E2E: cold start silent turn 1, welcome audio, branch turn 2 (POC-07)
    - _Requirements: 20.9_
  - [x] 20.8 E2E: two retries then silent route (POC-08)
    - _Requirements: 20.10_
  - [x] 20.9 E2E: changed request during auth (POC-09)
    - _Requirements: 20.11_
  - [x] 20.10 E2E: auth gate locks transfer/metadata until verify (POC-10)
    - _Requirements: 20.12_
  - [x] 20.11 E2E: existing-patient reschedule (POC-11)
    - _Requirements: 20.13_
  - [x] 20.12 E2E: wellness-vs-sick disambiguation (POC-12)
    - _Requirements: 20.14_
  - [x] 20.13 E2E: preferred provider unavailable, alternative without re-ask (POC-13)
    - _Requirements: 20.15_
  - [x] 20.14 E2E: cancel/list/confirm (POC-14/15/16)
    - _Requirements: 20.16, 20.17, 20.18_

- [x] 21. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional (tests) and can be skipped for a faster MVP; core implementation
  tasks are never optional.
- Tasks annotated **[DEFERRED — SpinSci contract]** (15.1, 17.1) and the hotword list in 1.2/16.3 are
  blocked on SpinSci supplying wire schemas (Req 16.2) and the hotword keyword list (Req 21, TBD);
  they are scaffolded with mocks/config so they are ready when the contracts arrive.
- Pure decision logic is extracted first and covered by one property-based test per property
  (Properties 1–33, Hypothesis, ≥100 iterations, tagged
  `Feature: spinsci-switchboard-poc, Property {n}: {text}`); property tests sit next to the code they validate.
- PoC scenario tests (POC-01..16) are example/integration tests that drive the assembled graph.
- Verbatim scripts are referenced from Appendix C/E in `SpinsciPoCRequirement/` and copied byte-for-byte;
  fidelity is enforced by Property 23 and the example test 4.4.
- Each task references specific requirement clauses and/or design properties for traceability.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "2.1", "3.1", "4.1", "5.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "3.3", "3.4", "4.2", "5.2", "6.1", "8.1", "9.1", "11.1", "12.1", "13.1"] },
    { "id": 3, "tasks": ["4.3", "4.4", "4.5", "4.6", "6.2", "6.3", "6.4", "6.5", "8.2", "8.3", "9.2", "9.3", "11.2", "11.3", "11.4", "12.2", "12.3", "12.4", "13.2", "13.3", "13.4", "15.1"] },
    { "id": 4, "tasks": ["8.4", "8.5", "9.4", "9.5", "9.6", "9.7", "11.5", "11.6", "11.7", "11.8", "15.2"] },
    { "id": 5, "tasks": ["8.6", "15.3", "15.4", "16.1", "16.2", "16.3", "16.4", "16.5", "16.6"] },
    { "id": 6, "tasks": ["16.7", "16.8", "16.9", "17.1"] },
    { "id": 7, "tasks": ["17.2", "18.1"] },
    { "id": 8, "tasks": ["18.2", "20.1", "20.2", "20.3", "20.4", "20.5", "20.6", "20.7", "20.8", "20.9", "20.10", "20.11", "20.12", "20.13", "20.14"] }
  ]
}
```
