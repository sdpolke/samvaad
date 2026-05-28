# BDR-Calling Integration into Samvaad — Technical Plan

## Executive Summary

This document outlines how to bring bdr-calling's outbound BDR (Business Development Representative) capabilities into Samvaad without altering Samvaad's existing architecture. The approach leverages Samvaad's extensible configuration layers — `workflow_configurations`, `template_context_variables`, the telephony provider registry, and the campaign system — to support BDR use cases natively.

---

## 1. Architecture Comparison

### Samvaad (Dograh)
- Multi-tenant: Organizations → Users → Workflows → Workflow Runs
- Visual workflow builder (ReactFlow node graph)
- Versioned workflow definitions with `workflow_configurations` JSON blob
- Registry-based telephony providers (Twilio, Vonage, Telnyx, Plivo, Cloudonix, ARI, Vobiz)
- Campaign system for bulk outbound calling (CSV source, rate limiting, retry, scheduling)
- PipecatEngine interprets workflow graph nodes at runtime

### bdr-calling
- Single-purpose outbound voice agent
- File-based per-customer JSON configs (`CustomerConfig`)
- Flat pipeline: STT → CallState → RAG → LLM → TTS
- Two telephony providers: Twilio + Exotel
- Features: IVR navigation, voicemail detection + message, idle monitoring with goodbye phrases, callback scheduling, TTS expression tuning, static knowledge injection

---

## 2. Feature Gap Analysis

| BDR Feature | Samvaad Status | Gap Level |
|---|---|---|
| Outbound calling | ✅ Supported (campaigns + test calls) | None |
| System prompt with placeholders | ✅ Supported (workflow nodes + template_context_variables) | None |
| LLM model/temperature override | ✅ Supported (model_overrides in workflow_configurations) | None |
| TTS voice selection | ✅ Supported (model_overrides.tts) | None |
| Voicemail detection | ✅ Supported (workflow_configurations.voicemail_detection) | None |
| Campaign CSV with lead data | ✅ Supported (campaign source_type=csv) | None |
| Retry on busy/no-answer/voicemail | ✅ Supported (campaign retry_config) | None |
| Call scheduling (time slots) | ✅ Supported (campaign schedule_config) | None |
| Max call duration | ✅ Supported (workflow_configurations.max_call_duration) | None |
| Idle timeout | ✅ Supported (workflow_configurations.max_user_idle_timeout) | None |
| **TTS expression (emotion, speed)** | ❌ Not exposed | **Medium** |
| **VAD tuning per workflow** | ❌ Not exposed | **Medium** |
| **Goodbye phrase detection** | ❌ Not supported | **Medium** |
| **IVR/Call state detection + DTMF navigation** | ❌ Not supported | **High** |
| **Callback scheduling tool** | ❌ Not supported | **Medium** |
| **Exotel telephony provider** | ❌ Not in registry | **High** |
| **Static knowledge in system prompt** | ⚠️ Partial (knowledge base exists but different mechanism) | **Low** |

---

## 3. Integration Strategy

### Principle: Use existing extension points, no architecture changes

Samvaad's architecture provides these extension points that we'll use:

1. **`workflow_configurations`** — Extensible JSON blob on each workflow version. New keys can be added without schema migrations.
2. **`model_overrides`** — Already supports per-workflow LLM/TTS/STT switching.
3. **`template_context_variables`** — Dynamic variable injection into workflow runs.
4. **Telephony provider registry** — `ProviderSpec` + `register()` pattern.
5. **Campaign system** — CSV source with context variables per row.
6. **PipecatEngine** — Workflow node interpreter that can be extended with new node types.
7. **Organization configurations** — Key-value store for org-level settings.

---

## 4. Implementation Plan

### Phase 1: Add Exotel Telephony Provider (High Priority)

**What**: Register Exotel as a new telephony provider in Samvaad's registry.

**Where**: `api/services/telephony/providers/exotel/`

