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
    // A 401 on any call except the login itself means the saved login is no
    // longer valid (token expired after 8h, or the server's signing secret
    // changed). Drop it and return to sign-in instead of leaving the user on
    // a page that silently has no data.
    if (res.status === 401 && path !== '/auth/login') {
      setToken(null);
      try {
        localStorage.removeItem('cip_user');
        sessionStorage.removeItem('cip_case_context');
      } catch { /* storage unavailable: nothing to clear */ }
      window.location.assign('/login');
    }
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
  caseTypes: (caseId: string) => request<CaseTypeRow[]>(`/cases/${caseId}/case-types`),
  classifyCase: (caseId: string) => request<CaseTypeSuggestion[]>(`/cases/${caseId}/classify`, { method: 'POST' }),
  confirmCaseType: (caseId: string, caseType: string, decision: 'CONFIRMED' | 'REJECTED', notes?: string) =>
    request<CaseTypeRow>(`/cases/${caseId}/case-types/${caseType}/confirm`, {
      method: 'POST', body: JSON.stringify({ decision, notes }),
    }),
  moduleStatus: (caseId: string) => request<ModuleStatusResponse>(`/cases/${caseId}/module-status`),
  evidenceSummary: (caseId: string) => request<EvidenceSummary>(`/cases/${caseId}/evidence-summary`),
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

// Axis B: case-type classification. A case can carry multiple case types at
// once (a case tagged both Financial and Assault runs both branches'
// modules) -- so these are always arrays, never a single value.
export type CaseTypeStatus = 'SUGGESTED' | 'CONFIRMED' | 'REJECTED';

export interface CaseTypeRow {
  case_id: string;
  case_type: string;
  status: CaseTypeStatus;
  confidence: number | null;
  reason: string | null;
  confirmed_by: string | null;
  confirmed_at: string | null;
}

export interface CaseTypeSuggestion {
  case_type: string;
  confidence: number;
  reason: string;
  signals: { kind: 'STRUCTURAL' | 'KEYWORD'; [key: string]: any }[];
}

// Case-type gating: a module's leads only appear once its case type is
// CONFIRMED on this case; until then they are counted here as held back.
export interface ModuleStatus {
  case_type: string;
  status: CaseTypeStatus | 'NOT_SUGGESTED';
  active_leads: number;
  held_back_leads: number;
  lead_type_counts: Record<string, { active: number; held_back: number }>;
}

export interface ModuleStatusResponse {
  case_id: string;
  modules: ModuleStatus[];
  cross_cutting_leads: number;
  cross_cutting_lead_type_counts: Record<string, number>;
}

// Live per-case inventory of connected records. Digital = records the
// platform reads directly; Physical = records ABOUT physical evidence.
export interface EvidenceSource {
  key: string;
  label: string;
  branch: 'DIGITAL' | 'PHYSICAL';
  count: number;
}

export interface EvidenceSummary {
  case_id: string;
  sources: EvidenceSource[];
  totals: { DIGITAL: number; PHYSICAL: number };
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
