import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/endpoints';
import type { ProcurementRequest } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { ErrorBanner } from '../components/ErrorBanner';
import { Loading } from '../components/Loading';
import { TrustBadge } from '../components/TrustBadge';

export const ApprovalInboxPage: React.FC = () => {
  const { user } = useAuth();

  const [workflows, setWorkflows] = useState<ProcurementRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ message: string; correlationId?: string } | null>(null);

  // Filter state
  const [statusFilter, setStatusFilter] = useState<'awaiting_approval' | 'all'>('awaiting_approval');

  // Selected item for inline decision dialog
  const [selectedRequest, setSelectedRequest] = useState<ProcurementRequest | null>(null);
  const [actionReason, setActionReason] = useState('');
  const [actionSubmitting, setActionSubmitting] = useState(false);
  const [actionError, setActionError] = useState<{ message: string; correlationId?: string } | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Stable idempotency key generated once when dialog opens
  const [idempotencyKey, setIdempotencyKey] = useState<string>('');

  const fetchWorkflows = async () => {
    try {
      setLoading(true);
      setError(null);
      const filter = statusFilter === 'all' ? undefined : statusFilter;
      const data = await api.workflows.list(filter, 100, 0);
      setWorkflows(data);
    } catch (err: any) {
      setError({
        message: err.message || 'Failed to fetch workflow approval list.',
        correlationId: err.correlationId,
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWorkflows();
  }, [statusFilter]);

  const openDecisionModal = (req: ProcurementRequest) => {
    setSelectedRequest(req);
    setActionReason('');
    setActionError(null);
    setActionSuccess(null);
    setIdempotencyKey(crypto.randomUUID());
  };

  const closeDecisionModal = () => {
    setSelectedRequest(null);
    setActionReason('');
    setActionError(null);
  };

  const handleDecision = async (decision: 'approved' | 'rejected') => {
    if (!selectedRequest) return;

    if (decision === 'rejected' && (!actionReason || actionReason.trim().length < 5)) {
      setActionError({ message: 'Rejection requires a documented reason (at least 5 characters).' });
      return;
    }

    setActionSubmitting(true);
    setActionError(null);

    try {
      const recVersion = selectedRequest.recommendation?.version ?? 1;
      await api.workflows.approveOrReject(selectedRequest.thread_id, {
        decision,
        reason: actionReason.trim() || undefined,
        recommendation_version: recVersion,
        idempotency_key: idempotencyKey,
      });

      setActionSuccess(
        decision === 'approved'
          ? `Request #${selectedRequest.id.slice(0, 8)} approved and sent to MCP ERP execution.`
          : `Request #${selectedRequest.id.slice(0, 8)} rejected.`
      );

      // Refresh inbox
      await fetchWorkflows();
      setTimeout(() => {
        closeDecisionModal();
      }, 1500);
    } catch (err: any) {
      if (err.status === 409) {
        setActionError({
          message: 'Conflict: Recommendation version changed or decision was already submitted. Please refresh.',
          correlationId: err.correlationId,
        });
      } else if (err.status === 403) {
        setActionError({
          message: 'Access Denied: You cannot approve this request under POL-002 (self-approval prohibited or missing approver role).',
          correlationId: err.correlationId,
        });
      } else {
        setActionError({
          message: err.message || 'Failed to submit approval decision.',
          correlationId: err.correlationId,
        });
      }
    } finally {
      setActionSubmitting(false);
    }
  };

  const canApproveRole = user && (user.role === 'approver' || user.role === 'admin');

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '1.5rem',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#111827', margin: 0 }}>
            Approval Inbox
          </h1>
          <p style={{ fontSize: '0.875rem', color: '#6b7280', marginTop: '0.25rem' }}>
            Human-in-the-loop governance for purchase orders (POL-002). Server-side authorization prohibits self-approval.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as any)}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              border: '1px solid #d1d5db',
              fontSize: '0.85rem',
              backgroundColor: '#ffffff',
            }}
          >
            <option value="awaiting_approval">Awaiting Approval Only</option>
            <option value="all">All Workflows</option>
          </select>

          <button
            type="button"
            onClick={fetchWorkflows}
            style={{
              padding: '6px 12px',
              backgroundColor: '#f3f4f6',
              border: '1px solid #d1d5db',
              borderRadius: '6px',
              fontSize: '0.85rem',
              cursor: 'pointer',
            }}
          >
            ↻ Refresh
          </button>
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: '1.5rem' }}>
          <ErrorBanner
            error={error.message}
            correlationId={error.correlationId}
            onRetry={fetchWorkflows}
          />
        </div>
      )}

      {loading ? (
        <Loading label="Loading workflow tasks..." />
      ) : workflows.length === 0 ? (
        <div
          style={{
            backgroundColor: '#ffffff',
            borderRadius: '8px',
            border: '1px solid #e5e7eb',
            padding: '3rem 1.5rem',
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>✨</div>
          <h3 style={{ margin: 0, fontSize: '1.1rem', color: '#374151' }}>
            No workflows awaiting approval
          </h3>
          <p style={{ fontSize: '0.875rem', color: '#6b7280', marginTop: '0.35rem' }}>
            All candidate evaluations have been resolved or are currently running.
          </p>
          <Link
            to="/requests/new"
            style={{
              display: 'inline-block',
              marginTop: '1rem',
              padding: '8px 16px',
              backgroundColor: '#2563eb',
              color: '#ffffff',
              borderRadius: '6px',
              textDecoration: 'none',
              fontSize: '0.875rem',
              fontWeight: 500,
            }}
          >
            + Create New Request
          </Link>
        </div>
      ) : (
        <div
          style={{
            backgroundColor: '#ffffff',
            borderRadius: '8px',
            border: '1px solid #e5e7eb',
            overflow: 'hidden',
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
          }}
        >
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ backgroundColor: '#f9fafb', borderBottom: '1px solid #e5e7eb', color: '#4b5563' }}>
                  <th style={{ padding: '0.75rem 1rem' }}>Request ID</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Product / Qty</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Recommended Supplier</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Total Cost</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Score</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Status</th>
                  <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {workflows.map((req) => {
                  const isOwnRequest = user && req.requester_id === user.id;
                  const isAwaiting = req.status === 'awaiting_approval';
                  const rec = req.recommendation;

                  return (
                    <tr
                      key={req.id}
                      style={{
                        borderBottom: '1px solid #f3f4f6',
                        transition: 'background-color 0.1s',
                      }}
                    >
                      <td style={{ padding: '0.75rem 1rem', verticalAlign: 'middle' }}>
                        <Link
                          to={`/workflows/${req.thread_id}`}
                          style={{ fontWeight: 600, color: '#2563eb', textDecoration: 'none' }}
                        >
                          #{req.id.slice(0, 8)}
                        </Link>
                        <div style={{ fontSize: '0.75rem', color: '#9ca3af' }}>
                          by {req.requester_id.slice(0, 8)}
                        </div>
                      </td>

                      <td style={{ padding: '0.75rem 1rem', verticalAlign: 'middle' }}>
                        <div style={{ fontWeight: 500, color: '#111827' }}>{req.product_id}</div>
                        <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>
                          {req.quantity.toLocaleString()} units
                        </div>
                      </td>

                      <td style={{ padding: '0.75rem 1rem', verticalAlign: 'middle' }}>
                        {rec ? (
                          <div>
                            <div style={{ fontWeight: 500 }}>{rec.supplier_name}</div>
                            <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>
                              ${rec.unit_price} / unit &middot; {rec.delivery_days}d delivery
                            </div>
                          </div>
                        ) : (
                          <span style={{ color: '#9ca3af', fontStyle: 'italic' }}>None selected</span>
                        )}
                      </td>

                      <td style={{ padding: '0.75rem 1rem', verticalAlign: 'middle', fontWeight: 600 }}>
                        {rec ? `$${rec.total_cost} ${rec.currency}` : '—'}
                      </td>

                      <td style={{ padding: '0.75rem 1rem', verticalAlign: 'middle' }}>
                        {rec ? (
                          <span style={{ fontWeight: 700, color: '#1d4ed8' }}>{rec.score}/100</span>
                        ) : (
                          '—'
                        )}
                      </td>

                      <td style={{ padding: '0.75rem 1rem', verticalAlign: 'middle' }}>
                        <span
                          style={{
                            padding: '2px 8px',
                            borderRadius: '12px',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            textTransform: 'uppercase',
                            backgroundColor:
                              req.status === 'executed' || req.status === 'completed'
                                ? '#dcfce7'
                                : req.status === 'awaiting_approval'
                                ? '#fef3c7'
                                : req.status === 'rejected'
                                ? '#fee2e2'
                                : '#eff6ff',
                            color:
                              req.status === 'executed' || req.status === 'completed'
                                ? '#166534'
                                : req.status === 'awaiting_approval'
                                ? '#92400e'
                                : req.status === 'rejected'
                                ? '#991b1b'
                                : '#1e40af',
                          }}
                        >
                          {req.status.replace('_', ' ')}
                        </span>
                      </td>

                      <td style={{ padding: '0.75rem 1rem', verticalAlign: 'middle', textAlign: 'right' }}>
                        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', alignItems: 'center' }}>
                          <Link
                            to={`/workflows/${req.thread_id}`}
                            style={{
                              padding: '4px 8px',
                              backgroundColor: '#f3f4f6',
                              border: '1px solid #d1d5db',
                              borderRadius: '4px',
                              color: '#374151',
                              textDecoration: 'none',
                              fontSize: '0.75rem',
                            }}
                          >
                            Details
                          </Link>

                          {isAwaiting && (
                            <button
                              type="button"
                              onClick={() => openDecisionModal(req)}
                              disabled={isOwnRequest || !canApproveRole}
                              title={
                                isOwnRequest
                                  ? 'Self-approval prohibited (POL-002)'
                                  : !canApproveRole
                                  ? 'Approver role required'
                                  : 'Review and approve/reject'
                              }
                              style={{
                                padding: '4px 10px',
                                backgroundColor: isOwnRequest || !canApproveRole ? '#e5e7eb' : '#2563eb',
                                color: isOwnRequest || !canApproveRole ? '#9ca3af' : '#ffffff',
                                border: 'none',
                                borderRadius: '4px',
                                fontSize: '0.75rem',
                                fontWeight: 600,
                                cursor: isOwnRequest || !canApproveRole ? 'not-allowed' : 'pointer',
                              }}
                            >
                              Review &amp; Decide
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Decision Modal */}
      {selectedRequest && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 50,
            padding: '1rem',
          }}
        >
          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: '8px',
              maxWidth: '600px',
              width: '100%',
              padding: '1.75rem',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 700, color: '#111827' }}>
                Review Procurement Decision
              </h2>
              <button
                type="button"
                onClick={closeDecisionModal}
                style={{ background: 'none', border: 'none', fontSize: '1.25rem', cursor: 'pointer', color: '#6b7280' }}
              >
                &times;
              </button>
            </div>

            {actionSuccess && (
              <div
                style={{
                  padding: '0.75rem 1rem',
                  backgroundColor: '#dcfce7',
                  border: '1px solid #bbf7d0',
                  borderRadius: '6px',
                  color: '#166534',
                  fontSize: '0.85rem',
                  marginBottom: '1rem',
                }}
              >
                ✓ {actionSuccess}
              </div>
            )}

            {actionError && (
              <div style={{ marginBottom: '1rem' }}>
                <ErrorBanner
                  error={actionError.message}
                  correlationId={actionError.correlationId}
                  onDismiss={() => setActionError(null)}
                />
              </div>
            )}

            <div style={{ padding: '0.75rem', backgroundColor: '#f9fafb', borderRadius: '6px', marginBottom: '1rem', fontSize: '0.85rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                <span style={{ color: '#6b7280' }}>Request ID:</span>
                <code>{selectedRequest.id}</code>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                <span style={{ color: '#6b7280' }}>Product &amp; Quantity:</span>
                <strong>{selectedRequest.product_id} &times; {selectedRequest.quantity} units</strong>
              </div>
              {selectedRequest.recommendation && (
                <>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                    <span style={{ color: '#6b7280' }}>Recommended Supplier:</span>
                    <strong>{selectedRequest.recommendation.supplier_name}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                    <span style={{ color: '#6b7280' }}>Total Cost:</span>
                    <strong>${selectedRequest.recommendation.total_cost} {selectedRequest.recommendation.currency}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                    <span style={{ color: '#6b7280' }}>Deterministic Score:</span>
                    <span style={{ fontWeight: 700, color: '#1d4ed8' }}>
                      {selectedRequest.recommendation.score} / 100
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#6b7280' }}>Recommendation Version:</span>
                    <span>v{selectedRequest.recommendation.version}</span>
                  </div>
                </>
              )}
            </div>

            <div style={{ marginBottom: '1.25rem' }}>
              <label
                htmlFor="modal-reason"
                style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#374151', marginBottom: '0.35rem' }}
              >
                Decision Notes / Rejection Reason
              </label>
              <textarea
                id="modal-reason"
                rows={2}
                value={actionReason}
                onChange={(e) => setActionReason(e.target.value)}
                disabled={actionSubmitting}
                placeholder="Audit explanation (required for rejection, min 5 chars)..."
                style={{
                  width: '100%',
                  padding: '0.5rem 0.75rem',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  fontSize: '0.85rem',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button
                type="button"
                onClick={closeDecisionModal}
                disabled={actionSubmitting}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#ffffff',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  fontSize: '0.85rem',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => handleDecision('rejected')}
                disabled={actionSubmitting}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#fef2f2',
                  color: '#dc2626',
                  border: '1px solid #fecaca',
                  borderRadius: '6px',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: actionSubmitting ? 'not-allowed' : 'pointer',
                }}
              >
                Reject
              </button>
              <button
                type="button"
                onClick={() => handleDecision('approved')}
                disabled={actionSubmitting}
                style={{
                  padding: '0.5rem 1.25rem',
                  backgroundColor: actionSubmitting ? '#93c5fd' : '#16a34a',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: '6px',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: actionSubmitting ? 'not-allowed' : 'pointer',
                }}
              >
                {actionSubmitting ? 'Submitting...' : 'Approve & Execute (Idempotent)'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
