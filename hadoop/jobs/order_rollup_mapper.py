#!/usr/bin/env python3
"""Job A (ETL) mapper: order-item line -> (order_id, item payload).

The DataCo file has one line per order *item*; delivery attributes repeat on every item
of an order. Keying by order_id lets the shuffle bring all items of an order together so
the reducer can emit exactly one record per order.
"""
import sys

for line in sys.stdin:
    f = line.rstrip("\n").split("\t")
    if len(f) < 30:
        sys.stderr.write("reporter:counter:DelayLens,MalformedLines,1\n")
        continue
    # order-level attributes (identical on every item of an order)
    order = [f[3], f[4], f[5], f[6], f[7], f[8], f[9], f[10], f[11], f[12], f[13], f[14],
             f[15], f[16], f[17], f[18], f[19], f[29], f[2]]
    # item-level measures
    item = [f[23], f[26], f[28], f[20], f[21]]  # quantity, sales, profit, category, department
    print(f[0] + "\t" + "\t".join(order) + "\t" + "\t".join(item))
