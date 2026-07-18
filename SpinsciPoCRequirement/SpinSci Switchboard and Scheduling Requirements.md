**SpinSci AI Virtual Switchboard — Vendor Requirements** 

SpinSci AI Virtual Switchboard — Vendor Requirements (POC) 

How to read this document 

Part 1: Overview 

Part 2: Core requirements 

Part 3: Reference appendices  
**SpinSci AI Virtual Switchboard — Vendor Requirements (POC)** 

| Version  | 2.1 |
| :---- | :---- |
| **Date**  | 2026-06-23 |
| **Audience**  | SpinSci orchestration POC |

**How to read this document** 

**If you need to… Start here** 

| Understand what to build  | Part 1 — Overview |
| :---- | :---- |
| Implement routing, auth, and phase logic  | Part 2 — Core requirements |
| Look up exact caller wording  | Appendix C — Caller scripts |
| Look up transfer lines or route details  | Appendix B and Appendix E |
| Understand scheduling, visit types, and the Scheduling Engine  | Scheduling experience |
| Sign off the POC  | POC acceptance |

**Identifier prefixes:** REQ- requirement · GATE- precondition · AC- acceptance criterion 

**Part 1: Overview** 

**What you are building** 

SpinSci AI is the inbound phone switchboard agent for SpinSci. Your orchestrator handles five **conversation phases** that are invisible to the caller: 

Greeting → Business Hours or After Hours → Authentication (when required) → Routing → Transfer or hangup 

Every phase shares one **Call State Ledger** (session record). Phase changes are usually **silent** — the caller should not know they moved between modules.  
**POC objective** 

Demonstrate end-to-end calls with: 

Correct phase routing and shared state 

Mandatory verbatim caller speech (Appendix C) 

Authentication gating before transfer when required 

Terminal transfer/hangup where **only** the prescribed spoken line is heard 

**Appointment management:** schedule, cancel, reschedule, list, and confirm — via switchboard → Scheduling Init → SpinSci Scheduling Engine 

**Vendor delivers** 

Conversation orchestrator and phase routing 

NLU / dialogue logic per phase 

Connectors to SpinSci backend services (patient lookup, directory, routing, identity validation) Telephony integration for transfer and hangup 

**SpinSci provides separately** 

API schemas and integration contracts for backend services 

After-hours hotword keyword list (**TBD** — required before hotword QA) 

Optional detailed edge-case annexes (not required if this document is met) 

**Scope** 

**In scope:** Five switchboard phases, ledger, business/after-hours logic, intents, auth, routing, mandatory speech, and **full appointment management**: 

**appointment\_action Caller intent (examples)** 

| create  | Schedule a new appointment, book a visit, see a doctor |
| :---- | :---- |
| **cancel**  | Cancel an appointment, can’t make my appointment |
| **reschedule**  | Change appointment time/date, move my appointment |
| **list**  | What appointments do I have, upcoming visits |
| **confirm**  | Confirm my appointment, verify appointment details |

All five actions route existing patients through **Authentication → Scheduling Init → SpinSci Scheduling Engine** (see Scheduling experience).  
**Out of scope:** Full edge-case matrices, medical advice, callbacks, driving directions, telling callers about internal architecture, low-level telephony wiring. 

**Key terms** 

**Term Meaning** 

| Call State Ledger  | Shared session record for the call |
| :---- | :---- |
| **Internal intent**  | Ledger field intent (e.g. Scheduling, Triage) |
| **Routing intent**  | Destination string returned by routing resolution — **not** the same as ledger intent |
| **Silent turn**  | Backend action may run, but SpinSci AI says nothing |
| **after\_hours**  | Boolean from Chicago schedule — controls business vs after-hours behavior |
| **Terminal action**  | Transfer or hangup — ends the orchestration path |
| **Transfer message**  | The single spoken line played when connecting the caller |
| **Scheduling agent**  | Downstream agent for a specific **specialty** — collects visit type and hands off to the Scheduling Engine |
| **Scheduling Init**  | First scheduling phase after switchboard auth — determines visit type and reason for visit |
| **SpinSci Scheduling Engine**  | Core scheduling service — maps visit reasons, checks provider availability, and presents bookable slots |
| **visit\_type**  | Classification that drives scheduling rules — primarily **sick** or **wellness** for POC ( **create** only) |
| **appointment\_action**  | What the caller wants to do: create · cancel · reschedule · list · confirm |

**The ten rules that matter most** 

1\. **One ledger, whole call.** Initialize in Greeting; pass full state on every phase change. 2\. **First turn is silent.** Turn 1 \= patient lookup only. Welcome audio comes from configuration, not SpinSci AI’s text. 

3\. **Never narrate internals.** Callers must not hear system names, JSON, or field names. 4\. **Auth before routing** for most intents when the patient is not new. 

5\. **Records skips auth.** New-patient scheduling skips auth but still routes. 

