"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowUp, ChevronDown, ChevronRight, Database, Loader2, Sparkles, Wrench } from "lucide-react";
import { API } from "@/lib/api";
import { BarList, TrendLine } from "@/components/charts";

type Step = { node: string; status: string; tool?: string; tools?: string[]; args?: unknown; ms?: number; source?: string; detail?: string };
type Msg = { role: "user" | "assistant"; content: string; steps?: Step[]; done?: boolean; llmOk?: boolean };
type ChartSpec = { type: "bar" | "line"; title?: string; unit?: string; data: { label: string; value: number }[] };

export const SUGGESTIONS = [
  "Which regions have the worst late-delivery rate, and is geography really the cause?",
  "Compare shipping modes: promised vs actual days and late %",
  "What happens to the late rate if First Class promises 2 days and Same Day has a 12:00 cutoff?",
  "Which open orders are most likely to ship late? Total sales at stake?",
  "Show the monthly late-delivery trend for 2017",
  "Run a live Hadoop job: late % by order state for the USCA market",
  "LATAM orders shipped by Second Class: late % by country",
  "Which product categories get the most page views, and are they delivered late?",
];

function parseBlocks(text: string): ({ kind: "md"; text: string } | { kind: "chart"; spec: ChartSpec })[] {
  const out: ({ kind: "md"; text: string } | { kind: "chart"; spec: ChartSpec })[] = [];
  const re = /```chart\s*([\s\S]*?)```/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    out.push({ kind: "md", text: text.slice(last, m.index) });
    try {
      out.push({ kind: "chart", spec: JSON.parse(m[1]) });
    } catch {
      /* malformed chart block: drop it */
    }
    last = m.index + m[0].length;
  }
  let tail = text.slice(last);
  const open = tail.indexOf("```chart");
  if (open >= 0) tail = tail.slice(0, open); // chart still streaming
  out.push({ kind: "md", text: tail });
  return out;
}

function ChartBlock({ spec }: { spec: ChartSpec }) {
  if (!spec?.data?.length) return null;
  const unit = spec.unit ?? "";
  const peak = Math.max(...spec.data.map((d) => d.value));
  return (
    <div className="my-3 rounded-lg border border-border p-3">
      {spec.title && <div className="mb-2 text-xs font-semibold">{spec.title}</div>}
      {spec.type === "line" ? (
        <TrendLine data={spec.data} x="label" series={[{ key: "value", name: spec.title ?? "value" }]} unit={unit} height={200} />
      ) : (
        <BarList rows={spec.data} unit={unit} highlight={spec.data.filter((d) => d.value === peak).map((d) => d.label)} />
      )}
    </div>
  );
}

