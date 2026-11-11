import React, { useState } from 'react';

interface TimelineProps {
  status: string;
  currentNode?: string | null;
  failureReason?: string | null;
}

interface StepInfo {
  id: string;
  label: string;
  description: string;
  traceDetails: string;
}

const STEPS: StepInfo[] = [
  {
    id: 'request_created',
    label: 'Request Created',
    description: 'Validated input & budget constraints',
    traceDetails: 'Pydantic v2 schema validation passed. Authenticated requester JWT identity. Initialized thread in PostgreSQL LangGraph checkpointer.',
  },
  {
    id: 'research',
    label: 'Specialist Research',
    description: 'Parallel supplier catalog & Qdrant policy retrieval',
    traceDetails: 'Parallel dispatch: SupplierSpecialist executed SQL join on PostgreSQL (active quotations + inventory) and enriched MongoDB compliance profiles ($in). PolicySpecialist queried Qdrant vector index via hybrid dense (bge-small-en-v1.5) and sparse (BM25) search.',
  },
  {
    id: 'comparison',
    label: 'Deterministic Scoring',
    description: 'Rules-based candidate scoring & ranking',
    traceDetails: 'Executed SCORING_VERSION 1.0 formula: (0.55 × Price) + (0.30 × Delivery) + (0.15 × Risk). Evaluated candidate exclusions (capacity, delivery days, missing certifications) with Decimal precision.',
  },
  {
    id: 'validation',
    label: 'Recommendation Validation',
    description: 'Invariant & compliance policy checks',
    traceDetails: 'Checked POL-002 approval thresholds and corporate compliance invariants. Attached verified policy evidence citations from Qdrant vector store.',
  },
  {
    id: 'awaiting_approval',
    label: 'Approval Gate',
    description: 'Human-in-the-loop governance (POL-002)',
    traceDetails: 'Workflow graph interrupted before execution node. State serialized to PostgreSQL checkpoint. Requester self-approval prohibited; awaiting authorized non-self approver.',
  },
  {
    id: 'execution',
    label: 'MCP Execution',
    description: 'Idempotent ERP purchase order creation',
    traceDetails: 'Sandboxed Model Context Protocol (MCP) gateway called. Validated recommendation version and idempotency key. Generated ERP Purchase Order.',
  },
  {
    id: 'completed',
    label: 'Result Recorded',
    description: 'Audit trail persisted & workflow finalized',
    traceDetails: 'ERP purchase order reference logged to audit_events. Telemetry finalized and workflow terminated.',
  },
];