**Steps**:

1. Create provider folder structure:
```
api/services/telephony/providers/exotel/
├── __init__.py          # register(ProviderSpec(...))
├── provider.py          # ExotelProvider(TelephonyProvider)
├── transport.py         # Transport factory (WebSocket frame serializer)
├── routes.py            # Webhook endpoints for Exotel callbacks
├── schemas.py           # Pydantic request/response models
└── serializer.py        # Exotel WebSocket frame serializer
```

2. Implement `ProviderSpec`:
```python
from api.services.telephony.registry import ProviderSpec, register

spec = ProviderSpec(
    name="exotel",
    provider_cls=ExotelProvider,
    config_loader=_load_exotel_config,
    transport_factory=create_exotel_transport,
    transport_sample_rate=8000,
    config_request_cls=ExotelConfigRequest,
    config_response_cls=ExotelConfigResponse,
    account_id_credential_field="account_sid",
    ui_metadata=ProviderUIMetadata(
        display_name="Exotel",
        fields=[
            ProviderUIField(name="api_key", label="API Key", type="password", sensitive=True),
            ProviderUIField(name="api_token", label="API Token", type="password", sensitive=True),
            ProviderUIField(name="account_sid", label="Account SID", type="text"),
            ProviderUIField(name="subdomain", label="Subdomain", type="text", 
                          placeholder="api.in.exotel.com"),
            ProviderUIField(name="app_id", label="App ID", type="text"),
        ],
    ),
)
register(spec)
```

3. Port bdr-calling's `app/telephony/exotel/` logic:
   - `provider.py` → Handshake parsing (detect `stream_sid` in start data)
   - `serializer.py` → Exotel WebSocket frame serialization (μ-law 8kHz)
   - `client.py` → REST API for initiating outbound calls

4. Add import in `api/services/telephony/providers/__init__.py`

5. Add Alembic migration for `WorkflowRunMode` enum to include `"exotel"`.

**Reference**: Use bdr-calling's `app/telephony/exotel/` as the source implementation. Adapt to Samvaad's `TelephonyProvider` base class and registry pattern.

---

### Phase 2: Extend `workflow_configurations` for BDR Features (Medium Priority)

**What**: Add new configuration keys to `workflow_configurations` that the pipeline reads at runtime.

**No schema migration needed** — `workflow_configurations` is already a JSON column.

#### 2a. TTS Expression Config

**New key**: `tts_expression`

```json
{
  "workflow_configurations": {
    "tts_expression": {
      "emotion": "content",
      "speed": 0.8
    }
  }
}
```

**Implementation**: In `api/services/pipecat/service_factory.py`, when creating the TTS service, check for `tts_expression` in `run_configs` and apply Cartesia's `GenerationConfig`:

```python
# In create_tts_service() or the TTS creation path
tts_expression = run_configs.get("tts_expression")
if tts_expression and hasattr(tts_service, 'settings'):
    from pipecat.services.cartesia.tts import GenerationConfig
    tts_service.settings.generation_config = GenerationConfig(
        emotion=tts_expression.get("emotion"),
        speed=tts_expression.get("speed", 1.0),
    )
```

#### 2b. VAD Tuning Per Workflow

**New key**: `vad_config`

```json
{
  "workflow_configurations": {
    "vad_config": {
      "confidence": 0.55,
      "start_secs": 0.12,
      "stop_secs": 0.45,
      "min_volume": 0.0
    }
  }
}
```

**Implementation**: In `run_pipeline.py`, read `vad_config` from `run_configs` and pass to the VAD analyzer creation:

```python
vad_config = run_configs.get("vad_config")
if vad_config:
    vad = SileroVADAnalyzer(params=VADParams(
        confidence=vad_config.get("confidence", 0.5),
        start_secs=vad_config.get("start_secs", 0.2),
        stop_secs=vad_config.get("stop_secs", 0.8),
        min_volume=vad_config.get("min_volume", 0.6),
    ))
```

