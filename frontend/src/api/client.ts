// In production, set VITE_API_BASE (e.g. https://your-backend.onrender.com/api)
// as a build-time env var. Falls back to local dev backend otherwise.
const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000/api';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function getToken(): string | null {
  return localStorage.getItem('cip_token');
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem('cip_token', token);
  else localStorage.removeItem('cip_token');
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail || 'request failed');
  }
  return res.json();
}

export const api = {
  login: (username: string, password: string) =>
    request<{ token: string; role: string; username: string; display_name: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<{ username: string; role: string }>('/me'),
  listCases: () => request<CaseRow[]>('/cases'),
  caseGraph: (caseId: string, reason: string) =>
    request<GraphData>(`/cases/${caseId}/graph?reason=${encodeURIComponent(reason)}`),
  caseLeads: (caseId: string, reason: string) =>
    request<Lead[]>(`/cases/${caseId}/leads?reason=${encodeURIComponent(reason)}`),
  setDisposition: (leadId: string, disposition: string, notes?: string) =>
    request(`/leads/${leadId}/disposition`, { method: 'POST', body: JSON.stringify({ disposition, notes }) }),
  reviewQueue: () => request<ReviewCluster[]>('/review-queue'),
  resolveReview: (clusterId: string, decision: string, notes?: string) =>
    request(`/review-queue/${clusterId}/resolve`, { method: 'POST', body: JSON.stringify({ decision, notes }) }),
  entityDetail: (entityId: string) => request<any>(`/entities/${entityId}`),
  analyticsSummary: (reason: string) => request<AnalyticsSummary>(`/analytics/summary?reason=${encodeURIComponent(reason)}`),
  womenSafety: (reason: string) => request<WomenSafetyData>(`/women-safety?reason=${encodeURIComponent(reason)}`),
  evaluation: () => request<any>('/evaluation'),
  auditChain: () => request<{ entries: AuditEntry[]; verification: { valid: boolean; entry_count: number; broken_at_seq: number[] } }>('/audit/chain'),
  tamperDemo: (seq: number, new_reason: string) =>
    request<any>('/audit/tamper-demo', { method: 'POST', body: JSON.stringify({ seq, new_reason }) }),
  restoreDemo: (seq: number, original_reason: string, original_payload_raw: string) =>
    request<any>('/audit/restore-demo', { method: 'POST', body: JSON.stringify({ seq, original_reason, original_payload_raw }) }),
};

export interface CaseRow {
  case_id: string;
  title: string;
  category: string;
  opened_date: string;
}

export interface GraphNode {
  id: string;
  label: string;
  entity_type: string;
  is_official: boolean;
  is_utility: boolean;
}

export interface GraphLink {
  source: string;
  target: string;
  relationship_type: string;
  epistemic_status: string;
  source_record_id: string | null;
  source_record_type: string | null;
  timestamp: string | null;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface Lead {
  lead_id: string;
  lead_type: string;
  severity: string;
  entities_involved: string[];
  requires_human_verification: boolean;
  method_provenance?: string[];
  summary: string;
  signals: { signal: string; value: any }[];
  source_record_ids: string[];
  created_at: string;
  disposition: { disposition: string; actor: string; timestamp: string; notes?: string } | null;
}

export interface ReviewCluster {
  cluster_id: string;
  entity_type: string;
  reason: string;
  status: string;
  mentions: { mention_id: string; text: string; source_record_id: string; fir_role: string | null }[];
}

export interface AnalyticsSummary {
  top_degree: { entity_id: string; label: string; entity_type: string; score: number }[];
  top_betweenness: { entity_id: string; label: string; entity_type: string; score: number }[];
  top_pagerank: { entity_id: string; label: string; entity_type: string; score: number }[];
  top_broker: { entity_id: string; label: string; entity_type: string; score: number }[];
  community_count: number;
  analysis_graph_size: { nodes: number; edges: number };
}

export interface WomenSafetyData {
  leads: Lead[];
  recruiters: { entity_id: string; label: string; entity_type: string; fanout_count: number }[];
  transporters: { entity_id: string; label: string; entity_type: string; methods: string[]; detail: any }[];
  repeat_locations: { entity_id: string; location: string; source_records: string[]; independent_source_count: number; linked_entities: string[] }[];
  chain_candidates: { recruiter: any; transporter: any; receiver_side: any }[];
}

export interface AuditEntry {
  seq: number;
  timestamp: string;
  actor: string;
  action: string;
  case_id: string | null;
  reason: string | null;
  payload_raw: string;
  prev_hash: string;
  hash: string;
}
