"""Tools the DelayLens agent can call. Every tool reads data produced by the Big Data pipeline:
Hadoop MapReduce KPI outputs (stored in MongoDB `kpis` / `scenarios`), order documents in MongoDB,
and — on request — a live MapReduce job submitted to the Hadoop cluster.
"""
from __future__ import annotations

import json
import os
import sys
import time
from functools import lru_cache
from pathlib import Path

from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hadoop"))

KPI_DIMENSIONS = ["all", "region", "market", "shipping_mode", "segment", "month", "delivery_status", "country",
                  "payment_type", "dow", "hour", "order_status", "region_mode", "market_mode", "mode_scheduled",
                  "scheduled_days", "category", "department", "product"]
OPEN_STATUSES = ["PENDING", "PENDING_PAYMENT", "PROCESSING", "ON_HOLD", "PAYMENT_REVIEW"]
SCHEDULED_DAYS = {"Standard Class": 4, "Second Class": 2, "First Class": 1, "Same Day": 0}
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# filter field -> MongoDB path on the `orders` collection
ORDER_FIELDS = {
    "market": "destination.market", "region": "destination.region", "country": "destination.country",
    "shipping_mode": "shipping.mode", "segment": "customer.segment", "category": "main_category",
    "department": "main_department", "payment_type": "payment_type", "order_status": "order_status",
    "delivery_status": "shipping.status", "month": "order_ym", "hour": "order_hour", "dow": "order_dow",
}


@lru_cache
def db():
    return MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017"),
                       serverSelectionTimeoutMS=3000)[os.environ.get("MONGO_DB", "delaylens")]


def _clean(rows):
    for r in rows:
        r.pop("_id", None)
        r.pop("source", None)
        r.pop("level", None)
    return rows


def _r(x, n=2):
    return None if x is None else round(float(x), n)


# ---------------------------------------------------------------- tools
def get_overall_kpis() -> dict:
    """Headline delivery KPIs computed by the Hadoop MapReduce jobs."""
    d = db()
    all_ = d.kpis.find_one({"dimension": "all"}, {"_id": 0, "source": 0, "level": 0, "key": 0})
    status = _clean(list(d.kpis.find({"dimension": "delivery_status"}, {"key": 1, "orders": 1})))
    items = d.order_items.estimated_document_count()
    open_high = d.orders.count_documents({"order_status": {"$in": OPEN_STATUSES}, "segment_late_pct": {"$gte": 75}})
    return {"source": "Hadoop MapReduce job delaylens-kpi-order-all (65,752 orders, Jan 2015 - Jan 2018)",
            "overall": all_, "delivery_status_breakdown": status, "order_items": items,
            "open_orders_in_segments_late_75pct_plus": open_high,
            "definitions": {"late_pct": "share of all orders with Delivery Status = Late delivery",
                            "on_time_pct": "shipping on time + advance shipping",
                            "avg_delay_days": "mean of (actual shipping days - scheduled days); negative = early"}}


def get_kpi_breakdown(dimension: str, sort_by: str = "late_pct", descending: bool = True, limit: int = 10,
                      min_orders: int = 0) -> dict:
    """KPIs per group for one dimension (output of the matching Hadoop job)."""
    if dimension not in KPI_DIMENSIONS:
        return {"error": f"unknown dimension {dimension}; choose from {KPI_DIMENSIONS}"}
    if sort_by not in {"late_pct", "orders", "avg_delay_days", "avg_delay_when_late", "sales", "profit",
                       "on_time_pct", "canceled_pct", "key"}:
        sort_by = "late_pct"
    q = {"dimension": dimension, "orders": {"$gte": int(min_orders)}}
    total = db().kpis.count_documents(q)
    rows = _clean(list(db().kpis.find(q).sort(sort_by, -1 if descending else 1).limit(int(min(limit, 200)))))
    if dimension == "dow":
        for r in rows:
            r["key"] = DOW[int(r["key"])]
    level = "order items" if dimension in ("category", "department", "product") else "orders"
    return {"source": f"Hadoop MapReduce job delaylens-kpi-{'item' if level == 'order items' else 'order'}-{dimension}",
            "unit": level, "groups_total": total, "sorted_by": sort_by, "rows": rows}


