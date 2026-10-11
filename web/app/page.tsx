"use client";

import { BarList, Columns, OutcomeMix, TrendLine } from "@/components/charts";
import { Card, Hero, Insight, Loading, PageHeader, StatTile } from "@/components/ui";
import { fmt, type Kpi, useApi } from "@/lib/api";

type Scenario = { scenario: string; policy: string; late_orders: number; late_pct: number };
type Overview = {
  kpis: { overall: Kpi; open_orders_in_segments_late_75pct_plus: number };
  month: Kpi[];
  shipping_mode: Kpi[];
  market: Kpi[];
  open_orders_by_mode: { _id: string; orders: number; sales: number; expected_late: number }[];
  scenarios: Scenario[];
};

export default function OverviewPage() {
  const { data, error } = useApi<Overview>("/api/overview");
  if (!data) return <Loading error={error} />;
  const o = data.kpis.overall;
  const worstMode = [...data.shipping_mode].sort((a, b) => b.late_pct - a.late_pct)[0];
  const marketSpread = data.market.map((m) => m.late_pct);
  const months = data.month;
  const best = [...data.scenarios].sort((a, b) => a.late_pct - b.late_pct)[0];
  const openSales = data.open_orders_by_mode.reduce((a, r) => a + r.sales, 0);
  const openExpLate = data.open_orders_by_mode.reduce((a, r) => a + r.expected_late, 0);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Delivery performance at a glance"
        lead={
          <>
            {fmt.pct(o.late_pct)} of {fmt.int(o.orders)} DataCo orders (Jan 2015 – Jan 2018) shipped late. Lateness is
            driven by the promise attached to each shipping mode — {worstMode.key} is late {fmt.pct(worstMode.late_pct)} of
            the time — while markets differ by less than {(Math.max(...marketSpread) - Math.min(...marketSpread)).toFixed(1)} points.
          </>
        }
        source="All KPIs on this page were computed by Hadoop MapReduce jobs on HDFS and served from MongoDB."
      />

      <div className="grid gap-4 lg:grid-cols-[1.2fr_2fr]">
        <Hero label="Late-delivery rate" value={fmt.pct(o.late_pct)} note={<>{fmt.int(o.late)} of {fmt.int(o.orders)} orders arrived after the promised date</>} />
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
          <StatTile label="On time or early" value={fmt.pct(o.on_time_pct)} note={`${fmt.int(o.on_time + o.advance)} orders`} />
          <StatTile label="Shipping canceled" value={fmt.pct(o.canceled_pct)} note={`${fmt.int(o.canceled)} orders`} />
          <StatTile label="Average delay when late" value={`${o.avg_delay_when_late.toFixed(2)} days`} note={`avg actual ${o.avg_real_days.toFixed(2)} vs promised ${o.avg_scheduled_days.toFixed(2)} days`} />
          <StatTile label="Sales value" value={fmt.money(o.sales)} note="all order items" />
          <StatTile label="Open orders" value={fmt.int(data.open_orders_by_mode.reduce((a, r) => a + r.orders, 0))} note={`${fmt.money(openSales)} not yet shipped`} />
          <StatTile label="Open orders likely late" value={fmt.int(openExpLate)} note="expected, from segment late rates" tone="bad" />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={`${worstMode.key} misses its promise ${fmt.pct(worstMode.late_pct, 0)} of the time`} subtitle="Late-delivery rate by shipping mode · Hadoop job kpi-order-shipping_mode">
          <BarList
            rows={[...data.shipping_mode].sort((a, b) => b.late_pct - a.late_pct).map((m) => ({ label: m.key, value: m.late_pct, note: `${fmt.int(m.orders)} orders` }))}
            highlight={[worstMode.key]}
            reference={o.late_pct}
            referenceLabel="all orders"
            sub={(l) => {
              const m = data.shipping_mode.find((x) => x.key === l)!;
              return `promised ${m.avg_scheduled_days.toFixed(0)}d · actual ${m.avg_real_days.toFixed(1)}d`;
            }}
          />
        </Card>
        <Card title="Outcome mix: no First Class order arrives on time" subtitle="Share of orders by delivery status, per shipping mode">
          <OutcomeMix rows={data.shipping_mode.map((m) => ({ label: m.key, late: m.late, on_time: m.on_time, advance: m.advance, canceled: m.canceled }))} />
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="The late rate has been flat for three years" subtitle={`Monthly late-delivery rate, ${months[0]?.key} to ${months.at(-1)?.key}`}>
          <TrendLine data={months} x="key" series={[{ key: "late_pct", name: "Late %" }]} unit="%" yDomain={[40, 65]} yTicks={[40, 45, 50, 55, 60, 65]} refY={o.late_pct} refLabel={`overall ${o.late_pct.toFixed(1)}%`} />
        </Card>
        <Card title="Order volume per month" subtitle="Orders placed per month (same period)">
          <Columns data={months} x="key" y="orders" name="Orders" digits={0} colorOf={() => "var(--gray-mark)"} />
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Every market sits within two points of the average" subtitle="Late-delivery rate by market · Hadoop job kpi-order-market">
          <BarList
            rows={[...data.market].sort((a, b) => b.late_pct - a.late_pct).map((m) => ({ label: m.key, value: m.late_pct, note: `${fmt.int(m.orders)} orders` }))}
            highlight={[]}
            reference={o.late_pct}
            referenceLabel="all orders"
            max={70}
          />
        </Card>
        <Card title={`Fixing the promises could cut the late rate to ${fmt.pct(best.late_pct)}`} subtitle="Late % under cumulative promise policies · Hadoop SLA scenario jobs">
          <BarList rows={data.scenarios.map((s) => ({ label: s.policy, value: s.late_pct, note: `${fmt.int(s.late_orders)} late orders` }))} highlight={[best.policy]} max={60} />
        </Card>
      </div>

      <Insight>
        <b>Reading the numbers.</b> Actual shipping time depends on the mode (First Class always takes 2 days, Second and
        Standard take 2–6 days), but the promise does not match it. Region, customer segment and product category barely
        move the late rate. The fix is mostly about setting promises, not about geography. Use the copilot (bottom right)
        to drill into any slice.
      </Insight>
    </div>
  );
}
