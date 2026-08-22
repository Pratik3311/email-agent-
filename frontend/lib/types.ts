export type Operation = {
  type: "query_database" | "search_emails";
  description: string;
  date_from: string | null;
  date_to: string | null;
  limit: number;
};

export type PlanView = {
  plan_id: string;
  status: string;
  intent: string;
  human_explanation: string;
  operations: Operation[];
  created_at: string;
  generated_sql?: string[];
  search_queries?: string[];
};

export type ChatResponse = {
  status: "answer" | "needs_clarification" | "awaiting_approval";
  session_id: string;
  answer?: string;
  message?: string;
  plan?: PlanView;
};

export type ApproveResponse = {
  status: "answer" | "failed";
  plan_id: string;
  session_id: string;
  answer?: string;
  evidence?: string[];
  error?: string;
};

export type EditResponse = {
  status: "awaiting_approval" | "needs_clarification" | "error";
  session_id: string;
  plan?: PlanView;
  message?: string;
};

export type EvidenceResponse = {
  plan_id: string;
  question: string;
  answer: string;
  evidence: string[];
  operations: Record<string, unknown>[];
  results: Record<string, unknown>[];
};

export type Health = { status: string; mcp_connected: boolean };

export type Msg =
  | { kind: "you"; text: string }
  | { kind: "agent"; text: string }
  | {
      kind: "plan";
      plan: PlanView;
      sql?: string[];
      searches?: string[];
      resolved?: "approved" | "rejected" | "edited";
      showSql?: boolean;
      editing?: boolean;
    }
  | { kind: "answer"; text: string; evidence: string[]; planId: string }
  | { kind: "error"; text: string };

export type Session = { id: string; title: string; at: number };