6\. **Silent handoffs to Auth and Routing.** No speech on those transition turns. 7\. **Routing is silent.** No filler ( Hang tight. , One moment. ) before transfer.  
8\. **Transfer speech \= prescribed line only.** Zero extra SpinSci AI words on terminal turns. 9\. **Never re-ask** a fact already in the ledger. 

10\. **Exact script wording.** Mandatory lines in Appendix C must match verbatim. 

**Part 2: Core requirements** 

**Architecture** 

**REQ-ARCH-01** One Call State Ledger per call, passed in full on every phase transition. 

**REQ-ARCH-02** Five phases: Greeting → Business Hours / After Hours → Authentication → Routing. Caller never hears about phases. 

**REQ-ARCH-03** after\_hours is set at call start and stays authoritative unless Business Hours corrects a misroute to After Hours. 

**REQ-ARCH-04** Transitions to Authentication and Routing are silent (no TTS), except Greeting Path A may speak an acknowledgment on the same turn as entering Business Hours or After Hours. 

**REQ-ARCH-05** SpinSci AI never speaks system names, JSON, UUIDs, or ledger field names. **REQ-ARCH-06** SpinSci AI is concise and TTS-friendly (short sentences; periods for number pauses). 

**Phase transitions** 

**Transition Enters Payload Spoken?** 

| ToBusinessHours  | Business Hours  | Full ledger \+ call summary  | Only if Path A ack on same turn |
| :---- | :---- | ----- | :---- |
| ToAfterHours  | After Hours  | Full ledger \+ call summary  | Same |
| ToAuthentication  | Authentication  | Full ledger \+ call summary  | **No** |
| ToRouting  | Routing  | Full ledger \+ call summary  | **No** |
| Transfer  | Terminal  | Per integration contract  | **Only** transfer message |
| Hangup  | Terminal  | Per integration contract  | **Only** goodbye line |

**The five phases** 

**Greeting phase** 

Start call, ANI lookup, welcome audio, collect name/intent, route to Business Hours or After Hours.  
**Rule Detail** 

| First turn  | Patient lookup only — no speech |
| :---- | :---- |
| Welcome  | Pre-configured audio: *Thank you for calling SpinSci. This is SpinSci AI, your virtual assistant.* |
| Scripts  | Use Scripts 1′–4′ per after\_hours and personalization (Appendix C) |
| Ready to hand off  | Need intent, specialty, provider, or specific request — **name alone is not enough** |
| Path A  | Intent clear → *Let me help you with that.* \+ transition same turn |

**Business Hours phase** 

Classify intent, directory/FAQ lookup, confirm provider/location, gate scheduling new/existing, route to auth or routing. 

**Rule Detail** 

| Directory lookup  | First provider/directory lookup on a turn is silent |
| :---- | :---- |
| FAQ  | *Let me check that for you.* \+ lookup in same turn |
| Other lookups  | *One moment.* \+ lookup in same turn |
| Scheduling  | Ask new/existing before auth/routing if appointment\_action \= create and patient\_status is null |
| Appointment actions  | Set ledger appointment\_action from caller intent: create, cancel, reschedule, list, confirm |
| Existing scheduling  | **specialty required**; after auth → Scheduling Init → SpinSci Scheduling Engine |
| Records  | Skip auth → go straight to Routing |
| Retry  | 2 spoken retries, then silent ToRouting on 3rd |
| Triage lookup  | Never use "Triage" as a directory specialty — use real specialty/provider |

**After Hours phase** 

Escalation, hotwords, restricted-service handling, closed-department messaging, and limited live connect.  
**Rule Detail** 

| Restricted services  | INFORM → ASK → wait → Auth → Route (scheduling, referrals, triage, etc.) |
| :---- | :---- |
| Hotword (patient)  | Silent ToRouting; patient\_verified \= N/A; urgent transfer line |
| Billing / MyChart  | Closed messaging — no in-hours department transfer |
| Retry  | 2 spoken retries, then silent ToRouting |

*TBD:* Full hotword keyword list from SpinSci. 

**Authentication phase** 

Verify patient before routing for auth-required intents. 

**Rule Detail** 

| Flow  | Phone → read-back → lookup → DOB → identity validation → Routing |
| :---- | :---- |
| ANI reuse  | Don’t repeat Greeting’s ANI lookup if already done |
| Auth failure  | *No problem. I’ll connect you now.* \+ route same turn |
| Changed request  | Return to Business Hours or After Hours — **never** straight to Routing |

**Routing phase** 

Resolve destination, execute transfer, hangup, or handoff to a downstream agent. 

**Rule Detail** 

| Routing resolution  | Zero speech — no filler at all |
| :---- | :---- |
| Transfer / hangup  | **Zero SpinSci AI text** — only the prescribed transfer or goodbye line |
| Transfer message  | Pick line from Appendix E by ledger intent |
| Existing scheduling  | Hand off to **Scheduling Init** for ledger **specialty** → **SpinSci Scheduling Engine** |
| Switchboard  | Don’t falsely name a specific clinical team |

