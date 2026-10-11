"""Runs a fixed set of questions through the LangGraph copilot and records tools, latency and answers.

Usage: cd agent && ../.venv/bin/python eval_copilot.py   -> docs/results/copilot_eval.json
Each question has the figure the answer must contain (taken from the Hadoop KPI outputs).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from graph import ask  # noqa: E402

CASES = [
    ("What is our overall late-delivery rate and how many orders were late?", [54.82, 36048]),
    ("Compare shipping modes: promised vs actual days and late %.", [95.27, 76.72, 38.13]),
    ("Among product categories with at least 1,000 order lines, which has the highest late rate?", ["Accessories", 56.97]),
    ("If First Class promised 2 days and Second Class 4 days, what would the late rate be?", [32.78]),
    ("How many open orders are in segments that are late at least 75% of the time, and how much sales is at stake?", [11674]),
    ("In the LATAM market, which shipping mode is late most often?", ["First Class"]),
    ("Which month in 2016 had the highest late-delivery rate?", ["2016-06", 57.28]),
    ("Write me a poem about cats.", []),
]


def main() -> None:
    out = []
    for q, expect in CASES:
        t0 = time.time()
        final = {}
        for ev in ask(q):
            if ev["type"] == "final":
                final = ev
        secs = round(time.time() - t0, 1)
        ans = final.get("answer", "")
        nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", ans)]
        # a number counts when the answer states it at any rounding (54.82 matches 54.8 or 54.82)
        hits = [e for e in expect if (e in ans if isinstance(e, str) else any(abs(n - e) <= 0.051 for n in nums))]
        out.append({"question": q, "tools": [t["tool"] for t in final.get("tools", [])], "seconds": secs,
                    "expected": expect, "found": hits, "pass": len(hits) == len(expect),
                    "llm_ok": final.get("llm_ok"), "answer": ans})
        print(f"{'PASS' if len(hits) == len(expect) else 'CHECK'} {secs:5.1f}s {[t['tool'] for t in final.get('tools', [])]} :: {q}", flush=True)
    (ROOT / "docs/results/copilot_eval.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
