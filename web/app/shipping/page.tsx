"use client";

import { Columns, Heatmap, OutcomeMix } from "@/components/charts";
import { Card, DataTable, Insight, Loading, PageHeader } from "@/components/ui";
import { API, fmt, type Kpi, useApi } from "@/lib/api";
import { useEffect, useState } from "react";

type Res = { rows: Kpi[] };
type QRow = { group: number; orders: number; late_pct: number };
const MODES = ["First Class", "Second Class", "Same Day", "Standard Class"];

export default function ShippingPage() {
  const modes = useApi<Res>("/api/kpis/shipping_mode");
  const marketMode = useApi<Res>("/api/kpis/market_mode?limit=40");
  const [sameDay, setSameDay] = useState<QRow[] | null>(null);
  useEffect(() => {
    fetch(`${API}/api/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filters: { shipping_mode: "Same Day", delivery_status: ["Late delivery", "Shipping on time", "Advance shipping"] }, group_by: "hour", limit: 30 }),
    })
      .then((r) => r.json())
      .then((d) => setSameDay(d.rows))
      .catch(() => setSameDay([]));
  }, []);
  if (!modes.data || !marketMode.data) return <Loading error={modes.error || marketMode.error} />;

  const rows = MODES.map((m) => modes.data!.rows.find((r) => r.key === m)!).filter(Boolean);
  const cell = new Map(marketMode.data.rows.map((r) => [r.key, r]));
  const markets = [...new Set(marketMode.data.rows.map((r) => r.key.split("|")[0]))].sort();
  const fc = rows.find((r) => r.key === "First Class")!;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Shipping modes and delivery promises"
        lead={
          <>
            Every First Class order is promised {fc.avg_scheduled_days.toFixed(0)} day and takes {fc.avg_real_days.toFixed(0)}, so all
            {" "}{fmt.int(fc.late)} shipped First Class orders were late. Second Class promises 2 days and averages 4. Same Day orders
            placed after noon arrive the next day.
          </>
        }
        source="Hadoop jobs kpi-order-shipping_mode, kpi-order-market_mode; Same Day hours from a MongoDB aggregation"
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Promised vs actual shipping days" subtitle="Average days per order, by shipping mode">
          <Columns
            data={rows.map((r) => ({ mode: r.key, Promised: r.avg_scheduled_days, Actual: r.avg_real_days }))}
            x="mode"
            unit=" d"
            digits={2}
            series={[
              { key: "Promised", name: "Promised days", color: "var(--gray-mark)" },
              { key: "Actual", name: "Actual days", color: "var(--accent)" },
            ]}
          />
        </Card>
        <Card title="Delivery outcome by shipping mode" subtitle="Share of orders: late, on time, early, canceled">
          <OutcomeMix rows={rows.map((m) => ({ label: m.key, late: m.late, on_time: m.on_time, advance: m.advance, canceled: m.canceled }))} />
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Same Day: orders after 12:00 are always late" subtitle="Late % of shipped Same Day orders by hour the order was placed">
          {sameDay ? (
            <Columns
              data={sameDay.map((r) => ({ hour: `${String(r.group).padStart(2, "0")}h`, late: r.late_pct, n: r.orders }))}
              x="hour"
              y="late"
              name="Late %"
              unit="%"
              colorOf={(r) => ((r.late as number) > 50 ? "var(--accent)" : "var(--gray-mark)")}
            />
          ) : (
            <div className="text-sm text-muted">Loading…</div>
          )}
        </Card>
        <Card title="The same pattern holds in every market" subtitle="Late % by market (rows) and shipping mode (columns)">
          <Heatmap
            rows={markets}
            cols={MODES}
            value={(r, c) => {
              const k = cell.get(`${r}|${c}`);
              return k ? { v: k.late_pct, n: k.orders } : undefined;
            }}
            rowLabel="Market"
            colLabel="Mode"
            min={30}
            max={100}
          />
        </Card>
      </div>

      <Insight>
        Promise calibration: First Class should promise 2 days (it always delivers in 2), Second Class 4 days (its median), and
        Same Day needs a 12:00 order cutoff. See <a className="underline" href="/scenarios">Promise what-if</a> for the effect of each change.
      </Insight>

      <Card title="Shipping-mode KPI table" subtitle="All orders, including canceled shipments">
        <DataTable
          rows={rows}
          cols={[
            { key: "key", label: "Mode" },
            { key: "orders", label: "Orders", num: true, fmt: (v) => fmt.int(v as number) },
            { key: "late_pct", label: "Late %", num: true, fmt: (v) => fmt.pct(v as number) },
            { key: "on_time_pct", label: "On time / early %", num: true, fmt: (v) => fmt.pct(v as number) },
            { key: "canceled_pct", label: "Canceled %", num: true, fmt: (v) => fmt.pct(v as number) },
            { key: "avg_scheduled_days", label: "Promised d", num: true, fmt: (v) => (v as number).toFixed(2) },
            { key: "avg_real_days", label: "Actual d", num: true, fmt: (v) => (v as number).toFixed(2) },
            { key: "avg_delay_when_late", label: "Delay when late", num: true, fmt: (v) => fmt.days(v as number) },
            { key: "sales", label: "Sales", num: true, fmt: (v) => fmt.money(v as number) },
          ]}
        />
      </Card>
    </div>
  );
}
