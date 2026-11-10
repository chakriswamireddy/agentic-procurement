export interface UserInfo {
  id: string;
  email: string;
  role: 'requester' | 'approver' | 'admin' | 'auditor';
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserInfo;
}

export interface Product {
  id: string;
  sku: string;
  name: string;
  category: string;
  attributes: Record<string, unknown>;
}

export interface QuotationSummary {
  id: string;
  product_id: string;
  unit_price: string;
  currency: string;
  available_quantity: number;
  delivery_days: number;
  valid_until: string;
}

export interface SupplierProfile {
  supplier_type?: string;
  certifications: string[];
  compliance: Record<string, unknown>;
  regional_registrations: Record<string, unknown>;
  source?: Record<string, unknown>;
}

export interface Supplier {
  id: string;
  name: string;
  category: string;
  location: string;
  status: 'active' | 'inactive' | 'suspended';
}

export interface SupplierDetail extends Supplier {
  profile?: SupplierProfile;
  quotations: QuotationSummary[];
}

export interface SupplierListResponse {
  items: Supplier[];
  total: number;
  limit: number;
  offset: number;
}

export interface ProcurementConstraints {
  max_delivery_days?: number | null;
  required_certifications?: string[];
  max_unit_price?: string | number | null;
  notes?: string | null;
}

export interface CreateRequestPayload {
  product_id: string;
  quantity: number;
  constraints?: ProcurementConstraints;
}

export interface RecommendationSummary {
  id?: string;
  supplier_id: string;
  supplier_name: string;
  score: string;
  scoring_version: string;
  total_cost: string;
  unit_price: string;
  currency: string;
  delivery_days: number;
  version: number;
  caveats: string[];
  evidence_chunk_ids: string[];
}

export interface ProcurementRequest {
  id: string;
  thread_id: string;
  requester_id: string;
  product_id: string;
  product_name?: string;
  category?: string;
  quantity: number;
  constraints: Record<string, unknown>;
  status: string;
  created_at?: string;
  recommendation?: RecommendationSummary | null;
}

export interface WorkflowView {
  request_id: string;
  thread_id: string;
  status: string;
  current_node?: string | null;
  awaiting_approval: boolean;
  failure_reason?: string | null;
  recommendation?: RecommendationSummary | null;
  evidence_chunk_ids: string[];
  issues: Array<Record<string, unknown>>;
}

export interface PolicyEvidenceItem {
  chunk_id: string;
  document_id: string;
  version: string;
  section: string;
  text: string;
  effective_from: string;
  effective_until?: string | null;
  classification: string;
  dense_score?: number | null;
  sparse_score?: number | null;
  combined_score?: number | null;
}

export interface PolicySearchResponse {
  query: string;
  total_chunks: number;
  retrieved_count: number;
  abstain: boolean;
  abstain_reason?: string | null;
  results: PolicyEvidenceItem[];
}

export interface ApprovalDecisionPayload {
  decision: 'approved' | 'rejected';
  reason?: string | null;
  recommendation_version?: number | null;
  idempotency_key?: string | null;
}
