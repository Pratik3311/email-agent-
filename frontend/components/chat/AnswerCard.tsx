"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { EvidenceResponse } from "@/lib/types";

export default function AnswerCard({
  text,
  evidence,
  planId,
}: {
  text: string;
  evidence: string[];
  planId: string;
}) {
  const [detail, setDetail] = useState<EvidenceResponse | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggleEvidence() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (!detail) {
      try {
        setDetail(await api.evidence(planId));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load evidence.");
      }
    }
  }

  return (
    <div className="brutal-card relative ml-8 max-w-[85%] p-4">
      <span className="tag absolute -top-3 left-3 bg-ink text-accent">Analysis complete</span>
      <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed">{text}</p>

      {evidence.length > 0 && (
        <ul className="mt-3 space-y-1 border-2 border-ink bg-cream p-2 text-xs">
          {evidence.map((e, i) => (
            <li key={i}>▪ {e}</li>
          ))}
        </ul>
      )}

      <button
        className="brutal-btn mt-3 bg-accent"
        onClick={toggleEvidence}
      >
        {open ? "Hide evidence" : "View evidence"}
      </button>

      {open && (
        <div className="mt-3 max-h-72 overflow-auto border-2 border-ink bg-cream p-2 text-[11px]">
          {error && <p className="font-bold">{error}</p>}
          {detail && (
            <>
              <p className="mb-2 font-bold uppercase">Retrieved data ({detail.results.length} result set{detail.results.length === 1 ? "" : "s"})</p>
              <pre className="whitespace-pre-wrap break-all">
                {JSON.stringify(detail.results, null, 1)}
              </pre>
            </>
          )}
          {!detail && !error && <span>loading…</span>}
        </div>
      )}
    </div>
  );
}