export const Timeline: React.FC<TimelineProps> = ({ status, currentNode, failureReason }) => {
  const [expandedStep, setExpandedStep] = useState<string | null>(null);

  const getStepState = (stepIndex: number): 'done' | 'current' | 'pending' | 'failed' => {
    if (status === 'failed' || status === 'inconclusive') {
      if (stepIndex === 1 && (currentNode === 'supplier_research' || currentNode === 'policy_retrieval')) return 'failed';
      if (stepIndex === 2 && currentNode === 'comparison') return 'failed';
      if (stepIndex === 3 && currentNode === 'validation') return 'failed';
    }

    if (status === 'rejected' && stepIndex === 4) {
      return 'failed';
    }

    const statusMap: Record<string, number> = {
      received: 0,
      researching: 1,
      supplier_research: 1,
      policy_retrieval: 1,
      comparison: 2,
      validation: 3,
      awaiting_approval: 4,
      resuming: 5,
      execute_tool: 5,
      executed: 6,
      completed: 6,
    };

    const currentLevel = statusMap[status] ?? (currentNode ? (statusMap[currentNode] ?? 0) : 0);

    if (stepIndex < currentLevel) return 'done';
    if (stepIndex === currentLevel) return 'current';
    return 'pending';
  };

  return (
    <div style={{ margin: '1.5rem 0' }}>
      <h4 style={{ margin: '0 0 1rem 0', fontSize: '1rem', color: '#1f2937' }}>
        Workflow Execution Timeline
      </h4>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
        {STEPS.map((step, idx) => {
          const state = getStepState(idx);
          const isLast = idx === STEPS.length - 1;

          let badgeColor = '#9ca3af';
          let badgeBg = '#f3f4f6';
          let textColor = '#6b7280';

          if (state === 'done') {
            badgeColor = '#059669';
            badgeBg = '#d1fae5';
            textColor = '#111827';
          } else if (state === 'current') {
            badgeColor = '#2563eb';
            badgeBg = '#dbeafe';
            textColor = '#1e40af';
          } else if (state === 'failed') {
            badgeColor = '#dc2626';
            badgeBg = '#fee2e2';
            textColor = '#991b1b';
          }

          return (
            <div key={step.id} style={{ display: 'flex', gap: '1rem' }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                <div
                  style={{
                    width: '24px',
                    height: '24px',
                    borderRadius: '50%',
                    backgroundColor: badgeBg,
                    border: `2px solid ${badgeColor}`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    color: badgeColor,
                    zIndex: 1,
                  }}
                >
                  {state === 'done' ? '✓' : state === 'failed' ? '✕' : idx + 1}
                </div>
                {!isLast && (
                  <div
                    style={{
                      width: '2px',
                      flex: 1,
                      minHeight: '24px',
                      backgroundColor: state === 'done' ? '#10b981' : '#e5e7eb',
                      margin: '2px 0',
                    }}
                  />
                )}
              </div>

              <div style={{ paddingBottom: isLast ? '0' : '1.25rem', flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontWeight: state === 'current' ? 700 : 600, color: textColor, fontSize: '0.9rem' }}>
                      {step.label}
                    </span>
                    {state === 'current' && (
                      <span
                        style={{
                          fontSize: '0.7rem',
                          padding: '1px 6px',
                          backgroundColor: '#dbeafe',
                          color: '#1d4ed8',
                          borderRadius: '10px',
                          fontWeight: 600,
                        }}
                      >
                        Active
                      </span>
                    )}
                    {state === 'failed' && (
                      <span
                        style={{
                          fontSize: '0.7rem',
                          padding: '1px 6px',
                          backgroundColor: '#fee2e2',
                          color: '#b91c1c',
                          borderRadius: '10px',
                          fontWeight: 600,
                        }}
                      >
                        {status === 'rejected' ? 'Rejected' : 'Halted'}
                      </span>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => setExpandedStep(expandedStep === step.id ? null : step.id)}
                    style={{
                      background: '#ffffff',
                      border: '1px solid #d1d5db',
                      borderRadius: '4px',
                      padding: '2px 8px',
                      fontSize: '0.72rem',
                      color: '#4b5563',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
                    }}
                  >
                    <span>{expandedStep === step.id ? 'Hide Trace ▲' : 'View Trace ▼'}</span>
                  </button>
                </div>
                <div style={{ fontSize: '0.8rem', color: '#6b7280', marginTop: '2px' }}>
                  {step.description}
                </div>
                {expandedStep === step.id && (
                  <div
                    style={{
                      marginTop: '0.5rem',
                      padding: '0.65rem 0.85rem',
                      backgroundColor: '#f8fafc',
                      border: '1px solid #cbd5e1',
                      borderRadius: '6px',
                      fontSize: '0.78rem',
                      color: '#334155',
                      lineHeight: 1.45,
                    }}
                  >
                    <div style={{ fontWeight: 600, color: '#0f172a', marginBottom: '3px' }}>
                      🔍 Agent Execution Trace Details:
                    </div>
                    {step.traceDetails}
                  </div>
                )}
                {state === 'failed' && failureReason && (
                  <div style={{ fontSize: '0.8rem', color: '#dc2626', marginTop: '4px', fontStyle: 'italic' }}>
                    Reason: {failureReason}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
