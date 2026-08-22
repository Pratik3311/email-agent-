"use client";

import type { Session } from "@/lib/types";

export default function SessionSidebar({
  sessions,
  activeId,
  onSelect,
  onNew,
}: {
  sessions: Session[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  return (
    <aside className="hidden w-64 shrink-0 flex-col gap-4 lg:flex">
      <button
        onClick={onNew}
        className="brutal-btn bg-ink text-left text-paper hover:bg-ink/90"
      >
        + New chat
      </button>

      <section className="brutal-card flex-1 overflow-auto p-3">
        <h2 className="text-[10px] font-black uppercase tracking-widest text-ink/60">
          Conversations
        </h2>
        {sessions.length === 0 && (
          <p className="mt-3 text-[11px] text-ink/50">
            No conversations yet. Ask your first question →
          </p>
        )}
        <ul className="mt-2 space-y-1.5">
          {sessions.map((s) => (
            <li key={s.id}>
              <button
                onClick={() => onSelect(s.id)}
                className={`w-full border-2 border-ink px-2 py-1.5 text-left text-[11px] font-bold leading-tight ${
                  s.id === activeId ? "bg-accent shadow-brutal-sm" : "bg-paper hover:bg-cream"
                }`}
              >
                <span className="line-clamp-2">{s.title}</span>
                <span className="mt-0.5 block text-[9px] font-normal text-ink/50">
                  {new Date(s.at).toLocaleString()}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </aside>
  );
}
