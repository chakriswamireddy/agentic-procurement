import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../api/endpoints';
import type { ProcurementRequest, SupplierDetail } from '../api/types';
import { ErrorBanner } from '../components/ErrorBanner';
import { Loading } from '../components/Loading';
import { ScoreBreakdown } from '../components/ScoreBreakdown';
import { TrustBadge } from '../components/TrustBadge';

export const RequestPage: React.FC = () => {
  const { requestId } = useParams<{ requestId: string }>();

  const [request, setRequest] = useState<ProcurementRequest | null>(null);
  const [supplier, setSupplier] = useState<SupplierDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ message: string; correlationId?: string } | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      if (!requestId) return;
      try {
        setLoading(true);
        const req = await api.requests.get(requestId);
        if (active) {
          setRequest(req);
          if (req.recommendation?.supplier_id) {
            try {
              const sup = await api.suppliers.get(req.recommendation.supplier_id);
              if (active) setSupplier(sup);
            } catch {
              // Non-blocking
            }
          }
        }
      } catch (err: any) {
        if (active) {
          setError({
            message: err.message || 'Failed to load procurement request.',
            correlationId: err.correlationId,
          });
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [requestId]);

  if (loading) {
    return <Loading label={`Loading request ${requestId}...`} />;
  }

  if (error || !request) {
    return (
      <div style={{ maxWidth: '800px', margin: '2rem auto' }}>
        <ErrorBanner
          error={error?.message || `Request ${requestId} not found.`}
          correlationId={error?.correlationId}
          onRetry={() => window.location.reload()}
        />
        <div style={{ marginTop: '1rem' }}>
          <Link to="/requests/new" style={{ color: '#2563eb', fontSize: '0.875rem' }}>
            &larr; Create New Request
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '900px', margin: '0 auto' }}>
      {/* Header card */}
      <div
        style={{
          backgroundColor: '#ffffff',
          borderRadius: '8px',
          border: '1px solid #e5e7eb',
          padding: '1.5rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
          boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <h1 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 700, color: '#111827' }}>
              Request #{request.id.slice(0, 8)}
            </h1>
            <span
              style={{
                padding: '2px 8px',
                borderRadius: '12px',
                fontSize: '0.75rem',
                fontWeight: 600,
                textTransform: 'uppercase',
                backgroundColor:
                  request.status === 'executed' || request.status === 'completed'
                    ? '#dcfce7'
                    : request.status === 'awaiting_approval'
                    ? '#fef3c7'
                    : request.status === 'rejected'
                    ? '#fee2e2'
                    : '#eff6ff',
                color:
                  request.status === 'executed' || request.status === 'completed'
                    ? '#166534'
                    : request.status === 'awaiting_approval'
                    ? '#92400e'
                    : request.status === 'rejected'
                    ? '#991b1b'
                    : '#1e40af',
              }}
            >
              {request.status.replace('_', ' ')}
            </span>
          </div>

          <div style={{ fontSize: '0.8rem', color: '#6b7280', marginTop: '0.35rem' }}>
            Created: {request.created_at ? new Date(request.created_at).toLocaleString() : 'N/A'} &middot; Requester ID: {request.requester_id}
          </div>
        </div>

        <div>
          <Link
            to={`/workflows/${request.thread_id}`}
            style={{
              padding: '8px 16px',
              backgroundColor: '#2563eb',
              color: '#ffffff',
              textDecoration: 'none',
              borderRadius: '6px',
              fontSize: '0.875rem',
              fontWeight: 600,
            }}
          >
            View Live Workflow &rarr;
          </Link>
        </div>
      </div>

      {/* Request parameters */}
      <div
        style={{
          backgroundColor: '#ffffff',
          borderRadius: '8px',
          border: '1px solid #e5e7eb',
          padding: '1.25rem',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 600, color: '#1f2937' }}>
            Request Specifications
          </h2>
          <TrustBadge level="verified" />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem' }}>
          <div>
            <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>Product ID</div>
            <div style={{ fontSize: '0.9rem', fontWeight: 600 }}>{request.product_id}</div>
          </div>
          <div>
            <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>Requested Quantity</div>
            <div style={{ fontSize: '0.9rem', fontWeight: 600 }}>{request.quantity.toLocaleString()} units</div>
          </div>
          <div>
            <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>Max Delivery Days</div>
            <div style={{ fontSize: '0.9rem', fontWeight: 600 }}>
              {(request.constraints as any)?.max_delivery_days ?? 'None'}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>Max Unit Price</div>
            <div style={{ fontSize: '0.9rem', fontWeight: 600 }}>
              {(request.constraints as any)?.max_unit_price ? `$${(request.constraints as any).max_unit_price}` : 'None'}
            </div>
          </div>
        </div>
      </div>

      {/* Recommendation and Score Breakdown */}
      {request.recommendation ? (
        <div>
          <h2 style={{ fontSize: '1rem', fontWeight: 600, color: '#1f2937', marginBottom: '0.75rem' }}>
            Selected Recommendation
          </h2>
          <ScoreBreakdown recommendation={request.recommendation} />

          {supplier && (
            <div
              style={{
                marginTop: '1rem',
                backgroundColor: '#ffffff',
                borderRadius: '8px',
                border: '1px solid #e5e7eb',
                padding: '1.25rem',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                <h3 style={{ margin: 0, fontSize: '0.95rem', color: '#1f2937' }}>
                  Supplier Profile Details
                </h3>
                <span style={{ fontSize: '0.75rem', color: '#6b7280' }}>
                  PostgreSQL Core + MongoDB Profile
                </span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem', fontSize: '0.85rem' }}>
                <div>
                  <div style={{ color: '#6b7280', fontSize: '0.75rem' }}>Location</div>
                  <div style={{ fontWeight: 500 }}>{supplier.location}</div>
                </div>
                <div>
                  <div style={{ color: '#6b7280', fontSize: '0.75rem' }}>Status</div>
                  <div style={{ fontWeight: 500, textTransform: 'capitalize' }}>{supplier.status}</div>
                </div>
                <div>
                  <div style={{ color: '#6b7280', fontSize: '0.75rem' }}>Certifications</div>
                  <div style={{ fontWeight: 500 }}>
                    {supplier.profile?.certifications?.join(', ') || 'None listed'}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div
          style={{
            padding: '2rem',
            textAlign: 'center',
            backgroundColor: '#ffffff',
            borderRadius: '8px',
            border: '1px solid #e5e7eb',
            color: '#6b7280',
          }}
        >
          No recommendation available yet. Workflow may still be evaluating or failed.
        </div>
      )}
    </div>
  );
};
