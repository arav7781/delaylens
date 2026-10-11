"""Step 4b: analytical MongoDB queries (results saved for the report and dashboard).

Q1 worst-performing regions (Hadoop KPI collection)
Q2 shipping-mode comparison (aggregation pipeline on orders)
Q3 open orders in segments with a high historical late rate ($lookup into the Hadoop KPIs)
Q4 worst region x shipping-mode combinations (aggregation, min volume)
Q5 monthly trend ($dateToString)
Q6 product categories with the most delay ($unwind embedded items)
Q7 open-order exposure by shipping mode (sales and expected late orders)
Q8 consistency check: MongoDB aggregation vs Hadoop MapReduce output
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
OPEN = ["PENDING", "PENDING_PAYMENT", "PROCESSING", "ON_HOLD", "PAYMENT_REVIEW"]
d = MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017"))[os.environ.get("MONGO_DB", "delaylens")]

QUERIES = {
    "Q1_worst_regions": {
        "shell": "db.kpis.find({dimension:'region'}, {_id:0,key:1,orders:1,late_pct:1,avg_delay_days:1}).sort({late_pct:-1}).limit(5)",
        "run": lambda: list(d.kpis.find({"dimension": "region"},
                                        {"_id": 0, "key": 1, "orders": 1, "late_pct": 1, "avg_delay_days": 1,
                                         "avg_delay_when_late": 1}).sort("late_pct", -1).limit(5)),
    },
    "Q2_shipping_mode_comparison": {
        "shell": "db.orders.aggregate([{$match:{'shipping.is_canceled':0}},{$group:{_id:'$shipping.mode',orders:{$sum:1},late_rate:{$avg:'$shipping.is_late'},avg_sched:{$avg:'$shipping.days_scheduled'},avg_real:{$avg:'$shipping.days_real'},avg_delay:{$avg:'$shipping.delay_days'},sales:{$sum:'$sales'}}},{$sort:{late_rate:-1}}])",
        "run": lambda: list(d.orders.aggregate([
            {"$match": {"shipping.is_canceled": 0}},
            {"$group": {"_id": "$shipping.mode", "orders": {"$sum": 1}, "late_rate": {"$avg": "$shipping.is_late"},
                        "avg_scheduled_days": {"$avg": "$shipping.days_scheduled"},
                        "avg_real_days": {"$avg": "$shipping.days_real"},
                        "avg_delay_days": {"$avg": "$shipping.delay_days"}, "sales": {"$sum": "$sales"}}},
            {"$sort": {"late_rate": -1}}])),
    },
    "Q3_open_orders_high_late_segments": {
        "shell": "db.orders.aggregate([{$match:{order_status:{$in:OPEN}}},{$addFields:{seg:{$concat:['$destination.region','|','$shipping.mode']}}},{$lookup:{from:'kpis',localField:'seg',foreignField:'key',pipeline:[{$match:{dimension:'region_mode'}}],as:'kpi'}},{$unwind:'$kpi'},{$match:{'kpi.late_pct':{$gte:75}}},{$sort:{'kpi.late_pct':-1,sales:-1}},{$limit:10}])",
        "run": lambda: {
            "count": d.orders.count_documents({"order_status": {"$in": OPEN}, "segment_late_pct": {"$gte": 75}}),
            "top": list(d.orders.aggregate([
                {"$match": {"order_status": {"$in": OPEN}}},
                {"$addFields": {"seg": {"$concat": ["$destination.region", "|", "$shipping.mode"]}}},
                {"$lookup": {"from": "kpis", "localField": "seg", "foreignField": "key", "pipeline": [
                    {"$match": {"dimension": "region_mode"}}, {"$project": {"_id": 0, "late_pct": 1, "orders": 1}}],
                    "as": "kpi"}},
                {"$unwind": "$kpi"}, {"$match": {"kpi.late_pct": {"$gte": 75}}},
                {"$project": {"order_ym": 1, "order_status": 1, "shipping.mode": 1, "destination.region": 1,
                              "sales": 1, "segment_late_pct": "$kpi.late_pct"}},
                {"$sort": {"segment_late_pct": -1, "sales": -1}}, {"$limit": 10}])),
        },
    },
    "Q4_worst_region_mode": {
        "shell": "db.orders.aggregate([{$match:{'shipping.is_canceled':0}},{$group:{_id:{region:'$destination.region',mode:'$shipping.mode'},orders:{$sum:1},late_rate:{$avg:'$shipping.is_late'}}},{$match:{orders:{$gte:200}}},{$sort:{late_rate:-1}},{$limit:10}])",
        "run": lambda: list(d.orders.aggregate([
            {"$match": {"shipping.is_canceled": 0}},
            {"$group": {"_id": {"region": "$destination.region", "mode": "$shipping.mode"}, "orders": {"$sum": 1},
                        "late_rate": {"$avg": "$shipping.is_late"}}},
            {"$match": {"orders": {"$gte": 200}}}, {"$sort": {"late_rate": -1}}, {"$limit": 10}])),
    },
    "Q5_monthly_trend": {
        "shell": "db.orders.aggregate([{$group:{_id:{$dateToString:{format:'%Y-%m',date:'$order_ts'}},orders:{$sum:1},late_rate:{$avg:'$shipping.is_late'},sales:{$sum:'$sales'}}},{$sort:{_id:1}}])",
        "run": lambda: list(d.orders.aggregate([
            {"$group": {"_id": {"$dateToString": {"format": "%Y-%m", "date": "$order_ts"}}, "orders": {"$sum": 1},
                        "late_rate": {"$avg": "$shipping.is_late"}, "sales": {"$sum": "$sales"}}},
            {"$sort": {"_id": 1}}])),
    },
    "Q6_category_delay": {
        "shell": "db.orders.aggregate([{$match:{'shipping.is_canceled':0}},{$unwind:'$items'},{$group:{_id:'$items.category',lines:{$sum:1},late_rate:{$avg:'$shipping.is_late'},avg_delay:{$avg:'$shipping.delay_days'}}},{$match:{lines:{$gte:500}}},{$sort:{late_rate:-1}},{$limit:10}])",
        "run": lambda: list(d.orders.aggregate([
            {"$match": {"shipping.is_canceled": 0}}, {"$unwind": "$items"},
            {"$group": {"_id": "$items.category", "lines": {"$sum": 1}, "late_rate": {"$avg": "$shipping.is_late"},
                        "avg_delay_days": {"$avg": "$shipping.delay_days"}}},
            {"$match": {"lines": {"$gte": 500}}}, {"$sort": {"late_rate": -1}}, {"$limit": 10}])),
    },
    "Q7_open_order_exposure": {
        "shell": "db.orders.aggregate([{$match:{order_status:{$in:OPEN}}},{$group:{_id:'$shipping.mode',orders:{$sum:1},sales:{$sum:'$sales'},expected_late:{$sum:{$divide:['$segment_late_pct',100]}}}},{$sort:{expected_late:-1}}])",
        "run": lambda: list(d.orders.aggregate([
            {"$match": {"order_status": {"$in": OPEN}}},
            {"$group": {"_id": "$shipping.mode", "orders": {"$sum": 1}, "sales": {"$sum": "$sales"},
                        "expected_late": {"$sum": {"$divide": ["$segment_late_pct", 100]}}}},
            {"$sort": {"expected_late": -1}}])),
    },
    "Q8_hadoop_vs_mongo_check": {
        "shell": "compare db.kpis region late counts with db.orders.aggregate group-by region",
        "run": lambda: _consistency(),
    },
}


def _consistency() -> dict:
    mongo = {r["_id"]: r for r in d.orders.aggregate([
        {"$group": {"_id": "$destination.region", "orders": {"$sum": 1}, "late": {"$sum": "$shipping.is_late"}}}])}
    hadoop = {r["key"]: r for r in d.kpis.find({"dimension": "region", "level": "order"})}
    mismatches = [k for k in hadoop if hadoop[k]["orders"] != mongo.get(k, {}).get("orders")
                  or hadoop[k]["late"] != mongo.get(k, {}).get("late")]
    return {"regions_compared": len(hadoop), "mismatches": mismatches,
            "orders_total_hadoop": sum(r["orders"] for r in hadoop.values()),
            "orders_total_mongo": sum(r["orders"] for r in mongo.values())}


def main() -> None:
    out = {}
    for name, q in QUERIES.items():
        t0 = time.time()
        res = q["run"]()
        out[name] = {"shell": q["shell"], "ms": round(1000 * (time.time() - t0), 1), "result": res}
        print(f"{name}: {out[name]['ms']} ms")
    plan = d.orders.find({"destination.region": "Western Europe", "shipping.mode": "First Class"}).explain()
    out["index_check"] = {"query": "orders.find({destination.region, shipping.mode})",
                          "winning_plan": json.dumps(plan["queryPlanner"]["winningPlan"])[:400]}
    (ROOT / "docs/results/mongo_queries.json").write_text(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