#### 2c. Goodbye Phrase Detection

**New key**: `goodbye_detection`

```json
{
  "workflow_configurations": {
    "goodbye_detection": {
      "enabled": true,
      "phrases": ["goodbye", "bye", "not interested", "no thanks"],
      "action": "end_call"
    }
  }
}
```

**Implementation**: Create a new frame processor `GoodbyeDetectorProcessor` in `api/services/pipecat/` that monitors transcription frames and triggers call termination when a goodbye phrase is detected. Insert it into the pipeline after STT.

#### 2d. Call State Detection (IVR Navigation)

**New key**: `call_state_detection`

```json
{
  "workflow_configurations": {
    "call_state_detection": {
      "enabled": true,
      "max_ivr_secs": 60,
      "ivr_target_description": "business development or the decision-maker",
      "voicemail_message": "Hi, this is {agent_name}..."
    }
  }
}
```

**Implementation**: Port bdr-calling's `app/core/call_state.py` as a new processor in `api/services/pipecat/call_state_detector.py`. This is the most complex feature:

1. Create `CallStateDetectorProcessor` following the same pattern as bdr-calling's `CallStateDetector`
2. Insert it into the pipeline after STT (before user aggregator) for outbound calls
3. Use the workflow's configured LLM for classification (via `inference_llm` or a lightweight side-channel call)
4. Wire DTMF output through pipecat's existing `OutputDTMFUrgentFrame`
5. On human detection → proceed with normal workflow
6. On voicemail → speak configured message and end call

**Key difference from bdr-calling**: Instead of hardcoding Groq for classification, use the workflow's configured LLM provider (already resolved in `run_pipeline.py`).

---

### Phase 3: Callback Scheduling Tool (Medium Priority)

**What**: Add a built-in "schedule_callback" tool that workflows can enable.

**Approach**: Implement as a new tool category in Samvaad's tool system.

#### 3a. Database Model

Add a new model for callback requests:

```python
class CallbackRequestModel(Base):
    __tablename__ = "callback_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True)
    
    lead_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=False)
    company = Column(String, nullable=True)
    
    callback_date = Column(String, nullable=False)  # YYYY-MM-DD
    callback_time = Column(String, nullable=False)
    timezone = Column(String, nullable=False)
    reason = Column(Text, nullable=True)
    
    status = Column(String, default="pending")  # pending, completed, cancelled
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
```

#### 3b. Tool Registration

In the PipecatEngine or pipeline setup, when `workflow_configurations.callback_scheduling.enabled` is true, register the `schedule_callback` function on the LLM service:

```json
{
  "workflow_configurations": {
    "callback_scheduling": {
      "enabled": true
    }
  }
}
```

The tool schema matches bdr-calling's:
- Parameters: `date`, `time`, `timezone`, `reason`
- Stores to DB with workflow_run context (phone number from initial_context)
- Returns confirmation message

#### 3c. Campaign Integration

Callbacks stored in the DB can be:
- Surfaced in the campaign UI as "pending callbacks"
- Auto-queued as new campaign runs at the scheduled time (via ARQ background task)

---

### Phase 4: Static Knowledge Injection (Low Priority)

**What**: Allow embedding static knowledge text directly into the system prompt, similar to bdr-calling's `knowledge` field.

**Approach**: This already partially exists in Samvaad via the workflow node's prompt field and knowledge base system. Two options:

**Option A** (Recommended — zero code change): Use `template_context_variables` to inject knowledge:

```json
{
  "template_context_variables": {
    "knowledge": "New Mexico Partnership is the state's economic development organization..."
  }
}
```

Then reference `{{knowledge}}` in the workflow node's system prompt. Samvaad's template engine already substitutes these.

**Option B**: Add a `static_knowledge` key to `workflow_configurations` that gets prepended to the system prompt at pipeline runtime. This is more explicit but requires a code change in the prompt assembly logic.

