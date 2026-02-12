/**
 * API client — typed fetch wrappers for the admin dashboard.
 * All endpoints point to the FastAPI backend at /api/v1/admin/*.
 */

import { getStoredToken } from './auth';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getStoredToken();
  const authHeaders: Record<string, string> = token
    ? { Authorization: `Bearer ${token}` }
    : {};

  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...authHeaders, ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json();
}

// ── Types ──────────────────────────────────

export interface DashboardData {
  status_counts: Record<string, number>;
  cost: { today_usd: number; last7d_usd: number };
  approval: { pending: number };
  top_errors: { error_code: string; count: number }[];
  tool_denies: number;
  cost_by_department: { department: string; cost_usd: number }[];
}

export interface TraceRow {
  trace_id: string;
  department: string;
  status: string;
  last_event_at: string | null;
  current_step: string | null;
  current_agent_id: string | null;
  total_cost_usd: number;
  risk_level: string | null;
  data_sensitivity: string | null;
  last_error_code: string | null;
  last_error_message_short: string | null;
  approval_pending: boolean;
  summary: string | null;
}

export interface TraceEvent {
  created_at: string | null;
  event_type: string;
  agent_id: string;
  decision: string | null;
  status: string | null;
  reason: string | null;
  tool_name: string | null;
  model: string | null;
  cost_usd: number | null;
  latency_ms: number | null;
  tokens_in: number | null;
  tokens_out: number | null;
  artifact_ids: string | null;
  approver_id: string | null;
  risk_level: string | null;
  error_code: string | null;
  error_message_short: string | null;
}

export interface TraceDetail {
  header: {
    trace_id: string;
    department: string;
    status: string;
    started_at: string | null;
    ended_at: string | null;
    total_cost_usd: number;
    total_tokens_in: number | null;
    total_tokens_out: number | null;
    risk_level: string | null;
    data_sensitivity: string | null;
    audit_chain_ok: boolean | null;
    summary: string | null;
  } | null;
  events: TraceEvent[];
  event_count: number;
}

export interface ApprovalRow {
  trace_id: string;
  department: string;
  requester_id: string | null;
  requested_at: string | null;
  waiting_seconds: number;
  risk_level: string | null;
  current_step: string | null;
  summary: string | null;
}

export interface PolicyEvent {
  created_at: string | null;
  trace_id: string;
  department: string;
  agent_id: string;
  event_type: string;
  decision: string | null;
  reason: string | null;
  tool_name: string | null;
  resource: string | null;
  risk_level: string | null;
}

export interface AgentRow {
  id: string;
  name: string;
  department: string;
  tier: string;
  status: string;
  description: string | null;
  prompt_version: number;
  prompt_updated_at: string | null;
  prompt_updated_by: string | null;
  has_prompt_override: boolean;
}

export interface PromptHistoryEntry {
  version: number;
  prompt_text: string;
  changed_by: string;
  changed_at: string | null;
  change_reason: string | null;
}

export interface AgentPromptData {
  agent_id: string;
  agent_name: string;
  department: string;
  current_prompt: string | null;
  has_override: boolean;
  default_prompt: string | null;
  prompt_version: number;
  prompt_updated_at: string | null;
  prompt_updated_by: string | null;
  history: PromptHistoryEntry[];
}

// ── API Functions ──────────────────────────

export interface UserRow {
  id: string;
  email: string;
  name: string;
  department: string;
  role: string;
  is_active: boolean;
  status_label: string;
  created_at: string | null;
}

