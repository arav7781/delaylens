"use client";

import { useState } from "react";
import { BarList } from "@/components/charts";
import { Card, DataTable, Loading, PageHeader, StatTile } from "@/components/ui";
import { fmt, useApi } from "@/lib/api";

type Options = { regions: string[]; markets: string[]; shipping_modes: string[] };
type AtRisk = {
  matching_open_orders: number;
  matching_sales: number;
  expected_late_orders: number;
  top: { order_id: number; date: string; status: string; mode: string; region: string; country: string; category: string; sales: number; segment_late_pct: number }[];
};
type Overview = { open_orders_by_mode: { _id: string; orders: number; sales: number; expected_late: number }[] };

function Select({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (v: string) => void }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-ink-2">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)} className="rounded-md border border-border bg-surface px-2 py-1.5 text-sm text-ink">
        <option value="">All</option>
        {options.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </label>
  );
}

export default function OrdersPage() {
  const opts = useApi<Options>("/api/options");
  const ov = useApi<Overview>("/api/overview");
  const [f, setF] = useState({ region: "", market: "", shipping_mode: "", min: 75 });
  const qs = new URLSearchParams({ min_segment_late_pct: String(f.min), limit: "50" });
  if (f.region) qs.set("region", f.region);
  if (f.market) qs.set("market", f.market);
  if (f.shipping_mode) qs.set("shipping_mode", f.shipping_mode);
  const risk = useApi<AtRisk>(`/api/orders/at-risk?${qs}`);
  if (!opts.data || !ov.data) return <Loading error={opts.error || ov.error} />;
  const byMode = [...ov.data.open_orders_by_mode].sort((a, b) => b.expected_late - a.expected_late);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Open orders likely to ship late"
        lead={
          <>
            Open orders (pending, processing, on hold, payment review) are scored with the historical late rate of their region ×
            shipping-mode segment from the Hadoop KPIs. Customer-service teams can contact these customers before the
            promised date passes.
          </>
        }
        source="MongoDB orders collection · segment_late_pct from Hadoop job kpi-order-region_mode · no machine learning involved"
      />

      <div className="flex flex-wrap items-end gap-3">
        <Select label="Region" value={f.region} options={opts.data.regions} onChange={(v) => setF({ ...f, region: v })} />
        <Select label="Market" value={f.market} options={opts.data.markets} onChange={(v) => setF({ ...f, market: v })} />
        <Select label="Shipping mode" value={f.shipping_mode} options={opts.data.shipping_modes} onChange={(v) => setF({ ...f, shipping_mode: v })} />
        <label className="flex flex-col gap-1 text-xs text-ink-2">
          Segment late % at least
          <input type="number" min={0} max={100} value={f.min} onChange={(e) => setF({ ...f, min: Number(e.target.value) })}
            className="w-28 rounded-md border border-border bg-surface px-2 py-1.5 text-sm text-ink" />
        </label>
      </div>

      <div className={`grid grid-cols-1 gap-4 md:grid-cols-3 ${risk.loading ? "opacity-60" : ""}`}>
        <StatTile label="Matching open orders" value={risk.data ? fmt.int(risk.data.matching_open_orders) : "…"} />
        <StatTile label="Sales at stake" value={risk.data ? fmt.money(risk.data.matching_sales) : "…"} />
        <StatTile label="Expected to arrive late" value={risk.data ? fmt.int(risk.data.expected_late_orders) : "…"} note="sum of segment late rates" tone="bad" />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_2fr]">
        <Card title="Expected late open orders by mode" subtitle="All open orders, before filters">
          <BarList rows={byMode.map((r) => ({ label: r._id, value: r.expected_late, note: `${fmt.int(r.orders)} open orders` }))} unit="" digits={0}
            highlight={[byMode[0]._id]} sub={(l) => `of ${fmt.int(byMode.find((r) => r._id === l)!.orders)}`} />
        </Card>
        <Card title="Orders to act on first" subtitle="Highest segment late rate, then highest sales">
          {risk.data ? (
            <DataTable
              rows={risk.data.top}
              cols={[
                { key: "order_id", label: "Order" },
                { key: "date", label: "Placed" },
                { key: "status", label: "Status" },
                { key: "mode", label: "Mode" },
                { key: "region", label: "Region" },
                { key: "category", label: "Category" },
                { key: "sales", label: "Sales", num: true, fmt: (v) => fmt.money(v as number) },
                { key: "segment_late_pct", label: "Segment late %", num: true, fmt: (v) => fmt.pct(v as number) },
              ]}
              max={25}
            />
          ) : (
            <Loading error={risk.error} />
          )}
        </Card>
      </div>
    </div>
  );
}
