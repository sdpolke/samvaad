'use client';

import { FileStack, Loader2 } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';

import {
    duplicateWorkflowTemplateApiV1WorkflowTemplatesDuplicatePost,
    getWorkflowTemplatesApiV1WorkflowTemplatesGet,
} from '@/client/sdk.gen';
import type { WorkflowTemplateResponse } from '@/client/types.gen';
import { Button } from '@/components/ui/button';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/lib/auth';
import logger from '@/lib/logger';

const SWITCHBOARD_TEMPLATE_NAME = 'spinsci-switchboard';
const SWITCHBOARD_TEMPLATE_DESCRIPTION = 'SpinSci AI Virtual Switchboard (inbound).';

/**
 * Hardcoded fallback entry for the switchboard template, used when the API
 * response does not include it (Req 2.6).
 */
const SWITCHBOARD_FALLBACK: WorkflowTemplateResponse = {
    id: -1,
    template_name: SWITCHBOARD_TEMPLATE_NAME,
    template_description: SWITCHBOARD_TEMPLATE_DESCRIPTION,
    template_json: {},
    created_at: '',
};

interface CreateFromTemplateDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

export function CreateFromTemplateDialog({ open, onOpenChange }: CreateFromTemplateDialogProps) {
    const router = useRouter();
    const { user, getAccessToken } = useAuth();

    const [templates, setTemplates] = useState<WorkflowTemplateResponse[]>([]);
    const [loading, setLoading] = useState(false);
    const [selectedTemplate, setSelectedTemplate] = useState<WorkflowTemplateResponse | null>(null);
    const [workflowName, setWorkflowName] = useState('');
    const [isCreating, setIsCreating] = useState(false);

    // Fetch templates when dialog opens
    useEffect(() => {
        if (!open) return;

        const fetchTemplates = async () => {
            setLoading(true);
            try {
                const accessToken = await getAccessToken();
                const response = await getWorkflowTemplatesApiV1WorkflowTemplatesGet({
                    headers: {
                        Authorization: `Bearer ${accessToken}`,
                    },
                });

                const fetched = response.data ?? [];

                // Ensure the switchboard entry is always present (Req 2.6)
                const hasSwitchboard = fetched.some(
                    (t) => t.template_name === SWITCHBOARD_TEMPLATE_NAME
                );

                if (hasSwitchboard) {
                    setTemplates(fetched);
                } else {
                    setTemplates([SWITCHBOARD_FALLBACK, ...fetched]);
                }
            } catch (error) {
                logger.error(`Error fetching workflow templates: ${error}`);
                // Still show the switchboard fallback even on fetch failure
                setTemplates([SWITCHBOARD_FALLBACK]);
            } finally {
                setLoading(false);
            }
        };

        fetchTemplates();
    }, [open, getAccessToken]);

    // Reset state when dialog closes
    useEffect(() => {
        if (!open) {
            setSelectedTemplate(null);
            setWorkflowName('');
        }
    }, [open]);

    const handleConfirm = useCallback(async () => {
        if (!selectedTemplate || !workflowName.trim() || !user) return;

        setIsCreating(true);
        try {
            const accessToken = await getAccessToken();
            const response = await duplicateWorkflowTemplateApiV1WorkflowTemplatesDuplicatePost({
                body: {
                    template_id: selectedTemplate.id,
                    workflow_name: workflowName.trim(),
                },
                headers: {
                    Authorization: `Bearer ${accessToken}`,
                },
            });

            if (response.data?.id) {
                // Success — navigate to the new workflow (Req 2.4)
                onOpenChange(false);
                router.push(`/workflow/${response.data.id}`);
            } else if (response.error) {
                // Server returned an error body (Req 2.5, 2.7)
                const message =
                    typeof response.error === 'object' && response.error !== null && 'detail' in response.error
                        ? String((response.error as { detail?: unknown }).detail)
                        : 'Failed to create workflow from template';
                toast.error(message);
                logger.error(`Template instantiation failed: ${message}`);
            }
        } catch (error) {
            // Network/unexpected error — keep dialog open (Req 2.5, 2.7)
            toast.error('Failed to create workflow from template');
            logger.error(`Error creating workflow from template: ${error}`);
        } finally {
            setIsCreating(false);
        }
    }, [selectedTemplate, workflowName, user, getAccessToken, onOpenChange, router]);

    const canConfirm = selectedTemplate !== null && workflowName.trim().length > 0 && !isCreating;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-lg">
                <DialogHeader>
                    <DialogTitle>Create from Template</DialogTitle>
                    <DialogDescription>
                        Select a template and provide a name for your new workflow.
                    </DialogDescription>
                </DialogHeader>

                {loading ? (
                    <div className="flex items-center justify-center py-8">
                        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                    </div>
                ) : (
                    <div className="space-y-4">
                        {/* Template list */}
                        <div className="space-y-2 max-h-60 overflow-y-auto">
                            {templates.map((template) => (
                                <button
                                    key={template.id}
                                    type="button"
                                    className={`w-full text-left p-3 rounded-md border transition-colors ${
                                        selectedTemplate?.id === template.id
                                            ? 'border-primary bg-primary/5'
                                            : 'border-border hover:border-primary/50'
                                    }`}
                                    onClick={() => setSelectedTemplate(template)}
                                >
                                    <div className="flex items-start gap-3">
                                        <FileStack className="w-5 h-5 mt-0.5 shrink-0 text-muted-foreground" />
                                        <div>
                                            <div className="font-medium text-sm">
                                                {template.template_name}
                                            </div>
                                            <div className="text-xs text-muted-foreground mt-0.5">
                                                {template.template_description}
                                            </div>
                                        </div>
                                    </div>
                                </button>
                            ))}
                            {templates.length === 0 && (
                                <p className="text-sm text-muted-foreground text-center py-4">
                                    No templates available.
                                </p>
                            )}
                        </div>

                        {/* Workflow name input */}
                        <div className="space-y-1.5">
                            <label htmlFor="workflow-name" className="text-sm font-medium">
                                Workflow Name
                            </label>
                            <Input
                                id="workflow-name"
                                placeholder="Enter a name for the new workflow"
                                value={workflowName}
                                onChange={(e) => setWorkflowName(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' && canConfirm) {
                                        handleConfirm();
                                    }
                                }}
                            />
                        </div>
                    </div>
                )}

                <DialogFooter>
                    <Button
                        variant="outline"
                        onClick={() => onOpenChange(false)}
                        disabled={isCreating}
                    >
                        Cancel
                    </Button>
                    <Button onClick={handleConfirm} disabled={!canConfirm}>
                        {isCreating ? (
                            <>
                                <Loader2 className="w-4 h-4 animate-spin" />
                                Creating...
                            </>
                        ) : (
                            'Create Workflow'
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
