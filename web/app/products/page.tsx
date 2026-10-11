"use client";

import { BarList, Columns, TrendLine } from "@/components/charts";
import { Card, DataTable, Insight, Loading, PageHeader } from "@/components/ui";
import { DOW, fmt, type Kpi, useApi } from "@/lib/api";

type Res = { rows: Kpi[] };
type Clicks = { rows: { key: string; views: number; order_items?: number; late_pct?: number }[] };

export default function ProductsPage() {
  const cats = useApi<Res>("/api/kpis/category?limit=60&min_orders=1000");
  const depts = useApi<Res>("/api/kpis/department?limit=20");
  const views = useApi<Clicks>("/api/clicks/category?limit=12");
  const hours = useApi<Clicks>("/api/clicks/hour?limit=24");
  const dows = useApi<Clicks>("/api/clicks/dow?limit=7");
  if (!cats.data || !depts.data || !views.data || !hours.data || !dows.data)
    return <Loading error={cats.error || depts.error || views.error} />;

  const c = [...cats.data.rows].sort((a, b) => b.late_pct - a.late_pct);
  const spread = c[0].late_pct - c.at(-1)!.late_pct;
  const hourRows = [...hours.data.rows].sort((a, b) => Number(a.key) - Number(b.key)).map((r) => ({ hour: `${r.key.padStart(2, "0")}h`, views: r.views }));
  const peak = [...hours.data.rows].sort((a, b) => b.views - a.views)[0];
  const totalViews = hours.data.rows.reduce((a, r) => a + r.views, 0);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Products and web traffic"
        lead={
          <>
            Product categories with at least 1,000 order lines range from {fmt.pct(c.at(-1)!.late_pct)} to {fmt.pct(c[0].late_pct)} late
            — a {spread.toFixed(1)}-point spread. What is bought matters far less than how it is shipped. The clickstream jobs processed
            {" "}{fmt.int(totalViews)} product page views from the web access logs.
          </>
        }
        source="Hadoop jobs kpi-item-category, kpi-item-department (180,519 order lines) and clicks-* (access logs, Sep 2017 – Jan 2018)"
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={`${c[0].key} has the highest late rate: ${fmt.pct(c[0].late_pct)}`} subtitle="Late % of order lines by product category (≥ 1,000 lines)">
          <BarList rows={c.map((r) => ({ label: r.key, value: r.late_pct, note: `${fmt.int(r.orders)} order lines` }))} highlight={[c[0].key]} max={65}
            sub={(l) => fmt.compact(c.find((r) => r.key === l)!.orders)} />
        </Card>
        <Card title="Departments" subtitle="Late % of order lines by store department">
          <BarList
            rows={[...depts.data.rows].sort((a, b) => b.late_pct - a.late_pct).map((r) => ({ label: r.key, value: r.late_pct, note: `${fmt.int(r.orders)} lines` }))}
            highlight={[]}
            max={65}
          />
          <div className="mt-4">
            <DataTable
              rows={[...depts.data.rows].sort((a, b) => b.sales - a.sales).slice(0, 6)}
              cols={[
                { key: "key", label: "Department" },
                { key: "orders", label: "Lines", num: true, fmt: (v) => fmt.int(v as number) },
                { key: "sales", label: "Sales", num: true, fmt: (v) => fmt.money(v as number) },
                { key: "profit", label: "Profit", num: true, fmt: (v) => fmt.money(v as number) },
              ]}
            />
          </div>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={`Traffic peaks at ${peak.key.padStart(2, "0")}:00`} subtitle="Product page views by hour of day (clickstream MapReduce job)">
          <TrendLine data={hourRows} x="hour" series={[{ key: "views", name: "Page views" }]} digits={0} />
        </Card>
        <Card title="Page views by weekday" subtitle="Views per day of week">
          <Columns
            data={[...dows.data.rows].sort((a, b) => Number(a.key) - Number(b.key)).map((r) => ({ day: DOW[Number(r.key)], views: r.views }))}
            x="day"
            y="views"
            name="Page views"
            digits={0}
            colorOf={() => "var(--gray-mark)"}
          />
        </Card>
      </div>

      <Card title="Most viewed categories vs what was ordered" subtitle="Page views (access logs) joined with order lines and late % (orders) by category name">
        <DataTable
          rows={views.data.rows}
          cols={[
            { key: "key", label: "Category" },
            { key: "views", label: "Page views", num: true, fmt: (v) => fmt.int(v as number) },
            { key: "order_items", label: "Order lines", num: true, fmt: (v) => (v ? fmt.int(v as number) : "–") },
            { key: "late_pct", label: "Late %", num: true, fmt: (v) => (v ? fmt.pct(v as number) : "–") },
          ]}
        />
      </Card>
      <Insight>
        The access logs cover a later period (Sep 2017 – Jan 2018) than most orders, so treat views as a demand signal, not a
        conversion rate.
      </Insight>
    </div>
  );
}
