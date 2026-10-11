#!/usr/bin/env python3
"""Generic delivery-KPI mapper (Hadoop Streaming).

Environment (passed with -cmdenv):
  LEVEL   order | item      which input layout is being read (Job A output or cleaned items)
  DIM     the grouping dimension, e.g. region, shipping_mode, category, region_mode
  FILTER  optional "field=value;field=value" equality filter (used by the AI agent's ad-hoc jobs)
  SLA     optional promise-policy what-if, e.g. "First_Class=2,Second_Class=4": re-scores every
          shipped order against the new promised days (late = actual days > promised days)
  CUTOFF  optional hour, e.g. "12": Same Day orders placed at/after it are promised next day (1 day)

Emits:  key \t count,late,on_time,advance,canceled,delay_sum,late_delay_sum,real_sum,sched_sum,sales,profit
The value is a vector of sums, so the same reducer can run as a combiner.
"""
import os
import sys

ORDER_COLS = ["order_id", "order_ts", "order_ym", "order_dow", "order_hour", "payment_type",
              "shipping_mode", "days_real", "days_scheduled", "delay_days", "delivery_status",
              "is_late", "is_canceled", "market", "order_region", "order_country", "order_state",
              "customer_segment", "order_status", "customer_id", "n_items", "total_qty",
              "total_sales", "total_profit", "category", "department"]
ITEM_COLS = ["order_id", "order_item_id", "customer_id", "order_ts", "order_ym", "order_dow",
             "order_hour", "payment_type", "shipping_mode", "days_real", "days_scheduled",
             "delay_days", "delivery_status", "is_late", "is_canceled", "market", "order_region",
             "order_country", "order_state", "customer_segment", "category", "department",
             "product_name", "quantity", "unit_price", "discount_rate", "total_sales",
             "item_total", "total_profit", "order_status"]

# dimension name -> column(s) forming the key
DIMS = {
    "all": [], "region": ["order_region"], "market": ["market"], "shipping_mode": ["shipping_mode"],
    "segment": ["customer_segment"], "month": ["order_ym"], "delivery_status": ["delivery_status"],
    "country": ["order_country"], "payment_type": ["payment_type"], "dow": ["order_dow"],
    "hour": ["order_hour"], "order_status": ["order_status"], "category": ["category"],
    "department": ["department"], "product": ["product_name"], "scheduled_days": ["days_scheduled"],
    "region_mode": ["order_region", "shipping_mode"], "market_mode": ["market", "shipping_mode"],
    "mode_scheduled": ["shipping_mode", "days_scheduled"], "state": ["order_state"],
}

level = os.environ.get("LEVEL", "order")
cols = ORDER_COLS if level == "order" else ITEM_COLS
idx = {c: i for i, c in enumerate(cols)}
dim = os.environ.get("DIM", "region")
key_idx = [idx[c] for c in DIMS[dim]]
filters = []
for part in filter(None, os.environ.get("FILTER", "").split(";")):
    k, v = part.split("=", 1)
    filters.append((idx[k.strip()], v.strip()))
sla = {}
for part in filter(None, os.environ.get("SLA", "").split(",")):
    k, v = part.split("=", 1)
    sla[k.replace("_", " ").strip()] = float(v)
cutoff = int(os.environ["CUTOFF"]) if os.environ.get("CUTOFF") else None

for line in sys.stdin:
    f = line.rstrip("\n").split("\t")
    if len(f) != len(cols):
        sys.stderr.write("reporter:counter:DelayLens,MalformedLines,1\n")
        continue
    if any(f[i] != v for i, v in filters):
        continue
    status = f[idx["delivery_status"]]
    real, sched = float(f[idx["days_real"]]), float(f[idx["days_scheduled"]])
    delay = float(f[idx["delay_days"]])
    if sla or cutoff is not None:
        mode = f[idx["shipping_mode"]]
        sched = sla.get(mode, sched)
        if cutoff is not None and mode == "Same Day" and int(f[idx["order_hour"]]) >= cutoff:
            sched = 1.0
        if status != "Shipping canceled":
            status = "Late delivery" if real > sched else "Shipping on time" if real == sched else "Advance shipping"
        delay = real - sched
    late = 1 if status == "Late delivery" else 0
    key = "|".join(f[i] for i in key_idx) if key_idx else "ALL"
    vec = [1, late, 1 if status == "Shipping on time" else 0, 1 if status == "Advance shipping" else 0,
           1 if status == "Shipping canceled" else 0, delay, delay if late else 0.0, real, sched,
           float(f[idx["total_sales"]]), float(f[idx["total_profit"]])]
    print(key + "\t" + ",".join(f"{v:g}" if isinstance(v, float) else str(v) for v in vec))