export const api = {
  getDashboard: (hours = 24) =>
    fetchJSON<DashboardData>(`/admin/dashboard?hours=${hours}`),

  getTraces: (params?: {
    status?: string;
    department?: string;
    risk_level?: string;
    approval_pending?: boolean;
    q?: string;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.department) qs.set('department', params.department);
    if (params?.risk_level) qs.set('risk_level', params.risk_level);
    if (params?.approval_pending !== undefined)
      qs.set('approval_pending', String(params.approval_pending));
    if (params?.q) qs.set('q', params.q);
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    return fetchJSON<{ traces: TraceRow[]; count: number }>(
      `/admin/traces?${qs.toString()}`
    );
  },

  getTraceDetail: (traceId: string) =>
    fetchJSON<TraceDetail>(`/admin/traces/${traceId}`),

  getApprovals: (limit = 50) =>
    fetchJSON<{ approvals: ApprovalRow[]; count: number }>(
      `/admin/approvals?limit=${limit}`
    ),

  getPolicies: (params?: {
    days?: number;
    decision?: string;
    event_type?: string;
    department?: string;
    tool_name?: string;
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.days) qs.set('days', String(params.days));
    if (params?.decision) qs.set('decision', params.decision);
    if (params?.event_type) qs.set('event_type', params.event_type);
    if (params?.department) qs.set('department', params.department);
    if (params?.tool_name) qs.set('tool_name', params.tool_name);
    if (params?.limit) qs.set('limit', String(params.limit));
    return fetchJSON<{ events: PolicyEvent[]; count: number }>(
      `/admin/policies?${qs.toString()}`
    );
  },

  getAgents: (department?: string) => {
    const qs = department ? `?department=${department}` : '';
    return fetchJSON<{ agents: AgentRow[]; count: number }>(
      `/admin/agents${qs}`
    );
  },

  getAgentPrompt: (agentId: string) =>
    fetchJSON<AgentPromptData>(`/admin/agents/${agentId}/prompt`),

  updateAgentPrompt: (
    agentId: string,
    data: { prompt_text: string; changed_by?: string; change_reason?: string }
  ) =>
    fetchJSON<{ status: string; prompt_version: number; message: string }>(
      `/admin/agents/${agentId}/prompt`,
      { method: 'PUT', body: JSON.stringify(data) }
    ),

  rollbackAgentPrompt: (
    agentId: string,
    data: { target_version: number; changed_by?: string }
  ) =>
    fetchJSON<{
      status: string;
      from_version: number;
      to_version: number;
      message: string;
    }>(`/admin/agents/${agentId}/prompt/rollback`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  testAgent: (
    agentId: string,
    data: { message: string; thread_id?: string }
  ) =>
    fetchJSON<{
      agent_id: string;
      agent_name: string;
      thread_id: string | null;
      response: string;
      status: string;
    }>(`/admin/agents/${agentId}/test`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getLLMSettings: () =>
    fetchJSON<{
      provider: string;
      model: string;
      api_key_set: boolean;
      api_key_masked: string;
      available_providers: {
        id: string;
        name: string;
        models: string[];
      }[];
    }>('/admin/settings/llm'),

  updateLLMSettings: (data: { provider?: string; api_key?: string }) =>
    fetchJSON<{ status: string; message: string }>('/admin/settings/llm', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  syncAgentPrompts: () =>
    fetchJSON<{
      status: string;
      created: string[];
      created_count: number;
      updated: string[];
      updated_count: number;
      skipped: { name: string; reason: string }[];
      total_classes: number;
    }>('/admin/agents/sync-prompts', { method: 'POST' }),

  // ── User Management ────────────────────────

  getUsers: (params?: { department?: string; role?: string }) => {
    const qs = new URLSearchParams();
    if (params?.department) qs.set('department', params.department);
    if (params?.role) qs.set('role', params.role);
    return fetchJSON<{ users: UserRow[]; count: number }>(
      `/admin/users?${qs.toString()}`
    );
  },

  createUser: (data: { email: string; name: string; department: string; role: string }) =>
    fetchJSON<{
      user: { id: string; email: string; name: string; department: string; role: string; status_label: string };
      invite_token: string;
      invite_link: string;
      expires_at: string;
    }>('/admin/users', { method: 'POST', body: JSON.stringify(data) }),

  deleteUser: (userId: string) =>
    fetchJSON<{ status: string; message: string }>(`/admin/users/${userId}`, { method: 'DELETE' }),

  // ── Auth ───────────────────────────────────

  login: (data: { email: string; password: string }) =>
    fetchJSON<{ access_token: string; token_type: string; user: UserRow }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getInviteInfo: (token: string) =>
    fetchJSON<{
      name: string;
      email: string;
      department: string;
      role: string;
      valid: boolean;
      message: string;
    }>(`/auth/invite-info?token=${encodeURIComponent(token)}`),

  setPassword: (data: { token: string; password: string }) =>
    fetchJSON<{ access_token: string; token_type: string; user: UserRow }>('/auth/set-password', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // ── Approval Decisions ─────────────────────

  decideApproval: (traceId: string, data: { decision: 'approved' | 'rejected'; reason?: string }) =>
    fetchJSON<{
      status: string;
      trace_id: string;
      decision: string;
      decided_by: string;
      decided_at: string;
    }>(`/admin/approvals/${traceId}/decide`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};