**Scheduling experience** 

Scheduling spans three layers. Callers experience one continuous conversation — they must not hear about internal handoffs.  
SpinSci AI (switchboard) → Authentication → Scheduling Init → SpinSci Scheduling Engine 

**Responsibility split** 

**Layer Owns Does not own** 

| SpinSci AI (switchboard)  | Specialty, location,  provider, new/existing, appointment\_action , auth gating | Visit type (sick vs wellness), slot search, booking |
| ----- | :---- | :---- |
| **Scheduling Init**  | Visit type, reason for visit, urgency screening | Final slot selection (delegates to Engine) |
| **SpinSci Scheduling Engine**  | Visit-type rules, provider availability, slot matching, booking | Switchboard routing, patient authentication |

**Appointment actions (POC scope)** 

SpinSci AI MUST classify scheduling-related calls into one of five **appointment\_action** values and pass it on the ledger. The SpinSci Scheduling Engine executes the action after switchboard auth and Scheduling Init. 

**appointment\_action Switchboard collects**   
**Ask** 

**new/existing?**   
**Visit type (Scheduling Init)?**   
**Auth? Engine** 

**responsibility** 

| create  | specialty ,  location/provider | Yes (if  unknown) | Yes — sick vs  wellness | Yes if  existing | Provider  availability → offer slots → book |
| :---- | ----- | :---- | :---- | ----- | :---- |
| **cancel**  | specialty ,  optional existing appt date | **No** (existing  implied) | **No**  | **Yes**  | Locate  appointment → cancel |
| **reschedule**  | specialty ,  optional existing appt date | **No** (existing  implied) | **No**  | **Yes**  | Locate  appointment → offer new slots → reschedule |
| **list**  | specialty  | **No** (existing  implied) | **No**  | **Yes**  | Retrieve and read upcoming  appointments |
| **confirm**  | specialty  | **No** (existing  implied) | **No**  | **Yes**  | Retrieve and  confirm  appointment  details |

**REQ-SCHED-00 — Action classification.** When **intent** \= Scheduling, Business Hours MUST set **appointment\_action** from caller speech. Do not default to create when the caller said cancel,  
reschedule, list, or confirm. 

**REQ-SCHED-00b — Existing patient for manage actions.** cancel , reschedule , list , and confirm imply an **existing** patient. Do not ask new/existing; proceed to Authentication after **specialty** is confirmed. 

**End-to-end flow (existing patient, schedule new appointment)** 

1\. Switchboard: collect scheduling intent \+ specialty (+ location/provider when needed) 2\. Switchboard: confirm existing patient → Authentication 

3\. Switchboard: silent Routing → hand off to scheduling agent for specialty 

4\. Scheduling Init: determine visit\_type (sick vs wellness) from caller reason 5\. SpinSci Scheduling Engine: check provider availability for visit\_type \+ specialty 6\. SpinSci Scheduling Engine: offer slots and complete booking (or escalate) 

**End-to-end flow (cancel, reschedule, list, confirm)** 

1\. Switchboard: recognize appointment\_action (cancel / reschedule / list / confirm) \+ specialty 2\. Switchboard: skip new/existing → Authentication 

3\. Switchboard: silent Routing → Scheduling Init for specialty 

4\. Scheduling Init: pass action \+ context to Engine (no visit\_type) 

5\. SpinSci Scheduling Engine: locate appointments, cancel, reschedule, list, or confirm 

**Switchboard handoff (existing patients)** 

When **intent** \= Scheduling and the caller is an **existing** patient (or appointment\_action is cancel / reschedule / list / confirm), route to **Scheduling Init for ledger specialty** after authentication. 

**REQ-SCHED-01 — Specialty required.** Ledger **specialty** MUST be populated and confirmed before handoff. 

**REQ-SCHED-02 — Specialty-scoped handoff.** Hand off to the scheduling agent mapped to ledger **specialty** (SpinSci provides the mapping). 

**REQ-SCHED-03 — New vs existing split.** 

**Patient status / action Destination**

| New ( create only)  | General new-patient intake path |
| :---- | :---- |
| **Existing** or **create** after existing confirmed  | Scheduling Init for **specialty** → Engine |
| **cancel / reschedule / list / confirm**  | Scheduling Init for **specialty** → Engine (always existing; always auth) |

**REQ-SCHED-04 — Payload on handoff.** Pass full Call State Ledger including **specialty** , **location** , **provider\_name** , **appointment\_action** , verification status, and call summary. 

**REQ-SCHED-05 — Switchboard does not ask visit type.** SpinSci AI collects routing context only (specialty, provider, location, new/existing). **Visit type is determined in Scheduling Init**, not on the switchboard. 

**Scheduling Init — visit types** 

Scheduling Init runs immediately after switchboard handoff. Its job is to classify **why** the patient needs an appointment. 

**REQ-SCHED-06 — Visit type required before Engine.** For new appointments ( appointment\_action \= create ), **visit\_type** MUST be set before invoking the SpinSci Scheduling Engine. 

