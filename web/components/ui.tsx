"use client";

import type { ReactNode } from "react";

export function PageHeader({ title, lead, source }: { title: string; lead?: ReactNode; source?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
      {lead && <p className="mt-1 max-w-3xl text-sm text-ink-2">{lead}</p>}
      {source && <p className="mt-1 text-xs text-muted">{source}</p>}
    </div>
  );
}

export function Card({
  title, subtitle, children, className = "", right,
}: { title?: string; subtitle?: ReactNode; children: ReactNode; className?: string; right?: ReactNode }) {
  return (
    <section className={`card p-4 md:p-5 ${className}`}>
      {(title || right) && (
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-sm font-semibold">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-ink-2">{subtitle}</p>}
          </div>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function StatTile({ label, value, note, tone }: { label: string; value: string; note?: ReactNode; tone?: "bad" | "good" }) {
  return (
    <div className="card p-4">
      <div className="text-xs text-ink-2">{label}</div>
      <div className="mt-1 text-2xl font-semibold" style={tone === "bad" ? { color: "var(--critical)" } : undefined}>
        {value}
      </div>
      {note && <div className="mt-1 text-xs text-muted">{note}</div>}
    </div>
  );
}

export function Hero({ label, value, note }: { label: string; value: string; note: ReactNode }) {
  return (
    <div className="card p-5">
      <div className="text-xs text-ink-2">{label}</div>
      <div className="mt-1 text-5xl font-semibold tracking-tight">{value}</div>
      <div className="mt-2 text-sm text-ink-2">{note}</div>
    </div>
  );
}

export function Loading({ error }: { error?: string | null }) {
  if (error)
    return (
      <div className="card p-6 text-sm" style={{ color: "var(--critical)" }}>
        Could not load data: {error}. Is the API running on port 8000?
      </div>
    );
  return <div className="card p-6 text-sm text-muted">Loading…</div>;
}

export function DataTable<T extends Record<string, unknown>>({
  rows, cols, max = 200,
}: {
  rows: T[];
  cols: { key: string; label: string; fmt?: (v: unknown, r: T) => ReactNode; num?: boolean }[];
  max?: number;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-grid text-left text-xs text-ink-2">
            {cols.map((c) => (
              <th key={c.key} className={`px-2 py-2 font-medium ${c.num ? "text-right" : ""}`}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="tnum">
          {rows.slice(0, max).map((r, i) => (
            <tr key={i} className="border-b border-grid last:border-0">
              {cols.map((c) => (
                <td key={c.key} className={`px-2 py-1.5 ${c.num ? "text-right" : ""}`}>
                  {c.fmt ? c.fmt(r[c.key], r) : String(r[c.key] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Insight({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border-l-2 px-3 py-2 text-sm text-ink-2" style={{ borderColor: "var(--accent)", background: "var(--accent-wash)" }}>
      {children}
    </div>
  );
}
