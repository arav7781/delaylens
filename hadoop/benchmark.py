"""Scalability benchmark: processing time vs. data volume.

The DataCo file (180,519 item rows, ~50 MB) is sampled down (0.25x, 0.5x) and replicated up
(2x, 4x, 8x, with order ids shifted per copy) to show how the MapReduce jobs scale. For each size:
  * Hadoop Streaming (Python) KPI job, region dimension, with combiner
  * native Java MapReduce KPI job, region dimension, with combiner
  * single-process pandas group-by baseline (read + aggregate)
Combiner effect: Streaming job without the combiner at 1x and 8x (shuffle bytes, time).
Output: docs/results/benchmark.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hadoop_utils as H  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/processed/order_items.tsv"
SCALED = ROOT / "data/scaled"
SCALED.mkdir(parents=True, exist_ok=True)
COLS = (ROOT / "data/processed/order_items.schema").read_text().strip().split("\t")
SIZES = [0.25, 0.5, 1, 2, 4, 8]


def make(scale: float) -> Path:
    path = SCALED / f"items_x{scale}.tsv"
    if path.exists():
        return path
    lines = SRC.read_text().splitlines(keepends=True)
    if scale < 1:
        path.write_text("".join(lines[: int(len(lines) * scale)]))
        return path
    with path.open("w") as out:
        for k in range(int(scale)):
            for line in lines:
                f = line.split("\t", 2)
                out.write(f"{int(f[0]) + k * 100000}\t{int(f[1]) + k * 1000000}\t{f[2]}")
    return path


def pandas_baseline(path: Path) -> float:
    t0 = time.time()
    df = pd.read_csv(path, sep="\t", names=COLS, usecols=["order_region", "delivery_status", "delay_days"])
    df["late"] = df["delivery_status"].eq("Late delivery")
    df.groupby("order_region").agg(items=("late", "size"), late=("late", "sum"), delay=("delay_days", "mean"))
    return round(time.time() - t0, 2)


def main() -> None:
    # optional: python benchmark.py 1 16  -> (re)measure only these sizes and merge into the saved results
    sizes = [float(a) if "." in a else int(a) for a in sys.argv[1:]] or SIZES
    out_path = ROOT / "docs/results/benchmark.json"
    keep = {r["scale"]: r for r in json.loads(out_path.read_text())["rows"]} if out_path.exists() and sys.argv[1:] else {}
    rows = []
    for s in sizes:
        path = make(s)
        hd = f"/delaylens/bench/x{s}"
        H.hdfs("-mkdir", "-p", hd)
        H.hdfs("-put", "-f", str(path), hd + "/")
        n = sum(1 for _ in path.open())
        mb = round(path.stat().st_size / 1e6, 1)
        st = H.run_streaming(f"bench-streaming-x{s}", hd, f"/delaylens/bench_out/st_x{s}", "kpi_mapper.py",
                             "kpi_reducer.py final", combiner="kpi_reducer.py combine",
                             env={"LEVEL": "item", "DIM": "region"}, reduces=2)
        jv = H.run_java_kpi(f"bench-java-x{s}", hd, f"/delaylens/bench_out/java_x{s}", 16)
        pdt = pandas_baseline(path)
        row = {"scale": s, "rows": n, "mb": mb, "map_tasks": st["counters"].get("Launched map tasks"),
               "streaming_s": st["seconds"], "java_s": jv["seconds"], "pandas_s": pdt,
               "streaming_shuffle_bytes": st["counters"].get("Reduce shuffle bytes"),
               "java_shuffle_bytes": jv["counters"].get("Reduce shuffle bytes")}
        if s in (1, 8, 16):
            nc = H.run_streaming(f"bench-streaming-nocombiner-x{s}", hd, f"/delaylens/bench_out/nc_x{s}",
                                 "kpi_mapper.py", "kpi_reducer.py final", combiner=None,
                                 env={"LEVEL": "item", "DIM": "region"}, reduces=2,
                                 files=["kpi_mapper.py", "kpi_reducer.py"])
            row["no_combiner_s"] = nc["seconds"]
            row["no_combiner_shuffle_bytes"] = nc["counters"].get("Reduce shuffle bytes")
        rows.append(row)
        print(json.dumps(row), flush=True)
    for r in rows:
        keep[r["scale"]] = r
    out_path.write_text(json.dumps({
        "job": "late-delivery KPI by order region (item level)",
        "cluster": "single-node pseudo-distributed Hadoop 3.5.0, YARN 8 GB / 8 vcores, 16 MB HDFS blocks",
        "rows": [keep[k] for k in sorted(keep)]}, indent=2))


if __name__ == "__main__":
    main()
