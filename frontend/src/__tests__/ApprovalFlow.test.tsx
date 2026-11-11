import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ApprovalInboxPage } from '../pages/ApprovalInboxPage';
import { api } from '../api/endpoints';
import * as AuthContextModule from '../auth/AuthContext';
import type { ProcurementRequest } from '../api/types';

vi.mock('../api/endpoints', () => ({
  api: {
    workflows: {
      list: vi.fn(),
      approveOrReject: vi.fn(),
    },
  },
}));

describe('ApprovalInboxPage & Decision Flow', () => {
  const mockWorkflows: ProcurementRequest[] = [
    {
      id: 'req-uuid-1',
      thread_id: 'thread-1',
      requester_id: 'user-requester-id',
      product_id: 'prod-laptops',
      quantity: 50,
      constraints: {},
      status: 'awaiting_approval',
      recommendation: {
        supplier_id: 'sup-tech-1',
        supplier_name: 'Apex Technologies',
        score: '94.5',
        scoring_version: 'v1.0.0',
        total_cost: '45000.00',
        unit_price: '900.00',
        currency: 'USD',
        delivery_days: 7,
        version: 1,
        caveats: [],
        evidence_chunk_ids: ['chk-1'],
      },
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('allows approver to open decision modal and submit approval with stable idempotency key', async () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: { id: 'user-approver-id', email: 'approver@example.com', role: 'approver' },
      token: 'valid-token',
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      isAuthenticated: true,
    });

    vi.mocked(api.workflows.list).mockResolvedValue(mockWorkflows);
    vi.mocked(api.workflows.approveOrReject).mockResolvedValue({
      request_id: 'req-uuid-1',
      thread_id: 'thread-1',
      status: 'executed',
      awaiting_approval: false,
      evidence_chunk_ids: ['chk-1'],
      issues: [],
    });

    render(
      <MemoryRouter>
        <ApprovalInboxPage />
      </MemoryRouter>
    );

    // Wait for workflow to load
    await waitFor(() => {
      expect(screen.getByText('Apex Technologies')).toBeInTheDocument();
    });

    // Click Review & Decide button
    const decideBtn = screen.getByRole('button', { name: /Review & Decide/i });
    expect(decideBtn).not.toBeDisabled();
    fireEvent.click(decideBtn);

    // Modal opens
    expect(screen.getByText('Review Procurement Decision')).toBeInTheDocument();
    expect(screen.getByText('v1')).toBeInTheDocument();

    // Click Approve
    const approveBtn = screen.getByRole('button', { name: /Approve & Execute/i });
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(api.workflows.approveOrReject).toHaveBeenCalledTimes(1);
    });

    const callArgs = vi.mocked(api.workflows.approveOrReject).mock.calls[0];
    expect(callArgs[0]).toBe('thread-1');
    expect(callArgs[1].decision).toBe('approved');
    expect(callArgs[1].recommendation_version).toBe(1);
    expect(callArgs[1].idempotency_key).toBeTruthy();
  });

  it('enforces POL-002: disables review for requester (prohibiting self-approval)', async () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: { id: 'user-requester-id', email: 'requester@example.com', role: 'requester' },
      token: 'valid-token',
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      isAuthenticated: true,
    });

    vi.mocked(api.workflows.list).mockResolvedValue(mockWorkflows);

    render(
      <MemoryRouter>
        <ApprovalInboxPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Apex Technologies')).toBeInTheDocument();
    });

    const decideBtn = screen.getByRole('button', { name: /Review & Decide/i });
    expect(decideBtn).toBeDisabled();
    expect(decideBtn).toHaveAttribute('title', 'Self-approval prohibited (POL-002)');
  });

  it('requires reason for rejection (min 5 chars)', async () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: { id: 'user-approver-id', email: 'approver@example.com', role: 'approver' },
      token: 'valid-token',
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      isAuthenticated: true,
    });

    vi.mocked(api.workflows.list).mockResolvedValue(mockWorkflows);

    render(
      <MemoryRouter>
        <ApprovalInboxPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Apex Technologies')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Review & Decide/i }));

    // Click reject without reason
    const rejectBtn = screen.getByRole('button', { name: /^Reject$/i });
    fireEvent.click(rejectBtn);

    expect(screen.getByText(/Rejection requires a documented reason/i)).toBeInTheDocument();
    expect(api.workflows.approveOrReject).not.toHaveBeenCalled();
  });
});