**Primary visit types (POC):** 

**visit\_type Caller signals (examples) Engine use** 

| wellness  | Annual physical, check-up, routine visit, preventive exam, wellness visit | Wellness scheduling rules; typically primary care context |
| :---- | :---- | :---- |
| **sick**  | Symptoms, pain, fever, cold/flu, “not feeling well,” acute complaint | Sick-visit rules; may trigger urgency  screening |

**REQ-SCHED-07 — Wellness \+ symptom disambiguation.** When the caller mentions **both** a wellness keyword (physical, check-up, annual exam) **and** a specific symptom (hand pain, headache, back hurts), Scheduling Init MUST ask one clarifying question before setting visit\_type : 

Just to make sure I schedule the right type of visit — are you looking for an annual wellness exam, or would you like to be seen for your \[symptom\]? 

Wellness confirmed → visit\_type \= wellness 

Symptom visit → visit\_type \= sick 

Both → visit\_type \= wellness (caller may mention concern during visit) 

**REQ-SCHED-08 — Do not re-ask known reason.** If call summary or conversation already contains a clear visit reason, map it directly — do not ask again. 

**REQ-SCHED-09 — Manage actions skip visit type.** For cancel , reschedule , list , and confirm , Scheduling Init MUST NOT ask sick vs wellness. Pass **appointment\_action** and ledger context directly to the SpinSci Scheduling Engine.  
**REQ-SCHED-09b — Cancel.** Engine locates the target appointment (using patient record, specialty, and optional date from ledger) and completes cancellation. 

**REQ-SCHED-09c — Reschedule.** Engine locates the appointment, presents alternative slots, and completes the reschedule. 

**REQ-SCHED-09d — List.** Engine retrieves upcoming appointments for the patient in the relevant specialty and presents them to the caller. 

**REQ-SCHED-09e — Confirm.** Engine retrieves the appointment in question and confirms date, time, provider, and location with the caller. 

**SpinSci Scheduling Engine — provider availability and booking** 

The **SpinSci Scheduling Engine** is the system of record for scheduling logic. Scheduling Init invokes it after required context is known ( visit\_type for **create** only). 

**REQ-SCHED-10 — Engine inputs.** The Engine MUST receive at minimum: 

**Input Source Required for** 

| specialty  | Switchboard ledger  | All actions |
| ----- | :---- | :---- |
| visit\_type  | Scheduling Init  | **create** only |
| patient\_id / verified patient  | Authentication  | All actions |
| location  | Switchboard ledger  | When known |
| provider\_name  | Switchboard ledger  | When known |
| appointment\_action  | Switchboard ledger  | All actions |
| existing\_appointment\_date  | Caller or ledger  | **cancel / reschedule** when provided |

**REQ-SCHED-11 — Provider availability.** The Engine determines which providers can see the patient for the given **visit\_type** at the given **specialty** and **location** . For example: 

Patient’s PCP may not accept **sick** visits but does accept **wellness** 

A selected provider may not have availability for the requested visit type 

Alternative providers at the same location may be offered when the first choice is unavailable 

**REQ-SCHED-12 — Availability-driven conversation.** When the preferred provider is unavailable for the visit type, the Engine (via the scheduling agent) MUST offer alternatives — e.g. another provider at the same location who accepts that visit type — without re-asking facts already collected (discharge dates, visit reason, etc.). 

**REQ-SCHED-13 — Slot presentation.** For **create** and **reschedule** , the Engine returns bookable openings. The scheduling agent presents them to the caller and completes the action through the  
Engine. 

**REQ-SCHED-13b — List and confirm presentation.** For **list** and **confirm** , the Engine returns appointment details for the scheduling agent to read back to the caller. 

**REQ-SCHED-14 — Urgency escalation.** If Scheduling Init or the Engine detects urgent symptoms during sick-visit handling, escalate per SpinSci urgency rules (live agent or triage) before continuing self-service booking. 

**Scheduling flow diagram** 

Switchboard Scheduling Init SpinSci Scheduling Engine ─────────── ─────────────── ───────────────────────── specialty ✓ visit\_type (sick/wellness) provider availability location / provider ✓ → reason for visit → slot search \+ booking existing \+ auth ✓ urgency screen alternative providers handoff ────────────────────► handoff ─────────────────► 

**POC note:** If **specialty** is not activated for scheduling in SpinSci’s catalog, the switchboard MUST inform the caller and offer an alternate path (SpinSci defines fallback).  
**Routing at a glance** 

**Intent Auth? Routing? Special notes** 

