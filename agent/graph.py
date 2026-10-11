"""DelayLens Copilot: a LangGraph agent over the Hadoop / MongoDB delivery analytics.

    START -> planner --(tool calls)--> tools --> planner ... (max 4 rounds)
                     \--(enough data)--> analyst -> END
                     \--(LLM unreachable)--> fallback -> analyst -> END

planner  LLM with function calling picks tools (KPI breakdowns from Hadoop, MongoDB queries,
         promise-policy simulations, live MapReduce jobs).
tools    executes the calls against MongoDB / the Hadoop cluster.
fallback keyword router used when the LLM gateway cannot be reached, so the copilot still
         answers from the data.
analyst  streams the final grounded answer (markdown, optional ```chart block for the UI).
"""
from __future__ import annotations

import json
import os
import re
import time
from functools import lru_cache
from typing import Any, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

import tools as T
from llm_client import build_llm_client

MAX_ROUNDS = 4


class AgentState(TypedDict, total=False):
    question: str
    history: list[dict]
    messages: list[dict]
    pending: list[dict]
    results: list[dict]
    rounds: int
    llm_ok: bool
    llm_error: str
    answer: str


@lru_cache
def llm():
    return build_llm_client()


def model_name() -> str:
    return os.environ.get("CHAT_MODEL", "azure/deepSeek-V4-Flash")


@lru_cache
def vocabulary() -> str:
    d = T.db()
    regions = sorted(d.orders.distinct("destination.region"))
    markets = sorted(d.orders.distinct("destination.market"))
    cats = [r["key"] for r in d.kpis.find({"dimension": "category"}).sort("orders", -1).limit(25)]
    return (f"Regions: {', '.join(regions)}.\nMarkets: {', '.join(markets)}.\n"
            "Shipping modes: Standard Class (4 scheduled days), Second Class (2), First Class (1), Same Day (0).\n"
            "Customer segments: Consumer, Corporate, Home Office. Payment types: DEBIT, TRANSFER, PAYMENT, CASH.\n"
            f"Top product categories: {', '.join(cats)}.\n"
            "Order statuses: COMPLETE, CLOSED, PENDING, PENDING_PAYMENT, PROCESSING, ON_HOLD, PAYMENT_REVIEW, "
            "CANCELED, SUSPECTED_FRAUD. Open = PENDING, PENDING_PAYMENT, PROCESSING, ON_HOLD, PAYMENT_REVIEW.\n"
            "Months: 2015-01 .. 2018-01 (YYYY-MM). Countries are in English (e.g. United States, France, Mexico).")


PLANNER_PROMPT = """You are the planning step of DelayLens Copilot, an analytics agent for the DataCo global
supply chain (180,519 order items / 65,752 orders, Jan 2015 - Jan 2018). Delivery KPIs were computed with
Hadoop MapReduce on HDFS and stored in MongoDB together with the order documents. Each order also carries
segment_late_pct: the historical late % of its region x shipping-mode segment (from Hadoop).
Known structure of the data: First Class is promised 1 day but always takes 2; Second Class is promised 2
and takes 2-6 days; Standard is promised 4 and takes 2-6; Same Day orders placed at/after 12:00 arrive the
next day. So most lateness comes from delivery promises (SLA) per shipping mode, not from geography.

Your job: decide which tools to call to answer the user's question with real numbers.
- Prefer get_kpi_breakdown / get_overall_kpis (precomputed by Hadoop) for rankings and comparisons.
- Use query_orders for filtered combinations (e.g. one market + one shipping mode, a month range).
- Use simulate_sla_policy for "what if we promise X days / add a cutoff" questions; get_sla_scenarios for the
  precomputed Hadoop scenarios.
- Use find_at_risk_open_orders for lists of open orders to act on now.
- Use run_hadoop_job only if the user asks to run a Hadoop / MapReduce job, or for a breakdown no other tool has.
- Use exact names from the vocabulary below. Call several tools in one round when useful.
- When you have enough data (or the question needs no data, e.g. a greeting), reply with the single word DONE.

Vocabulary:
{vocab}"""

ANALYST_PROMPT = """You are DelayLens Copilot, a senior supply-chain analyst. Answer the user's question using ONLY
the tool results provided (computed from the DataCo dataset with Hadoop MapReduce and MongoDB).
Never invent numbers: every number you write must appear in the tool results or be a simple difference/ratio
of numbers that do. If the data does not answer the question, say what is missing.

Style:
- Lead with the direct answer and its key number(s) in the first sentence.
- Then short evidence: a compact markdown table or 2-5 bullets. Percentages with 1 decimal.
- Where useful, end with 1-3 concrete, data-backed recommendations for the logistics team.
- Name the source briefly at the end in italics (e.g. _Source: Hadoop KPI job by region, 65,752 orders_).
- Keep it under ~220 words unless the user asks for detail.
- Definitions: late % = orders with Delivery Status "Late delivery" / all orders; on-time % = on time + advance;
  avg delay = actual minus scheduled shipping days (negative = early).
- If a comparison over 3-15 groups would help, add ONE chart block exactly like:
```chart
{{"type": "bar", "title": "Late % by shipping mode", "unit": "%", "data": [{{"label": "First Class", "value": 95.3}}]}}
```
  type is "bar" or "line" (line for time series). Values must come from the tool results.
- If the question is outside supply-chain analytics, answer briefly and steer back to what you can analyse.
{fallback_note}"""


