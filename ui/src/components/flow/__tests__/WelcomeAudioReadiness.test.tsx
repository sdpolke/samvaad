import { describe, expect, it } from "vitest";

import type { NodeSpec } from "@/client/types.gen";
import { needsWelcomeAudioRecording } from "@/components/flow/nodes/GenericNode";
import type { FlowNodeData } from "@/components/flow/types";

// ─── Minimal fixtures ─────────────────────────────────────────────────────

const startCallSpec: NodeSpec = {
    name: "startCall",
    display_name: "Start Call",
    description: "Entry point of the call flow",
    category: "core" as never,
    icon: "Phone",
    version: "1.0.0",
    properties: [
        {
            name: "prompt",
            type: "mention_textarea",
            display_name: "Prompt",
            description: "System prompt for the agent",
        } as never,
    ],
    examples: [],
    graph_constraints: null,
};

const agentNodeSpec: NodeSpec = {
    name: "agentNode",
    display_name: "Agent",
    description: "An agent step in the flow",
    category: "core" as never,
    icon: "Bot",
    version: "1.0.0",
    properties: [],
    examples: [],
    graph_constraints: null,
};

// ─── Tests ────────────────────────────────────────────────────────────────

describe("needsWelcomeAudioRecording", () => {
    it("returns true when startCall has greeting_type='audio' and no greeting_recording_id", () => {
        const data: FlowNodeData = {
            name: "Greeting",
            greeting_type: "audio",
        };

        expect(needsWelcomeAudioRecording(startCallSpec, data)).toBe(true);
    });

    it("returns true when greeting_recording_id is an empty string", () => {
        const data: FlowNodeData = {
            name: "Greeting",
            greeting_type: "audio",
            greeting_recording_id: "",
        };

        expect(needsWelcomeAudioRecording(startCallSpec, data)).toBe(true);
    });

    it("returns false when greeting_recording_id is set", () => {
        const data: FlowNodeData = {
            name: "Greeting",
            greeting_type: "audio",
            greeting_recording_id: "rec-uuid-123",
        };

        expect(needsWelcomeAudioRecording(startCallSpec, data)).toBe(false);
    });

    it("returns false when greeting_type is 'text' (not audio)", () => {
        const data: FlowNodeData = {
            name: "Greeting",
            greeting_type: "text",
        };

        expect(needsWelcomeAudioRecording(startCallSpec, data)).toBe(false);
    });

    it("returns false when greeting_type is undefined", () => {
        const data: FlowNodeData = {
            name: "Greeting",
        };

        expect(needsWelcomeAudioRecording(startCallSpec, data)).toBe(false);
    });

    it("returns false for non-startCall spec even with audio and no recording", () => {
        const data: FlowNodeData = {
            name: "Agent Step",
            greeting_type: "audio",
        };

        expect(needsWelcomeAudioRecording(agentNodeSpec, data)).toBe(false);
    });
});
