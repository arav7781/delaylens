#!/usr/bin/env bash
# Re-runs the batch layer: clean -> Hadoop pipeline -> (optional benchmark sizes) -> MongoDB load -> queries
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
PY=.venv/bin/python
$PY scripts/01_profile_clean.py > docs/results/run_clean.log 2>&1 && echo "clean ok"
$PY hadoop/run_pipeline.py > docs/results/run_pipeline.log 2>&1 && echo "pipeline ok: $(tail -1 docs/results/run_pipeline.log)"
if [ $# -gt 0 ]; then $PY hadoop/benchmark.py "$@" > docs/results/run_benchmark.log 2>&1 && echo "benchmark ok"; fi
$PY mongo/load_mongo.py > docs/results/run_load.log 2>&1 && echo "load ok"
$PY mongo/queries.py > docs/results/run_queries.log 2>&1 && echo "queries ok"
echo REFRESH_DONE