def _short(obj: Any, limit: int = 7000) -> str:
    s = T.to_json(obj)
    return s if len(s) <= limit else s[:limit] + "...(truncated)"


def _emit(kind: str, **data):
    try:
        get_stream_writer()({"type": kind, **data})
    except Exception:
        pass


def _parse_args(raw: str | None) -> dict:
    """Tool arguments from the LLM; tolerate empty strings and concatenated objects such as '{}{}'."""
    if not raw or not raw.strip():
        return {}
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        try:
            out, _ = json.JSONDecoder().raw_decode(raw.strip())
        except json.JSONDecodeError:
            return {}
    return out if isinstance(out, dict) else {}


# ---------------------------------------------------------------- nodes
def planner(state: AgentState) -> AgentState:
    msgs = state.get("messages") or (
        [{"role": "system", "content": PLANNER_PROMPT.format(vocab=vocabulary())}]
        + state.get("history", [])[-6:] + [{"role": "user", "content": state["question"]}])
    _emit("step", node="planner", status="thinking", round=state.get("rounds", 0) + 1)
    t0 = time.time()
    try:
        m = llm().chat_tools(model_name(), msgs, T.openai_tools(), max_tokens=700, timeout=45)
    except Exception as e:
        _emit("step", node="planner", status="llm_unavailable", detail=str(e)[:160])
        return {"llm_ok": False, "llm_error": str(e)[:300], "pending": [], "messages": msgs}
    calls = [{"id": tc.id, "name": tc.function.name, "args": _parse_args(tc.function.arguments)}
             for tc in (m.tool_calls or [])]
    if calls and state.get("rounds", 0) < MAX_ROUNDS:
        msgs = msgs + [{"role": "assistant", "content": m.content or "",
                        "tool_calls": [{"id": c["id"], "type": "function",
                                        "function": {"name": c["name"], "arguments": json.dumps(c["args"])}}
                                       for c in calls]}]
        _emit("step", node="planner", status="planned", tools=[c["name"] for c in calls],
              ms=round(1000 * (time.time() - t0)))
        return {"llm_ok": True, "pending": calls, "messages": msgs}
    _emit("step", node="planner", status="ready", ms=round(1000 * (time.time() - t0)))
    return {"llm_ok": True, "pending": [], "messages": msgs}


def run_tools(state: AgentState) -> AgentState:
    msgs, results = list(state["messages"]), list(state.get("results", []))
    for c in state["pending"]:
        _emit("step", node="tools", status="calling", tool=c["name"], args=c["args"])
        t0 = time.time()
        res = T.call_tool(c["name"], c["args"])
        ms = round(1000 * (time.time() - t0))
        results.append({"tool": c["name"], "args": c["args"], "result": res, "ms": ms})
        msgs.append({"role": "tool", "tool_call_id": c["id"], "content": _short(res)})
        _emit("step", node="tools", status="error" if isinstance(res, dict) and "error" in res else "done",
              tool=c["name"], ms=ms, source=res.get("source") if isinstance(res, dict) else None)
    return {"messages": msgs, "results": results, "pending": [], "rounds": state.get("rounds", 0) + 1}


KEYWORDS = [
    (r"what if|what-if|promise|sla|scenario|cutoff|simulat", "get_sla_scenarios"),
    (r"high[- ]risk|risky|flag|at risk|which orders|open orders", "find_at_risk_open_orders"),
    (r"hadoop|mapreduce|pipeline|benchmark|hdfs|yarn|scal", "get_pipeline_info"),
    (r"click|view|traffic|visit|access log", "get_clickstream_insights"),
]
DIM_WORDS = [(r"region.*(mode|shipping)|(mode|shipping).*region", "region_mode"), (r"region", "region"),
             (r"market", "market"), (r"shipping|mode|class|same day", "shipping_mode"),
             (r"categor|product", "category"), (r"department", "department"), (r"month|trend|time|season", "month"),
             (r"countr", "country"), (r"segment|customer", "segment"), (r"payment", "payment_type"),
             (r"weekday|day of week", "dow"), (r"hour", "hour")]