| Scheduling  | Yes if existing or manage action; No if new  create | Yes  | All appointment\_action values in scope; create asks  new/existing;  cancel/reschedule/list/confirm → Engine |
| :---- | ----- | :---- | :---- |
| **Referrals**  | Yes  | Yes |  |
| **Triage**  | Yes  | Yes  | Use real specialty for lookup |
| **Pharmacy**  | Yes  | Yes  | Never say medication names |
| **Paging**  | Yes (typical)  | Yes  | Provider vs patient affects after hours path |
| **Billing**  | Yes in-hours  | Yes  | Closed after hours |
| **Records**  | **No**  | Yes (direct)  | Lab results → General, not  Records |
| **mychart**  | Yes (live path)  | Yes  | FAQ first; closed after hours |
| **General**  | Yes  | Yes |  |
| **Directory**  | Yes if connecting  | Yes or hangup  | Info-only may end in goodbye |
| **Hotword-Urgent**  | **No**  | Yes (silent)  | After hours only |

Full matrix with transfer lines: Appendix B. 

**REQ-ROUTE-01** Implement this routing logic for all POC scenarios. 

**REQ-ROUTE-02** Greeting may pre-fill intent before Business Hours continues. 

**REQ-ROUTE-03** Existing scheduling routes through Scheduling Init and the SpinSci Scheduling Engine per Scheduling experience. 

**Gates and auth** 

**GATE-AUTH — Don’t route before verify** 

When intent requires auth and patient is not new and not yet verified: 

Block transfer and routing resolution 

Run silent patient lookup on ANI before first auth phrase (non-provider)  
**GATE-TRANSFER-SPEECH** 

On transfer/hangup turns: only the prescribed spoken line is played. No parallel SpinSci AI speech. 

**GATE-LOOKUP-SPEECH** 

Lookups may use *One moment.* or (FAQ only) *Let me check that for you.* — **must** invoke the lookup in the same turn. 

Exceptions: Business Hours first directory lookup is silent; Routing phase has zero speech. 

**GATE-AH-SPEC — After-hours routing mode** 

Business hours: never use after-hours switchboard routing mode 

After hours (post-auth routing): must use after-hours switchboard routing — not the caller’s real specialty for routing resolution (except hotword immediate path) 

**REQ-AUTH-01 — When auth is required** 

Auth required when intent is Scheduling, Referrals, Triage, Billing, mychart, Paging, Directory, Pharmacy, or General **and** patient is not new. 

**Skip auth:** Records; Scheduling \+ new patient (still must route before transfer). **Default to existing** (don’t ask new/existing): Billing, MyChart, Paging, Directory, Pharmacy, General. 

**Session and schedule** 

**Timezone:** America/Chicago 

**Business hours:** 

**Day Hours** 

| Monday–Friday  | 8:00 AM – 5:00 PM |
| :---- | :---- |
| Saturday  | 8:00 AM – 12:00 PM |
| Sunday  | Closed |

Calls outside business hours use the **After Hours** phase. The after\_hours flag is set at call start from this schedule. 

**Default hangup line:** *Thank you for calling SpinSci. Goodbye.* 

**Default transfer fallback:** *One moment while I connect you.*  
**Integration capabilities** 

Vendor implements connectors for these backend capabilities. Exact API contracts will be provided by SpinSci. 

**Capability Purpose** 

| Patient lookup  | Lookup by ANI or confirmed phone |
| :---- | :---- |
| Provider / directory lookup  | Find providers, locations, departments |
| FAQ / knowledge base  | Answer informational questions |
| Date-of-birth validation  | Verify DOB against record |
| Identity verification  | Confirm patient identity |
| Routing intent resolution  | List available routes for a department |
| Route metadata resolution  | Resolve queue/destination details |
| Transfer  | Connect caller to destination |
| Hangup  | End call gracefully |
| Scheduling agent handoff  | Route to Scheduling Init for specialty — all five appointment\_action values |
| SpinSci Scheduling Engine  | Schedule, cancel, reschedule, list, confirm; provider availability; slots |

**Routing chain:** List available routes, then resolve route metadata using the **exact** intent string returned — never parallel, never fabricated. 

**Existing scheduling:** Hand off to Scheduling Init for ledger **specialty** . Scheduling Init invokes the **SpinSci Scheduling Engine** for provider availability and booking. 

**Transfer payload:** Must include destination, call summary, verification status, and spoken transfer message (when telephony transfer applies).  
**POC acceptance** 

**Acceptance criteria** 

**ID Must be true** 

