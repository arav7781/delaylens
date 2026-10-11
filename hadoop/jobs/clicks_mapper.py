#!/usr/bin/env python3
"""Clickstream mapper: product page views from the DataCo access logs.

Input columns: ts, ym, hour, dow, department, category, product, ip
DIM = category | department | product | hour | dow | month
Emits key \t 1   (word-count pattern; the reducer sums and is reused as the combiner)
"""
import os
import sys

COL = {"month": 1, "hour": 2, "dow": 3, "department": 4, "category": 5, "product": 6}[os.environ.get("DIM", "category")]
for line in sys.stdin:
    f = line.rstrip("\n").split("\t")
    if len(f) != 8:
        sys.stderr.write("reporter:counter:DelayLens,MalformedLines,1\n")
        continue
    print(f"{f[COL]}\t1")
