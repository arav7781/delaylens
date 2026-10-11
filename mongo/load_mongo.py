"""Step 4a: load cleaned records + Hadoop MapReduce results into MongoDB.

Collections (database `delaylens`)
  orders         one document per order (output of Hadoop Job A) with embedded items[] and the
                 historical late rate of its region x shipping-mode segment (from the Hadoop KPIs)
  order_items    one document per order item (cleaned flat records)
  kpis           every Hadoop KPI output row, tagged by dimension (region, shipping_mode, ...)
  scenarios      promise-policy (SLA) what-if results from the Hadoop scenario jobs
  clickstream    page-view counts from the access-log MapReduce jobs
  hadoop_jobs    job metadata (duration, counters), cluster config and the scalability benchmark
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from pymongo import ASCENDING, DESCENDING, MongoClient

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "hadoop" / "results"
DOCS = ROOT / "docs" / "results"

ORDER_COLS = ["order_id", "order_ts", "order_ym", "order_dow", "order_hour", "payment_type",
              "shipping_mode", "days_real", "days_scheduled", "delay_days", "delivery_status",
              "is_late", "is_canceled", "market", "order_region", "order_country", "order_state",
              "customer_segment", "order_status", "customer_id", "n_items", "total_qty",
              "total_sales", "total_profit", "main_category", "main_department"]


def db():
    return MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017"))[os.environ.get("MONGO_DB", "delaylens")]


def main() -> None:
    t0 = time.time()
    d = db()
    for c in ["orders", "order_items", "kpis", "scenarios", "clickstream", "hadoop_jobs", "model_metrics"]:
        d[c].drop()

    items = pd.read_csv(ROOT / "data/processed/order_items.csv")
    orders = pd.read_csv(ROOT / "data/processed/orders_mr.tsv", sep="\t", names=ORDER_COLS)
    seg = {r["key"]: r["late_pct"] for r in json.loads((RES / "kpi_order_region_mode.json").read_text())}

    # order_items: flat documents
    items_docs = items.drop(columns=["order_country_raw"]).to_dict("records")
    for r in items_docs:
        r["order_ts"] = datetime.fromisoformat(r["order_ts"])
        r["ship_ts"] = datetime.fromisoformat(r["ship_ts"])
    d.order_items.insert_many(items_docs, ordered=False)

    # orders: nested documents with the item list embedded (denormalised read model)
    lines = {}
    for r in items[["order_id", "product_name", "category", "department", "quantity", "unit_price",
                    "discount_rate", "sales", "profit"]].itertuples(index=False):
        lines.setdefault(r.order_id, []).append({
            "product": r.product_name, "category": r.category, "department": r.department,
            "qty": int(r.quantity), "unit_price": float(r.unit_price), "discount_rate": float(r.discount_rate),
            "sales": float(r.sales), "profit": float(r.profit)})
    docs = []
    for o in orders.itertuples(index=False):
        docs.append({
            "_id": int(o.order_id),
            "order_ts": datetime.fromisoformat(o.order_ts), "order_ym": o.order_ym,
            "order_dow": int(o.order_dow), "order_hour": int(o.order_hour),
            "customer": {"id": int(o.customer_id), "segment": o.customer_segment},
            "payment_type": o.payment_type, "order_status": o.order_status,
            "shipping": {"mode": o.shipping_mode, "days_scheduled": int(o.days_scheduled),
                         "days_real": int(o.days_real), "delay_days": int(o.delay_days),
                         "status": o.delivery_status, "is_late": int(o.is_late), "is_canceled": int(o.is_canceled)},
            "destination": {"market": o.market, "region": o.order_region, "country": o.order_country,
                            "state": o.order_state},
            "n_items": int(o.n_items), "total_qty": int(o.total_qty),
            "sales": float(o.total_sales), "profit": float(o.total_profit),
            "main_category": o.main_category, "main_department": o.main_department,
            "items": lines.get(o.order_id, []),
            "segment_late_pct": seg.get(f"{o.order_region}|{o.shipping_mode}"),
        })
    d.orders.insert_many(docs, ordered=False)

    # Hadoop KPI outputs
    kpi_docs = []
    for f in sorted(RES.glob("kpi_*.json")):
        _, level, dim = f.stem.split("_", 2)
        if level == "item" and dim == "region":
            dim = "region_items"  # item-level cross-check of the order-level region KPI
        for r in json.loads(f.read_text()):
            doc = {"dimension": dim, "level": level, "source": f"hadoop:/delaylens/out/{f.stem}", **r}
            if "|" in r["key"]:
                a, b = r["key"].split("|", 1)
                first, second = {"region_mode": ("region", "shipping_mode"), "market_mode": ("market", "shipping_mode"),
                                 "mode_scheduled": ("shipping_mode", "scheduled_days")}[dim]
                doc[first], doc[second] = a, b
            kpi_docs.append(doc)
    d.kpis.insert_many(kpi_docs)

    d.scenarios.insert_many([json.loads(f.read_text()) for f in sorted(RES.glob("scenario_*.json"))])

    click_docs = []
    for f in sorted(RES.glob("clicks_*.json")):
        dim = f.stem.split("_", 1)[1]
        click_docs += [{"dimension": dim, **r} for r in json.loads(f.read_text())]
    d.clickstream.insert_many(click_docs)

    jobs = json.loads((DOCS / "hadoop_jobs.json").read_text())
    d.hadoop_jobs.insert_many([{**j, "run": "pipeline"} for j in jobs["jobs"]])
    d.hadoop_jobs.insert_one({"_id": "cluster", **jobs["cluster"], "hdfs_put_seconds": jobs["hdfs_put_seconds"],
                              "total_seconds": jobs["total_seconds"]})
    bench = DOCS / "benchmark.json"
    if bench.exists():
        d.hadoop_jobs.insert_one({"_id": "benchmark", **json.loads(bench.read_text())})

    # indexes that serve the dashboard / agent queries
    d.orders.create_index([("destination.region", ASCENDING), ("shipping.mode", ASCENDING)])
    d.orders.create_index([("segment_late_pct", DESCENDING)])
    d.orders.create_index([("order_status", ASCENDING)])
    d.orders.create_index([("order_ts", ASCENDING)])
    d.orders.create_index([("shipping.status", ASCENDING)])
    d.orders.create_index([("destination.market", ASCENDING)])
    d.order_items.create_index([("order_id", ASCENDING)])
    d.order_items.create_index([("category", ASCENDING)])
    d.kpis.create_index([("dimension", ASCENDING), ("key", ASCENDING)], unique=True)
    d.kpis.create_index([("key", ASCENDING)])
    d.clickstream.create_index([("dimension", ASCENDING), ("views", DESCENDING)])

    counts = {c: d[c].estimated_document_count() for c in d.list_collection_names()}
    stats = d.command("dbstats")
    summary = {"collections": counts, "data_size_mb": round(stats["dataSize"] / 1e6, 1),
               "storage_size_mb": round(stats["storageSize"] / 1e6, 1),
               "index_size_mb": round(stats["indexSize"] / 1e6, 1), "seconds": round(time.time() - t0, 1)}
    (DOCS / "mongo_load.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
