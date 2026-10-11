"use client";

import { TrendLine } from "@/components/charts";
import { Card, DataTable, Insight, Loading, PageHeader, StatTile } from "@/components/ui";
import { fmt, useApi } from "@/lib/api";

type Job = { name: string; engine: string; seconds: number; level?: string; dim?: string; groups?: number; counters: Record<string, number | string> };
type Bench = { rows: { scale: number; rows: number; mb: number; map_tasks: number; streaming_s: number; java_s: number; pandas_s: number; streaming_shuffle_bytes: number; no_combiner_shuffle_bytes?: number; no_combiner_s?: number }[]; job: string; cluster: string };
type Pipeline = {
  cluster: Record<string, string | number>;
  benchmark: Bench | null;
  jobs: Job[];
  profile: { raw_profile: { rows: number; columns: number; unique_orders: number; missing_pct: Record<string, number>; exact_duplicate_rows: number; date_min: string; date_max: string }; cleaning_steps: string[]; access_logs: { raw_rows: number; clean_rows: number; duplicates_removed: number } };
  mongo_load: { collections: Record<string, number>; data_size_mb: number; storage_size_mb: number; index_size_mb: number };
  mongo_queries: Record<string, { shell: string; ms: number }>;
};

const STAGES = [
  { t: "DataCo dataset", d: "Mendeley Data · 180,519 order lines (53 cols) + 469,977 access-log lines" },
  { t: "Python cleaning", d: "pandas: dedupe, missing values, ISO dates, English country names, delay label check" },
  { t: "HDFS", d: "16 MB blocks · replication 1 · orders + clickstream TSV" },
  { t: "MapReduce on YARN", d: "Job A order roll-up → 30+ KPI, clickstream and SLA-scenario jobs · combiners · Java job" },
  { t: "MongoDB", d: "orders (embedded items), kpis, scenarios, clickstream, hadoop_jobs · indexes" },
  { t: "LangGraph agent + API", d: "FastAPI · planner → tools → analyst · live MapReduce tool" },
  { t: "Next.js dashboard", d: "KPI pages · promise what-if · copilot chat" },
];

