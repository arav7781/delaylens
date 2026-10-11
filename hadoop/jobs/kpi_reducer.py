#!/usr/bin/env python3
"""Generic delivery-KPI reducer / combiner (Hadoop Streaming).

  kpi_reducer.py combine   -> sums the vectors, same format as the mapper (safe as a combiner)
  kpi_reducer.py final     -> sums and derives the KPIs:

key, orders, late, on_time, advance, canceled, late_pct, on_time_pct, canceled_pct,
avg_delay_days, avg_delay_when_late, avg_real_days, avg_scheduled_days, sales, profit
"""
import sys

mode = sys.argv[1] if len(sys.argv) > 1 else "final"
current, acc = None, None


def emit(key, a):
    if key is None:
        return
    if mode == "combine":
        print(key + "\t" + ",".join(f"{v:g}" if isinstance(v, float) else str(int(v)) for v in a))
        return
    n, late, on_time, adv, canc, dsum, ldsum, rsum, ssum, sales, profit = a
    n = int(n)
    out = [key, n, int(late), int(on_time), int(adv), int(canc),
           round(100 * late / n, 2), round(100 * (on_time + adv) / n, 2), round(100 * canc / n, 2),
           round(dsum / n, 3), round(ldsum / late, 3) if late else 0.0,
           round(rsum / n, 3), round(ssum / n, 3), round(sales, 2), round(profit, 2)]
    print("\t".join(str(v) for v in out))


for line in sys.stdin:
    key, val = line.rstrip("\n").split("\t", 1)
    vec = [float(x) for x in val.split(",")]
    if key != current:
        emit(current, acc)
        current, acc = key, vec
    else:
        acc = [x + y for x, y in zip(acc, vec)]
emit(current, acc)
