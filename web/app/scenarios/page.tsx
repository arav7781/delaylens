"use client";

import { useEffect, useState } from "react";
import { BarList } from "@/components/charts";
import { Card, DataTable, Insight, Loading, PageHeader, StatTile } from "@/components/ui";
import { API, fmt, useApi } from "@/lib/api";

type Scenario = { scenario: string; policy: string; late_orders: number; late_pct: number; by_mode: Record<string, { late_pct: number; avg_promised_days: number }> };
type Sim = {
  late_pct_now: number;
  late_pct_policy: number;
  late_orders_avoided: number;
  ms: number;
  by_mode: { mode: string; orders: number; late_pct_now: number; late_pct_policy: number }[];
};

const MODES = ["First Class", "Second Class", "Same Day", "Standard Class"];

function NumberField({ label, value, onChange, min = 0, max = 10 }: { label: string; value: number; onChange: (v: number) => void; min?: number; max?: number }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-ink-2">
      {label}
      <input type="number" min={min} max={max} value={value} onChange={(e) => onChange(Number(e.target.value))}
        className="w-full rounded-md border border-border bg-page px-2 py-1.5 text-sm text-ink tnum" />
    </label>
  );
}

export default function ScenariosPage() {
  const sc = useApi<{ scenarios: Scenario[]; source: string }>("/api/scenarios");
  const [p, setP] = useState({ first_class_days: 2, second_class_days: 4, standard_class_days: 4, same_day_days: 0, same_day_cutoff_hour: 12 as number | null });
  const [sim, setSim] = useState<Sim | null>(null);
  useEffect(() => {
    const t = setTimeout(() => {
      fetch(`${API}/api/simulate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p) })
        .then((r) => r.json())
        .then(setSim)
        .catch(() => setSim(null));
    }, 250);
    return () => clearTimeout(t);
  }, [p]);
  if (!sc.data) return <Loading error={sc.error} />;
  const s = sc.data.scenarios;
  const best = [...s].sort((a, b) => a.late_pct - b.late_pct)[0];
  const base = s.find((x) => x.scenario.startsWith("S0"))!;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Delivery-promise what-if"
        lead={
          <>
            Re-scoring all 65,752 orders against better-calibrated promises lowers the late rate from {fmt.pct(base.late_pct)} to{" "}
            {fmt.pct(best.late_pct)} ({fmt.int(base.late_orders - best.late_orders)} fewer late orders), without shipping anything faster.
            Actual shipping days stay as recorded; only the promised days change.
          </>
        }
        source="Precomputed: Hadoop MapReduce SLA scenario jobs (kpi_mapper with SLA/CUTOFF). Interactive: MongoDB aggregation."
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={`Cumulative policies take the late rate to ${fmt.pct(best.late_pct)}`} subtitle="Late % after each change (each step includes the ones above it)">
          <BarList rows={s.map((x) => ({ label: x.policy, value: x.late_pct, note: `${fmt.int(x.late_orders)} late orders` }))} highlight={[best.policy]} max={60} />
        </Card>
        <Card title="Late % by mode under each policy" subtitle="Hadoop scenario outputs">
          <DataTable
            rows={s.map((x) => ({ policy: x.scenario.replace(/_/g, " "), ...Object.fromEntries(MODES.map((m) => [m, x.by_mode[m]?.late_pct])) }))}
            cols={[{ key: "policy", label: "Scenario" }, ...MODES.map((m) => ({ key: m, label: m, num: true, fmt: (v: unknown) => fmt.pct(v as number, 1) }))]}
          />
        </Card>
      </div>

      <Card title="Try your own promise policy" subtitle="Promised days per shipping mode, and an optional Same Day order cutoff. Recomputed live over every order in MongoDB.">
        <div className="grid gap-5 lg:grid-cols-[1fr_1.4fr]">
          <div className="grid grid-cols-2 gap-3">
            <NumberField label="First Class promise (days)" value={p.first_class_days} onChange={(v) => setP({ ...p, first_class_days: v })} />
            <NumberField label="Second Class promise (days)" value={p.second_class_days} onChange={(v) => setP({ ...p, second_class_days: v })} />
            <NumberField label="Standard Class promise (days)" value={p.standard_class_days} onChange={(v) => setP({ ...p, standard_class_days: v })} />
            <NumberField label="Same Day promise (days)" value={p.same_day_days} onChange={(v) => setP({ ...p, same_day_days: v })} />
            <label className="col-span-2 flex items-center gap-2 text-xs text-ink-2">
              <input type="checkbox" checked={p.same_day_cutoff_hour !== null} onChange={(e) => setP({ ...p, same_day_cutoff_hour: e.target.checked ? 12 : null })} />
              Same Day cutoff: orders at/after
              <input type="number" min={0} max={23} disabled={p.same_day_cutoff_hour === null} value={p.same_day_cutoff_hour ?? 12}
                onChange={(e) => setP({ ...p, same_day_cutoff_hour: Number(e.target.value) })}
                className="w-16 rounded-md border border-border bg-page px-2 py-1 text-sm text-ink" />
              :00 are promised next day
            </label>
          </div>
          {sim ? (
            <div className="flex flex-col gap-3">
              <div className="grid grid-cols-3 gap-3">
                <StatTile label="Late rate today" value={fmt.pct(sim.late_pct_now)} />
                <StatTile label="Late rate with policy" value={fmt.pct(sim.late_pct_policy)} />
                <StatTile label="Late orders avoided" value={fmt.int(sim.late_orders_avoided)} note={`computed in ${sim.ms} ms`} />
              </div>
              <DataTable
                rows={sim.by_mode}
                cols={[
                  { key: "mode", label: "Mode" },
                  { key: "orders", label: "Orders", num: true, fmt: (v) => fmt.int(v as number) },
                  { key: "late_pct_now", label: "Late % today", num: true, fmt: (v) => fmt.pct(v as number) },
                  { key: "late_pct_policy", label: "Late % with policy", num: true, fmt: (v) => fmt.pct(v as number) },
                ]}
              />
            </div>
          ) : (
            <div className="text-sm text-muted">Computing…</div>
          )}
        </div>
      </Card>

      <Insight>
        Trade-off: a longer promise is easier to keep but can lower conversion at checkout. The two cheapest fixes are a 2-day First
        Class promise (it always arrives in 2) and a 12:00 Same Day cutoff. Neither makes the promise worse than what customers
        already get.
      </Insight>
    </div>
  );
}
