import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/endpoints';
import type { Product } from '../api/types';
import { ErrorBanner } from '../components/ErrorBanner';
import { Loading } from '../components/Loading';

const KNOWN_CERTIFICATIONS = ['ISO-9001', 'ISO-14001', 'SOC-2', 'RoHS', 'CE'];

export const NewRequestPage: React.FC = () => {
  const navigate = useNavigate();

  const [products, setProducts] = useState<Product[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Form fields
  const [productId, setProductId] = useState('');
  const [quantity, setQuantity] = useState<number | ''>(500);
  const [maxDeliveryDays, setMaxDeliveryDays] = useState<number | ''>(14);
  const [maxUnitPrice, setMaxUnitPrice] = useState<string>('');
  const [certifications, setCertifications] = useState<string[]>(['ISO-9001']);
  const [notes, setNotes] = useState('');

  // State
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<{ message: string; correlationId?: string } | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        setLoadingProducts(true);
        const data = await api.products.list();
        if (active) {
          setProducts(data);
          if (data.length > 0 && !productId) {
            setProductId(data[0].id);
          }
        }
      } catch (err: any) {
        if (active) {
          setLoadError(err.message || 'Failed to load products list from backend.');
        }
      } finally {
        if (active) setLoadingProducts(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, []);

  const selectedProduct = products.find((p) => p.id === productId);

  const toggleCert = (cert: string) => {
    setCertifications((prev) =>
      prev.includes(cert) ? prev.filter((c) => c !== cert) : [...prev, cert]
    );
  };

  const validate = (): boolean => {
    const errors: Record<string, string> = {};
    if (!productId) {
      errors.productId = 'Please select a product.';
    }
    if (quantity === '' || quantity <= 0) {
      errors.quantity = 'Quantity must be greater than 0.';
    } else if (quantity > 100000) {
      errors.quantity = 'Quantity cannot exceed 100,000 units.';
    }

    if (maxDeliveryDays !== '' && maxDeliveryDays < 0) {
      errors.maxDeliveryDays = 'Max delivery days must be 0 or greater.';
    }

    if (maxUnitPrice !== '') {
      const priceNum = parseFloat(maxUnitPrice);
      if (isNaN(priceNum) || priceNum < 0) {
        errors.maxUnitPrice = 'Max unit price must be a non-negative number.';
      }
    }

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!validate()) {
      return;
    }

    setSubmitting(true);
    try {
      const constraints: Record<string, any> = {};
      if (maxDeliveryDays !== '') {
        constraints.max_delivery_days = Number(maxDeliveryDays);
      }
      if (maxUnitPrice.trim() !== '') {
        constraints.max_unit_price = maxUnitPrice.trim();
      }
      if (certifications.length > 0) {
        constraints.required_certifications = certifications;
      }
      if (notes.trim()) {
        constraints.notes = notes.trim();
      }

      const req = await api.requests.create({
        product_id: productId,
        quantity: Number(quantity),
        constraints,
      });

      // On successful creation, navigate to the workflow execution page
      navigate(`/workflows/${req.thread_id}`);
    } catch (err: any) {
      setFormError({
        message: err.message || 'Failed to submit procurement request.',
        correlationId: err.correlationId,
      });
    } finally {
      setSubmitting(false);
    }
  };

  if (loadingProducts) {
    return <Loading label="Loading catalog products..." />;
  }

  return (
    <div style={{ maxWidth: '720px', margin: '0 auto' }}>
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#111827', margin: 0 }}>
          New Procurement Request
        </h1>
        <p style={{ fontSize: '0.875rem', color: '#6b7280', marginTop: '0.25rem' }}>
          Initiate an automated procurement workflow. LangGraph specialists evaluate suppliers against PostgreSQL quotes, MongoDB certifications, and Qdrant policy rules.
        </p>
      </div>

      {loadError && (
        <div style={{ marginBottom: '1.5rem' }}>
          <ErrorBanner error={loadError} onRetry={() => window.location.reload()} />
        </div>
      )}

      {formError && (
        <div style={{ marginBottom: '1.5rem' }}>
          <ErrorBanner
            error={formError.message}
            correlationId={formError.correlationId}
            onDismiss={() => setFormError(null)}
          />
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        style={{
          backgroundColor: '#ffffff',
          borderRadius: '8px',
          border: '1px solid #e5e7eb',
          padding: '1.75rem',
          boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
        }}
      >
        {/* Product selection */}
        <div style={{ marginBottom: '1.25rem' }}>
          <label
            htmlFor="product_id"
            style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, color: '#374151', marginBottom: '0.35rem' }}
          >
            Product <span style={{ color: '#ef4444' }}>*</span>
          </label>
          {products.length === 0 ? (
            <div style={{ fontSize: '0.875rem', color: '#ef4444' }}>
              No products available in database. Please run demo seed script.
            </div>
          ) : (
            <select
              id="product_id"
              name="product_id"
              value={productId}
              onChange={(e) => setProductId(e.target.value)}
              disabled={submitting}
              style={{
                width: '100%',
                padding: '0.5rem 0.75rem',
                border: `1px solid ${fieldErrors.productId ? '#ef4444' : '#d1d5db'}`,
                borderRadius: '6px',
                fontSize: '0.875rem',
                backgroundColor: '#ffffff',
              }}
            >
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.id} &mdash; {p.name} ({p.sku}) &mdash; {p.category}
                </option>
              ))}
            </select>
          )}
          {fieldErrors.productId && (
            <div style={{ color: '#ef4444', fontSize: '0.75rem', marginTop: '0.25rem' }}>
              {fieldErrors.productId}
            </div>
          )}
          {selectedProduct && (
            <div
              style={{
                marginTop: '0.5rem',
                padding: '0.5rem 0.75rem',
                backgroundColor: '#f9fafb',
                borderRadius: '4px',
                fontSize: '0.75rem',
                color: '#4b5563',
                display: 'flex',
                gap: '1rem',
              }}
            >
              <span><strong>Category:</strong> {selectedProduct.category}</span>
              <span><strong>SKU:</strong> {selectedProduct.sku}</span>
            </div>
          )}
        </div>

        {/* Quantity */}
        <div style={{ marginBottom: '1.25rem' }}>
          <label
            htmlFor="quantity"
            style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, color: '#374151', marginBottom: '0.35rem' }}
          >
            Quantity (Units) <span style={{ color: '#ef4444' }}>*</span>
          </label>
          <input
            id="quantity"
            name="quantity"
            type="number"
            min={1}
            max={100000}
            required
            value={quantity}
            onChange={(e) => setQuantity(e.target.value === '' ? '' : Number(e.target.value))}
            disabled={submitting}
            placeholder="e.g. 500"
            style={{
              width: '100%',
              padding: '0.5rem 0.75rem',
              border: `1px solid ${fieldErrors.quantity ? '#ef4444' : '#d1d5db'}`,
              borderRadius: '6px',
              fontSize: '0.875rem',
              boxSizing: 'border-box',
            }}
          />
          {fieldErrors.quantity && (
            <div style={{ color: '#ef4444', fontSize: '0.75rem', marginTop: '0.25rem' }}>
              {fieldErrors.quantity}
            </div>
          )}
          <span style={{ fontSize: '0.75rem', color: '#6b7280' }}>
            Maximum allowable order is 100,000 units. Deterministic validation checks supplier inventory.
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.25rem' }}>
          {/* Max delivery days */}
          <div>
            <label
              htmlFor="max_delivery_days"
              style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, color: '#374151', marginBottom: '0.35rem' }}
            >
              Max Delivery Days
            </label>
            <input
              id="max_delivery_days"
              name="max_delivery_days"
              type="number"
              min={0}
              value={maxDeliveryDays}
              onChange={(e) => setMaxDeliveryDays(e.target.value === '' ? '' : Number(e.target.value))}
              disabled={submitting}
              placeholder="e.g. 14"
              style={{
                width: '100%',
                padding: '0.5rem 0.75rem',
                border: `1px solid ${fieldErrors.maxDeliveryDays ? '#ef4444' : '#d1d5db'}`,
                borderRadius: '6px',
                fontSize: '0.875rem',
                boxSizing: 'border-box',
              }}
            />
            {fieldErrors.maxDeliveryDays && (
              <div style={{ color: '#ef4444', fontSize: '0.75rem', marginTop: '0.25rem' }}>
                {fieldErrors.maxDeliveryDays}
              </div>
            )}
          </div>

          {/* Max unit price */}
          <div>
            <label
              htmlFor="max_unit_price"
              style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, color: '#374151', marginBottom: '0.35rem' }}
            >
              Max Unit Price (USD)
            </label>
            <input
              id="max_unit_price"
              name="max_unit_price"
              type="text"
              value={maxUnitPrice}
              onChange={(e) => setMaxUnitPrice(e.target.value)}
              disabled={submitting}
              placeholder="e.g. 1200.00"
              style={{
                width: '100%',
                padding: '0.5rem 0.75rem',
                border: `1px solid ${fieldErrors.maxUnitPrice ? '#ef4444' : '#d1d5db'}`,
                borderRadius: '6px',
                fontSize: '0.875rem',
                boxSizing: 'border-box',
              }}
            />
            {fieldErrors.maxUnitPrice && (
              <div style={{ color: '#ef4444', fontSize: '0.75rem', marginTop: '0.25rem' }}>
                {fieldErrors.maxUnitPrice}
              </div>
            )}
          </div>
        </div>

        {/* Required Certifications */}
        <div style={{ marginBottom: '1.25rem' }}>
          <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, color: '#374151', marginBottom: '0.35rem' }}>
            Required Certifications
          </label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            {KNOWN_CERTIFICATIONS.map((cert) => {
              const selected = certifications.includes(cert);
              return (
                <button
                  key={cert}
                  type="button"
                  onClick={() => toggleCert(cert)}
                  disabled={submitting}
                  style={{
                    padding: '4px 10px',
                    borderRadius: '16px',
                    border: selected ? '1px solid #2563eb' : '1px solid #d1d5db',
                    backgroundColor: selected ? '#eff6ff' : '#ffffff',
                    color: selected ? '#1d4ed8' : '#4b5563',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    cursor: submitting ? 'not-allowed' : 'pointer',
                  }}
                >
                  {selected ? `✓ ${cert}` : `+ ${cert}`}
                </button>
              );
            })}
          </div>
          <span style={{ fontSize: '0.75rem', color: '#6b7280', marginTop: '0.25rem', display: 'block' }}>
            Suppliers without matching MongoDB profiles will be excluded with reason code.
          </span>
        </div>

        {/* Notes */}
        <div style={{ marginBottom: '1.5rem' }}>
          <label
            htmlFor="notes"
            style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, color: '#374151', marginBottom: '0.35rem' }}
          >
            Request Notes (Free text)
          </label>
          <textarea
            id="notes"
            name="notes"
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            disabled={submitting}
            placeholder="Context or department notes (stored as metadata; decisions remain deterministic)..."
            style={{
              width: '100%',
              padding: '0.5rem 0.75rem',
              border: '1px solid #d1d5db',
              borderRadius: '6px',
              fontSize: '0.875rem',
              boxSizing: 'border-box',
              resize: 'vertical',
            }}
          />
        </div>

        {/* Submit */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem', alignItems: 'center' }}>
          <button
            type="submit"
            disabled={submitting || products.length === 0}
            style={{
              padding: '0.625rem 1.25rem',
              backgroundColor: submitting ? '#93c5fd' : '#2563eb',
              color: '#ffffff',
              border: 'none',
              borderRadius: '6px',
              fontSize: '0.875rem',
              fontWeight: 600,
              cursor: submitting ? 'not-allowed' : 'pointer',
            }}
          >
            {submitting ? 'Submitting & Dispatching Graph...' : 'Submit Procurement Request'}
          </button>
        </div>
      </form>
    </div>
  );
};
