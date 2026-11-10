import React from 'react';
import { ApiError } from '../api/client';

interface ErrorBannerProps {
  error: ApiError | Error | string | null;
  onRetry?: () => void;
  onDismiss?: () => void;
  correlationId?: string;
  title?: string;
}

export const ErrorBanner: React.FC<ErrorBannerProps> = ({
  error,
  onRetry,
  onDismiss,
  correlationId: propCorrelationId,
  title,
}) => {
  if (!error) return null;

  let message = 'An unexpected error occurred.';
  let code = 'error';
  let correlationId = propCorrelationId;
  let status: number | undefined;
  let retryAfter: number | undefined;

  if (error instanceof ApiError) {
    message = error.message;
    code = error.code;
    correlationId = correlationId || error.correlationId;
    status = error.status;
    retryAfter = error.retryAfter;
  } else if (error instanceof Error) {
    message = error.message;
  } else if (typeof error === 'string') {
    message = error;
  }

  const isRateLimited = status === 429;
  const isConflict = status === 409;
  const isForbidden = status === 403;

  return (
    <div
      role="alert"
      style={{
        backgroundColor: '#fce8e6',
        border: '1px solid #fad2cf',
        borderRadius: '6px',
        padding: '1rem',
        margin: '1rem 0',
        color: '#c5221f',
        position: 'relative',
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: '0.25rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span>⚠️</span>
          <span>{title || (isRateLimited ? 'Rate Limit Exceeded' : isConflict ? 'State Conflict' : isForbidden ? 'Access Denied' : 'Error')}</span>
          {status && <span style={{ fontSize: '0.8rem', opacity: 0.8 }}>({status})</span>}
        </div>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss error"
            style={{
              background: 'none',
              border: 'none',
              fontSize: '1.1rem',
              color: '#c5221f',
              cursor: 'pointer',
              lineHeight: 1,
            }}
          >
            &times;
          </button>
        )}
      </div>

      <p style={{ margin: '0.5rem 0', fontSize: '0.9rem', color: '#374151' }}>{message}</p>

      {isRateLimited && retryAfter && (
        <p style={{ margin: '0.25rem 0', fontSize: '0.85rem', fontWeight: 500 }}>
          Please wait {retryAfter} seconds before retrying this request.
        </p>
      )}

      {isConflict && (
        <p style={{ margin: '0.25rem 0', fontSize: '0.85rem', color: '#b06000' }}>
          Tip: This recommendation or decision changed. Please refresh the page to view the latest state.
        </p>
      )}

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.75rem', fontSize: '0.8rem' }}>
        {correlationId ? (
          <span style={{ color: '#6b7280', fontFamily: 'monospace' }}>
            ID: {correlationId}
          </span>
        ) : <span />}

        {onRetry && !isRateLimited && (
          <button
            type="button"
            onClick={onRetry}
            style={{
              padding: '4px 12px',
              backgroundColor: '#ffffff',
              border: '1px solid #d1d5db',
              borderRadius: '4px',
              fontSize: '0.85rem',
              cursor: 'pointer',
              color: '#1f2937',
            }}
          >
            Retry
          </button>
        )}
      </div>
    </div>
  );
};
