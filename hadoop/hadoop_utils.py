"""Helpers to drive the local Hadoop cluster from Python (pipeline runner, benchmark, AI agent)."""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

HADOOP_DIR = Path(__file__).resolve().parent
JOBS = HADOOP_DIR / "jobs"
PY = "/opt/homebrew/bin/python3"
HADOOP_HOME = Path.home() / "opt" / "hadoop-3.5.0"


def hadoop_env() -> dict:
    env = dict(os.environ)
    env["JAVA_HOME"] = "/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"
    env["HADOOP_HOME"] = str(HADOOP_HOME)
    env["HADOOP_CONF_DIR"] = str(HADOOP_DIR / "conf")
    env["HADOOP_LOG_DIR"] = str(Path.home() / "opt" / "hadoop-data" / "logs")
    env["PATH"] = f"{env['JAVA_HOME']}/bin:{HADOOP_HOME}/bin:{HADOOP_HOME}/sbin:/opt/homebrew/bin:" + env.get("PATH", "")
    return env


def streaming_jar() -> str:
    return str(next((HADOOP_HOME / "share/hadoop/tools/lib").glob("hadoop-streaming-*.jar")))


def run(cmd: list[str], check: bool = True, timeout: int = 1800) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, env=hadoop_env(), capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f"command failed ({p.returncode}): {' '.join(cmd)}\n{p.stderr[-3000:]}")
    return p


def hdfs(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["hdfs", "dfs", *args], check=check)


def cluster_up() -> bool:
    try:
        p = run(["hdfs", "dfsadmin", "-report"], check=False, timeout=30)
        return p.returncode == 0 and "Live datanodes (1)" in p.stdout
    except Exception:
        return False


COUNTER_NAMES = [
    "Map input records", "Map output records", "Map output bytes", "Combine input records",
    "Combine output records", "Reduce input groups", "Reduce shuffle bytes", "Reduce input records",
    "Reduce output records", "Launched map tasks", "Launched reduce tasks", "Data-local map tasks",
    "HDFS: Number of bytes read", "HDFS: Number of bytes written", "CPU time spent (ms)",
    "GC time elapsed (ms)", "Total time spent by all map tasks (ms)",
    "Total time spent by all reduce tasks (ms)", "OrdersEmitted", "MalformedLines",
]


def parse_counters(log: str) -> dict:
    out = {}
    for name in COUNTER_NAMES:
        m = re.search(r"^\s*" + re.escape(name) + r"=(\d+)", log, re.M)
        if m:
            out[name] = int(m.group(1))
    m = re.search(r"Running job: (job_\d+_\d+)", log)
    if m:
        out["job_id"] = m.group(1)
    return out


def run_streaming(name: str, inp: str, out: str, mapper: str, reducer: str | None,
                  combiner: str | None = None, env: dict | None = None, reduces: int = 1,
                  files: list[str] | None = None, extra_d: dict | None = None) -> dict:
    """Run one Hadoop Streaming job; returns timing + counters."""
    hdfs("-rm", "-r", "-f", "-skipTrash", out, check=False)
    cmd = ["hadoop", "jar", streaming_jar(), "-D", f"mapreduce.job.name={name}",
           "-D", f"mapreduce.job.reduces={reduces if reducer else 0}"]
    for k, v in (extra_d or {}).items():
        cmd += ["-D", f"{k}={v}"]
    ship = files or sorted({mapper.split()[0], *(x.split()[0] for x in [reducer, combiner] if x)})
    cmd += ["-files", ",".join(str(JOBS / f) for f in ship)]
    cmd += ["-input", inp, "-output", out, "-mapper", f"{PY} {mapper}"]
    if combiner:
        cmd += ["-combiner", f"{PY} {combiner}"]
    if reducer:
        cmd += ["-reducer", f"{PY} {reducer}"]
    for k, v in (env or {}).items():
        cmd += ["-cmdenv", f"{k}={v}"]
    t0 = time.time()
    p = run(cmd, check=False)
    secs = time.time() - t0
    if p.returncode != 0:
        raise RuntimeError(f"job {name} failed:\n{p.stderr[-4000:]}")
    return {"name": name, "input": inp, "output": out, "seconds": round(secs, 2),
            "counters": parse_counters(p.stderr), "engine": "hadoop-streaming"}


def run_java_kpi(name: str, inp: str, out: str, key_col: int, combiner: bool = True) -> dict:
    hdfs("-rm", "-r", "-f", "-skipTrash", out, check=False)
    cmd = ["hadoop", "jar", str(HADOOP_DIR / "java" / "delaylens-mr.jar"), "DelayKpiJob",
           "-D", f"delaylens.key.col={key_col}", "-D", f"mapreduce.job.name={name}", inp, out]
    t0 = time.time()
    p = run(cmd, check=False)
    secs = time.time() - t0
    if p.returncode != 0:
        raise RuntimeError(f"java job {name} failed:\n{p.stderr[-4000:]}")
    return {"name": name, "input": inp, "output": out, "seconds": round(secs, 2),
            "counters": parse_counters(p.stderr), "engine": "java-mapreduce"}


def cat_output(out: str) -> list[list[str]]:
    p = run(["hdfs", "dfs", "-cat", f"{out}/part-*"])
    return [line.split("\t") for line in p.stdout.splitlines() if line.strip()]


KPI_FIELDS = ["key", "orders", "late", "on_time", "advance", "canceled", "late_pct", "on_time_pct",
              "canceled_pct", "avg_delay_days", "avg_delay_when_late", "avg_real_days",
              "avg_scheduled_days", "sales", "profit"]


def kpi_rows(out: str) -> list[dict]:
    rows = []
    for f in cat_output(out):
        r = dict(zip(KPI_FIELDS, f))
        for k in KPI_FIELDS[1:6]:
            r[k] = int(r[k])
        for k in KPI_FIELDS[6:]:
            r[k] = float(r[k])
        rows.append(r)
    return rows