---

### Phase 5: Outbound Greeting with Placeholder Substitution (Low Priority)

**What**: Support `{caller_name}`, `{agent_name}`, `{time_of_day}` placeholders in outbound greeting messages.

**Samvaad already supports this** via `template_context_variables`. The campaign CSV provides per-row values (lead_name, company, etc.) that get injected into `initial_context`. The workflow's start node can reference these in its greeting prompt.

**Enhancement needed**: Ensure the PipecatEngine's greeting/first-message logic substitutes `initial_context` variables into the greeting text before TTS. Check if this already happens in the start node's prompt rendering.

---

## 5. Configuration Mapping Reference

This table shows how each bdr-calling `CustomerConfig` field maps to Samvaad:

| BDR CustomerConfig Field | Samvaad Location | Notes |
|---|---|---|
| `customer_id` | Workflow ID | One workflow per "customer" |
| `display_name` | `workflow.name` | |
| `agent_name` | `template_context_variables.agent_name` | Referenced in prompt as `{{agent_name}}` |
| `system_prompt` | Workflow start node prompt | |
| `greeting_prompt` | Workflow start node greeting config | |
| `tts_voice_id` | `workflow_configurations.model_overrides.tts.voice` | |
| `tts_model` | `workflow_configurations.model_overrides.tts.model` | |
| `tts_expression` | `workflow_configurations.tts_expression` | **New key** |
| `llm_model` | `workflow_configurations.model_overrides.llm.model` | |
| `llm_temperature` | `workflow_configurations.model_overrides.llm.temperature` | |
| `knowledge` | `template_context_variables.knowledge` | Injected into prompt |
| `vectordb` | Samvaad knowledge base system | Different mechanism, same outcome |
| `call.direction` | Campaign = outbound; inbound via phone number routing | |
| `call.idle_timeout_secs` | `workflow_configurations.max_user_idle_timeout` | |
| `call.goodbye_phrases` | `workflow_configurations.goodbye_detection.phrases` | **New key** |
| `call.end_call_tool_enabled` | Workflow tool node configuration | |
| `greeting.outbound_message` | Workflow start node + `template_context_variables` | |
| `greeting.outbound_delay_secs` | `workflow_configurations.outbound_greeting_delay` | **New key** |
| `greeting.caller_name_param` | Campaign CSV column mapping → `initial_context` | |
| `vad.*` | `workflow_configurations.vad_config` | **New key** |
| `voicemail.*` | `workflow_configurations.voicemail_detection` | Already supported |
| `call_state_detection.*` | `workflow_configurations.call_state_detection` | **New key** |
| `tools[]` | Workflow tool nodes (HTTP/webhook tools) | |

---

## 6. Campaign CSV → BDR Context Variables

bdr-calling passes per-call context (lead_name, company, campaign, etc.) via telephony custom parameters. In Samvaad, this maps directly to the campaign system:

**Campaign CSV format**:
```csv
phone_number,lead_name,company,description
+1234567890,John Smith,Acme Corp,Interested in expansion
+0987654321,Jane Doe,Beta Inc,Follow-up from webinar
```

**How it flows**:
1. Campaign source sync reads CSV → creates `queued_runs` with context
2. Campaign dispatcher creates `workflow_run` with `initial_context = {phone_number, lead_name, company, description}`
3. PipecatEngine renders workflow node prompts with `initial_context` variables
4. `{lead_name}` in greeting → substituted from `initial_context.lead_name`

This is already how Samvaad campaigns work. No changes needed.

---

## 7. Implementation Priority & Effort

