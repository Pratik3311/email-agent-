"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ApprovalCard from "@/components/chat/ApprovalCard";
import AnswerCard from "@/components/chat/AnswerCard";
import SessionSidebar from "@/components/SessionSidebar";
import SidePanel from "@/components/SidePanel";
import { api } from "@/lib/api";
import type { Msg, Session } from "@/lib/types";

const SUGGESTIONS = [
  "What were the rejection cases in the last 2 days?",
  "Who sent the most emails this month?",
  "Which companies do we talk to the most?",
];

const SESSIONS_KEY = "ci-sessions";
const msgsKey = (id: string) => `ci-msgs-${id}`;

function loadSessions(): Session[] {
  try {
    return JSON.parse(localStorage.getItem(SESSIONS_KEY) ?? "[]");
  } catch {
    return [];
  }
}

export default function ChatPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => setSessions(loadSessions()), []);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, busy]);

  const persist = useCallback((id: string, messages: Msg[], firstQuestion?: string) => {
    try {
      localStorage.setItem(msgsKey(id), JSON.stringify(messages));
      const existing = loadSessions();
      if (!existing.some((s) => s.id === id) && firstQuestion) {
        const next = [{ id, title: firstQuestion.slice(0, 80), at: Date.now() }, ...existing];
        localStorage.setItem(SESSIONS_KEY, JSON.stringify(next.slice(0, 50)));
        setSessions(next);
      }
    } catch {
      /* localStorage unavailable — chat still works, history just won't persist */
    }
  }, []);

  function update(updater: (prev: Msg[]) => Msg[], sid?: string | null, firstQ?: string) {
    setMsgs((prev) => {
      const next = updater(prev);
      const id = sid ?? sessionId;
      if (id) persist(id, next, firstQ);
      return next;
    });
  }

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setInput("");
    setBusy(true);
    const question = text.trim();
    update((p) => [...p, { kind: "you", text: question }]);
    try {
      const res = await api.chat(question, sessionId);
      setSessionId(res.session_id);
      if (res.status === "answer") {
        update((p) => [...p, { kind: "agent", text: res.answer ?? "" }], res.session_id, question);
      } else if (res.status === "needs_clarification") {
        update((p) => [...p, { kind: "agent", text: res.message ?? "" }], res.session_id, question);
      } else if (res.status === "awaiting_approval" && res.plan) {
        update((p) => [...p, { kind: "plan", plan: res.plan! }], res.session_id, question);
      }
    } catch (e) {
      update((p) => [
        ...p,
        { kind: "error", text: e instanceof Error ? e.message : "Something went wrong." },
      ]);
    } finally {
      setBusy(false);
    }
  }

  function patchPlan(planId: string, patch: Partial<Extract<Msg, { kind: "plan" }>>) {
    update((p) =>
      p.map((m) => (m.kind === "plan" && m.plan.plan_id === planId ? { ...m, ...patch } : m))
    );
  }

  async function approve(planId: string) {
    setBusy(true);
    patchPlan(planId, { resolved: "approved" });
    update((p) => [...p, { kind: "agent", text: "Running approved plan…" }]);
    try {
      const res = await api.approve(planId);
      update((p) => p.filter((m) => !(m.kind === "agent" && m.text === "Running approved plan…")));
      if (res.status === "answer") {
        update((p) => [
          ...p,
          { kind: "answer", text: res.answer ?? "", evidence: res.evidence ?? [], planId },
        ]);
      } else {
        update((p) => [...p, { kind: "error", text: res.error ?? "Execution failed." }]);
      }
    } catch (e) {
      update((p) => [
        ...p,
        { kind: "error", text: e instanceof Error ? e.message : "Execution failed." },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function reject(planId: string) {
    setBusy(true);
    try {
      await api.reject(planId);
      patchPlan(planId, { resolved: "rejected" });
      update((p) => [...p, { kind: "agent", text: "Plan rejected — nothing was executed." }]);
    } catch (e) {
      update((p) => [
        ...p,
        { kind: "error", text: e instanceof Error ? e.message : "Reject failed." },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function edit(planId: string, instruction: string) {
    setBusy(true);
    try {
      const res = await api.edit(planId, instruction);
      patchPlan(planId, { resolved: "edited" });
      if (res.status === "awaiting_approval" && res.plan) {
        update((p) => [...p, { kind: "plan", plan: res.plan! }]);
      } else {
        update((p) => [...p, { kind: "agent", text: res.message ?? "Could not update the plan." }]);
      }
    } catch (e) {
      update((p) => [
        ...p,
        { kind: "error", text: e instanceof Error ? e.message : "Edit failed." },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function toggleSql(planId: string) {
    const msg = msgs.find(
      (m): m is Extract<Msg, { kind: "plan" }> => m.kind === "plan" && m.plan.plan_id === planId
    );
    if (!msg) return;
    if (msg.showSql) {
      patchPlan(planId, { showSql: false });
      return;
    }
    patchPlan(planId, { showSql: true });
    if (!msg.sql) {
      try {
        const detail = await api.planDetail(planId);
        patchPlan(planId, {
          sql: detail.generated_sql ?? [],
          searches: detail.search_queries ?? [],
        });
      } catch {
        patchPlan(planId, { sql: ["(could not load SQL)"] });
      }
    }
  }

  function newChat() {
    setSessionId(null);
    setMsgs([]);
  }

  function selectSession(id: string) {
    setSessionId(id);
    try {
      setMsgs(JSON.parse(localStorage.getItem(msgsKey(id)) ?? "[]"));
    } catch {
      setMsgs([]);
    }
  }

  return (
    <div className="flex h-[calc(100vh-120px)] gap-4">
      <SessionSidebar
        sessions={sessions}
        activeId={sessionId}
        onSelect={selectSession}
        onNew={newChat}
      />

      <section className="brutal-card flex flex-1 flex-col overflow-hidden">
        <div className="border-b-2 border-ink px-4 py-2.5 text-sm font-black uppercase tracking-wide">
          {msgs.length ? "Conversation" : "Ask Company AI"}
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto p-4 pt-6">
          {msgs.length === 0 && (
            <div className="mt-8 text-center">
              <p className="text-sm font-bold">
                Ask a question about your company&apos;s email data.
              </p>
              <p className="mx-auto mt-1 max-w-md text-xs text-ink/60">
                The agent will propose a plan and wait for your approval before
                touching the database.
              </p>
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="border-2 border-ink bg-paper px-2.5 py-1.5 text-[11px] font-bold hover:bg-accent"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {msgs.map((m, i) => {
            if (m.kind === "you") {
              return (
                <div key={i} className="flex justify-end">
                  <div className="brutal-card relative max-w-[75%] bg-accent p-3">
                    <span className="tag absolute -top-3 left-3 bg-ink text-paper">You</span>
                    <p className="mt-1 whitespace-pre-wrap text-sm">{m.text}</p>
                  </div>
                </div>
              );
            }
            if (m.kind === "agent") {
              return (
                <div key={i} className="brutal-card relative ml-8 max-w-[85%] p-3">
                  <span className="tag absolute -top-3 left-3 bg-paper">Agent</span>
                  <p className="mt-1 whitespace-pre-wrap text-sm">{m.text}</p>
                </div>
              );
            }
            if (m.kind === "plan") {
              return (
                <ApprovalCard
                  key={m.plan.plan_id}
                  msg={m}
                  busy={busy}
                  onApprove={() => approve(m.plan.plan_id)}
                  onReject={() => reject(m.plan.plan_id)}
                  onEdit={(instruction) => edit(m.plan.plan_id, instruction)}
                  onToggleSql={() => toggleSql(m.plan.plan_id)}
                />
              );
            }
            if (m.kind === "answer") {
              return (
                <AnswerCard key={i} text={m.text} evidence={m.evidence} planId={m.planId} />
              );
            }
            return (
              <div key={i} className="brutal-card ml-8 max-w-[85%] border-red-600 p-3">
                <span className="tag bg-red-600 text-paper">Error</span>
                <p className="mt-2 text-sm">{m.text}</p>
              </div>
            );
          })}

          {busy && (
            <p className="ml-8 animate-pulse text-xs font-bold uppercase text-ink/50">
              agent is thinking…
            </p>
          )}
          <div ref={bottomRef} />
        </div>

        <form
          className="flex gap-2 border-t-2 border-ink p-3"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <input
            className="flex-1 border-2 border-ink bg-paper px-3 py-2 text-sm outline-none placeholder:text-ink/40"
            placeholder="Message the agent…"
            value={input}
            disabled={busy}
            onChange={(e) => setInput(e.target.value)}
          />
          <button className="brutal-btn bg-accent px-5" type="submit" disabled={busy}>
            ➤
          </button>
        </form>
      </section>

      <SidePanel />
    </div>
  );
}
