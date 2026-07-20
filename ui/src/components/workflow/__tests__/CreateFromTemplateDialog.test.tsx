import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// ─── Mocks (vi.hoisted ensures variables are available to hoisted vi.mock) ────

const { mockPush, mockGetTemplates, mockDuplicate, mockToastError, mockGetAccessToken } = vi.hoisted(() => ({
    mockPush: vi.fn(),
    mockGetTemplates: vi.fn(),
    mockDuplicate: vi.fn(),
    mockToastError: vi.fn(),
    mockGetAccessToken: vi.fn().mockResolvedValue('test-token'),
}));

vi.mock('next/navigation', () => ({
    useRouter: () => ({ push: mockPush }),
}));

vi.mock('@/client/sdk.gen', () => ({
    getWorkflowTemplatesApiV1WorkflowTemplatesGet: (...args: unknown[]) => mockGetTemplates(...args),
    duplicateWorkflowTemplateApiV1WorkflowTemplatesDuplicatePost: (...args: unknown[]) => mockDuplicate(...args),
}));

vi.mock('@/lib/auth', () => ({
    useAuth: () => ({
        user: { id: 1 },
        getAccessToken: mockGetAccessToken,
    }),
}));

vi.mock('sonner', () => ({
    toast: { error: mockToastError },
}));