| AC-01  | Turn 1: lookup only, no speech; welcome from config |
| :---- | :---- |
| AC-02  | Path A: *Let me help you with that.* \+ phase transition same turn |
| AC-03  | Caller never hears system names or JSON |
| AC-04  | Auth and Routing transitions are speech-free |
| AC-05  | Hotword / retry-3: silent Routing; urgent line in transfer message only |
| AC-06  | Changed request in auth returns to Business/After Hours |
| AC-07  | Routing phase: zero speech during routing resolution |
| AC-08  | Transfer/hangup: only prescribed line spoken |
| AC-09  | Records skips auth |
| AC-10  | Scheduling asks new/existing before auth when unknown |
| AC-11  | Auth refusal still connects — never hang up for refusal alone |
| AC-12  | After-hours switchboard routing never used during business hours |
| AC-13  | First directory lookup in Business Hours is silent |
| AC-14  | Existing scheduling: specialty on ledger before handoff; routes to Scheduling Init for that specialty |
| AC-15  | New scheduling: routes to general new-patient path, not specialty scheduling agent |
| AC-16  | Switchboard does not ask sick vs wellness — that happens in Scheduling Init |
| AC-17  | Scheduling Init sets visit\_type before SpinSci Scheduling Engine is invoked |
| AC-18  | Engine checks provider availability for visit\_type \+ specialty ; offers alternatives when preferred provider unavailable |
| AC-19  | Wellness \+ symptom ambiguity triggers disambiguation question before visit\_type is set |
| AC-20  | cancel , reschedule , list , confirm skip new/existing and skip visit type |
| AC-21  | Switchboard sets correct appointment\_action from caller intent (not always create ) |
| AC-22  | Cancel/reschedule/list/confirm require auth and route to Engine for specialty |

**Minimum test scenarios** 

**POC-01 — Scheduling (existing, wellness)** 

Primary care \+ existing patient → auth → Scheduling Init → caller wants annual physical → visit\_type \= wellness → Engine finds provider availability → offers slots.  
**POC-01b — Scheduling (existing, sick)** 

Existing patient \+ sore throat / sick visit → auth → Scheduling Init → visit\_type \= sick → Engine checks PCP/ICC availability for sick visits → offers slots or alternative provider. 

**POC-01c — Scheduling (new, in hours)** 

New patient → skip auth → general new-patient intake path. 

**POC-02 — Records (in hours)** 

Skip auth → silent Routing → Records transfer line. 

**POC-03 — After-hours scheduling** 

Restricted INFORM/ASK script → if caller agrees → auth → after-hours routing. 

**POC-04 — After-hours hotword** 

Silent Routing → patient\_verified \= N/A → urgent transfer line. 

**POC-05 — No routing filler** 

Between auth complete and transfer: zero SpinSci AI speech. 

**POC-06 — Auth refusal** 

*No problem. I’ll connect you now.* → transfer (not hangup). 

**POC-07 — Cold start** 

Turn 1 silent; welcome audio; Script 4′ or branch on turn 2\. 

**POC-08 — Retry exhaustion** 

Two retries spoken; third silent Routing. 

**POC-09 — Changed request in auth** 

*Sure, let me get you to the right place for that.* → Business or After Hours. 

**POC-10 — Auth gate** 

Transfer and routing resolution locked until verify resolves. 

**POC-11 — Reschedule (existing)** 

Reschedule request → specialty confirmed → auth → Scheduling Init (no visit type) → Engine locates appointment → offers new slots. 

**POC-12 — Wellness \+ symptom disambiguation** 

Caller says “I need a physical because my hand hurts” → Scheduling Init asks wellness vs sick for hand → sets visit\_type from answer → Engine proceeds. 

**POC-13 — Provider unavailable for visit type** 

Engine returns that PCP cannot see patient for visit type → scheduling agent offers alternative provider at same location → does not re-ask visit reason or discharge date. 

**POC-14 — Cancel appointment** 

Caller cancels Cardiology appointment → appointment\_action \= cancel → auth → Engine cancels matched appointment.  
**POC-15 — List upcoming appointments** 

Caller asks what appointments they have → appointment\_action \= list → auth → Engine lists upcoming visits for specialty. 

**POC-16 — Confirm appointment** 

Caller confirms tomorrow’s appointment → appointment\_action \= confirm → auth → Engine reads back appointment details. 

**Part 3: Reference appendices**  
**Appendix A — Call flow diagram** 

**![][image1]**  
Call flow — what callers hear 

Phase transitions are inaudible unless noted. Welcome audio on turn 1 is configuration-driven.  
**Appendix B — Route matrix** 

**Intent Set in Auth? To Routing? Hangup path? Transfer line (see Appendix E)**

| Scheduling  | Greeting or  Business Hours | Existing  yes; new  no | Yes  | No  | Existing: scheduling agent for specialty . New: general new patient path |
| :---- | ----- | ----- | :---- | :---- | :---- |
| **Referrals**  | Business Hours | Yes  | After auth  | No  | Referrals |
| **Triage**  | Greeting or  Business Hours | Yes  | After auth  | No  | Triage |
| **Pharmacy**  | Business Hours | Yes  | After auth  | No  | Pharmacy |
| **Paging**  | Greeting or  Business Hours | Yes  (typical) | Yes  | No  | Paging |
| **Billing**  | Business Hours | Yes in  hours | After auth  | After-hours  closed | Billing |
| **Records**  | Business Hours | **No**  | Direct  | No  | Records |
| **mychart**  | Business Hours | Yes (live)  | After auth  | After-hours  closed | mychart |
| **General**  | Business Hours | Yes  | After auth  | No  | General |
| **Directory**  | Business Hours | If  connecting | After auth if  transfer | If info only  | Per final intent |
| **Hotword-Urgent**  | After  Hours | No  | Silent  | No  | Hotword-Urgent |
| **Fallback**  | Routing  phase | Varies  | Yes  | Maybe  | Switchboard /  fallback |

