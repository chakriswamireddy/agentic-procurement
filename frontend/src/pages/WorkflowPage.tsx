import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../api/endpoints';
import type { PolicyEvidenceItem, ProcurementRequest, WorkflowView } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { usePolling } from '../hooks/usePolling';
import { ErrorBanner } from '../components/ErrorBanner';
import { Loading } from '../components/Loading';
import { Timeline } from '../components/Timeline';
import { ScoreBreakdown } from '../components/ScoreBreakdown';
import { EvidenceList } from '../components/EvidenceList';
import { TrustBadge } from '../components/TrustBadge';

export const WorkflowPage: React.FC = () => {
  const { threadId } = useParams<{ threadId: string }>();
  const { user } = useAuth();

  // Procurement request details
  const [requestDetails, setRequestDetails] = useState<ProcurementRequest | null>(null);
  const [evidenceItems, setEvidenceItems] = useState<PolicyEvidenceItem[]>([]);
  const [loadingEvidence, setLoadingEvidence] = useState(false);

  // Approval form state
  const [actionReason, setActionReason] = useState('');
  const [actionSubmitting, setActionSubmitting] = useState(false);
  const [actionError, setActionError] = useState<{ message: string; correlationId?: string } | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState<string>(() => crypto.randomUUID());

  // Poller for workflow status
  const {
    data: workflow,
    isLoading: pollingLoading,
    error: pollingError,
    refresh,
  } = usePolling<WorkflowView>(
    () => api.workflows.get(threadId || ''),
    {
      intervalMs: 2000,
      enabled: Boolean(threadId),
      shouldStop: (view: WorkflowView) =>
        ['awaiting_approval', 'approved', 'rejected', 'executed', 'failed', 'needs_info', 'inconclusive'].includes(
          view.status
        ),
    }
  );

  // Load procurement request details once request_id is known
  useEffect(() => {
    let active = true;
    if (workflow?.request_id) {
      api.requests
        .get(workflow.request_id)
        .then((req) => {
          if (active) setRequestDetails(req);
        })
        .catch(() => {
          // Non-blocking fallback
        });
    }
    return () => {
      active = false;
    };
  }, [workflow?.request_id]);

  // Load policy evidence citations when available
  useEffect(() => {
    let active = true;
    if (workflow?.recommendation?.supplier_name || requestDetails?.product_id) {
      setLoadingEvidence(true);
      const query = requestDetails?.product_id ? `procurement rules ${requestDetails.product_id}` : 'procurement policy';
      api.policies
        .search(query, 5)
        .then((res: any) => {
          if (active && (res.evidence || res.results)) {
            setEvidenceItems(res.evidence || res.results);
          }
        })
        .catch(() => {
          // Gracefully fallback to ID list
        })
        .finally(() => {
          if (active) setLoadingEvidence(false);
        });
    }
    return () => {
      active = false;
    };
  }, [workflow?.recommendation?.supplier_name, requestDetails?.product_id]);

  const handleDecision = async (decision: 'approved' | 'rejected') => {
    if (!workflow) return;

    if (decision === 'rejected' && (!actionReason || actionReason.trim().length < 5)) {
      setActionError({ message: 'Rejection requires a documented reason (at least 5 characters).' });
      return;
    }

    setActionSubmitting(true);
    setActionError(null);
    setActionSuccess(null);

    try {
      const recVersion = workflow.recommendation?.version ?? 1;
      const res = await api.workflows.approveOrReject(workflow.thread_id, {
        decision,
        reason: actionReason.trim() || undefined,
        recommendation_version: recVersion,
        idempotency_key: idempotencyKey,
      });

      setActionSuccess(
        decision === 'approved'
          ? `Recommendation approved successfully (v${recVersion}). Dispatched to MCP ERP execution.`
          : `Recommendation rejected. Workflow terminated.`
      );
      // Generate new idempotency key for future distinct operations
      setIdempotencyKey(crypto.randomUUID());
      refresh();
    } catch (err: any) {
      if (err.status === 409) {
        setActionError({
          message: 'Conflict: Recommendation version changed or decision was already submitted. Refreshing...',
          correlationId: err.correlationId,
        });
        refresh();
      } else if (err.status === 403) {
        setActionError({
          message: 'Access Denied: You are not authorized to approve this workflow (POL-002 self-approval prohibited).',
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

  const handleRetryExecution = async () => {
    if (!workflow) return;
    setActionSubmitting(true);
    setActionError(null);
    try {
      await api.workflows.retryExecution(workflow.thread_id);
      setActionSuccess('Execution retry dispatched to MCP service.');
      refresh();
    } catch (err: any) {
      setActionError({
        message: err.message || 'Failed to retry execution.',
        correlationId: err.correlationId,
      });
    } finally {
      setActionSubmitting(false);
    }
  };

  if (pollingLoading && !workflow) {
    return <Loading label={`Initializing graph state for thread ${threadId}...`} />;
  }

  if (pollingError && !workflow) {
    return (
      <div style={{ maxWidth: '800px', margin: '2rem auto' }}>
        <ErrorBanner
          error={pollingError.message || `Workflow ${threadId} not found or inaccessible.`}
          correlationId={pollingError.correlationId}
          onRetry={refresh}
        />
        <div style={{ marginTop: '1rem' }}>
          <Link to="/requests/new" style={{ color: '#2563eb', fontSize: '0.875rem' }}>
            &larr; Return to New Request
          </Link>
        </div>
      </div>
    );
  }

  if (!workflow) {
    return null;
  }

  const isRequester = user && requestDetails && user.id === requestDetails.requester_id;
  const canApproveRole = user && (user.role === 'approver' || user.role === 'admin');
  const isAwaiting = workflow.awaiting_approval || workflow.status === 'awaiting_approval';
  const isInconclusive = workflow.status === 'inconclusive';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Header */}
      <div
        style={{
          backgroundColor: '#ffffff',
          borderRadius: '8px',
          border: '1px solid #e5e7eb',
          padding: '1.25rem 1.5rem',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
          boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <h1 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 700, color: '#111827' }}>
              Workflow Detail
            </h1>
            <span
              style={{
                padding: '3px 10px',
                borderRadius: '12px',
                fontSize: '0.75rem',
                fontWeight: 600,
                textTransform: 'uppercase',
                backgroundColor:
                  workflow.status === 'executed' || workflow.status === 'completed'
                    ? '#dcfce7'
                    : workflow.status === 'awaiting_approval'
                    ? '#fef3c7'
                    : workflow.status === 'rejected' || workflow.status === 'failed'
                    ? '#fee2e2'
                    : '#eff6ff',
                color:
                  workflow.status === 'executed' || workflow.status === 'completed'
                    ? '#166534'
                    : workflow.status === 'awaiting_approval'
                    ? '#92400e'
                    : workflow.status === 'rejected' || workflow.status === 'failed'
                    ? '#991b1b'
                    : '#1e40af',
              }}
            >
              {workflow.status.replace('_', ' ')}
            </span>
          </div>

          <div style={{ fontSize: '0.8rem', color: '#6b7280', marginTop: '0.35rem', display: 'flex', gap: '1rem' }}>
            <span>
              <strong>Thread:</strong> <code>{workflow.thread_id}</code>
            </span>
            <span>
              <strong>Request:</strong> <code>{workflow.request_id}</code>
            </span>
            {workflow.current_node && (
              <span>
                <strong>Node:</strong> <code>{workflow.current_node}</code>
              </span>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
            <TrustBadge level="verified" />
            <TrustBadge level="computed" />
            <TrustBadge level="policy" />
          </div>
          <button
            type="button"
            onClick={refresh}
            style={{
              padding: '6px 12px',
              backgroundColor: '#f3f4f6',
              border: '1px solid #d1d5db',
              borderRadius: '6px',
              fontSize: '0.8rem',
              fontWeight: 500,
              cursor: 'pointer',
              color: '#374151',
            }}
          >
            ↻ Refresh
          </button>
        </div>
      </div>

      {actionSuccess && (
        <div
          style={{
            padding: '1rem',
            backgroundColor: '#dcfce7',
            border: '1px solid #bbf7d0',
            borderRadius: '6px',
            color: '#166534',
            fontSize: '0.875rem',
          }}
        >
          ✓ {actionSuccess}
        </div>
      )}

      {actionError && (
        <ErrorBanner
          error={actionError.message}
          correlationId={actionError.correlationId}
          onDismiss={() => setActionError(null)}
        />
      )}

      {/* Timeline Progression */}
      <Timeline
        status={workflow.status}
        currentNode={workflow.current_node}
        failureReason={workflow.failure_reason}
      />

      {/* Inconclusive or Failure callouts */}
      {isInconclusive && (
        <div
          style={{
            padding: '1rem 1.25rem',
            backgroundColor: '#fffbeb',
            border: '1px solid #fef3c7',
            borderRadius: '8px',
            color: '#92400e',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600 }}>
            <span>⚠️</span>
            <span>Workflow Inconclusive: Safety Policy Constraint Triggered</span>
          </div>
          <p style={{ margin: '0.5rem 0 0', fontSize: '0.85rem' }}>
            Candidate retrieval or policy evidence did not meet confidence thresholds. In compliance with POL-002,
            automated execution is halted to prevent non-compliant procurement actions.
          </p>
        </div>
      )}

      {workflow.status === 'failed' && (
        <div
          style={{
            padding: '1rem 1.25rem',
            backgroundColor: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: '8px',
            color: '#991b1b',
          }}
        >
          <div style={{ fontWeight: 600 }}>Execution Failed</div>
          <p style={{ margin: '0.5rem 0 0', fontSize: '0.85rem' }}>
            {workflow.failure_reason || 'An unexpected error occurred during specialist execution.'}
          </p>
          {canApproveRole && (
            <button
              type="button"
              onClick={handleRetryExecution}
              disabled={actionSubmitting}
              style={{
                marginTop: '0.75rem',
                padding: '6px 14px',
                backgroundColor: '#dc2626',
                color: '#ffffff',
                border: 'none',
                borderRadius: '6px',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: actionSubmitting ? 'not-allowed' : 'pointer',
              }}
            >
              {actionSubmitting ? 'Retrying...' : 'Retry Execution (Idempotent)'}
            </button>
          )}
        </div>
      )}

      {/* Recommendation and Score Breakdown */}
      {workflow.recommendation && (
        <div>
          <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#1f2937', marginBottom: '0.75rem' }}>
            Evaluation Recommendation
          </h2>
          <ScoreBreakdown recommendation={workflow.recommendation} />
        </div>
      )}

      {/* Validation Issues / Excluded Suppliers */}
      {workflow.issues && workflow.issues.length > 0 && (
        <div
          style={{
            backgroundColor: '#ffffff',
            borderRadius: '8px',
            border: '1px solid #e5e7eb',
            padding: '1.25rem',
          }}
        >
          <h3 style={{ margin: '0 0 0.75rem', fontSize: '1rem', color: '#374151' }}>
            Candidate Exclusions & Invariant Checks ({workflow.issues.length})
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {workflow.issues.map((iss, i) => (
              <div
                key={i}
                style={{
                  padding: '0.5rem 0.75rem',
                  backgroundColor: '#f9fafb',
                  border: '1px solid #e5e7eb',
                  borderRadius: '6px',
                  fontSize: '0.8rem',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <span style={{ fontWeight: 600, color: '#b91c1c' }}>
                    {String(iss.code || iss.reason || 'EXCLUDED')}:
                  </span>{' '}
                  <span style={{ color: '#4b5563' }}>{String(iss.message || iss.description || JSON.stringify(iss))}</span>
                </div>
                {iss.supplier_id ? (
                  <span style={{ fontSize: '0.75rem', color: '#6b7280' }}>
                    Supplier: {String(iss.supplier_id)}
                  </span>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Policy Evidence Section */}
      <div
        style={{
          backgroundColor: '#ffffff',
          borderRadius: '8px',
          border: '1px solid #e5e7eb',
          padding: '1.25rem',
        }}
      >
        {loadingEvidence ? (
          <Loading label="Resolving policy citation chunks..." />
        ) : (
          <EvidenceList
            evidenceIds={workflow.evidence_chunk_ids || []}
            evidenceItems={evidenceItems}
            inconclusive={isInconclusive}
          />
        )}
      </div>

      {/* Human-in-the-Loop Approval Decision Box */}
      {isAwaiting && (
        <div
          style={{
            backgroundColor: '#ffffff',
            borderRadius: '8px',
            border: '2px solid #3b82f6',
            padding: '1.5rem',
            boxShadow: '0 4px 6px -1px rgba(0,0,0,0.05)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <div>
              <h3 style={{ margin: 0, fontSize: '1.15rem', color: '#1e3a8a' }}>
                Human Approval Required (POL-002)
              </h3>
              <p style={{ margin: '0.25rem 0 0', fontSize: '0.85rem', color: '#4b5563' }}>
                Review deterministic scoring, vendor quote validity, and policy citations before executing ERP order.
              </p>
            </div>
            <TrustBadge level="policy" />
          </div>

          {/* Self-approval safety warning */}
          {isRequester && (
            <div
              style={{
                padding: '0.75rem 1rem',
                backgroundColor: '#fef2f2',
                border: '1px solid #fecaca',
                borderRadius: '6px',
                color: '#991b1b',
                fontSize: '0.85rem',
                marginBottom: '1rem',
              }}
            >
              <strong>POL-002 Self-Approval Prohibited:</strong> You are the author of this procurement request (
              <code>{user?.email}</code>). To prevent fraud and conflicts of interest, an independent approver or administrator must review and approve this order. Direct API approval calls will return HTTP 403.
            </div>
          )}

          {!canApproveRole && !isRequester && (
            <div
              style={{
                padding: '0.75rem 1rem',
                backgroundColor: '#fffbeb',
                border: '1px solid #fef3c7',
                borderRadius: '6px',
                color: '#92400e',
                fontSize: '0.85rem',
                marginBottom: '1rem',
              }}
            >
              Your current role (<strong>{user?.role}</strong>) does not have approval privileges. Only users with the <code>approver</code> or <code>admin</code> role may authorize purchases.
            </div>
          )}

          <div style={{ marginBottom: '1rem' }}>
            <label
              htmlFor="approval-reason"
              style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, color: '#374151', marginBottom: '0.35rem' }}
            >
              Decision Notes / Audit Reason
            </label>
            <input
              id="approval-reason"
              type="text"
              value={actionReason}
              onChange={(e) => setActionReason(e.target.value)}
              disabled={actionSubmitting || isRequester || !canApproveRole}
              placeholder="e.g. Approved within quarterly capital allocation; Qdrant policy citations verified."
              style={{
                width: '100%',
                padding: '0.5rem 0.75rem',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                fontSize: '0.875rem',
                boxSizing: 'border-box',
              }}
            />
            <span style={{ fontSize: '0.75rem', color: '#6b7280', marginTop: '0.25rem', display: 'block' }}>
              Note: Rejection requires at least 5 characters explaining the decision.
            </span>
          </div>

          <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
            <button
              type="button"
              onClick={() => handleDecision('rejected')}
              disabled={actionSubmitting || isRequester || !canApproveRole}
              style={{
                padding: '0.625rem 1.25rem',
                backgroundColor: '#fef2f2',
                color: '#dc2626',
                border: '1px solid #fecaca',
                borderRadius: '6px',
                fontSize: '0.875rem',
                fontWeight: 600,
                cursor: actionSubmitting || isRequester || !canApproveRole ? 'not-allowed' : 'pointer',
              }}
            >
              {actionSubmitting ? 'Processing...' : 'Reject Order'}
            </button>

            <button
              type="button"
              onClick={() => handleDecision('approved')}
              disabled={actionSubmitting || isRequester || !canApproveRole}
              style={{
                padding: '0.625rem 1.25rem',
                backgroundColor: actionSubmitting || isRequester || !canApproveRole ? '#93c5fd' : '#16a34a',
                color: '#ffffff',
                border: 'none',
                borderRadius: '6px',
                fontSize: '0.875rem',
                fontWeight: 600,
                cursor: actionSubmitting || isRequester || !canApproveRole ? 'not-allowed' : 'pointer',
              }}
            >
              {actionSubmitting ? 'Authorizing & Calling MCP...' : 'Approve & Execute (Idempotent)'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