vi.mock('@/lib/logger', () => ({
    default: { error: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

// ─── Imports under test (AFTER mocks) ─────────────────────────────────────────

import { CreateFromTemplateDialog } from '../CreateFromTemplateDialog';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function renderDialog(open = true) {
    const onOpenChange = vi.fn();
    render(<CreateFromTemplateDialog open={open} onOpenChange={onOpenChange} />);
    return { onOpenChange };
}

const TEMPLATE_A = {
    id: 10,
    template_name: 'alpha-template',
    template_description: 'Alpha template description',
    template_json: {},
    created_at: '2025-01-01T00:00:00Z',
};

const TEMPLATE_B = {
    id: 20,
    template_name: 'beta-template',
    template_description: 'Beta template description',
    template_json: {},
    created_at: '2025-01-02T00:00:00Z',
};

const SWITCHBOARD_TEMPLATE = {
    id: 99,
    template_name: 'spinsci-switchboard',
    template_description: 'SpinSci AI Virtual Switchboard (inbound).',
    template_json: {},
    created_at: '2025-01-03T00:00:00Z',
};

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('CreateFromTemplateDialog', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it('renders fetched templates with their template_name and template_description (Req 2.1, 2.2)', async () => {
        mockGetTemplates.mockResolvedValue({ data: [TEMPLATE_A, TEMPLATE_B] });

        renderDialog();

        await waitFor(() => {
            expect(screen.getByText('alpha-template')).toBeInTheDocument();
        });
        expect(screen.getByText('Alpha template description')).toBeInTheDocument();
        expect(screen.getByText('beta-template')).toBeInTheDocument();
        expect(screen.getByText('Beta template description')).toBeInTheDocument();
    });

    it('always renders the switchboard fallback when fetch does not include it (Req 2.6)', async () => {
        mockGetTemplates.mockResolvedValue({ data: [TEMPLATE_A] });

        renderDialog();

        await waitFor(() => {
            expect(screen.getByText('spinsci-switchboard')).toBeInTheDocument();
        });
        expect(screen.getByText('SpinSci AI Virtual Switchboard (inbound).')).toBeInTheDocument();
        // The fetched template should also be present
        expect(screen.getByText('alpha-template')).toBeInTheDocument();
    });

    it('uses the fetched switchboard entry when API includes it (no duplicate) (Req 2.6)', async () => {
        mockGetTemplates.mockResolvedValue({ data: [TEMPLATE_A, SWITCHBOARD_TEMPLATE] });

        renderDialog();

        await waitFor(() => {
            expect(screen.getByText('spinsci-switchboard')).toBeInTheDocument();
        });
        // Should only have one switchboard entry, not two
        const switchboardEntries = screen.getAllByText('spinsci-switchboard');
        expect(switchboardEntries).toHaveLength(1);
    });

    it('still shows switchboard fallback when fetch fails entirely (Req 2.6)', async () => {
        mockGetTemplates.mockRejectedValue(new Error('Network error'));

        renderDialog();

        await waitFor(() => {
            expect(screen.getByText('spinsci-switchboard')).toBeInTheDocument();
        });
        expect(screen.getByText('SpinSci AI Virtual Switchboard (inbound).')).toBeInTheDocument();
    });

    it('calls duplicate endpoint with selected template_id and user-provided workflow_name on confirm (Req 2.3)', async () => {
        mockGetTemplates.mockResolvedValue({ data: [TEMPLATE_A] });
        mockDuplicate.mockResolvedValue({ data: { id: 42 } });

        renderDialog();

        // Wait for templates to load
        await waitFor(() => {
            expect(screen.getByText('alpha-template')).toBeInTheDocument();
        });

        // Select a template
        fireEvent.click(screen.getByText('alpha-template'));

        // Enter workflow name
        const input = screen.getByPlaceholderText('Enter a name for the new workflow');
        fireEvent.change(input, { target: { value: 'My New Workflow' } });

        // Click Create
        fireEvent.click(screen.getByRole('button', { name: /Create Workflow/i }));

        await waitFor(() => {
            expect(mockDuplicate).toHaveBeenCalledWith(
                expect.objectContaining({
                    body: {
                        template_id: TEMPLATE_A.id,
                        workflow_name: 'My New Workflow',
                    },
                })
            );
        });
    });

    it('on successful creation, navigates to /workflow/{id} (Req 2.4)', async () => {
        mockGetTemplates.mockResolvedValue({ data: [TEMPLATE_A] });
        mockDuplicate.mockResolvedValue({ data: { id: 55 } });

        const { onOpenChange } = renderDialog();

        await waitFor(() => {
            expect(screen.getByText('alpha-template')).toBeInTheDocument();
        });

        fireEvent.click(screen.getByText('alpha-template'));
        const input = screen.getByPlaceholderText('Enter a name for the new workflow');
        fireEvent.change(input, { target: { value: 'Test WF' } });
        fireEvent.click(screen.getByRole('button', { name: /Create Workflow/i }));

        await waitFor(() => {
            expect(mockPush).toHaveBeenCalledWith('/workflow/55');
        });
        expect(onOpenChange).toHaveBeenCalledWith(false);
    });

    it('on failed creation, shows error toast and does NOT navigate — dialog stays open (Req 2.5, 2.7)', async () => {
        mockGetTemplates.mockResolvedValue({ data: [TEMPLATE_A] });
        mockDuplicate.mockResolvedValue({ data: null, error: { detail: 'Validation failed' } });

        renderDialog();

        await waitFor(() => {
            expect(screen.getByText('alpha-template')).toBeInTheDocument();
        });

        fireEvent.click(screen.getByText('alpha-template'));
        const input = screen.getByPlaceholderText('Enter a name for the new workflow');
        fireEvent.change(input, { target: { value: 'Failing Workflow' } });
        fireEvent.click(screen.getByRole('button', { name: /Create Workflow/i }));

        await waitFor(() => {
            expect(mockToastError).toHaveBeenCalledWith('Validation failed');
        });
        expect(mockPush).not.toHaveBeenCalled();
    });

    it('Create button is disabled when no template is selected or workflow name is empty', async () => {
        mockGetTemplates.mockResolvedValue({ data: [TEMPLATE_A] });

        renderDialog();

        await waitFor(() => {
            expect(screen.getByText('alpha-template')).toBeInTheDocument();
        });

        // Initially disabled — nothing selected, no name
        const createBtn = screen.getByRole('button', { name: /Create Workflow/i });
        expect(createBtn).toBeDisabled();

        // Select template but no name yet — still disabled
        fireEvent.click(screen.getByText('alpha-template'));
        expect(createBtn).toBeDisabled();

        // Enter name — now enabled
        const input = screen.getByPlaceholderText('Enter a name for the new workflow');
        fireEvent.change(input, { target: { value: 'Valid Name' } });
        expect(createBtn).not.toBeDisabled();
    });
});
