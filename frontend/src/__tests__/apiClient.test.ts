import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { apiRequest, ApiError, setAuthToken, getAuthToken, onUnauthorized } from '../api/client';

describe('API Client', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    setAuthToken(null);
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('parses successful JSON responses', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'Content-Type': 'application/json' }),
      json: async () => ({ id: 'req-123', status: 'awaiting_approval' }),
      text: async () => JSON.stringify({ id: 'req-123', status: 'awaiting_approval' }),
    });

    const res = await apiRequest<{ id: string; status: string }>('/procurement/requests/req-123');
    expect(res.id).toBe('req-123');
    expect(res.status).toBe('awaiting_approval');
  });

  it('handles 204 No Content with empty object', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      headers: new Headers(),
      text: async () => '',
    });

    const res = await apiRequest('/some-endpoint');
    expect(res).toEqual({});
  });

  it('attaches Bearer token when auth is enabled', async () => {
    setAuthToken('mock-jwt-token');
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'Content-Type': 'application/json' }),
      json: async () => ({ ok: true }),
      text: async () => JSON.stringify({ ok: true }),
    });

    await apiRequest('/auth/me');

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [, options] = vi.mocked(global.fetch).mock.calls[0];
    const headers = options?.headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer mock-jwt-token');
  });

  it('handles 401 Unauthorized and notifies listeners', async () => {
    setAuthToken('expired-jwt');
    const unauthorizedCallback = vi.fn();
    const unsubscribe = onUnauthorized(unauthorizedCallback);

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      headers: new Headers({ 'Content-Type': 'application/json' }),
      json: async () => ({ detail: 'Token expired' }),
      text: async () => JSON.stringify({ detail: 'Token expired' }),
    });

    await expect(apiRequest('/protected')).rejects.toThrow(ApiError);
    expect(unauthorizedCallback).toHaveBeenCalledTimes(1);
    expect(getAuthToken()).toBeNull();

    unsubscribe();
  });

  it('parses 429 Rate Limit and extracts Retry-After header', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      headers: new Headers({
        'Content-Type': 'application/json',
        'Retry-After': '15',
      }),
      json: async () => ({ detail: 'Rate limit exceeded' }),
      text: async () => JSON.stringify({ detail: 'Rate limit exceeded' }),
    });

    try {
      await apiRequest('/heavy-action');
      expect.unreachable();
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(429);
      expect(err.retryAfter).toBe(15);
    }
  });

  it('parses error envelope and correlation ID', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      headers: new Headers({
        'Content-Type': 'application/json',
        'X-Correlation-ID': 'corr-test-456',
      }),
      json: async () => ({ detail: 'Stale recommendation version' }),
      text: async () => JSON.stringify({ detail: 'Stale recommendation version' }),
    });

    try {
      await apiRequest('/workflows/wf-1/approval');
      expect.unreachable();
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(409);
      expect(err.correlationId).toBe('corr-test-456');
    }
  });

  it('handles network failure with status 0 friendly ApiError', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Failed to fetch'));

    try {
      await apiRequest('/unreachable');
      expect.unreachable();
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(0);
      expect(err.code).toBe('network_error');
    }
  });
});