**Intent collection notes** 

**Intent Collected Notes** 

| Scheduling  | Greeting or Business Hours  | Set appointment\_action ( create · cancel ·  reschedule · list ·  confirm ); specialty  required; visit\_type only for create |
| :---- | :---- | :---- |
| Referrals  | Business Hours  | Usually existing patient |
| Triage  | Greeting or Business Hours  | Real specialty for lookup, not “Triage” |
| Pharmacy  | Business Hours  | Urgent may become Triage |
| Paging  | Greeting or Business Hours  | Sets caller\_is\_provider , ah\_intent\_selection |
| Billing  | Business Hours  | Closed after hours |
| Records  | Business Hours  | Lab results → General |
| mychart  | Business Hours  | FAQ first |
| General  | Business Hours  | Includes lab-results routing |
| Directory  | Business Hours  | Info vs connect pivot |
| Hotword-Urgent  | After Hours  | patient\_verified \= N/A |

**Appendix C — Caller scripts** 

All wording is **mandatory**. Placeholders ( {{caller\_name}} , {FirstName} ) are filled at runtime. 

**Greeting** 

**ROUTING REQUEST** — used standalone and in Scripts 3′, 4, 4′, Path B, Path D 

To ensure your call is routed correctly, please provide the provider, specialty, or location you are trying to reach, along with the reason for your call today. 

**Script 4 — Standard in hours (no Step 0\)** 

Thank you for calling SpinSci. This is SpinSci AI, your virtual assistant. To ensure your call is routed correctly, please provide the provider, specialty, or location you are trying to reach, along with the reason for your call today.  
**Script 3′ — After hours (after Step 0\)** — note: no period before *and* 

Our offices are currently closed, so options may be limited, but I’ll do my best to help, and to ensure your call is routed correctly, please provide the provider, specialty, or location you are trying to reach, along with the reason for your call today. 

**Script 2′ — Personalized in hours** 

Am I speaking with {FirstName}? 

**Path A** 

Hi {{caller\_name}}, nice to meet you. Let me help you with that. 

or 

Let me help you with that. 

**Path B** 

Hi {{caller\_name}}, nice to meet you. To ensure your call is routed correctly, please provide the provider, specialty, or location you are trying to reach, along with the reason for your call today. 

**Path D** 

No worries — I can still help you. To ensure your call is routed correctly, please provide the provider, specialty, or location you are trying to reach, along with the reason for your call today. 

**Path E** 

I didn’t quite catch that. Could you repeat that for me? 

**Medication** (never repeat medication name) 

You’re calling about your prescription. 

**Goodbye retention**  
Before you go, is there anything else I can help you with? 

**Hangup** 

Thank you for calling SpinSci. Goodbye. 

**Business Hours** 

**Situation Say exactly**

| FAQ lookup  | Let me check that for you. |
| :---- | :---- |
| Other lookup  | One moment. |
| Directory close  | Can I help with anything else before we end our call? |
| Scheduling gate  | Are you a new or existing patient? |
| Search trouble  | I’m having some trouble finding that. Would you like me to connect you with someone who can help? |
| Retry 1  | I’m sorry, I didn’t catch that. How can I help you direct your call today? |
| Retry 2  | I’m still having trouble understanding. Please tell me what you need help with — like scheduling, a nurse, or a provider. |
| List cap  | I have a few more as well. Would you like me to continue, or does one of those sound right? |
| Goodbye retention  | Before you go, is there anything else I can help you with? |
| Closing  | Thank you for calling SpinSci. Have a great day. |

**After Hours** 

**Situation Say exactly**

| Paging clarifier (pick one)  | Just to route this correctly — are you calling from a hospital or medical facility, or are you the patient? / Are you a doctor or calling from a medical facility, or are you calling for yourself as the patient? / Are you staff calling about a patient, or are you calling for yourself? |
| :---- | :---- |
| Restricted service (scheduling example)  | I’m sorry, our scheduling services are currently closed. You’re welcome to call back during business hours, or I can connect you to someone — though they won’t be from the specific office you’re calling about. Would you like me to do that? |
| MyChart closed  | I’m sorry, MyChart support is currently closed. Please call back during business hours for live assistance. |
| Billing closed  | I’m sorry, our billing department is currently closed. Please call back during business hours for billing assistance. |
| Directory gate  | Let me check that for you. |
| No match  | I wasn’t able to find a match. Would you like me to try a different search? |
| Live connect offer  | Since our offices are currently closed, I can connect you to someone — though they won’t be from the specific office you’re calling about. Would you like me to do that? |
| Retry 1  | I’m sorry, I didn’t catch that. How can I help you? |
| Retry 2  | I’m still having trouble understanding. Could you tell me what you need help with? |
| Follow-up  | Is there anything else I can help with? / Did that help, or is there anything else I can assist with? |