| Phase | Feature | Backend Effort | UI Effort | Priority | Dependencies |
|---|---|---|---|---|---|
| 1 | Exotel provider | 3-5 days | 0 (uses existing telephony UI) | High | None |
| 2a | TTS expression | 0.5 day | 0.5 day | Medium | None |
| 2b | VAD tuning | 0.5 day | 0.5 day | Medium | None |
| 2c | Goodbye detection | 1-2 days | 1 day | Medium | None |
| 2d | Call state detection (IVR) | 3-5 days | 2-3 days | High | Phase 1 (for Exotel testing) |
| 3 | Callback scheduling | 2-3 days | 1 day | Medium | DB migration |
| 4 | Static knowledge injection | 0 days | 0 days | Low | Already possible via template vars |
| 5 | Greeting placeholder substitution | 0.5 day | 0 days | Low | Verify existing behavior |

**Total estimated effort**: 15-22 days (backend + UI combined)

---

## 8. Migration Path for Existing BDR Customers

To migrate an existing bdr-calling customer config (e.g., `newmexico_outbound.json`) to Samvaad:

1. **Create a workflow** with a single conversation node containing the `system_prompt`
2. **Set `template_context_variables`**:
   ```json
   {
     "agent_name": "Jacqueline Torres",
     "knowledge": "<static knowledge text>"
   }
   ```
3. **Set `workflow_configurations`**:
   ```json
   {
     "max_user_idle_timeout": 20,
     "model_overrides": {
       "llm": { "provider": "groq", "model": "llama-3.3-70b-versatile", "temperature": 0.7 },
       "tts": { "provider": "cartesia", "voice": "<voice_id>", "model": "sonic-3" }
     },
     "tts_expression": { "emotion": "content", "speed": 0.8 },
     "vad_config": { "confidence": 0.55, "start_secs": 0.12, "stop_secs": 0.45 },
     "voicemail_detection": {
       "enabled": true,
       "message": "Hi, this is Jacqueline Torres calling from New Mexico Partnership..."
     },
     "call_state_detection": {
       "enabled": true,
       "max_ivr_secs": 60,
       "ivr_target_description": "business development, economic development, or the decision-maker"
     },
     "goodbye_detection": {
       "enabled": true,
       "phrases": ["goodbye", "bye", "not interested", "no thanks"]
     },
     "callback_scheduling": { "enabled": true }
   }
   ```
4. **Create a campaign** with the CSV of leads, pointing to this workflow
5. **Configure Exotel** (or Twilio) as the telephony provider for the org

---

## 9. UI Changes Required

The Samvaad UI manages workflow configurations through a settings page at `/workflow/[workflowId]/settings/page.tsx`. BDR features need corresponding UI controls.

### Architecture of UI Configuration

- **Type definitions**: `ui/src/types/workflow-configurations.ts` — TypeScript interfaces for all config shapes
- **Settings page**: `ui/src/app/workflow/[workflowId]/settings/page.tsx` — Main settings page with sidebar navigation (General, Model Overrides, Template Variables, Dictionary, Voicemail Detection, Recordings, etc.)
- **Dialog components**: `ui/src/app/workflow/[workflowId]/components/` — Separate dialog components for complex configs (e.g., `VoicemailDetectionDialog.tsx`, `ConfigurationsDialog.tsx`)
- **Pattern**: Each config section is a `<Card>` with header, content, and save button. Complex configs get their own dialog.

### 9a. Type Definitions (`ui/src/types/workflow-configurations.ts`)

Add new interfaces:

```typescript
// TTS Expression (Cartesia emotion/speed)
export interface TTSExpressionConfiguration {
    enabled: boolean;
    emotion?: string;  // "content", "happy", "sad", etc.
    speed?: number;    // 0.5 - 2.0
}

// VAD Tuning
export interface VADConfiguration {
    enabled: boolean;
    confidence: number;   // 0.0 - 1.0
    start_secs: number;   // seconds
    stop_secs: number;    // seconds
    min_volume: number;   // 0.0 - 1.0
}

// Goodbye Detection
export interface GoodbyeDetectionConfiguration {
    enabled: boolean;
    phrases: string[];
    action: 'end_call' | 'prompt_goodbye';
}

// Call State Detection (IVR Navigation)
export interface CallStateDetectionConfiguration {
    enabled: boolean;
    max_ivr_secs: number;
    ivr_target_description: string;
    voicemail_message?: string;
    use_workflow_llm: boolean;
    provider?: string;
    model?: string;
    api_key?: string;
}

// Callback Scheduling
export interface CallbackSchedulingConfiguration {
    enabled: boolean;
}
```

