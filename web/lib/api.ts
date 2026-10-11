"use client";

import { useEffect, useState } from "react";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Kpi = {
  key: string;
  orders: number;
  late: number;
  on_time: number;
  advance: number;
  canceled: number;
  late_pct: number;
  on_time_pct: number;
  canceled_pct: number;
  avg_delay_days: number;
  avg_delay_when_late: number;
  avg_real_days: number;
  avg_scheduled_days: number;
  sales: number;
  profit: number;
  dimension?: string;
};

export function useApi<T>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (!path) return;
    let alive = true;
    setLoading(true);
    fetch(`${API}${path}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
        return r.json();
      })
      .then((d) => alive && (setData(d), setError(null)))
      .catch((e) => alive && setError(String(e.message ?? e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);
  return { data, error, loading };
}

// round half-up before toFixed so 57.55 prints as 57.6 (binary floats would print 57.5)
const r = (n: number, d: number) => (Math.round(n * 10 ** d + 1e-9) / 10 ** d).toFixed(d);

export const fmt = {
  int: (n: number) => Math.round(n).toLocaleString("en-US"),
  pct: (n: number, d = 1) => `${r(n, d)}%`,
  days: (n: number) => `${n > 0 ? "+" : ""}${r(n, 2)} d`,
  money: (n: number) =>
    n >= 1e6 ? `$${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `$${(n / 1e3).toFixed(1)}K` : `$${n.toFixed(0)}`,
  compact: (n: number) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}K` : `${n}`),
};

export const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
