"use client";

import { useState } from "react";
import type { Msg } from "@/lib/types";

type PlanMsg = Extract<Msg, { kind: "plan" }>;

export default function ApprovalCard({
  msg,
  busy,
  onApprove,
  onReject,
  onEdit,
  onToggleSql,
}: {
  msg: PlanMsg;
  busy: boolean;
  onApprove: () => void;
  onReject: () => void;
  onEdit: (instruction: string) => void;
  onToggleSql: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [instruction, setInstruction] = useState("");
  const { plan, resolved } = msg;

  const op = plan.operations[0];
  const dateRange =
    op?.date_from || op?.date_to
      ? `${op?.date_from ?? "…"} → ${op?.date_to ?? "…"}`
      : "not restricted";

  return (
    <div className="brutal-card relative ml-8 max-w-[85%] p-4">
      <span className="tag absolute -top-3 left-3 bg-accent">
        {resolved ? `Plan · ${resolved}` : "Approval required"}
      </span>

      <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed">{plan.human_explanation}</p>

      <div className="mt-3 grid grid-cols-1 gap-1 border-2 border-ink bg-cream p-2 text-xs sm:grid-cols-3">
        <div>
          <span className="font-bold uppercase text-ink/60">Operation</span>
          <div>{plan.operations.map((o) => o.type).join(", ") || "—"}</div>
        </div>
        <div>
          <span className="font-bold uppercase text-ink/60">Date range</span>
          <div>{dateRange}</div>
        </div>
        <div>
          <span className="font-bold uppercase text-ink/60">Max results</span>
          <div>{op?.limit ?? "—"}</div>
        </div>
      </div>

      {!resolved && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button className="brutal-btn bg-accent" disabled={busy} onClick={onApprove}>
            ✓ Approve &amp; Run
          </button>
          <button
            className="brutal-btn bg-paper"
            disabled={busy}
            onClick={() => setEditing((v) => !v)}
          >
            Edit
          </button>
          <button className="brutal-btn bg-paper" disabled={busy} onClick={onReject}>
            ✗ Reject
          </button>
          <button
            className="text-xs font-bold underline underline-offset-2"
            onClick={onToggleSql}
          >
            {msg.showSql ? "Hide generated SQL" : "View generated SQL"}
          </button>
        </div>
      )}

      {editing && !resolved && (
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!instruction.trim()) return;
            onEdit(instruction.trim());
            setEditing(false);
            setInstruction("");
          }}
        >
          <input
            autoFocus
            className="flex-1 border-2 border-ink bg-paper px-2 py-1.5 text-xs outline-none placeholder:text-ink/40"
            placeholder="Describe the change, e.g. only customer-related emails…"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
          />
          <button className="brutal-btn bg-accent" type="submit" disabled={busy}>
            Update plan
          </button>
        </form>
      )}

      {msg.showSql && (
        <div className="mt-3 border-2 border-ink bg-ink p-2 text-[11px] text-accent">
          {(msg.sql ?? []).map((s, i) => (
            <pre key={`sql-${i}`} className="overflow-x-auto whitespace-pre-wrap">{s}</pre>
          ))}
          {(msg.searches ?? []).map((s, i) => (
            <pre key={`q-${i}`} className="overflow-x-auto whitespace-pre-wrap">search: {s}</pre>
          ))}
          {!msg.sql?.length && !msg.searches?.length && <span>loading…</span>}
        </div>
      )}
    </div>
  );
}
