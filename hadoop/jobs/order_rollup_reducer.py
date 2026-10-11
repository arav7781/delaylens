#!/usr/bin/env python3
"""Job A (ETL) reducer: all items of one order -> one order record.

Output columns (tab-separated):
order_id, order_ts, order_ym, order_dow, order_hour, payment_type, shipping_mode, days_real,
days_scheduled, delay_days, delivery_status, is_late, is_canceled, market, order_region,
order_country, order_state, customer_segment, order_status, customer_id,
n_items, total_qty, total_sales, total_profit, main_category, main_department
"""
import sys

current, header = None, None
n_items = qty = 0
sales = profit = 0.0
cat_sales = {}
cat_dept = {}


def flush():
    if current is None:
        return
    main_cat = max(cat_sales, key=cat_sales.get)
    print("\t".join([current] + header + [str(n_items), str(qty), f"{sales:.2f}", f"{profit:.2f}",
                                          main_cat, cat_dept[main_cat]]))
    sys.stderr.write("reporter:counter:DelayLens,OrdersEmitted,1\n")


for line in sys.stdin:
    f = line.rstrip("\n").split("\t")
    key = f[0]
    if key != current:
        flush()
        current, header = key, f[1:20]
        n_items = qty = 0
        sales = profit = 0.0
        cat_sales, cat_dept = {}, {}
    q, s, p, cat, dept = f[20], f[21], f[22], f[23], f[24]
    n_items += 1
    qty += int(float(q))
    sales += float(s)
    profit += float(p)
    cat_sales[cat] = cat_sales.get(cat, 0.0) + float(s)
    cat_dept[cat] = dept
flush()
