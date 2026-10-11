"""DelayLens API: dashboard data (MongoDB / Hadoop MapReduce results) + the LangGraph copilot over SSE.

Run:  cd agent && ../.venv/bin/python -m uvicorn server:app --port 8000
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import tools as T  # noqa: E402
from graph import ask  # noqa: E402

app = FastAPI(title="DelayLens API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
RESULTS = ROOT / "docs" / "results"


def _load(name: str):
    p = RESULTS / name
    return json.loads(p.read_text()) if p.exists() else None


@app.get("/api/health")
def health():
    out = {"mongo": False, "hadoop": False, "llm_model": os.environ.get("CHAT_MODEL")}
    try:
        T.db().command("ping")
        out["mongo"] = True
    except Exception as e:
        out["mongo_error"] = str(e)[:200]
    out["hadoop"] = _hadoop_up()
    return out


_HADOOP_CACHE = {"t": 0.0, "up": False}


def _hadoop_up() -> bool:
    """`hdfs dfsadmin -report` takes seconds while jobs run, so cache it for 30 s."""
    if time.time() - _HADOOP_CACHE["t"] > 30:
        try:
            import hadoop_utils as H
            _HADOOP_CACHE["up"] = H.cluster_up()
        except Exception:
            _HADOOP_CACHE["up"] = False
        _HADOOP_CACHE["t"] = time.time()
    return _HADOOP_CACHE["up"]


@app.get("/api/overview")
def overview():
    d = T.db()
    k = T.get_overall_kpis()
    month = list(d.kpis.find({"dimension": "month"}, {"_id": 0, "key": 1, "orders": 1, "late_pct": 1,
                                                      "on_time_pct": 1, "canceled_pct": 1, "sales": 1,
                                                      "avg_delay_days": 1}).sort("key", 1))
    modes = T.get_kpi_breakdown("shipping_mode", sort_by="late_pct")["rows"]
    markets = T.get_kpi_breakdown("market", sort_by="late_pct")["rows"]
    open_sales = list(d.orders.aggregate([
        {"$match": {"order_status": {"$in": T.OPEN_STATUSES}}},
        {"$group": {"_id": "$shipping.mode", "orders": {"$sum": 1}, "sales": {"$sum": "$sales"},
                    "expected_late": {"$sum": {"$divide": ["$segment_late_pct", 100]}}}}]))
    return {"kpis": k, "month": month, "shipping_mode": modes, "market": markets,
            "open_orders_by_mode": open_sales, "scenarios": T.get_sla_scenarios()["scenarios"]}


@app.get("/api/kpis/{dimension}")
def kpis(dimension: str, sort_by: str = "late_pct", limit: int = 60, min_orders: int = 0, descending: bool = True):
    res = T.get_kpi_breakdown(dimension, sort_by=sort_by, limit=limit, min_orders=min_orders, descending=descending)
    if "error" in res:
        raise HTTPException(400, res["error"])
    return res


@app.get("/api/clicks/{dimension}")
def clicks(dimension: str, limit: int = 30):
    return T.get_clickstream_insights(dimension, limit)


@app.get("/api/pipeline")
def pipeline():
    d = T.db()
    jobs = list(d.hadoop_jobs.find({"run": "pipeline"}, {"_id": 0}))
    return {"cluster": d.hadoop_jobs.find_one({"_id": "cluster"}, {"_id": 0}),
            "benchmark": d.hadoop_jobs.find_one({"_id": "benchmark"}, {"_id": 0}),
            "jobs": jobs, "profile": _load("profile.json"), "mongo_load": _load("mongo_load.json"),
            "mongo_queries": _load("mongo_queries.json"),
            "adhoc": list(d.adhoc_jobs.find({}, {"_id": 0}).sort("created", -1).limit(5))}


@app.get("/api/orders/at-risk")
def at_risk(min_segment_late_pct: float = 75, region: str | None = None, market: str | None = None,
            shipping_mode: str | None = None, limit: int = 25):
    return T.find_at_risk_open_orders(min_segment_late_pct, region, market, shipping_mode, limit)


@app.get("/api/scenarios")
def scenarios():
    return T.get_sla_scenarios()


@app.get("/api/options")
def options():
    d = T.db()
    return {"regions": sorted(d.orders.distinct("destination.region")),
            "markets": sorted(d.orders.distinct("destination.market")),
            "shipping_modes": list(T.SCHEDULED_DAYS),
            "segments": sorted(d.orders.distinct("customer.segment")),
            "payment_types": sorted(d.orders.distinct("payment_type")),
            "categories": [r["key"] for r in d.kpis.find({"dimension": "category"}).sort("orders", -1)]}


class PolicyIn(BaseModel):
    first_class_days: float = 1
    second_class_days: float = 2
    standard_class_days: float = 4
    same_day_days: float = 0
    same_day_cutoff_hour: int | None = None


@app.post("/api/simulate")
def simulate(p: PolicyIn):
    return T.simulate_sla_policy(**p.model_dump())


class ChatIn(BaseModel):
    message: str
    history: list[dict] = []


@app.post("/api/chat")
def chat(body: ChatIn):
    history = [{"role": m["role"], "content": str(m["content"])[:4000]} for m in body.history[-8:]
               if m.get("role") in ("user", "assistant") and m.get("content")]

    def gen():
        t0 = time.time()
        final = None
        try:
            for ev in ask(body.message, history):
                if ev["type"] == "final":
                    final = ev
                yield f"data: {json.dumps(ev, default=str)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)[:300]})}\n\n"
        try:
            T.db().agent_logs.insert_one({"question": body.message, "answer": (final or {}).get("answer"),
                                          "tools": (final or {}).get("tools"), "llm_ok": (final or {}).get("llm_ok"),
                                          "seconds": round(time.time() - t0, 2), "ts": time.time()})
        except Exception:
            pass
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class QueryIn(BaseModel):
    filters: dict = {}
    group_by: str | None = None
    limit: int = 30


@app.post("/api/query")
def query(q: QueryIn):
    res = T.query_orders(q.filters, q.group_by, q.limit)
    if q.group_by in ("hour", "dow", "month"):
        res["rows"].sort(key=lambda r: r["group"])
    return res