**Authentication** 

**Situation Say exactly** 

| ANI offer  | I can use the phone number you’re calling from to look up your record. Is that okay? |
| :---- | :---- |
| Phone — provider  | Could you please provide the phone number on file for the patient you’re calling about? |
| Phone — patient  | Could you please provide the phone number for the patient? |
| Phone read-back  | I have \[digit 1\] \[digit 2\] \[digit 3\]. \[digit 4\] \[digit 5\] \[digit 6\]. \[digit 7\] \[digit 8\] \[digit 9\] \[digit 10\]. Is that correct? |
| No record  | I wasn’t able to find a record with that phone number. Could you try a different number? |
| DOB — patient  | Could you please provide your date of birth? |
| DOB — provider  | Could you please tell me the full date of birth of the patient you’re calling about? |
| Name confirm  | Can you confirm the full name for the patient is {{FirstName}} {{LastName}}? |
| After confirm  | Thank you for confirming. |
| Auth fail → route  | No problem. I’ll connect you now. |
| Pushback  | It helps us pull up your record. If you’d prefer, I can connect you without it. |
| Changed request  | Sure, let me get you to the right place for that. |
| After-hours DOB opener  | Our offices are currently closed, so options may be limited, but I’ll do my best to help. Can you provide the patient’s date of birth? |

**Scheduling Init (downstream — not switchboard)** 

**Situation Say exactly**

| Visit reason (when unknown)  | What is the reason for your visit today? |
| :---- | :---- |
| Wellness \+ symptom disambiguation  | Just to make sure I schedule the right type of visit — are you looking for an annual wellness exam, or would you like to be seen for your \[symptom\]? |
| Provider unavailable for visit type  | *(SpinSci provides exact wording — offer alternative provider at same location)* |

**Appendix D — Call State Ledger fields** 

**Field Values / notes** 

| caller\_name  | From Greeting |
| ----- | :---- |
| **intent**  | Internal intent label |
| **patient\_status**  | null · new · existing |
| **provider\_name** |  |
| **specialty**  | Normalized when required |
| **scan\_type**  | MRI/CT · Mammo/Dexa · PET/Nuclear · US/Fluoro |
| **location**  | City / address / site |
| **department\_name , department\_id**  | From directory lookup |
| **selected\_id**  | Numeric record ID only |
| **patient\_verified**  | null · Success · Fail · N/A |
| **appointment\_action**  | create · cancel · reschedule · list · confirm |
| **existing\_appointment\_date**  | Optional — for cancel/reschedule when caller identifies which visit |
| **visit\_type**  | sick · wellness — set in Scheduling Init (not switchboard) |
| **visit\_reason**  | Caller-stated reason for visit — used to derive visit\_type |
| **preferred\_provider\_id**  | Set when caller selects or Engine assigns a provider |
| **preferred\_date**  | Caller-stated date preference (when offered) |
| **caller\_is\_provider**  | true for facility/provider paging |
| **patient\_id**  | From patient lookup |
| **after\_hours**  | Schedule flag |
| **greeting\_ani\_lookup\_done**  | Set by Greeting |
| **greeting\_ani\_match\_count**  | ANI match count |
| **ah\_intent\_selection**  | Hospital or Physician · Afterhours Answering Service |

**REQ-LEDGER-01:** Never re-ask a populated field. 

**REQ-LEDGER-03:** Ledger intent ≠ routing intent returned by routing resolution.  
**Appendix E — Transfer lines** 

Used as the spoken transfer message. Routing phase adds **no** other speech. 

**Intent / case Transfer line / action** 

| Scheduling — new  | Let me get you over to our scheduling department. One moment. *(general new-patient path)* |
| :---- | :---- |
| Scheduling — existing  | Let me connect you with our scheduling team for existing patients. One moment. *(hand off to Scheduling Init for specialty ; Engine handles availability)* |
| Triage  | Let me connect you with our nurse triage team. One moment. |
| Referrals  | Let me connect you with the referrals department. One moment. |
| Paging  | Let me connect you now. One moment. |
| Pharmacy  | Let me connect you with someone who can help with your medication. One moment. |
| Billing  | Let me get you over to the Billing department. One moment. |
| Records  | Let me get you over to the Records department. One moment. |
| mychart  | Let me get you over to the My Chart department. One moment. |
| General  | Let me connect you with someone who can help. One moment. |
| Hotword-Urgent  | Let me connect you with someone who can help right away. One moment. |
| Switchboard / fallback  | One moment while I connect you. |
| Switchboard (alt)  | Let me connect you with someone who can help. One moment. |
| Transfer error  | I apologize for the inconvenience. Please try calling back shortly. Thank you for calling SpinSci. |
| Hangup  | Thank you for calling SpinSci. Goodbye. |

**Forbidden in Routing phase:** Hang tight. and similar stall phrases. 

*End of document*
