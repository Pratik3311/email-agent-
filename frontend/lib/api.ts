import type {
  ApproveResponse,
  ChatResponse,
  EditResponse,
  EvidenceResponse,
  Health,
  PlanView,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail ?? `Request failed (${res.status})`);
  }
  return body as T;
}

export const api = {
  chat: (message: string, sessionId: string | null) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId }),
    }),

  approve: (planId: string) =>
    request<ApproveResponse>(`/api/approvals/${planId}/approve`, { method: "POST" }),

  reject: (planId: string) =>
    request<{ status: string }>(`/api/approvals/${planId}/reject`, { method: "POST" }),

  edit: (planId: string, instruction: string) =>
    request<EditResponse>(`/api/approvals/${planId}/edit`, {
      method: "POST",
      body: JSON.stringify({ instruction }),
    }),

  planDetail: (planId: string) =>
    request<PlanView>(`/api/approvals/${planId}?include_sql=true`),

  evidence: (planId: string) => request<EvidenceResponse>(`/api/approvals/${planId}/evidence`),

  health: () => request<Health>("/api/health"),

  dashboardOverview: () => request<Record<string, unknown>>("/api/dashboard/overview"),
  dashboardTrends: (days: number) =>
    request<{ days: number; series: { day: string; emails: number }[] }>(
      `/api/dashboard/trends?days=${days}`
    ),
  dashboardPeople: () =>
    request<{ ranking: string; people: Record<string, unknown>[] }>("/api/dashboard/people"),
  dashboardInsights: () =>
    request<{ insights: Record<string, unknown>[] }>("/api/dashboard/insights"),
};