def query_orders(filters: dict | None = None, group_by: str | None = None, limit: int = 15) -> dict:
    """Ad-hoc MongoDB aggregation over the order documents with whitelisted filters / grouping."""
    filters = filters or {}
    match = {}
    for k, v in filters.items():
        if k == "month_from":
            match.setdefault("order_ym", {})["$gte"] = str(v)
        elif k == "month_to":
            match.setdefault("order_ym", {})["$lte"] = str(v)
        elif k == "min_segment_late_pct":
            match["segment_late_pct"] = {"$gte": float(v)}
        elif k == "open_only" and v:
            match["order_status"] = {"$in": OPEN_STATUSES}
        elif k in ORDER_FIELDS:
            match[ORDER_FIELDS[k]] = {"$in": v} if isinstance(v, list) else v
    pipeline = [{"$match": match}] if match else []
    gid = f"${ORDER_FIELDS[group_by]}" if group_by in ORDER_FIELDS else None
    pipeline += [
        {"$group": {"_id": gid, "orders": {"$sum": 1}, "late": {"$sum": "$shipping.is_late"},
                    "canceled": {"$sum": "$shipping.is_canceled"}, "avg_delay_days": {"$avg": "$shipping.delay_days"},
                    "avg_scheduled_days": {"$avg": "$shipping.days_scheduled"},
                    "avg_real_days": {"$avg": "$shipping.days_real"}, "sales": {"$sum": "$sales"},
                    "avg_segment_late_pct": {"$avg": "$segment_late_pct"}}},
        {"$addFields": {"late_pct": {"$round": [{"$multiply": [100, {"$divide": ["$late", "$orders"]}]}, 2]}}},
        {"$sort": {"late_pct": -1, "orders": -1}}, {"$limit": int(min(limit, 50))}]
    t0 = time.time()
    rows = list(db().orders.aggregate(pipeline))
    for r in rows:
        r["group"] = r.pop("_id")
        for k in ("avg_delay_days", "avg_scheduled_days", "avg_real_days", "avg_segment_late_pct"):
            r[k] = _r(r[k], 3)
        r["sales"] = _r(r["sales"])
    return {"source": "MongoDB aggregation on delaylens.orders", "filters": filters, "group_by": group_by,
            "ms": round(1000 * (time.time() - t0), 1), "rows": rows}


def find_at_risk_open_orders(min_segment_late_pct: float = 75, region: str | None = None,
                             market: str | None = None, shipping_mode: str | None = None,
                             limit: int = 10) -> dict:
    """Open orders whose region x shipping-mode segment has a high historical late rate (Hadoop KPI)."""
    q = {"order_status": {"$in": OPEN_STATUSES}, "segment_late_pct": {"$gte": float(min_segment_late_pct)}}
    if region:
        q["destination.region"] = region
    if market:
        q["destination.market"] = market
    if shipping_mode:
        q["shipping.mode"] = shipping_mode
    proj = {"_id": 1, "order_ts": 1, "order_status": 1, "shipping.mode": 1, "shipping.days_scheduled": 1,
            "destination.region": 1, "destination.country": 1, "customer.segment": 1, "sales": 1,
            "main_category": 1, "segment_late_pct": 1}
    count = db().orders.count_documents(q)
    rows = []
    for o in db().orders.find(q, proj).sort([("segment_late_pct", -1), ("sales", -1)]).limit(int(min(limit, 50))):
        rows.append({"order_id": o["_id"], "date": o["order_ts"].strftime("%Y-%m-%d"), "status": o["order_status"],
                     "mode": o["shipping"]["mode"], "region": o["destination"]["region"],
                     "country": o["destination"]["country"], "category": o["main_category"],
                     "sales": round(o["sales"], 2), "segment_late_pct": o["segment_late_pct"]})
    agg = list(db().orders.aggregate([{"$match": q}, {"$group": {
        "_id": None, "s": {"$sum": "$sales"}, "e": {"$sum": {"$divide": ["$segment_late_pct", 100]}}}}]))
    return {"source": "MongoDB orders + historical late % of the order's region x shipping-mode segment "
                      "(Hadoop job delaylens-kpi-order-region_mode)",
            "open_statuses": OPEN_STATUSES, "matching_open_orders": count,
            "matching_sales": _r(agg[0]["s"]) if agg else 0,
            "expected_late_orders": _r(agg[0]["e"], 0) if agg else 0, "top": rows}