Add to `WorkflowConfigurations` interface:

```typescript
export interface WorkflowConfigurations {
    // ... existing fields ...
    tts_expression?: TTSExpressionConfiguration;
    vad_config?: VADConfiguration;
    goodbye_detection?: GoodbyeDetectionConfiguration;
    call_state_detection?: CallStateDetectionConfiguration;
    callback_scheduling?: CallbackSchedulingConfiguration;
}
```

### 9b. Settings Page Navigation

Add new nav items to `NAV_ITEMS` array in the settings page:

```typescript
const NAV_ITEMS = [
    { id: "general", label: "General", icon: Settings },
    { id: "models", label: "Model Overrides", icon: Brain },
    { id: "variables", label: "Template Variables", icon: Variable },
    { id: "dictionary", label: "Dictionary", icon: BookA },
    { id: "voicemail", label: "Voicemail Detection", icon: PhoneOff },
    // NEW BDR items:
    { id: "call-state", label: "Call State Detection", icon: Phone },
    { id: "goodbye", label: "Goodbye Detection", icon: HandMetal },
    { id: "vad", label: "VAD Tuning", icon: AudioLines },
    { id: "tts-expression", label: "TTS Expression", icon: Speech },
    { id: "callback", label: "Callback Scheduling", icon: CalendarClock },
    // existing:
    { id: "recordings", label: "Recordings", icon: Mic },
    { id: "deployment", label: "Add to Website", icon: Rocket },
    { id: "report", label: "Report", icon: FileDown },
    { id: "identity", label: "Agent UUID", icon: Fingerprint },
];
```

### 9c. New UI Components Needed

| Component | Location | Complexity | Pattern to Follow |
|---|---|---|---|
| `CallStateDetectionSection` | Settings page Card section | High | `VoicemailDetectionDialog.tsx` (has LLM config, system prompt, timing) |
| `GoodbyeDetectionSection` | Settings page Card section | Low | Simple switch + tag input for phrases |
| `VADConfigSection` | Settings page Card section | Low | Number inputs (confidence, start_secs, stop_secs, min_volume) |
| `TTSExpressionSection` | Settings page Card section | Low | Dropdown for emotion + number input for speed |
| `CallbackSchedulingSection` | Settings page Card section | Low | Simple enable/disable switch |

### 9d. Call State Detection UI (Most Complex)

This mirrors the `VoicemailDetectionDialog` pattern:

```
┌─────────────────────────────────────────────┐
│ Call State Detection (IVR Navigation)       │
│                                             │
│ [x] Enable Call State Detection             │
│                                             │
│ ┌─ IVR Configuration ─────────────────────┐ │
│ │ Max Detection Time: [60] seconds        │ │
│ │                                         │ │
│ │ Target Description:                     │ │
│ │ [business development or decision-maker]│ │
│ │                                         │ │
│ │ Voicemail Message (if VM detected):     │ │
│ │ [Hi, this is {agent_name} calling...]   │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│ ┌─ LLM for Classification ───────────────┐ │
│ │ [x] Use Workflow LLM                    │ │
│ │ [ ] Custom LLM:                         │ │
│ │     Provider: [Groq ▼]                  │ │
│ │     Model:    [llama-3.3-70b ▼]         │ │
│ │     API Key:  [••••••••]                │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│                          [Cancel] [Save]    │
└─────────────────────────────────────────────┘
```

### 9e. Goodbye Detection UI

