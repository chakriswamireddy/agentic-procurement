import React from 'react';
import type { RecommendationSummary } from '../api/types';
import { TrustBadge } from './TrustBadge';

interface ScoreBreakdownProps {
  recommendation: RecommendationSummary;
}

export const ScoreBreakdown: React.FC<ScoreBreakdownProps> = ({ recommendation }) => {
  return (
    <div
      style={{
        border: '1px solid #e5e7eb',
        borderRadius: '8px',
        padding: '1.25rem',
        backgroundColor: '#ffffff',
        boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
        <div>
          <h3 style={{ margin: 0, fontSize: '1.15rem', color: '#111827' }}>
            Recommended: {recommendation.supplier_name}
          </h3>
          <span style={{ fontSize: '0.8rem', color: '#6b7280' }}>
            ID: {recommendation.supplier_id} &middot; Scoring Version: {recommendation.scoring_version}
          </span>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <TrustBadge level="computed" />
          <TrustBadge level="verified" />
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
          gap: '12px',
          padding: '0.75rem',
          backgroundColor: '#f9fafb',
          borderRadius: '6px',
          marginBottom: '1rem',
        }}
      >
        <div>
          <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>Deterministic Score</div>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#1e40af' }}>
            {recommendation.score} / 100
          </div>
        </div>

        <div>
          <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>Estimated Total Cost</div>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#111827' }}>
            {recommendation.currency} {parseFloat(recommendation.total_cost).toLocaleString()}
          </div>
        </div>

        <div>
          <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>Unit Price</div>
          <div style={{ fontSize: '1rem', fontWeight: 600, color: '#374151', marginTop: '3px' }}>
            {recommendation.currency} {parseFloat(recommendation.unit_price).toLocaleString()}
          </div>
        </div>

        <div>
          <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>Delivery Lead Time</div>
          <div style={{ fontSize: '1rem', fontWeight: 600, color: '#374151', marginTop: '3px' }}>
            {recommendation.delivery_days} days
          </div>
        </div>
      </div>

      {recommendation.caveats && recommendation.caveats.length > 0 && (
        <div style={{ marginTop: '0.75rem' }}>
          <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#4b5563', marginBottom: '4px' }}>
            Eligibility Notes & Caveats:
          </div>
          <ul style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '0.85rem', color: '#4b5563' }}>
            {recommendation.caveats.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}

      <div style={{ marginTop: '1rem', paddingTop: '0.75rem', borderTop: '1px solid #f3f4f6', fontSize: '0.75rem', color: '#9ca3af' }}>
        Weights: Price 55% &middot; Delivery 30% &middot; Compliance Risk 15%. Total score is computed with Decimal precision and deterministic tie-breaking.
      </div>
    </div>
  );
};