function Trace({ steps, done }: { steps: Step[]; done?: boolean }) {
  const [open, setOpen] = useState(false);
  const tools = steps.filter((s) => (s.node === "tools" || s.node === "fallback") && s.status !== "calling");
  const label = done
    ? `Agent used ${tools.length} tool${tools.length === 1 ? "" : "s"}`
    : steps.at(-1)?.node === "tools" && steps.at(-1)?.status === "calling"
      ? `Running ${steps.at(-1)?.tool}…`
      : steps.at(-1)?.node === "analyst"
        ? "Writing answer…"
        : "Planning…";
  return (
    <div className="mb-2 text-xs text-ink-2">
      <button onClick={() => setOpen(!open)} className="inline-flex items-center gap-1 rounded-md px-1 py-0.5 hover:bg-surface-2">
        {done ? open ? <ChevronDown size={12} /> : <ChevronRight size={12} /> : <Loader2 size={12} className="animate-spin" />}
        <Wrench size={12} /> {label}
      </button>
      {open && (
        <ol className="ml-4 mt-1 flex flex-col gap-1 border-l border-grid pl-3">
          {steps.map((s, i) => (
            <li key={i} className="leading-snug">
              <span className="font-medium text-ink">{s.node}</span>{" "}
              {s.status === "planned" && <>chose {s.tools?.join(", ")}</>}
              {s.status === "calling" && (
                <>
                  → <code className="font-mono">{s.tool}</code>{" "}
                  <span className="font-mono text-muted">{JSON.stringify(s.args)}</span>
                </>
              )}
              {s.status === "done" && (
                <>
                  ✓ {s.tool} {s.ms !== undefined && <span className="text-muted">{s.ms} ms</span>}
                  {s.source && <div className="text-muted">{s.source}</div>}
                </>
              )}
              {s.status === "error" && <span style={{ color: "var(--critical)" }}>✗ {s.tool} failed</span>}
              {s.status === "llm_unavailable" && <span style={{ color: "var(--critical)" }}>LLM gateway unreachable → rule-based fallback</span>}
              {s.status === "ready" && <>has enough data</>}
              {s.status === "thinking" && <>round {String((s as { round?: number }).round ?? "")}</>}
              {s.status === "writing" && <>writing the answer</>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

let autoAsked = false; // survives React StrictMode's double effect run in development

export default function Copilot({ compact = false, initial }: { compact?: boolean; initial?: string }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (initial && !autoAsked) {
      autoAsked = true;
      send(initial);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [msgs]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);
    const history = msgs.filter((m) => m.content).map((m) => ({ role: m.role, content: m.content }));
    setMsgs((m) => [...m, { role: "user", content: q }, { role: "assistant", content: "", steps: [] }]);
    const patch = (fn: (m: Msg) => Msg) =>
      setMsgs((all) => {
        const copy = [...all];
        copy[copy.length - 1] = fn(copy[copy.length - 1]);
        return copy;
      });
    try {
      const res = await fetch(`${API}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: q, history }),
      });
      if (!res.body) throw new Error("no response body");
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const events = buf.split("\n\n");
        buf = events.pop() ?? "";
        for (const e of events) {
          const line = e.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          const ev = JSON.parse(line.slice(6));
          if (ev.type === "step") patch((m) => ({ ...m, steps: [...(m.steps ?? []), ev] }));
          else if (ev.type === "token") patch((m) => ({ ...m, content: m.content + ev.text }));
          else if (ev.type === "final") patch((m) => ({ ...m, content: ev.answer || m.content, llmOk: ev.llm_ok }));
          else if (ev.type === "error") patch((m) => ({ ...m, content: m.content + `\n\n_Error: ${ev.message}_` }));
        }
      }
    } catch (err) {
      patch((m) => ({ ...m, content: `_Could not reach the API: ${String(err)}_` }));
    } finally {
      patch((m) => ({ ...m, done: true }));
      setBusy(false);
    }
  }

  return (
    <div className={`flex min-h-0 flex-1 flex-col ${compact ? "" : "card"}`}>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {msgs.length === 0 && (
          <div className="flex flex-col gap-3">
            <div className="flex items-start gap-2 text-sm text-ink-2">
              <Sparkles size={16} className="mt-0.5 shrink-0 text-accent" />
              <p>
                Ask about delivery performance. The copilot is a LangGraph agent: it plans, calls tools over the
                Hadoop MapReduce KPIs and MongoDB (or launches a live MapReduce job), then writes a grounded answer.
              </p>
            </div>
            <div className={`grid gap-2 ${compact ? "" : "md:grid-cols-2"}`}>
              {SUGGESTIONS.slice(0, compact ? 5 : 8).map((s) => (
                <button key={s} onClick={() => send(s)}
                  className="rounded-lg border border-border px-3 py-2 text-left text-xs text-ink-2 hover:bg-surface-2">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="flex flex-col gap-4">
          {msgs.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-accent px-3.5 py-2 text-sm text-white">
                {m.content}
              </div>
            ) : (
              <div key={i} className="max-w-full">
                <Trace steps={m.steps ?? []} done={m.done} />
                <div className="md text-sm">
                  {parseBlocks(m.content).map((b, j) =>
                    b.kind === "md" ? (
                      <ReactMarkdown key={j} remarkPlugins={[remarkGfm]}>{b.text}</ReactMarkdown>
                    ) : (
                      <ChartBlock key={j} spec={b.spec} />
                    ),
                  )}
                </div>
                {m.done && m.llmOk === false && (
                  <div className="mt-1 inline-flex items-center gap-1 text-[11px] text-muted">
                    <Database size={11} /> answered by the rule-based fallback (LLM gateway offline)
                  </div>
                )}
              </div>
            ),
          )}
        </div>
        <div ref={endRef} />
      </div>
      <form
        className="flex items-end gap-2 border-t border-border p-3"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
          rows={1}
          placeholder="Ask about late deliveries, regions, shipping modes, what-if promises…"
          className="max-h-32 min-h-[40px] flex-1 resize-none rounded-lg border border-border bg-page px-3 py-2 text-sm outline-none focus:border-accent"
          aria-label="Message"
        />
        <button type="submit" disabled={busy || !input.trim()}
          className="grid h-10 w-10 place-items-center rounded-lg bg-accent text-white disabled:opacity-40" aria-label="Send">
          {busy ? <Loader2 size={16} className="animate-spin" /> : <ArrowUp size={16} />}
        </button>
      </form>
    </div>
  );
}
