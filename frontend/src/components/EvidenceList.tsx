import React from 'react';
import type { PolicyEvidenceItem } from '../api/types';
import { TrustBadge } from './TrustBadge';

interface EvidenceListProps {
  evidenceIds: string[];
  evidenceItems?: PolicyEvidenceItem[];
  inconclusive?: boolean;
}

export const EvidenceList: React.FC<EvidenceListProps> = ({
  evidenceIds,
  evidenceItems = [],
  inconclusive = false,
}) => {
  if (inconclusive) {
    return (
      <div
        style={{
          padding: '1rem',
          backgroundColor: '#fffbeb',
          border: '1px solid #fef3c7',
          borderRadius: '6px',
          color: '#92400e',
          fontSize: '0.9rem',
        }}
      >
        <strong>⚠️ Policy Research Inconclusive:</strong> Insufficient or weak policy evidence
        survived threshold filtering. In accordance with safety policies, automated recommendation
        cannot proceed to approval without authoritative evidence backing.
      </div>
    );
  }

  if (evidenceIds.length === 0 && evidenceItems.length === 0) {
    return (
      <p style={{ color: '#6b7280', fontSize: '0.9rem', fontStyle: 'italic' }}>
        No policy evidence citations attached to this workflow.
      </p>
    );
  }

  return (
    <div style={{ marginTop: '1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
        <h4 style={{ margin: 0, fontSize: '1rem', color: '#1f2937' }}>
          Policy Evidence Citations ({evidenceItems.length || evidenceIds.length})
        </h4>
        <TrustBadge level="policy" />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {evidenceItems.length > 0 ? (
          evidenceItems.map((item) => (
            <div
              key={item.chunk_id}
              style={{
                border: '1px solid #e5e7eb',
                borderRadius: '6px',
                padding: '0.85rem',
                backgroundColor: '#f9fafb',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: '0.5rem',
                  fontSize: '0.8rem',
                  color: '#4b5563',
                }}
              >
                <span>
                  <strong>{item.document_id}</strong> (v{item.version}) &middot; Section: {(item as any).section_path || item.section}
                </span>
                <span style={{ fontFamily: 'monospace' }}>
                  Effective: {item.effective_from}
                </span>
              </div>

              <blockquote
                style={{
                  margin: 0,
                  padding: '0.5rem 0.75rem',
                  backgroundColor: '#ffffff',
                  borderLeft: '3px solid #d97706',
                  fontStyle: 'normal',
                  fontSize: '0.875rem',
                  color: '#1f2937',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {item.text}
              </blockquote>

              <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: '#6b7280', display: 'flex', gap: '12px' }}>
                <span>Chunk ID: <code>{item.chunk_id.slice(0, 8)}...</code></span>
                {((item as any).score ?? item.combined_score) !== undefined && ((item as any).score ?? item.combined_score) !== null && (
                  <span>Hybrid RRF Score: {Number((item as any).score ?? item.combined_score).toFixed(4)}</span>
                )}
                <span>Classification: {item.classification}</span>
              </div>
            </div>
          ))
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {evidenceIds.map((id) => (
              <span
                key={id}
                style={{
                  padding: '3px 8px',
                  backgroundColor: '#f3f4f6',
                  border: '1px solid #d1d5db',
                  borderRadius: '4px',
                  fontSize: '0.8rem',
                  fontFamily: 'monospace',
                }}
              >
                {id}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