def get_sla_scenarios() -> dict:
    """Promise-policy what-if results precomputed by the Hadoop SLA scenario jobs."""
    out = []
    for sc in db().scenarios.find({}, {"_id": 0}).sort("name", 1):
        n = sum(r["orders"] for r in sc["rows"])
        late = sum(r["late"] for r in sc["rows"])
        out.append({"scenario": sc["name"], "policy": sc["label"], "late_orders": late,
                    "late_pct": round(100 * late / n, 2),
                    "by_mode": {r["key"]: {"late_pct": r["late_pct"], "avg_promised_days": r["avg_scheduled_days"]}
                                for r in sc["rows"]}})
    return {"source": "Hadoop MapReduce SLA scenario jobs (each re-scores all 65,752 orders: late = actual "
                      "shipping days > promised days)",
            "note": "Scenarios are cumulative: S1 includes S0's rules plus its change, S2 includes S1, and so on. "
                    "S3 = First Class 2d + Second Class 4d + Same Day cutoff 12:00; S4 adds Standard Class 5d.",
            "scenarios": out}


def simulate_sla_policy(first_class_days: float = 1, second_class_days: float = 2, standard_class_days: float = 4,
                        same_day_days: float = 0, same_day_cutoff_hour: int | None = None) -> dict:
    """Re-score every order against a custom promise policy (MongoDB aggregation, ~0.3 s)."""
    promise = {"First Class": first_class_days, "Second Class": second_class_days,
               "Standard Class": standard_class_days, "Same Day": same_day_days}
    branches = [{"case": {"$eq": ["$shipping.mode", m]}, "then": float(v)} for m, v in promise.items()]
    sched = {"$switch": {"branches": branches, "default": "$shipping.days_scheduled"}}
    if same_day_cutoff_hour is not None:
        sched = {"$cond": [{"$and": [{"$eq": ["$shipping.mode", "Same Day"]},
                                     {"$gte": ["$order_hour", int(same_day_cutoff_hour)]}]}, 1.0, sched]}
    t0 = time.time()
    rows = list(db().orders.aggregate([
        {"$addFields": {"_promise": sched}},
        {"$addFields": {"_late": {"$cond": [{"$and": [{"$eq": ["$shipping.is_canceled", 0]},
                                                      {"$gt": ["$shipping.days_real", "$_promise"]}]}, 1, 0]}}},
        {"$group": {"_id": "$shipping.mode", "orders": {"$sum": 1}, "late_new": {"$sum": "$_late"},
                    "late_now": {"$sum": "$shipping.is_late"}}},
        {"$sort": {"_id": 1}}]))
    n = sum(r["orders"] for r in rows)
    new, now = sum(r["late_new"] for r in rows), sum(r["late_now"] for r in rows)
    return {"source": "MongoDB aggregation re-scoring all 65,752 orders", "ms": round(1000 * (time.time() - t0)),
            "policy": {**{f"{m} promised days": v for m, v in promise.items()},
                       "Same Day cutoff hour": same_day_cutoff_hour},
            "late_pct_now": round(100 * now / n, 2), "late_pct_policy": round(100 * new / n, 2),
            "late_orders_avoided": now - new,
            "by_mode": [{"mode": r["_id"], "orders": r["orders"], "late_pct_now": round(100 * r["late_now"] / r["orders"], 2),
                         "late_pct_policy": round(100 * r["late_new"] / r["orders"], 2)} for r in rows],
            "note": "Actual shipping days are unchanged; only the promise changes. Longer promises can reduce conversion."}


def get_clickstream_insights(dimension: str = "category", limit: int = 10) -> dict:
    """Product page views (Hadoop job over 466k access-log lines), joined with order volume per category."""
    if dimension not in ("category", "department", "product", "hour", "month", "dow"):
        dimension = "category"
    rows = list(db().clickstream.find({"dimension": dimension}, {"_id": 0, "dimension": 0}).sort("views", -1).limit(int(limit)))
    if dimension in ("category", "department"):
        kp = {r["key"].lower(): r for r in db().kpis.find({"dimension": dimension})}
        for r in rows:
            k = kp.get(r["key"].lower())
            if k:
                r["order_items"] = k["orders"]
                r["late_pct"] = k["late_pct"]
    return {"source": f"Hadoop MapReduce job delaylens-clicks-{dimension} (access logs Sep 2017 - Jan 2018)",
            "rows": rows}


