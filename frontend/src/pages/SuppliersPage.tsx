import React, { useEffect, useState } from 'react';
import { api } from '../api/endpoints';
import type { Supplier, SupplierDetail } from '../api/types';
import { ErrorBanner } from '../components/ErrorBanner';
import { Loading } from '../components/Loading';
import { TrustBadge } from '../components/TrustBadge';

export const SuppliersPage: React.FC = () => {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ message: string; correlationId?: string } | null>(null);

  // Filters
  const [category, setCategory] = useState('');
  const [status, setStatus] = useState('');
  const [query, setQuery] = useState('');

  // Selected supplier for detail drawer/modal
  const [selectedSupplier, setSelectedSupplier] = useState<SupplierDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const fetchSuppliers = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.suppliers.list({
        category: category || undefined,
        status: status || undefined,
        q: query.trim() || undefined,
        limit: 50,
      });
      setSuppliers(res.items);
      setTotal(res.total);
    } catch (err: any) {
      setError({
        message: err.message || 'Failed to load suppliers from PostgreSQL database.',
        correlationId: err.correlationId,
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSuppliers();
  }, [category, status]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchSuppliers();
  };

  const openSupplierDetail = async (id: string) => {
    setLoadingDetail(true);
    setDetailError(null);
    setSelectedSupplier(null);
    try {
      const detail = await api.suppliers.get(id);
      setSelectedSupplier(detail);
    } catch (err: any) {
      setDetailError(err.message || 'Failed to load supplier profile from MongoDB.');
    } finally {
      setLoadingDetail(false);
    }
  };

  const isQuoteExpired = (validUntil?: string | null): boolean => {
    if (!validUntil) return false;
    return new Date(validUntil).getTime() < Date.now();
  };

  return (
    <div>
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#111827', margin: 0 }}>
          Suppliers &amp; Quotations Explorer
        </h1>
        <p style={{ fontSize: '0.875rem', color: '#6b7280', marginTop: '0.25rem' }}>
          Inspect relational vendor core records (PostgreSQL) joined with unstructured compliance profiles (MongoDB).
        </p>
      </div>

      {error && (
        <div style={{ marginBottom: '1.5rem' }}>
          <ErrorBanner
            error={error.message}
            correlationId={error.correlationId}
            onRetry={fetchSuppliers}
          />
        </div>
      )}

      {/* Filter toolbar */}
      <div
        style={{
          backgroundColor: '#ffffff',
          borderRadius: '8px',
          border: '1px solid #e5e7eb',
          padding: '1rem',
          marginBottom: '1.5rem',
          display: 'flex',
          flexWrap: 'wrap',
          gap: '1rem',
          alignItems: 'center',
          boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
        }}
      >
        <form onSubmit={handleSearchSubmit} style={{ display: 'flex', gap: '0.5rem', flex: 1, minWidth: '240px' }}>
          <input
            type="text"
            placeholder="Search suppliers by name or ID..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{
              flex: 1,
              padding: '0.45rem 0.75rem',
              border: '1px solid #d1d5db',
              borderRadius: '6px',
              fontSize: '0.85rem',
            }}
          />
          <button
            type="submit"
            style={{
              padding: '0.45rem 0.9rem',
              backgroundColor: '#2563eb',
              color: '#ffffff',
              border: 'none',
              borderRadius: '6px',
              fontSize: '0.85rem',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            Search
          </button>
        </form>

        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <div>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              style={{
                padding: '0.45rem 0.75rem',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                fontSize: '0.85rem',
                backgroundColor: '#ffffff',
              }}
            >
              <option value="">All Categories</option>
              <option value="hardware">Hardware</option>
              <option value="electronics">Electronics</option>
              <option value="accessories">Accessories</option>
              <option value="networking">Networking</option>
            </select>
          </div>

          <div>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              style={{
                padding: '0.45rem 0.75rem',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                fontSize: '0.85rem',
                backgroundColor: '#ffffff',
              }}
            >
              <option value="">All Statuses</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="suspended">Suspended</option>
            </select>
          </div>
        </div>
      </div>

      {/* Supplier Table */}
      {loading ? (
        <Loading label="Querying PostgreSQL supplier directory..." />
      ) : suppliers.length === 0 ? (
        <div
          style={{
            backgroundColor: '#ffffff',
            borderRadius: '8px',
            border: '1px solid #e5e7eb',
            padding: '2.5rem',
            textAlign: 'center',
            color: '#6b7280',
          }}
        >
          No suppliers matched the current filters.
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
          <div
            style={{
              padding: '0.75rem 1rem',
              backgroundColor: '#f9fafb',
              borderBottom: '1px solid #e5e7eb',
              fontSize: '0.75rem',
              color: '#6b7280',
              display: 'flex',
              justifyContent: 'space-between',
            }}
          >
            <span>Showing {suppliers.length} of {total} suppliers</span>
            <span>Source: <code>PostgreSQL / suppliers</code></span>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ backgroundColor: '#f9fafb', borderBottom: '1px solid #e5e7eb', color: '#4b5563' }}>
                  <th style={{ padding: '0.75rem 1rem' }}>Supplier Name</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Category</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Location</th>
                  <th style={{ padding: '0.75rem 1rem' }}>Status</th>
                  <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {suppliers.map((s) => (
                  <tr
                    key={s.id}
                    style={{
                      borderBottom: '1px solid #f3f4f6',
                      transition: 'background-color 0.1s',
                    }}
                  >
                    <td style={{ padding: '0.75rem 1rem', verticalAlign: 'middle' }}>
                      <div style={{ fontWeight: 600, color: '#111827' }}>{s.name}</div>
                      <div style={{ fontSize: '0.75rem', color: '#9ca3af' }}>ID: {s.id}</div>
                    </td>

                    <td style={{ padding: '0.75rem 1rem', verticalAlign: 'middle', textTransform: 'capitalize' }}>
                      {s.category}
                    </td>

                    <td style={{ padding: '0.75rem 1rem', verticalAlign: 'middle' }}>
                      {s.location}
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
                            s.status === 'active'
                              ? '#dcfce7'
                              : s.status === 'suspended'
                              ? '#fee2e2'
                              : '#f3f4f6',
                          color:
                            s.status === 'active'
                              ? '#166534'
                              : s.status === 'suspended'
                              ? '#991b1b'
                              : '#4b5563',
                        }}
                      >
                        {s.status}
                      </span>
                    </td>

                    <td style={{ padding: '0.75rem 1rem', verticalAlign: 'middle', textAlign: 'right' }}>
                      <button
                        type="button"
                        onClick={() => openSupplierDetail(s.id)}
                        style={{
                          padding: '4px 10px',
                          backgroundColor: '#eff6ff',
                          color: '#1d4ed8',
                          border: '1px solid #bfdbfe',
                          borderRadius: '4px',
                          fontSize: '0.75rem',
                          fontWeight: 500,
                          cursor: 'pointer',
                        }}
                      >
                        Explore Profile &rarr;
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Supplier Detail Modal / Drawer */}
      {(selectedSupplier || loadingDetail || detailError) && (
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
              maxWidth: '700px',
              width: '100%',
              maxHeight: '90vh',
              overflowY: 'auto',
              padding: '1.75rem',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div>
                <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 700, color: '#111827' }}>
                  {selectedSupplier?.name || 'Loading Supplier...'}
                </h2>
                <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>
                  Data Ownership: Core in <strong>PostgreSQL</strong>, Compliance in <strong>MongoDB</strong>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setSelectedSupplier(null);
                  setDetailError(null);
                }}
                style={{ background: 'none', border: 'none', fontSize: '1.25rem', cursor: 'pointer', color: '#6b7280' }}
              >
                &times;
              </button>
            </div>

            {loadingDetail && <Loading label="Querying MongoDB supplier profile..." />}

            {detailError && <ErrorBanner error={detailError} onDismiss={() => setDetailError(null)} />}

            {selectedSupplier && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                {/* Core Relational info */}
                <div style={{ padding: '0.75rem', backgroundColor: '#f9fafb', borderRadius: '6px', fontSize: '0.85rem' }}>
                  <div style={{ fontWeight: 600, color: '#374151', marginBottom: '0.5rem', display: 'flex', justifyContent: 'space-between' }}>
                    <span>PostgreSQL Core Record</span>
                    <TrustBadge level="verified" />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem' }}>
                    <div>
                      <span style={{ color: '#6b7280', fontSize: '0.75rem' }}>Supplier ID</span>
                      <div style={{ fontWeight: 500 }}>{selectedSupplier.id}</div>
                    </div>
                    <div>
                      <span style={{ color: '#6b7280', fontSize: '0.75rem' }}>Category</span>
                      <div style={{ fontWeight: 500, textTransform: 'capitalize' }}>{selectedSupplier.category}</div>
                    </div>
                    <div>
                      <span style={{ color: '#6b7280', fontSize: '0.75rem' }}>Location</span>
                      <div style={{ fontWeight: 500 }}>{selectedSupplier.location}</div>
                    </div>
                    <div>
                      <span style={{ color: '#6b7280', fontSize: '0.75rem' }}>Status</span>
                      <div style={{ fontWeight: 600, textTransform: 'uppercase', color: selectedSupplier.status === 'active' ? '#166534' : '#991b1b' }}>
                        {selectedSupplier.status}
                      </div>
                    </div>
                  </div>
                </div>

                {/* MongoDB Document Profile */}
                <div style={{ padding: '0.75rem', backgroundColor: '#f0fdf4', borderRadius: '6px', border: '1px solid #bbf7d0', fontSize: '0.85rem' }}>
                  <div style={{ fontWeight: 600, color: '#166534', marginBottom: '0.5rem', display: 'flex', justifyContent: 'space-between' }}>
                    <span>MongoDB Compliance &amp; Profile Document</span>
                    <span style={{ fontSize: '0.75rem', color: '#15803d' }}>collection: <code>supplier_profiles</code></span>
                  </div>

                  <div style={{ marginBottom: '0.75rem' }}>
                    <span style={{ color: '#4b5563', fontSize: '0.75rem', fontWeight: 600 }}>Active Certifications:</span>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginTop: '0.25rem' }}>
                      {selectedSupplier.profile?.certifications && selectedSupplier.profile.certifications.length > 0 ? (
                        selectedSupplier.profile.certifications.map((c) => (
                          <span
                            key={c}
                            style={{
                              padding: '2px 8px',
                              backgroundColor: '#dcfce7',
                              color: '#166534',
                              borderRadius: '12px',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                            }}
                          >
                            ✓ {c}
                          </span>
                        ))
                      ) : (
                        <span style={{ color: '#dc2626', fontSize: '0.75rem', fontStyle: 'italic' }}>
                          ⚠️ No certifications recorded in MongoDB
                        </span>
                      )}
                    </div>
                  </div>

                  {selectedSupplier.profile?.compliance && (
                    <div style={{ fontSize: '0.75rem', color: '#374151', marginTop: '0.5rem' }}>
                      <span style={{ fontWeight: 600 }}>Compliance Status:</span>
                      <pre style={{ margin: '0.25rem 0 0', backgroundColor: '#ffffff', padding: '0.5rem', borderRadius: '4px', overflowX: 'auto' }}>
                        {JSON.stringify(selectedSupplier.profile.compliance, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>

                {/* PostgreSQL Quotations */}
                <div>
                  <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.9rem', color: '#1f2937' }}>
                    Catalog Quotations ({selectedSupplier.quotations?.length || 0})
                  </h4>

                  {!selectedSupplier.quotations || selectedSupplier.quotations.length === 0 ? (
                    <p style={{ color: '#6b7280', fontSize: '0.8rem', fontStyle: 'italic' }}>
                      No quotations on file for this supplier.
                    </p>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                      {selectedSupplier.quotations.map((q) => {
                        const expired = isQuoteExpired(q.valid_until);
                        return (
                          <div
                            key={q.id}
                            style={{
                              padding: '0.65rem 0.85rem',
                              border: `1px solid ${expired ? '#fecaca' : '#e5e7eb'}`,
                              borderRadius: '6px',
                              backgroundColor: expired ? '#fff5f5' : '#ffffff',
                              fontSize: '0.8rem',
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                            }}
                          >
                            <div>
                              <div style={{ fontWeight: 600 }}>Product: {q.product_id}</div>
                              <div style={{ color: '#6b7280', fontSize: '0.75rem' }}>
                                Unit: ${q.unit_price} {q.currency} &middot; Delivery: {q.delivery_days} days &middot; Available: {q.available_quantity} units
                              </div>
                            </div>

                            <div style={{ textAlign: 'right' }}>
                              {expired ? (
                                <span style={{ padding: '2px 6px', backgroundColor: '#fee2e2', color: '#991b1b', borderRadius: '4px', fontSize: '0.7rem', fontWeight: 600 }}>
                                  EXPIRED QUOTE
                                </span>
                              ) : (
                                <span style={{ color: '#166534', fontSize: '0.75rem' }}>
                                  Valid until {q.valid_until ? new Date(q.valid_until).toLocaleDateString() : 'N/A'}
                                </span>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