export default function PipelinePage() {
  const { data, error } = useApi<Pipeline>("/api/pipeline");
  if (!data) return <Loading error={error} />;
  const jobs = [...data.jobs].sort((a, b) => a.name.localeCompare(b.name));
  const totalIn = jobs.reduce((a, j) => a + Number(j.counters["Map input records"] ?? 0), 0);
  const b = data.benchmark;
  const one = b?.rows.find((r) => r.scale === 1);
  const eight = b?.rows.find((r) => r.scale === 8);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Big Data pipeline"
        lead={<>A single-node Hadoop 3.5.0 cluster (HDFS + YARN) runs {jobs.length} MapReduce jobs over the cleaned DataCo data; results land in MongoDB, which feeds this dashboard and the LangGraph copilot.</>}
        source="Hadoop job counters are parsed from each job's output; timings are wall-clock on an Apple-silicon laptop."
      />

      <Card title="Architecture" subtitle="Data flows left to right; the copilot can also submit new MapReduce jobs back to YARN">
        <ol className="grid gap-2 md:grid-cols-7">
          {STAGES.map((s, i) => (
            <li key={s.t} className="relative rounded-lg border border-border p-3" style={i === 3 ? { borderColor: "var(--accent)", background: "var(--accent-wash)" } : undefined}>
              <div className="text-[11px] text-muted">{i + 1}</div>
              <div className="text-sm font-semibold">{s.t}</div>
              <div className="mt-1 text-[11px] leading-snug text-ink-2">{s.d}</div>
            </li>
          ))}
        </ol>
      </Card>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatTile label="Raw order lines" value={fmt.int(data.profile.raw_profile.rows)} note={`${data.profile.raw_profile.columns} columns · ${fmt.int(data.profile.raw_profile.unique_orders)} orders`} />
        <StatTile label="MapReduce jobs" value={String(jobs.length)} note={`${fmt.compact(totalIn)} records read in total`} />
        <StatTile label="HDFS block size" value={`${data.cluster.hdfs_block_size_mb} MB`} note={`YARN ${data.cluster.yarn_memory_mb} MB · ${data.cluster.yarn_vcores} vcores`} />
        <StatTile label="MongoDB documents" value={fmt.int(Object.values(data.mongo_load.collections).reduce((a, n) => a + n, 0))} note={`${data.mongo_load.data_size_mb} MB data · ${data.mongo_load.index_size_mb} MB indexes`} />
      </div>

      {b && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Scalability: run time vs data volume" subtitle={`${b.job}; ${b.cluster}`}>
            <TrendLine
              data={b.rows.map((r) => ({ size: `${r.scale}× (${fmt.compact(r.rows)})`, Streaming: r.streaming_s, Java: r.java_s, pandas: r.pandas_s }))}
              x="size"
              unit=" s"
              series={[
                { key: "Streaming", name: "Hadoop Streaming (Python)", color: "var(--s1)" },
                { key: "Java", name: "Hadoop Java MapReduce", color: "var(--s2)" },
                { key: "pandas", name: "pandas, single process", color: "var(--gray-mark)" },
              ]}
            />
          </Card>
          <Card title="Combiner effect on the shuffle" subtitle="Bytes moved from map to reduce, region KPI job">
            <DataTable
              rows={b.rows.filter((r) => r.no_combiner_shuffle_bytes).map((r) => ({ ...r, ratio: r.no_combiner_shuffle_bytes! / r.streaming_shuffle_bytes }))}
              cols={[
                { key: "scale", label: "Data", fmt: (v) => `${v}×` },
                { key: "rows", label: "Rows", num: true, fmt: (v) => fmt.int(v as number) },
                { key: "no_combiner_shuffle_bytes", label: "Shuffle, no combiner", num: true, fmt: (v) => `${((v as number) / 1e6).toFixed(1)} MB` },
                { key: "streaming_shuffle_bytes", label: "Shuffle, combiner", num: true, fmt: (v) => `${((v as number) / 1e3).toFixed(1)} KB` },
                { key: "no_combiner_s", label: "Time, no combiner", num: true, fmt: (v) => `${(v as number).toFixed(1)} s` },
                { key: "streaming_s", label: "Time, combiner", num: true, fmt: (v) => `${(v as number).toFixed(1)} s` },
              ]}
            />
            {one && eight && (
              <p className="mt-3 text-xs text-ink-2">
                8× the data ({fmt.int(eight.rows)} rows, {eight.mb} MB, {eight.map_tasks} map tasks) took {eight.streaming_s.toFixed(0)} s with
                Streaming vs {one.streaming_s.toFixed(0)} s at 1×: {(eight.streaming_s / one.streaming_s).toFixed(1)}× the time for 8× the data,
                because fixed job start-up cost is amortised and map tasks run in parallel.
              </p>
            )}
          </Card>
        </div>
      )}

      <Card title="MapReduce job log" subtitle="Counters reported by Hadoop for each job in the pipeline run">
        <DataTable
          rows={jobs.map((j) => ({ ...j, ...j.counters }))}
          max={60}
          cols={[
            { key: "name", label: "Job" },
            { key: "engine", label: "Engine" },
            { key: "seconds", label: "Wall s", num: true, fmt: (v) => (v as number).toFixed(1) },
            { key: "Launched map tasks", label: "Maps", num: true },
            { key: "Launched reduce tasks", label: "Reduces", num: true },
            { key: "Map input records", label: "Input recs", num: true, fmt: (v) => (v ? fmt.int(v as number) : "") },
            { key: "Map output records", label: "Map out", num: true, fmt: (v) => (v ? fmt.int(v as number) : "") },
            { key: "Combine output records", label: "Combine out", num: true, fmt: (v) => (v ? fmt.int(v as number) : "–") },
            { key: "Reduce shuffle bytes", label: "Shuffle", num: true, fmt: (v) => (v ? `${((v as number) / 1e3).toFixed(1)} KB` : "") },
            { key: "Reduce output records", label: "Output rows", num: true, fmt: (v) => (v ? fmt.int(v as number) : "") },
          ]}
        />
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Data preparation" subtitle={`${data.profile.raw_profile.date_min.slice(0, 10)} to ${data.profile.raw_profile.date_max.slice(0, 10)}`}>
          <ol className="ml-4 list-decimal space-y-1 text-sm text-ink-2">
            {data.profile.cleaning_steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
            <li>
              Access logs: {fmt.int(data.profile.access_logs.raw_rows)} lines, {fmt.int(data.profile.access_logs.duplicates_removed)} duplicates removed.
            </li>
          </ol>
        </Card>
        <Card title="MongoDB collections and queries" subtitle="Query times measured by mongo/queries.py">
          <DataTable
            rows={Object.entries(data.mongo_load.collections).map(([k, v]) => ({ k, v }))}
            cols={[{ key: "k", label: "Collection" }, { key: "v", label: "Documents", num: true, fmt: (v) => fmt.int(v as number) }]}
          />
          <div className="mt-3 flex flex-col gap-2">
            {Object.entries(data.mongo_queries ?? {})
              .filter(([, q]) => q.shell)
              .map(([name, q]) => (
                <details key={name} className="rounded-md border border-border px-2 py-1 text-xs">
                  <summary className="cursor-pointer text-ink-2">
                    {name.replace(/_/g, " ")} <span className="text-muted">· {q.ms} ms</span>
                  </summary>
                  <pre className="mt-1 overflow-x-auto whitespace-pre-wrap font-mono text-[11px] text-ink-2">{q.shell}</pre>
                </details>
              ))}
          </div>
        </Card>
      </div>
      <Insight>
        Hadoop and MongoDB agree: query Q8 recomputes the regional late counts with a MongoDB aggregation and finds no mismatch
        with the MapReduce output.
      </Insight>
    </div>
  );
}