```
┌─────────────────────────────────────────────┐
│ Goodbye Detection                           │
│                                             │
│ [x] Enable Goodbye Detection                │
│                                             │
│ Phrases (one per line or comma-separated):  │
│ ┌─────────────────────────────────────────┐ │
│ │ goodbye                                 │ │
│ │ bye                                     │ │
│ │ not interested                          │ │
│ │ no thanks                               │ │
│ │ + Add phrase                            │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│ Action: [End Call ▼]                        │
│                                             │
│                          [Cancel] [Save]    │
└─────────────────────────────────────────────┘
```

### 9f. VAD Tuning UI

```
┌─────────────────────────────────────────────┐
│ VAD Tuning                                  │
│                                             │
│ [x] Custom VAD Settings                     │
│                                             │
│ Confidence:  [0.55]  (0.0 - 1.0)           │
│ Start Secs:  [0.12]  (speech start delay)   │
│ Stop Secs:   [0.45]  (silence before stop)  │
│ Min Volume:  [0.0]   (minimum audio level)  │
│                                             │
│ Preset: [Telephony (recommended) ▼]         │
│         [Default]                           │
│         [Telephony (recommended)]           │
│         [Custom]                            │
│                                             │
│                          [Cancel] [Save]    │
└─────────────────────────────────────────────┘
```

### 9g. TTS Expression UI

```
┌─────────────────────────────────────────────┐
│ TTS Expression (Cartesia)                   │
│                                             │
│ [x] Enable Expression Settings              │
│                                             │
│ Emotion: [Content ▼]                        │
│          [None]                             │
│          [Content]                          │
│          [Happy]                            │
│          [Sad]                              │
│          [Angry]                            │
│          [Surprised]                        │
│                                             │
│ Speed:   [0.8]  (0.5 - 2.0)                │
│                                             │
│ Note: Only applies when using Cartesia TTS  │
│                                             │
│                          [Cancel] [Save]    │
└─────────────────────────────────────────────┘
```

### 9h. Implementation Order for UI

1. **Types** — Add interfaces to `workflow-configurations.ts` (5 min)
2. **VAD Tuning section** — Simple number inputs (30 min)
3. **TTS Expression section** — Dropdown + number (30 min)
4. **Goodbye Detection section** — Switch + phrase list (1 hr)
5. **Callback Scheduling section** — Just a switch (15 min)
6. **Call State Detection section** — Complex, mirrors voicemail dialog (2-3 hrs)

Total UI effort: ~5-6 hours

---

## 10. What Does NOT Change in Samvaad

- Database schema (except new `callback_requests` table and Exotel enum value)
- API route structure
- Authentication/authorization
- Workflow graph engine (PipecatEngine)
- Campaign orchestration logic
- Frontend/UI component architecture (same Card/Dialog pattern)
- Existing telephony providers
- Organization/user model
- Redis/ARQ task queue

---

## 11. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Call state detection adds latency | Medium | Use fast LLM (Groq) for classification; timeout defaults to HUMAN |
| Exotel WebSocket format differences | Low | Well-tested in bdr-calling; port directly |
| `workflow_configurations` JSON bloat | Low | Keys are optional; only read when present |
| Callback scheduling without campaign context | Low | Store org_id + workflow_run_id for traceability |
| DTMF support varies by provider | Medium | Only enable call_state_detection for providers that support DTMF output |

---

## 12. Testing Strategy

1. **Unit tests**: Each new processor (CallStateDetector, GoodbyeDetector) with mocked frames
2. **Integration tests**: End-to-end pipeline with new `workflow_configurations` keys
3. **Telephony tests**: Exotel provider with mock WebSocket (same pattern as existing Twilio tests)
4. **Campaign tests**: CSV → queued_run → dispatch with BDR-style context variables
5. **Regression**: Ensure existing workflows without BDR keys behave identically (all new features are opt-in via config flags)
