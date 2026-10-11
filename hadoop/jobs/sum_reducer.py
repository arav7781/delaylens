#!/usr/bin/env python3
"""Sums integer counts per key (reducer and combiner for the clickstream jobs)."""
import sys

current, total = None, 0
for line in sys.stdin:
    key, val = line.rstrip("\n").split("\t", 1)
    if key != current:
        if current is not None:
            print(f"{current}\t{total}")
        current, total = key, 0
    total += int(val)
if current is not None:
    print(f"{current}\t{total}")
