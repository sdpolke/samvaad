export interface AmbientNoiseConfiguration {
    enabled: boolean;
    volume: number;
    storage_key?: string;
    storage_backend?: string;
    original_filename?: string;
}

export type TurnStopStrategy = 'transcription' | 'turn_analyzer';

export interface VoicemailDetectionConfiguration {
    enabled: boolean;
    use_workflow_llm: boolean;
    provider?: string;
    model?: string;
    api_key?: string;
    system_prompt?: string;
    long_speech_timeout: number;  // seconds cutoff for long speech detection
}

export const DEFAULT_VOICEMAIL_DETECTION_CONFIGURATION: VoicemailDetectionConfiguration = {
    enabled: false,
    use_workflow_llm: true,
    long_speech_timeout: 8.0,
};

export interface ModelOverrides {
    llm?: {
        provider?: string;
        model?: string;
        api_key?: string;
        [key: string]: unknown;
    };
    tts?: {
        provider?: string;
        model?: string;
        voice?: string;
        api_key?: string;
        [key: string]: unknown;
    };
    stt?: {
        provider?: string;
        model?: string;
        api_key?: string;
        [key: string]: unknown;
    };
    realtime?: {
        provider?: string;
        model?: string;
        voice?: string;
        api_key?: string;
        [key: string]: unknown;
    };
    is_realtime?: boolean;
}

export interface WorkflowConfigurations {
    ambient_noise_configuration: AmbientNoiseConfiguration;
    max_call_duration: number;  // Maximum call duration in seconds
    max_user_idle_timeout: number;  // Maximum user idle time in seconds
    smart_turn_stop_secs: number;  // Timeout in seconds for incomplete turn detection
    turn_stop_strategy: TurnStopStrategy;  // Strategy for detecting end of user turn
    dictionary?: string;  // Comma-separated words for voice agent to listen for
    voicemail_detection?: VoicemailDetectionConfiguration;
    context_compaction_enabled?: boolean;  // Summarize context on node transitions to remove stale tool calls
    model_overrides?: ModelOverrides;  // Per-workflow model configuration overrides
    tts_expression?: TTSExpressionConfiguration;  // Cartesia TTS emotion/speed
    vad_config?: VADConfiguration;  // Per-workflow VAD tuning
    goodbye_detection?: GoodbyeDetectionConfiguration;  // Goodbye phrase detection
    call_state_detection?: CallStateDetectionConfiguration;  // IVR/voicemail/human detection
    callback_scheduling?: CallbackSchedulingConfiguration;  // Callback scheduling tool
    [key: string]: unknown;  // Allow additional properties for future configurations
}

// ── BDR Feature Configurations ──────────────────────────────────────────

export interface TTSExpressionConfiguration {
    enabled: boolean;
    emotion?: string;  // Cartesia emotion: "content", "happy", "sad", etc.
    speed?: number;    // 0.5 - 2.0
}

export const DEFAULT_TTS_EXPRESSION_CONFIGURATION: TTSExpressionConfiguration = {
    enabled: false,
    emotion: undefined,
    speed: 1.0,
};

export interface VADConfiguration {
    enabled: boolean;
    confidence: number;   // 0.0 - 1.0
    start_secs: number;   // seconds
    stop_secs: number;    // seconds
    min_volume: number;   // 0.0 - 1.0
}

export const DEFAULT_VAD_CONFIGURATION: VADConfiguration = {
    enabled: false,
    confidence: 0.5,
    start_secs: 0.2,
    stop_secs: 0.8,
    min_volume: 0.6,
};

export const TELEPHONY_VAD_PRESET: Omit<VADConfiguration, "enabled"> = {
    confidence: 0.55,
    start_secs: 0.12,
    stop_secs: 0.45,
    min_volume: 0.0,
};

export interface GoodbyeDetectionConfiguration {
    enabled: boolean;
    phrases: string[];
    action: "end_call" | "prompt_goodbye";
}

export const DEFAULT_GOODBYE_DETECTION_CONFIGURATION: GoodbyeDetectionConfiguration = {
    enabled: false,
    phrases: ["goodbye", "bye", "not interested", "no thanks"],
    action: "end_call",
};

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

export const DEFAULT_CALL_STATE_DETECTION_CONFIGURATION: CallStateDetectionConfiguration = {
    enabled: false,
    max_ivr_secs: 60,
    ivr_target_description: "",
    use_workflow_llm: false,
};

export interface CallbackSchedulingConfiguration {
    enabled: boolean;
}

export const DEFAULT_CALLBACK_SCHEDULING_CONFIGURATION: CallbackSchedulingConfiguration = {
    enabled: false,
};

export const DEFAULT_WORKFLOW_CONFIGURATIONS: WorkflowConfigurations = {
    ambient_noise_configuration: {
        enabled: false,
        volume: 0.3
    },
    max_call_duration: 600,  // 10 minutes
    max_user_idle_timeout: 10,  // 10 seconds
    smart_turn_stop_secs: 2,  // 2 seconds
    turn_stop_strategy: 'transcription',  // Default to transcription-based detection
    dictionary: ''
};
