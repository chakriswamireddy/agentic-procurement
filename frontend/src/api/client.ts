export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  correlationId?: string;
  retryAfter?: number;

  constructor(message: string, status: number, code = 'error', details: unknown = null, correlationId?: string, retryAfter?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
    this.correlationId = correlationId;
    this.retryAfter = retryAfter;
  }
}

let authToken: string | null = null;
const AUTH_STORAGE_KEY = 'agentic_procurement_token';

// Hydrate from sessionStorage if available
try {
  authToken = sessionStorage.getItem(AUTH_STORAGE_KEY);
} catch {
  // Ignore sessionStorage restriction if disabled
}

export function setAuthToken(token: string | null): void {
  authToken = token;
  try {
    if (token) {
      sessionStorage.setItem(AUTH_STORAGE_KEY, token);
    } else {
      sessionStorage.removeItem(AUTH_STORAGE_KEY);
    }
  } catch {
    // Ignore storage errors
  }
}

export function getAuthToken(): string | null {
  return authToken;
}

type AuthCallback = () => void;
const unauthorizedListeners: Set<AuthCallback> = new Set();

export function onUnauthorized(callback: AuthCallback): () => void {
  unauthorizedListeners.add(callback);
  return () => unauthorizedListeners.delete(callback);
}

function notifyUnauthorized(): void {
  setAuthToken(null);
  for (const listener of unauthorizedListeners) {
    try {
      listener();
    } catch {
      // Ignore listener errors
    }
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  const { auth = true, headers = {}, ...rest } = options;
  const url = path.startsWith('http') ? path : `/api/v1${path.startsWith('/') ? path : `/${path}`}`;

  const requestHeaders = new Headers(headers);
  if (!requestHeaders.has('Content-Type') && !(rest.body instanceof FormData) && !(rest.body instanceof URLSearchParams)) {
    requestHeaders.set('Content-Type', 'application/json');
  }

  if (auth && authToken) {
    requestHeaders.set('Authorization', `Bearer ${authToken}`);
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...rest,
      headers: requestHeaders,
    });
  } catch (err: unknown) {
    const errorMsg = err instanceof Error ? err.message : 'Network connection failed';
    throw new ApiError(`Network error: ${errorMsg}. Please check if the server is running.`, 0, 'network_error');
  }

  const correlationId = response.headers.get('x-correlation-id') || undefined;

  if (response.status === 401) {
    notifyUnauthorized();
    throw new ApiError('Authentication required or session expired', 401, 'unauthorized', null, correlationId);
  }

  if (response.status === 204) {
    return {} as T;
  }

  let responseData: unknown = null;
  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    try {
      responseData = await response.json();
    } catch {
      responseData = null;
    }
  } else {
    try {
      responseData = await response.text();
    } catch {
      responseData = null;
    }
  }

  if (!response.ok) {
    let errorCode = `http_${response.status}`;
    let errorMessage = `Request failed with status ${response.status}`;
    let errorDetails: unknown = null;

    if (responseData && typeof responseData === 'object') {
      const data = responseData as Record<string, unknown>;
      if (data.error && typeof data.error === 'object') {
        const errObj = data.error as Record<string, unknown>;
        errorCode = (errObj.code as string) || errorCode;
        errorMessage = (errObj.message as string) || errorMessage;
        errorDetails = errObj.details ?? null;
      } else if (data.detail) {
        errorMessage = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
        errorDetails = data.detail;
      }
    }

    let retryAfter: number | undefined;
    const retryHeader = response.headers.get('retry-after');
    if (retryHeader) {
      const parsed = parseInt(retryHeader, 10);
      if (!isNaN(parsed)) {
        retryAfter = parsed;
      }
    }

    throw new ApiError(errorMessage, response.status, errorCode, errorDetails, correlationId, retryAfter);
  }

  return responseData as T;
}
