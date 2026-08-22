"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const TOOLS = [
  "get_schema",
  "query_database",
  "search_emails",
  "get_distinct_values",
  "get_email",
];

export default function SidePanel() {
  const [connected, setConnected] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    async function check() {
      try {
        const h = await api.health();
        if (alive) setConnected(h.mcp_connected);
      } catch {
        if (alive) setConnected(false);
      }
    }
    check();
    const t = setInterval(check, 20000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const dot =
    connected === null ? "bg-ink/30" : connected ? "bg-green-500" : "bg-red-500";
  const label =
    connected === null ? "checking…" : connected ? "online" : "data service offline";

  return (
    <aside className="hidden w-72 shrink-0 flex-col gap-4 xl:flex">
      <section className="brutal-card p-4">
        <h2 className="text-sm font-black uppercase tracking-wide">Agent info</h2>
        <div className="mt-3 flex items-center gap-3">
          <span className="flex h-12 w-12 items-center justify-center border-2 border-ink bg-accent text-xl shadow-brutal-sm">
            ⚙
          </span>
          <div>
            <p className="text-xs font-bold">Company Intelligence Agent</p>
            <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase">
              <span className={`inline-block h-2 w-2 rounded-full ${dot}`} />
              {label}
            </p>
          </div>
        </div>
        <p className="mt-3 text-[11px] leading-relaxed text-ink/70">
          Answers questions about company email data. Every database operation
          requires your explicit approval before it runs. Read-only — the
          agent cannot modify anything.
        </p>
      </section>

      <section className="brutal-card p-4">
        <h2 className="text-sm font-black uppercase tracking-wide">Tools</h2>
        <ul className="mt-3 space-y-2">
          {TOOLS.map((t) => (
            <li
              key={t}
              className="flex items-center justify-between border-2 border-ink bg-cream px-2 py-1.5 text-[11px] font-bold"
            >
              {t}
              <span className="flex items-center gap-1 text-[9px] uppercase">
                <span className={`inline-block h-1.5 w-1.5 rounded-full ${dot}`} />
                {connected ? "active" : "…"}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="brutal-card p-4">
        <h2 className="text-sm font-black uppercase tracking-wide">💡 Tip</h2>
        <p className="mt-2 text-[11px] leading-relaxed text-ink/70">
          Ask follow-up questions to dive deeper — the agent remembers the
          conversation. Use “View generated SQL” on any plan to see exactly
          what will run.
        </p>
      </section>
    </aside>
  );
}
