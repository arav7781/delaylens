#!/usr/bin/env bash
# End-to-end pipeline. Prereqs: Docker (MongoDB), JDK 17, Hadoop 3.5.0 in ~/opt (see README).
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
PY=.venv/bin/python

docker start delaylens-mongo >/dev/null 2>&1 || docker run -d --name delaylens-mongo -p 27017:27017 -v delaylens-mongo-data:/data/db mongo:7.0
./hadoop/start-hadoop.sh

$PY scripts/01_profile_clean.py      # Step 1-2  profile + clean        -> data/processed
$PY hadoop/run_pipeline.py           # Step 3    HDFS + MapReduce jobs  -> hadoop/results
$PY hadoop/benchmark.py              #           scalability benchmark  -> docs/results/benchmark.json
$PY mongo/load_mongo.py              # Step 4    MongoDB load
$PY mongo/queries.py                 #           analytical queries     -> docs/results/mongo_queries.json
echo "Now start the API (scripts/start_app.sh) and open http://localhost:3000"
