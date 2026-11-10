import React from 'react';

export type TrustLevel = 'verified' | 'computed' | 'policy' | 'ai';

interface TrustBadgeProps {
  level: TrustLevel;
  text?: string;
  className?: string;
}

const BADGE_CONFIG: Record<TrustLevel, { label: string; tooltip: string; bg: string; color: string; border: string }> = {
  verified: {
    label: 'Verified Record',
    tooltip: 'Authoritative data from PostgreSQL business records or MongoDB profile store',
    bg: '#e6f4ea',
    color: '#137333',
    border: '#ceead6',
  },
  computed: {
    label: 'Computed',
    tooltip: 'Deterministic calculation via versioned scoring weights (SCORING_VERSION 1.0)',
    bg: '#e8f0fe',
    color: '#1a73e8',
    border: '#d2e3fc',
  },
  policy: {
    label: 'Policy Evidence',
    tooltip: 'Retrieved text chunk from active indexed Qdrant policy corpus',
    bg: '#fef7e0',
    color: '#b06000',
    border: '#feefc3',
  },
  ai: {
    label: 'AI-Generated Summary',
    tooltip: 'Grounded natural language explanation. Does not alter decisions or scores.',
    bg: '#f3e8fd',
    color: '#7627bb',
    border: '#e9d2fd',
  },
};

export const TrustBadge: React.FC<TrustBadgeProps> = ({ level, text, className }) => {
  const config = BADGE_CONFIG[level];

  return (
    <span
      className={className}
      title={config.tooltip}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        padding: '2px 8px',
        borderRadius: '12px',
        fontSize: '0.75rem',
        fontWeight: 600,
        backgroundColor: config.bg,
        color: config.color,
        border: `1px solid ${config.border}`,
        cursor: 'help',
        userSelect: 'none',
      }}
    >
      <span style={{ fontSize: '0.65rem' }}>●</span>
      {text || config.label}
    </span>
  );
};
