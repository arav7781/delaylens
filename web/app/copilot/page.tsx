"use client";

import { useEffect, useState } from "react";
import Copilot from "@/components/Copilot";
import { Card, PageHeader } from "@/components/ui";

const TOOLS = [
  ["get_overall_kpis", "headline KPIs (Hadoop job kpi-order-all)"],
  ["get_kpi_breakdown", "KPIs per region, market, mode, month, country, category… (Hadoop)"],
  ["query_orders", "filtered MongoDB aggregation over 65,752 order documents"],
  ["find_at_risk_open_orders", "open orders in segments that usually ship late"],
  ["get_sla_scenarios", "Hadoop promise-policy what-if results"],
  ["simulate_sla_policy", "custom promise policy, re-scored in MongoDB"],
  ["get_clickstream_insights", "page views from the access-log jobs"],
  ["get_pipeline_info", "cluster, job counters, benchmark"],
  ["run_hadoop_job", "submits a live MapReduce job to YARN"],
];

export default function CopilotPage() {
  const [q, setQ] = useState<string | undefined>();
  useEffect(() => {
    // deep link: /copilot?q=<question> asks the question on load (used for demos)
    setQ(new URLSearchParams(window.location.search).get("q") ?? undefined);
  }, []);
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="DelayLens Copilot"
        lead="A LangGraph agent that answers questions with numbers from the Hadoop MapReduce KPIs and MongoDB. It can also launch a new MapReduce job when a question needs one."
        source="Model: azure/deepSeek-V4-Flash via the LLM gateway (OpenAI-compatible function calling)"
      />
      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <div className="flex h-[calc(100vh-210px)] min-h-[520px] flex-col">
          <Copilot initial={q} />
        </div>
        <div className="flex flex-col gap-4">
          <Card title="How the agent works">
            <ol className="ml-4 list-decimal space-y-1.5 text-xs text-ink-2">
              <li><b className="text-ink">Planner</b> (LLM + function calling) picks tools and arguments.</li>
              <li><b className="text-ink">Tools</b> run against MongoDB and Hadoop; results go back to the planner (up to 4 rounds).</li>
              <li><b className="text-ink">Analyst</b> streams a grounded answer with a table or chart.</li>
              <li>If the LLM gateway is unreachable, a <b className="text-ink">rule-based fallback</b> still answers from the data.</li>
            </ol>
          </Card>
          <Card title="Tools">
            <ul className="space-y-1.5 text-xs">
              {TOOLS.map(([n, d]) => (
                <li key={n}>
                  <code className="font-mono text-ink">{n}</code>
                  <div className="text-ink-2">{d}</div>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
