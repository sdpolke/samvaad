"use client";

import { useState } from "react";

import { LLMConfigSelector } from "@/components/LLMConfigSelector";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
    type CallbackSchedulingConfiguration,
    type CallStateDetectionConfiguration,
    DEFAULT_CALLBACK_SCHEDULING_CONFIGURATION,
    DEFAULT_CALL_STATE_DETECTION_CONFIGURATION,
    DEFAULT_GOODBYE_DETECTION_CONFIGURATION,
    DEFAULT_TTS_EXPRESSION_CONFIGURATION,
    DEFAULT_VAD_CONFIGURATION,
    type GoodbyeDetectionConfiguration,
    TELEPHONY_VAD_PRESET,
    type TTSExpressionConfiguration,
    type VADConfiguration,
    type WorkflowConfigurations,
} from "@/types/workflow-configurations";

// ── TTS Expression Section ──────────────────────────────────────────────

interface TTSExpressionSectionProps {
    workflowConfigurations: WorkflowConfigurations;
    onSave: (configurations: WorkflowConfigurations) => Promise<void>;
}

export function TTSExpressionSection({ workflowConfigurations, onSave }: TTSExpressionSectionProps) {
    const config = (workflowConfigurations.tts_expression as TTSExpressionConfiguration) || DEFAULT_TTS_EXPRESSION_CONFIGURATION;
    const [enabled, setEnabled] = useState(config.enabled);
    const [emotion, setEmotion] = useState(config.emotion || "");
    const [speed, setSpeed] = useState(config.speed || 1.0);
    const [isSaving, setIsSaving] = useState(false);

    const handleSave = async () => {
        setIsSaving(true);
        try {
            const updated = { ...workflowConfigurations };
            if (enabled) {
                updated.tts_expression = { enabled: true, emotion: emotion || undefined, speed };
            } else {
                delete updated.tts_expression;
            }
            await onSave(updated);
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <Card id="tts-expression">
            <CardHeader>
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-base">TTS Expression</CardTitle>
                        <CardDescription>Configure emotion and speed for Cartesia TTS output.</CardDescription>
                    </div>
                    <Switch checked={enabled} onCheckedChange={setEnabled} />
                </div>
            </CardHeader>
            {enabled && (
                <CardContent className="space-y-4">
                    <div className="space-y-2">
                        <Label className="text-sm">Emotion</Label>
                        <Select value={emotion || "none"} onValueChange={(v) => setEmotion(v === "none" ? "" : v)}>
                            <SelectTrigger><SelectValue placeholder="Select emotion" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="none">None</SelectItem>
                                <SelectItem value="content">Content</SelectItem>
                                <SelectItem value="happy">Happy</SelectItem>
                                <SelectItem value="sad">Sad</SelectItem>
                                <SelectItem value="angry">Angry</SelectItem>
                                <SelectItem value="surprised">Surprised</SelectItem>
                                <SelectItem value="fearful">Fearful</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-2">
                        <Label className="text-sm">Speed ({speed}x)</Label>
                        <Input type="number" step="0.1" min="0.5" max="2.0" value={speed}
                            onChange={(e) => setSpeed(parseFloat(e.target.value) || 1.0)} />
                    </div>
                    <p className="text-xs text-muted-foreground">Only applies when using Cartesia as the TTS provider.</p>
                </CardContent>
            )}
            <CardFooter className="border-t pt-4">
                <Button onClick={handleSave} disabled={isSaving} size="sm">
                    {isSaving ? "Saving..." : "Save"}
                </Button>
            </CardFooter>
        </Card>
    );
}

// ── VAD Tuning Section ──────────────────────────────────────────────────

interface VADTuningSectionProps {
    workflowConfigurations: WorkflowConfigurations;
    onSave: (configurations: WorkflowConfigurations) => Promise<void>;
}

export function VADTuningSection({ workflowConfigurations, onSave }: VADTuningSectionProps) {
    const config = (workflowConfigurations.vad_config as VADConfiguration) || DEFAULT_VAD_CONFIGURATION;
    const [enabled, setEnabled] = useState(config.enabled);
    const [confidence, setConfidence] = useState(config.confidence);
    const [startSecs, setStartSecs] = useState(config.start_secs);
    const [stopSecs, setStopSecs] = useState(config.stop_secs);
    const [minVolume, setMinVolume] = useState(config.min_volume);
    const [isSaving, setIsSaving] = useState(false);

    const applyPreset = (preset: string) => {
        if (preset === "telephony") {
            setConfidence(TELEPHONY_VAD_PRESET.confidence);
            setStartSecs(TELEPHONY_VAD_PRESET.start_secs);
            setStopSecs(TELEPHONY_VAD_PRESET.stop_secs);
            setMinVolume(TELEPHONY_VAD_PRESET.min_volume);
        } else {
            setConfidence(DEFAULT_VAD_CONFIGURATION.confidence);
            setStartSecs(DEFAULT_VAD_CONFIGURATION.start_secs);
            setStopSecs(DEFAULT_VAD_CONFIGURATION.stop_secs);
            setMinVolume(DEFAULT_VAD_CONFIGURATION.min_volume);
        }
    };

    const handleSave = async () => {
        setIsSaving(true);
        try {
            const updated = { ...workflowConfigurations };
            if (enabled) {
                updated.vad_config = { enabled: true, confidence, start_secs: startSecs, stop_secs: stopSecs, min_volume: minVolume };
            } else {
                delete updated.vad_config;
            }
            await onSave(updated);
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <Card id="vad">
            <CardHeader>
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-base">VAD Tuning</CardTitle>
                        <CardDescription>Customize Voice Activity Detection parameters for telephony.</CardDescription>
                    </div>
                    <Switch checked={enabled} onCheckedChange={setEnabled} />
                </div>
            </CardHeader>
            {enabled && (
                <CardContent className="space-y-4">
                    <div className="space-y-2">
                        <Label className="text-sm">Preset</Label>
                        <Select onValueChange={applyPreset}>
                            <SelectTrigger><SelectValue placeholder="Select preset" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="telephony">Telephony (recommended)</SelectItem>
                                <SelectItem value="default">Default</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label className="text-xs">Confidence (0-1)</Label>
                            <Input type="number" step="0.05" min="0" max="1" value={confidence}
                                onChange={(e) => setConfidence(parseFloat(e.target.value) || 0.5)} />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-xs">Start Secs</Label>
                            <Input type="number" step="0.01" min="0" value={startSecs}
                                onChange={(e) => setStartSecs(parseFloat(e.target.value) || 0.2)} />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-xs">Stop Secs</Label>
                            <Input type="number" step="0.01" min="0" value={stopSecs}
                                onChange={(e) => setStopSecs(parseFloat(e.target.value) || 0.8)} />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-xs">Min Volume (0-1)</Label>
                            <Input type="number" step="0.05" min="0" max="1" value={minVolume}
                                onChange={(e) => setMinVolume(parseFloat(e.target.value) || 0.0)} />
                        </div>
                    </div>
                </CardContent>
            )}
            <CardFooter className="border-t pt-4">
                <Button onClick={handleSave} disabled={isSaving} size="sm">
                    {isSaving ? "Saving..." : "Save"}
                </Button>
            </CardFooter>
        </Card>
    );
}

// ── Goodbye Detection Section ───────────────────────────────────────────

interface GoodbyeDetectionSectionProps {
    workflowConfigurations: WorkflowConfigurations;
    onSave: (configurations: WorkflowConfigurations) => Promise<void>;
}

export function GoodbyeDetectionSection({ workflowConfigurations, onSave }: GoodbyeDetectionSectionProps) {
    const config = (workflowConfigurations.goodbye_detection as GoodbyeDetectionConfiguration) || DEFAULT_GOODBYE_DETECTION_CONFIGURATION;
    const [enabled, setEnabled] = useState(config.enabled);
    const [phrases, setPhrases] = useState<string[]>(config.phrases);
    const [action, setAction] = useState(config.action);
    const [newPhrase, setNewPhrase] = useState("");
    const [isSaving, setIsSaving] = useState(false);

    const addPhrase = () => {
        if (newPhrase.trim() && !phrases.includes(newPhrase.trim().toLowerCase())) {
            setPhrases([...phrases, newPhrase.trim().toLowerCase()]);
            setNewPhrase("");
        }
    };

    const removePhrase = (index: number) => {
        setPhrases(phrases.filter((_, i) => i !== index));
    };

    const handleSave = async () => {
        setIsSaving(true);
        try {
            const updated = { ...workflowConfigurations };
            if (enabled && phrases.length > 0) {
                updated.goodbye_detection = { enabled: true, phrases, action };
            } else {
                delete updated.goodbye_detection;
            }
            await onSave(updated);
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <Card id="goodbye">
            <CardHeader>
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-base">Goodbye Detection</CardTitle>
                        <CardDescription>Detect goodbye phrases and end calls gracefully.</CardDescription>
                    </div>
                    <Switch checked={enabled} onCheckedChange={setEnabled} />
                </div>
            </CardHeader>
            {enabled && (
                <CardContent className="space-y-4">
                    <div className="space-y-2">
                        <Label className="text-sm">Action</Label>
                        <Select value={action} onValueChange={(v) => setAction(v as "end_call" | "prompt_goodbye")}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="end_call">End Call Immediately</SelectItem>
                                <SelectItem value="prompt_goodbye">Speak Farewell First</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-2">
                        <Label className="text-sm">Phrases</Label>
                        <div className="flex gap-2">
                            <Input value={newPhrase} onChange={(e) => setNewPhrase(e.target.value)}
                                placeholder="Add phrase..." onKeyDown={(e) => e.key === "Enter" && addPhrase()} />
                            <Button variant="outline" size="sm" onClick={addPhrase}>Add</Button>
                        </div>
                        <div className="flex flex-wrap gap-1.5 mt-2">
                            {phrases.map((phrase, i) => (
                                <span key={i} className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-xs">
                                    {phrase}
                                    <button onClick={() => removePhrase(i)} className="text-muted-foreground hover:text-foreground">×</button>
                                </span>
                            ))}
                        </div>
                        {enabled && phrases.length === 0 && (
                            <p className="text-xs text-destructive">At least one phrase is required.</p>
                        )}
                    </div>
                </CardContent>
            )}
            <CardFooter className="border-t pt-4">
                <Button onClick={handleSave} disabled={isSaving || (enabled && phrases.length === 0)} size="sm">
                    {isSaving ? "Saving..." : "Save"}
                </Button>
            </CardFooter>
        </Card>
    );
}

// ── Call State Detection Section ────────────────────────────────────────

interface CallStateDetectionSectionProps {
    workflowConfigurations: WorkflowConfigurations;
    onSave: (configurations: WorkflowConfigurations) => Promise<void>;
}

export function CallStateDetectionSection({ workflowConfigurations, onSave }: CallStateDetectionSectionProps) {
    const config = (workflowConfigurations.call_state_detection as CallStateDetectionConfiguration) || DEFAULT_CALL_STATE_DETECTION_CONFIGURATION;
    const [enabled, setEnabled] = useState(config.enabled);
    const [maxIvrSecs, setMaxIvrSecs] = useState(config.max_ivr_secs);
    const [ivrTarget, setIvrTarget] = useState(config.ivr_target_description);
    const [voicemailMessage, setVoicemailMessage] = useState(config.voicemail_message || "");
    const [useWorkflowLlm, setUseWorkflowLlm] = useState(config.use_workflow_llm);
    const [provider, setProvider] = useState(config.provider || "groq");
    const [model, setModel] = useState(config.model || "llama-3.3-70b-versatile");
    const [apiKey, setApiKey] = useState(config.api_key || "");
    const [isSaving, setIsSaving] = useState(false);

    const handleSave = async () => {
        setIsSaving(true);
        try {
            const updated = { ...workflowConfigurations };
            if (enabled) {
                updated.call_state_detection = {
                    enabled: true,
                    max_ivr_secs: maxIvrSecs,
                    ivr_target_description: ivrTarget,
                    voicemail_message: voicemailMessage || undefined,
                    use_workflow_llm: useWorkflowLlm,
                    provider: useWorkflowLlm ? undefined : provider,
                    model: useWorkflowLlm ? undefined : model,
                    api_key: useWorkflowLlm ? undefined : apiKey,
                };
            } else {
                delete updated.call_state_detection;
            }
            await onSave(updated);
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <Card id="call-state">
            <CardHeader>
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-base">Call State Detection</CardTitle>
                        <CardDescription>Detect IVR, voicemail, or human for outbound calls.</CardDescription>
                    </div>
                    <Switch checked={enabled} onCheckedChange={setEnabled} />
                </div>
            </CardHeader>
            {enabled && (
                <CardContent className="space-y-4">
                    <div className="space-y-2">
                        <Label className="text-sm">Max Detection Time (seconds)</Label>
                        <Input type="number" min="10" max="300" value={maxIvrSecs}
                            onChange={(e) => setMaxIvrSecs(parseInt(e.target.value) || 60)} />
                    </div>
                    <div className="space-y-2">
                        <Label className="text-sm">IVR Target Description</Label>
                        <Input value={ivrTarget} onChange={(e) => setIvrTarget(e.target.value)}
                            placeholder="e.g., business development or the decision-maker" />
                        {enabled && !ivrTarget && (
                            <p className="text-xs text-destructive">Target description is required.</p>
                        )}
                    </div>
                    <div className="space-y-2">
                        <Label className="text-sm">Voicemail Message (optional)</Label>
                        <Textarea value={voicemailMessage} onChange={(e) => setVoicemailMessage(e.target.value)}
                            placeholder="Message to leave if voicemail is detected..." className="min-h-[80px]" />
                    </div>
                    <div className="space-y-3 border rounded-md p-3 bg-muted/10">
                        <div className="flex items-center space-x-2">
                            <Switch checked={useWorkflowLlm} onCheckedChange={setUseWorkflowLlm} />
                            <Label className="text-sm">Use Workflow LLM for classification</Label>
                        </div>
                        {!useWorkflowLlm && (
                            <LLMConfigSelector
                                provider={provider}
                                onProviderChange={setProvider}
                                model={model}
                                onModelChange={setModel}
                                apiKey={apiKey}
                                onApiKeyChange={setApiKey}
                            />
                        )}
                    </div>
                </CardContent>
            )}
            <CardFooter className="border-t pt-4">
                <Button onClick={handleSave} disabled={isSaving || (enabled && !ivrTarget)} size="sm">
                    {isSaving ? "Saving..." : "Save"}
                </Button>
            </CardFooter>
        </Card>
    );
}

// ── Callback Scheduling Section ─────────────────────────────────────────

interface CallbackSchedulingSectionProps {
    workflowConfigurations: WorkflowConfigurations;
    onSave: (configurations: WorkflowConfigurations) => Promise<void>;
}

export function CallbackSchedulingSection({ workflowConfigurations, onSave }: CallbackSchedulingSectionProps) {
    const config = (workflowConfigurations.callback_scheduling as CallbackSchedulingConfiguration) || DEFAULT_CALLBACK_SCHEDULING_CONFIGURATION;
    const [enabled, setEnabled] = useState(config.enabled);
    const [isSaving, setIsSaving] = useState(false);

    const handleSave = async () => {
        setIsSaving(true);
        try {
            const updated = { ...workflowConfigurations };
            if (enabled) {
                updated.callback_scheduling = { enabled: true };
            } else {
                delete updated.callback_scheduling;
            }
            await onSave(updated);
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <Card id="callback">
            <CardHeader>
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-base">Callback Scheduling</CardTitle>
                        <CardDescription>Allow the agent to schedule follow-up calls during conversations.</CardDescription>
                    </div>
                    <Switch checked={enabled} onCheckedChange={setEnabled} />
                </div>
            </CardHeader>
            <CardFooter className="border-t pt-4">
                <Button onClick={handleSave} disabled={isSaving} size="sm">
                    {isSaving ? "Saving..." : "Save"}
                </Button>
            </CardFooter>
        </Card>
    );
}
