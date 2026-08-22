"use client";

import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api";

type Overview = {
  total_emails: number;
  total_people: number;
  emails_last_7d: number;
  emails_last_30d: number;
  emails_with_attachments: number;
  top_senders: { email: string; display_name: string | null; sent_count: number }[];
  top_companies: { company: string; email_count: number }[];
};

type Person = {
  email: string;
  display_name: string | null;
  company: string | null;
  sent_count: number;
  received_count: number;
  last_email: string | null;
};

type Insight = {
  id: string;
  type: string;
  title: string;
  description: string;
  severity: string;
};

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="brutal-card p-4">
      <p className="text-2xl font-black">{value}</p>
      <p className="mt-1 text-[10px] font-bold uppercase tracking-widest text-ink/60">{label}</p>
    </div>
  );
}

export default function DashboardPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [series, setSeries] = useState<{ day: string; emails: number }[]>([]);
  const [days, setDays] = useState(30);
  const [people, setPeople] = useState<Person[]>([]);
  const [insights, setInsights] = useState<Insight[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [o, p, ins] = await Promise.all([
          api.dashboardOverview(),
          api.dashboardPeople(),
          api.dashboardInsights(),
        ]);
        setOverview(o as unknown as Overview);
        setPeople(p.people as unknown as Person[]);
        setInsights(ins.insights as unknown as Insight[]);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load dashboard data.");
      }
    })();
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const t = await api.dashboardTrends(days);
        setSeries(t.series.map((r) => ({ ...r, day: String(r.day).slice(0, 10) })));
      } catch {
        /* surfaced by the overview error banner */
      }
    })();
  }, [days]);

  return (
    <div className="space-y-4">
      {error && (
        <div className="brutal-card border-red-600 p-3 text-sm font-bold">
          ⚠ {error} — is the backend (and MCP server + database) running?
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        <StatCard label="Total emails" value={overview?.total_emails ?? "—"} />
        <StatCard label="Active people" value={overview?.total_people ?? "—"} />
        <StatCard label="Last 7 days" value={overview?.emails_last_7d ?? "—"} />
        <StatCard label="Last 30 days" value={overview?.emails_last_30d ?? "—"} />
        <StatCard label="With attachments" value={overview?.emails_with_attachments ?? "—"} />
      </div>

      <section className="brutal-card p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-black uppercase tracking-wide">Email volume</h2>
          <div className="flex gap-1.5">
            {[7, 30, 90].map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`border-2 border-ink px-2 py-1 text-[10px] font-bold ${
                  days === d ? "bg-accent shadow-brutal-sm" : "bg-paper"
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
        </div>
        <div className="mt-3 h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={series} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid stroke="#11111122" strokeDasharray="4 4" />
              <XAxis dataKey="day" stroke="#111" tick={{ fontSize: 10, fontFamily: "monospace" }} />
              <YAxis stroke="#111" tick={{ fontSize: 10, fontFamily: "monospace" }} allowDecimals={false} />
              <Tooltip
                contentStyle={{
                  background: "#FAF8F1",
                  border: "2px solid #111",
                  fontFamily: "monospace",
                  fontSize: 11,
                }}
              />
              <Line type="monotone" dataKey="emails" stroke="#111111" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="brutal-card p-4">
          <h2 className="text-sm font-black uppercase tracking-wide">Insights</h2>
          {insights.length === 0 && (
            <p className="mt-2 text-xs text-ink/50">No significant changes detected.</p>
          )}
          <ul className="mt-3 space-y-2">
            {insights.map((ins) => (
              <li key={ins.id} className="border-2 border-ink bg-cream p-2.5">
                <p className="text-xs font-bold">
                  <span className="tag mr-2 bg-accent">{ins.severity}</span>
                  {ins.title}
                </p>
                <p className="mt-1 text-[11px] text-ink/70">{ins.description}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="brutal-card p-4">
          <h2 className="text-sm font-black uppercase tracking-wide">Top companies</h2>
          <ul className="mt-3 space-y-1.5">
            {(overview?.top_companies ?? []).map((c) => (
              <li
                key={c.company}
                className="flex items-center justify-between border-2 border-ink bg-cream px-2.5 py-1.5 text-xs font-bold"
              >
                {c.company}
                <span>{c.email_count}</span>
              </li>
            ))}
            {!overview?.top_companies?.length && (
              <p className="text-xs text-ink/50">No company data available.</p>
            )}
          </ul>
        </section>
      </div>

      <section className="brutal-card p-4">
        <h2 className="text-sm font-black uppercase tracking-wide">People</h2>
        <p className="mt-0.5 text-[10px] text-ink/50">
          Ranked by emails sent — a transparent metric, not “influence”.
        </p>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full border-2 border-ink text-left text-xs">
            <thead className="bg-ink text-paper">
              <tr>
                <th className="px-2 py-1.5">Email</th>
                <th className="px-2 py-1.5">Name</th>
                <th className="px-2 py-1.5">Company</th>
                <th className="px-2 py-1.5 text-right">Sent</th>
                <th className="px-2 py-1.5 text-right">Received</th>
                <th className="px-2 py-1.5">Last email</th>
              </tr>
            </thead>
            <tbody>
              {people.map((p) => (
                <tr key={p.email} className="border-t-2 border-ink odd:bg-paper even:bg-cream">
                  <td className="px-2 py-1.5 font-bold">{p.email}</td>
                  <td className="px-2 py-1.5">{p.display_name ?? "—"}</td>
                  <td className="px-2 py-1.5">{p.company ?? "—"}</td>
                  <td className="px-2 py-1.5 text-right">{p.sent_count}</td>
                  <td className="px-2 py-1.5 text-right">{p.received_count}</td>
                  <td className="px-2 py-1.5">
                    {p.last_email ? String(p.last_email).slice(0, 10) : "—"}
                  </td>
                </tr>
              ))}
              {people.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-2 py-3 text-center text-ink/50">
                    No data yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
