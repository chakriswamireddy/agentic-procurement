import { apiRequest } from './client';
import type {
  ApprovalDecisionPayload,
  CreateRequestPayload,
  PolicySearchResponse,
  ProcurementRequest,
  Product,
  SupplierDetail,
  SupplierListResponse,
  TokenResponse,
  UserInfo,
  WorkflowView,
} from './types';

export const api = {
  auth: {
    login: (email: string, password: string): Promise<TokenResponse> =>
      apiRequest<TokenResponse>('/auth/login', {
        method: 'POST',
        auth: false,
        body: JSON.stringify({ email, password }),
      }),
    me: (): Promise<UserInfo> => apiRequest<UserInfo>('/auth/me'),
  },

  products: {
    list: (category?: string): Promise<Product[]> => {
      const query = category ? `?category=${encodeURIComponent(category)}` : '';
      return apiRequest<Product[]>(`/products${query}`);
    },
  },

  requests: {
    create: (payload: CreateRequestPayload): Promise<ProcurementRequest> =>
      apiRequest<ProcurementRequest>('/procurement/requests', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    get: (id: string): Promise<ProcurementRequest> =>
      apiRequest<ProcurementRequest>(`/procurement/requests/${id}`),
  },

  workflows: {
    get: (threadId: string): Promise<WorkflowView> =>
      apiRequest<WorkflowView>(`/workflows/${threadId}`),
    list: (status?: string, limit = 50, offset = 0): Promise<ProcurementRequest[]> => {
      const params = new URLSearchParams();
      if (status) params.set('status', status);
      params.set('limit', String(limit));
      params.set('offset', String(offset));
      return apiRequest<ProcurementRequest[]>(`/workflows?${params.toString()}`);
    },
    approveOrReject: (threadId: string, payload: ApprovalDecisionPayload): Promise<WorkflowView> =>
      apiRequest<WorkflowView>(`/workflows/${threadId}/approval`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    retryExecution: (threadId: string): Promise<WorkflowView> =>
      apiRequest<WorkflowView>(`/workflows/${threadId}/execution/retry`, {
        method: 'POST',
      }),
  },

  suppliers: {
    list: (params: {
      category?: string;
      location?: string;
      status?: string;
      q?: string;
      limit?: number;
      offset?: number;
    } = {}): Promise<SupplierListResponse> => {
      const search = new URLSearchParams();
      if (params.category) search.set('category', params.category);
      if (params.location) search.set('location', params.location);
      if (params.status) search.set('status', params.status);
      if (params.q) search.set('q', params.q);
      if (params.limit !== undefined) search.set('limit', String(params.limit));
      if (params.offset !== undefined) search.set('offset', String(params.offset));
      return apiRequest<SupplierListResponse>(`/suppliers?${search.toString()}`);
    },
    get: (id: string): Promise<SupplierDetail> =>
      apiRequest<SupplierDetail>(`/suppliers/${id}`),
  },

  policies: {
    search: (q: string, limit = 5): Promise<PolicySearchResponse> =>
      apiRequest<PolicySearchResponse>(`/policies/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  },
};