def get_pipeline_info() -> dict:
    d = db()
    cluster = d.hadoop_jobs.find_one({"_id": "cluster"}, {"_id": 0})
    bench = d.hadoop_jobs.find_one({"_id": "benchmark"}, {"_id": 0})
    jobs = [{"name": j["name"], "seconds": j["seconds"], "map_tasks": j["counters"].get("Launched map tasks"),
             "input_records": j["counters"].get("Map input records"), "engine": j.get("engine")}
            for j in d.hadoop_jobs.find({"run": "pipeline"}).sort("seconds", -1).limit(8)]
    return {"cluster": cluster, "slowest_jobs": jobs, "benchmark": bench,
            "mongo_collections": {c: d[c].estimated_document_count() for c in d.list_collection_names()}}


ADHOC_DIMS = ["region", "market", "shipping_mode", "segment", "month", "country", "payment_type", "dow", "hour",
              "order_status", "region_mode", "market_mode", "state", "scheduled_days"]
ADHOC_FILTERS = {"market": "market", "region": "order_region", "country": "order_country",
                 "shipping_mode": "shipping_mode", "segment": "customer_segment", "payment_type": "payment_type",
                 "month": "order_ym", "order_status": "order_status", "state": "order_state"}


def run_hadoop_job(dimension: str, filters: dict | None = None) -> dict:
    """Submit a live MapReduce job (Hadoop Streaming on YARN) over the HDFS order data."""
    import hadoop_utils as H
    if dimension not in ADHOC_DIMS:
        return {"error": f"dimension must be one of {ADHOC_DIMS}"}
    if not H.cluster_up():
        return {"error": "Hadoop cluster is not running (start with hadoop/start-hadoop.sh)"}
    parts = []
    for k, v in (filters or {}).items():
        if k not in ADHOC_FILTERS:
            return {"error": f"filter {k} not allowed; use {list(ADHOC_FILTERS)}"}
        if any(c in str(v) for c in ";=\t\n"):
            return {"error": "invalid filter value"}
        parts.append(f"{ADHOC_FILTERS[k]}={v}")
    flt = ";".join(parts)
    tag = f"{int(time.time())}"
    out = f"/delaylens/adhoc/{dimension}_{tag}"
    info = H.run_streaming(f"delaylens-agent-{dimension}", "/delaylens/out/orders", out, "kpi_mapper.py",
                           "kpi_reducer.py final", combiner="kpi_reducer.py combine",
                           env={"LEVEL": "order", "DIM": dimension, "FILTER": flt}, reduces=1)
    rows = sorted(H.kpi_rows(out), key=lambda r: -r["orders"])
    db().adhoc_jobs.insert_one({"dimension": dimension, "filters": filters, "rows": rows,
                                "seconds": info["seconds"], "job_id": info["counters"].get("job_id"),
                                "created": time.time()})
    keep = ["key", "orders", "late", "late_pct", "on_time_pct", "canceled_pct", "avg_delay_days", "sales"]
    return {"source": f"live Hadoop Streaming job {info['counters'].get('job_id')} on YARN",
            "hdfs_input": "/delaylens/out/orders", "hdfs_output": out, "filter": flt or "none",
            "seconds": info["seconds"], "map_tasks": info["counters"].get("Launched map tasks"),
            "records_scanned": info["counters"].get("Map input records"),
            "orders_matching_filter": sum(r["orders"] for r in rows),
            "rows": [{k: r[k] for k in keep} for r in rows[:25]], "groups_total": len(rows)}


