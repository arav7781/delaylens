"""Step 3: load the cleaned data into HDFS and run every MapReduce job on YARN.

  1. hdfs dfs -put   cleaned order items + access logs
  2. Job A           order roll-up (order items -> one record per order)      [ETL, chained]
  3. KPI jobs        delivery KPIs per dimension on the Job A output (orders)  [aggregation]
  4. KPI jobs        per product category / department / product (items)
  5. Click jobs      product page views from the access logs
  6. SLA scenarios   promise-policy what-if: re-score every order against new promised days
  7. Java job        native MapReduce version of the region KPI (cross-check)

Results -> hadoop/results/*.json and docs/results/hadoop_jobs.json
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hadoop_utils as H  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "hadoop" / "results"
DOCS = ROOT / "docs" / "results"
RES.mkdir(parents=True, exist_ok=True)
DOCS.mkdir(parents=True, exist_ok=True)

BASE = "/delaylens"
ORDER_DIMS = ["all", "region", "market", "shipping_mode", "segment", "month", "delivery_status",
              "country", "payment_type", "dow", "hour", "order_status", "region_mode", "market_mode",
              "mode_scheduled", "scheduled_days"]
ITEM_DIMS = ["category", "department", "product", "region"]
CLICK_DIMS = ["category", "department", "product", "hour", "month", "dow"]
# promise-policy what-if scenarios (cumulative); SLA = new promised days per shipping mode
SCENARIOS = {
    "S0_current": ("Current promises (First 1d, Second 2d, Standard 4d, Same Day 0d)", {}),
    "S1_first2": ("First Class promised 2 days", {"SLA": "First_Class=2"}),
    "S2_second4": ("+ Second Class promised 4 days", {"SLA": "First_Class=2,Second_Class=4"}),
    "S3_sameday_cutoff": ("+ Same Day orders after 12:00 promised next day",
                          {"SLA": "First_Class=2,Second_Class=4", "CUTOFF": "12"}),
    "S4_standard5": ("+ Standard Class promised 5 days",
                     {"SLA": "First_Class=2,Second_Class=4,Standard_Class=5", "CUTOFF": "12"}),
}


def kpi_job(level: str, dim: str) -> dict:
    src = f"{BASE}/out/orders" if level == "order" else f"{BASE}/raw/order_items"
    out = f"{BASE}/out/kpi_{level}_{dim}"
    info = H.run_streaming(
        f"delaylens-kpi-{level}-{dim}", src, out, "kpi_mapper.py", "kpi_reducer.py final",
        combiner="kpi_reducer.py combine", env={"LEVEL": level, "DIM": dim}, reduces=2)
    rows = H.kpi_rows(out)
    (RES / f"kpi_{level}_{dim}.json").write_text(json.dumps(rows, indent=1))
    info.update(level=level, dim=dim, groups=len(rows))
    print(f"  kpi {level}/{dim}: {len(rows)} groups in {info['seconds']}s", flush=True)
    return info


def click_job(dim: str) -> dict:
    out = f"{BASE}/out/clicks_{dim}"
    info = H.run_streaming(f"delaylens-clicks-{dim}", f"{BASE}/raw/access_logs", out,
                           "clicks_mapper.py", "sum_reducer.py", combiner="sum_reducer.py",
                           env={"DIM": dim}, reduces=1)
    rows = [{"key": k, "views": int(v)} for k, v in H.cat_output(out)]
    rows.sort(key=lambda r: -r["views"])
    (RES / f"clicks_{dim}.json").write_text(json.dumps(rows, indent=1))
    info.update(level="clicks", dim=dim, groups=len(rows))
    print(f"  clicks/{dim}: {len(rows)} groups in {info['seconds']}s", flush=True)
    return info


def scenario_job(name: str) -> dict:
    label, env = SCENARIOS[name]
    out = f"{BASE}/out/scenario_{name}"
    info = H.run_streaming(f"delaylens-sla-{name}", f"{BASE}/out/orders", out, "kpi_mapper.py",
                           "kpi_reducer.py final", combiner="kpi_reducer.py combine",
                           env={"LEVEL": "order", "DIM": "shipping_mode", **env}, reduces=1)
    rows = H.kpi_rows(out)
    (RES / f"scenario_{name}.json").write_text(json.dumps({"name": name, "label": label, "policy": env,
                                                           "rows": rows}, indent=1))
    info.update(level="scenario", dim=name, groups=len(rows))
    print(f"  scenario {name}: {sum(r['late'] for r in rows)} late orders in {info['seconds']}s", flush=True)
    return info


def main() -> None:
    if not H.cluster_up():
        sys.exit("Hadoop is not running: ./hadoop/start-hadoop.sh")
    t_all = time.time()
    jobs = []

    print("[1] loading HDFS", flush=True)
    H.hdfs("-mkdir", "-p", f"{BASE}/raw/order_items", f"{BASE}/raw/access_logs", f"{BASE}/out")
    t0 = time.time()
    H.hdfs("-put", "-f", str(ROOT / "data/processed/order_items.tsv"), f"{BASE}/raw/order_items/")
    H.hdfs("-put", "-f", str(ROOT / "data/processed/access_logs.tsv"), f"{BASE}/raw/access_logs/")
    put_secs = round(time.time() - t0, 2)
    fsck = H.run(["hdfs", "fsck", f"{BASE}/raw", "-files", "-blocks"], check=False).stdout
    blocks = {line.split()[0]: line for line in fsck.splitlines() if line.startswith(f"{BASE}/raw/") and "bytes" in line}
    print(f"  put in {put_secs}s", flush=True)

    print("[2] Job A: order roll-up", flush=True)
    a = H.run_streaming("delaylens-order-rollup", f"{BASE}/raw/order_items", f"{BASE}/out/orders",
                        "order_rollup_mapper.py", "order_rollup_reducer.py", reduces=2)
    a.update(level="etl", dim="order_id")
    jobs.append(a)
    print(f"  orders emitted: {a['counters'].get('OrdersEmitted')} in {a['seconds']}s", flush=True)
    H.run(["bash", "-c", f"hdfs dfs -cat {BASE}/out/orders/part-* > {ROOT}/data/processed/orders_mr.tsv"])

    print("[3-6] KPI, clickstream and SLA-scenario jobs (3 concurrent on YARN)", flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = [pool.submit(kpi_job, "order", d) for d in ORDER_DIMS]
        futs += [pool.submit(kpi_job, "item", d) for d in ITEM_DIMS]
        futs += [pool.submit(click_job, d) for d in CLICK_DIMS]
        futs += [pool.submit(scenario_job, n) for n in SCENARIOS]
        jobs += [f.result() for f in futs]

    print("[7] native Java MapReduce cross-check", flush=True)
    j = H.run_java_kpi("delaylens-java-kpi-region", f"{BASE}/raw/order_items", f"{BASE}/out/java_region", 16)
    j_rows = [dict(zip(["key", "items", "late", "late_pct", "avg_delay_days"], r)) for r in H.cat_output(f"{BASE}/out/java_region")]
    (RES / "java_kpi_item_region.json").write_text(json.dumps(j_rows, indent=1))
    j.update(level="item", dim="region", groups=len(j_rows))
    jobs.append(j)

    summary = {
        "cluster": {"mode": "pseudo-distributed (single node)", "hadoop": "3.5.0", "java": "OpenJDK 17",
                    "hdfs_block_size_mb": 16, "replication": 1, "yarn_memory_mb": 8192, "yarn_vcores": 8},
        "hdfs_put_seconds": put_secs,
        "hdfs_files": blocks,
        "jobs": jobs,
        "total_seconds": round(time.time() - t_all, 1),
    }
    (DOCS / "hadoop_jobs.json").write_text(json.dumps(summary, indent=2))
    print(f"done: {len(jobs)} jobs in {summary['total_seconds']}s")


if __name__ == "__main__":
    main()