def fallback(state: AgentState) -> AgentState:
    """Rule-based tool selection when the LLM gateway is unreachable."""
    q = state["question"].lower()
    calls = []
    for pat, tool in KEYWORDS:
        if re.search(pat, q):
            calls.append((tool, {}))
            break
    if not calls:
        for pat, dim in DIM_WORDS:
            if re.search(pat, q):
                calls.append(("get_kpi_breakdown", {"dimension": dim, "min_orders": 100 if dim in
                                                    ("country", "region_mode", "category") else 0}))
                break
    if not calls:
        calls.append(("get_overall_kpis", {}))
    results = []
    for name, args in calls:
        _emit("step", node="fallback", status="calling", tool=name, args=args)
        t0 = time.time()
        res = T.call_tool(name, args)
        results.append({"tool": name, "args": args, "result": res, "ms": round(1000 * (time.time() - t0))})
        _emit("step", node="fallback", status="done", tool=name)
    return {"results": results}


def _table(rows: list[dict], cols: list[str], n: int = 12) -> str:
    if not rows:
        return "_no rows_"
    cols = [c for c in cols if c in rows[0]]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows[:n]:
        out.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    return "\n".join(out)


def template_answer(results: list[dict]) -> str:
    parts = ["_The LLM gateway is unreachable, so here are the raw analytics for your question._\n"]
    for r in results:
        res = r["result"]
        parts.append(f"**{r['tool']}** — {res.get('source', '')}")
        if "rows" in res:
            parts.append(_table(res["rows"], ["key", "group", "orders", "late_pct", "on_time_pct", "avg_delay_days",
                                              "sales", "views"]))
        elif "top" in res:
            parts.append(f"{res['matching_open_orders']} matching open orders.\n\n" +
                         _table(res["top"], ["order_id", "date", "mode", "region", "sales", "segment_late_pct"]))
        elif "scenarios" in res:
            parts.append(_table(res["scenarios"], ["scenario", "policy", "late_orders", "late_pct"]))
        elif "overall" in res:
            o = res["overall"]
            parts.append(f"{o['orders']:,} orders · late {o['late_pct']}% · on time {o['on_time_pct']}% · "
                         f"canceled {o['canceled_pct']}% · avg delay {o['avg_delay_days']} days")
        else:
            parts.append("```json\n" + _short(res, 1500) + "\n```")
    return "\n\n".join(parts)


def analyst(state: AgentState) -> AgentState:
    results = state.get("results", [])
    _emit("step", node="analyst", status="writing")
    if not state.get("llm_ok", True):
        text = template_answer(results)
        _emit("token", text=text)
        return {"answer": text}
    evidence = "\n\n".join(f"### {r['tool']}({json.dumps(r['args'])})\n{_short(r['result'], 6000)}" for r in results)
    msgs = ([{"role": "system", "content": ANALYST_PROMPT.format(fallback_note="")}]
            + state.get("history", [])[-6:]
            + [{"role": "user", "content": f"Question: {state['question']}\n\nTool results:\n{evidence or '(none)'}"}])
    chunks = []
    try:
        for tok in llm().chat_stream(model_name(), msgs, max_tokens=1100, timeout=90):
            chunks.append(tok)
            _emit("token", text=tok)
    except Exception as e:
        text = template_answer(results) if results else f"Sorry, the language model failed: {e}"
        _emit("token", text=text)
        return {"answer": text}
    return {"answer": "".join(chunks)}


def route_after_planner(state: AgentState) -> str:
    if not state.get("llm_ok", True):
        return "fallback"
    return "tools" if state.get("pending") else "analyst"


@lru_cache
def build_graph():
    g = StateGraph(AgentState)
    g.add_node("planner", planner)
    g.add_node("tools", run_tools)
    g.add_node("fallback", fallback)
    g.add_node("analyst", analyst)
    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", route_after_planner, {"tools": "tools", "analyst": "analyst",
                                                             "fallback": "fallback"})
    g.add_edge("tools", "planner")
    g.add_edge("fallback", "analyst")
    g.add_edge("analyst", END)
    return g.compile()


def ask(question: str, history: list[dict] | None = None):
    """Yields stream events: {"type": "step"|"token", ...}, then {"type": "final", ...}."""
    graph = build_graph()
    state = {"question": question, "history": history or [], "rounds": 0, "results": []}
    final = {}
    for mode, chunk in graph.stream(state, stream_mode=["custom", "values"]):
        if mode == "custom":
            yield chunk
        else:
            final = chunk
    yield {"type": "final", "answer": final.get("answer", ""), "llm_ok": final.get("llm_ok", True),
           "tools": [{"tool": r["tool"], "args": r["args"], "ms": r["ms"]} for r in final.get("results", [])]}


if __name__ == "__main__":
    import sys
    for ev in ask(" ".join(sys.argv[1:]) or "Which regions have the worst late-delivery rate?"):
        if ev["type"] == "token":
            print(ev["text"], end="", flush=True)
        elif ev["type"] == "step":
            print(f"\n[{ev['node']}] {ev.get('status')} {ev.get('tool', '')} {ev.get('tools', '')}", flush=True)
        else:
            print("\n\nTOOLS:", ev["tools"])
