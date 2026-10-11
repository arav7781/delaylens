"use client";

import { BarList, Heatmap } from "@/components/charts";
import { Card, DataTable, Insight, Loading, PageHeader } from "@/components/ui";
import { fmt, type Kpi, useApi } from "@/lib/api";

type Res = { rows: Kpi[] };
const MODES = ["First Class", "Second Class", "Same Day", "Standard Class"];

export default function RegionsPage() {
  const regions = useApi<Res>("/api/kpis/region?limit=60");
  const pairs = useApi<Res>("/api/kpis/region_mode?limit=120&sort_by=key&descending=false");
  const countries = useApi<Res>("/api/kpis/country?limit=25&min_orders=500");
  const overall = useApi<Res>("/api/kpis/all");
  if (!regions.data || !pairs.data || !countries.data || !overall.data)
    return <Loading error={regions.error || pairs.error || countries.error} />;

  const avg = overall.data.rows[0].late_pct;
  const rows = [...regions.data.rows].sort((a, b) => b.late_pct - a.late_pct);
  const worst3 = rows.slice(0, 3).map((r) => r.key);
  const cell = new Map(pairs.data.rows.map((r) => [r.key, r]));
  const regionOrder = rows.map((r) => r.key);
  const stdOnly = MODES.map((m) => {
    const vals = regionOrder.map((r) => cell.get(`${r}|${m}`)).filter((k) => k && k.orders >= 100).map((k) => k!.late_pct);
    return { mode: m, min: Math.min(...vals), max: Math.max(...vals) };
  });

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Regions and markets"
        lead={
          <>
            The worst region, {rows[0].key}, is late {fmt.pct(rows[0].late_pct)} of the time and the best, {rows.at(-1)!.key}, {fmt.pct(rows.at(-1)!.late_pct)} —
            a {(rows[0].late_pct - rows.at(-1)!.late_pct).toFixed(1)}-point spread around the {fmt.pct(avg)} average. Within a
            shipping mode the regions look alike, so geography is not what makes orders late.
          </>
        }
        source="Hadoop jobs kpi-order-region (23 groups), kpi-order-region_mode (92 groups), kpi-order-country (164 groups)"
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_1.25fr]">
        <Card title={`${rows[0].key} has the highest late rate: ${fmt.pct(rows[0].late_pct)}`} subtitle="Late-delivery rate by order region, all 65,752 orders">
          <BarList
            rows={rows.map((r) => ({ label: r.key, value: r.late_pct, note: `${fmt.int(r.orders)} orders` }))}
            highlight={worst3}
            reference={avg}
            referenceLabel="all orders"
            max={65}
            sub={(l) => `${fmt.compact(rows.find((r) => r.key === l)!.orders)}`}
          />
        </Card>
        <Card title="Inside each shipping mode, regions barely differ" subtitle="Late % by region (rows) and shipping mode (columns) · hover for order counts">
          <Heatmap
            rows={regionOrder}
            cols={MODES}
            value={(r, c) => {
              const k = cell.get(`${r}|${c}`);
              return k ? { v: k.late_pct, n: k.orders } : undefined;
            }}
            rowLabel="Region"
            colLabel="Mode"
            min={30}
            max={100}
            note="small cells (< 100 orders) are noisy"
          />
        </Card>
      </div>

      <Insight>
        Range of late % across the regions (cells with ≥ 100 orders), per mode:{" "}
        {stdOnly.map((s) => `${s.mode} ${s.min.toFixed(0)}–${s.max.toFixed(0)}%`).join(" · ")}. First Class is late
        everywhere; the regional differences in the left chart mostly reflect each region&apos;s mix of shipping modes.
      </Insight>

      <Card title="Largest destination countries" subtitle="Countries with at least 500 orders, sorted by late rate">
        <DataTable
          rows={[...countries.data.rows].sort((a, b) => b.late_pct - a.late_pct)}
          cols={[
            { key: "key", label: "Country" },
            { key: "orders", label: "Orders", num: true, fmt: (v) => fmt.int(v as number) },
            { key: "late_pct", label: "Late %", num: true, fmt: (v) => fmt.pct(v as number) },
            { key: "on_time_pct", label: "On time / early %", num: true, fmt: (v) => fmt.pct(v as number) },
            { key: "canceled_pct", label: "Canceled %", num: true, fmt: (v) => fmt.pct(v as number) },
            { key: "avg_delay_days", label: "Avg delay", num: true, fmt: (v) => fmt.days(v as number) },
            { key: "sales", label: "Sales", num: true, fmt: (v) => fmt.money(v as number) },
          ]}
        />
      </Card>
    </div>
  );
}