# ---------------------------------------------------------------- registry + JSON schemas
def _s(props: dict, required: list | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


FILTER_SCHEMA = {"type": "object", "description": "Equality filters. Keys: market, region, country, shipping_mode, "
                 "segment, category, department, payment_type, order_status, delivery_status, month (YYYY-MM), "
                 "month_from, month_to, min_segment_late_pct (0-100), open_only (bool)",
                 "additionalProperties": True}

TOOLS = {
    "get_overall_kpis": (get_overall_kpis, "Headline delivery KPIs for the whole business (late %, on-time %, "
                         "canceled %, average delay, sales) computed by Hadoop MapReduce.", _s({})),
    "get_kpi_breakdown": (get_kpi_breakdown, "Delivery KPIs per group for one dimension, precomputed by Hadoop "
                          "MapReduce. Use for rankings/comparisons: worst regions, shipping modes, categories, "
                          "months, countries, region x shipping mode (region_mode), etc.",
                          _s({"dimension": {"type": "string", "enum": KPI_DIMENSIONS},
                              "sort_by": {"type": "string", "enum": ["late_pct", "orders", "avg_delay_days",
                                                                     "avg_delay_when_late", "sales", "profit",
                                                                     "on_time_pct", "canceled_pct", "key"]},
                              "descending": {"type": "boolean"}, "limit": {"type": "integer"},
                              "min_orders": {"type": "integer", "description": "ignore small groups"}},
                             ["dimension"])),
    "query_orders": (query_orders, "Flexible MongoDB aggregation over the 65,752 order documents: filter by any "
                     "combination (e.g. market=LATAM and shipping_mode=First Class, a month range) "
                     "and optionally group by one field. Returns orders, late %, delay, sales.",
                     _s({"filters": FILTER_SCHEMA,
                         "group_by": {"type": "string", "enum": list(ORDER_FIELDS)},
                         "limit": {"type": "integer"}})),
    "find_at_risk_open_orders": (find_at_risk_open_orders, "List OPEN orders (pending/processing/on hold/payment "
                                 "review) whose region x shipping-mode segment historically ships late most of "
                                 "the time (Hadoop KPI), with total sales and expected late orders.",
                                 _s({"min_segment_late_pct": {"type": "number", "description": "default 75"},
                                     "region": {"type": "string"}, "market": {"type": "string"},
                                     "shipping_mode": {"type": "string"}, "limit": {"type": "integer"}})),
    "get_sla_scenarios": (get_sla_scenarios, "Precomputed promise-policy what-if scenarios from Hadoop (e.g. First "
                          "Class promised 2 days, Same Day cutoff at 12:00) and the resulting late %.", _s({})),
    "simulate_sla_policy": (simulate_sla_policy, "Simulate a custom delivery-promise policy: set promised days per "
                            "shipping mode and an optional Same Day cutoff hour; re-scores all orders and returns "
                            "the new late % vs today. Use for 'what if we promise X days' questions.",
                            _s({"first_class_days": {"type": "number"}, "second_class_days": {"type": "number"},
                                "standard_class_days": {"type": "number"}, "same_day_days": {"type": "number"},
                                "same_day_cutoff_hour": {"type": "integer",
                                                         "description": "Same Day orders at/after this hour are promised 1 day"}})),
    "get_clickstream_insights": (get_clickstream_insights, "Product page views from the web access logs (Hadoop "
                                 "job), optionally compared with order volume and late % per category.",
                                 _s({"dimension": {"type": "string", "enum": ["category", "department", "product",
                                                                               "hour", "month", "dow"]},
                                     "limit": {"type": "integer"}})),
    "get_pipeline_info": (get_pipeline_info, "Technical facts about the Big Data pipeline: Hadoop cluster config, "
                          "MapReduce job runtimes and counters, scalability benchmark, MongoDB collections.", _s({})),
    "run_hadoop_job": (run_hadoop_job, "Submit a LIVE MapReduce job to the Hadoop cluster (takes ~20-40 s). Use "
                       "only when the user asks to run a Hadoop/MapReduce job, or needs a breakdown not available "
                       "otherwise (e.g. by state, or a filtered group-by recomputed from HDFS).",
                       _s({"dimension": {"type": "string", "enum": ADHOC_DIMS},
                           "filters": {"type": "object", "description": "keys: " + ", ".join(ADHOC_FILTERS)}},
                          ["dimension"])),
}


def openai_tools() -> list[dict]:
    return [{"type": "function", "function": {"name": n, "description": d, "parameters": p}}
            for n, (_, d, p) in TOOLS.items()]


def call_tool(name: str, args: dict) -> dict:
    if name not in TOOLS:
        return {"error": f"unknown tool {name}"}
    try:
        return TOOLS[name][0](**(args or {}))
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
    except Exception as e:  # surface failures to the agent instead of crashing the graph
        return {"error": f"{type(e).__name__}: {e}"}


def to_json(obj) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)
