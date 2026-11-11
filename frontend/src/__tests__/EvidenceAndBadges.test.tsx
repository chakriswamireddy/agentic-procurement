import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TrustBadge } from '../components/TrustBadge';
import { EvidenceList } from '../components/EvidenceList';
import type { PolicyEvidenceItem } from '../api/types';

describe('TrustBadge Component', () => {
  it('renders verified record badge', () => {
    render(<TrustBadge level="verified" />);
    expect(screen.getByText('Verified Record')).toBeInTheDocument();
  });

  it('renders computed badge', () => {
    render(<TrustBadge level="computed" />);
    expect(screen.getByText('Computed')).toBeInTheDocument();
  });

  it('renders policy rule evidence badge', () => {
    render(<TrustBadge level="policy" />);
    expect(screen.getByText('Policy Evidence')).toBeInTheDocument();
  });

  it('renders ai generated summary badge', () => {
    render(<TrustBadge level="ai" />);
    expect(screen.getByText('AI-Generated Summary')).toBeInTheDocument();
  });
});

describe('EvidenceList Component', () => {
  it('renders conclusive policy evidence safely as text (no XSS injection)', () => {
    const maliciousEvidence: PolicyEvidenceItem = {
      chunk_id: 'chk-safe-1',
      document_id: 'POL-002',
      version: '1.2.0',
      section: '3.4',
      text: '<script>alert("xss")</script> Purchases exceeding $10,000 require independent approval.',
      effective_from: '2024-01-01',
      classification: 'internal',
      dense_score: 0.912,
    };

    const { container } = render(
      <EvidenceList evidenceIds={['chk-safe-1']} evidenceItems={[maliciousEvidence]} />
    );

    // Should find the text content literally, not execute as script element
    expect(screen.getByText(/Purchases exceeding \$10,000/)).toBeInTheDocument();
    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByText('POL-002')).toBeInTheDocument();
    expect(screen.getByText(/Section: 3.4/)).toBeInTheDocument();
  });

  it('renders safety warning banner when evidence is inconclusive', () => {
    render(<EvidenceList evidenceIds={[]} inconclusive={true} />);
    expect(screen.getByText(/Policy Research Inconclusive/i)).toBeInTheDocument();
    expect(screen.getByText(/cannot proceed to approval without authoritative evidence backing/i)).toBeInTheDocument();
  });

  it('renders empty message when no evidence IDs are provided', () => {
    render(<EvidenceList evidenceIds={[]} inconclusive={false} />);
    expect(screen.getByText(/No policy evidence citations attached to this workflow/i)).toBeInTheDocument();
  });
});
