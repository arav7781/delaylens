# DelayLens — Agentic Big Data analytics for delivery delays

BDA CA3 case study. Hadoop MapReduce computes delivery KPIs from the DataCo Smart Supply Chain dataset,
MongoDB serves them, a LangGraph agent answers questions over them, and a Next.js dashboard shows them.

```
DataCo CSV ─▶ Python cleaning ─▶ HDFS ─▶ MapReduce on YARN (33 jobs) ─▶ MongoDB ─▶ FastAPI + LangGraph agent ─▶ Next.js dashboard
                                              ▲                                        │
                                              └──────── run_hadoop_job (live job) ─────┘
```

## Layout

| Path | What |
| --- | --- |
| `scripts/01_profile_clean.py` | Profile + clean the raw CSVs, write HDFS-ready TSVs (`data/processed/`) |
| `hadoop/conf/`, `hadoop/env.sh`, `hadoop/start-hadoop.sh` | Pseudo-distributed Hadoop 3.5.0 config (HDFS :9820, YARN :8088) |
| `hadoop/jobs/*.py` | Hadoop Streaming mappers/reducers (order roll-up, generic KPI with combiner, SLA what-if, clickstream) |
| `hadoop/java/DelayKpiJob.java` | Native Java MapReduce job (custom Writable + combiner) |
| `hadoop/run_pipeline.py` | Puts data on HDFS and runs all 33 jobs; results in `hadoop/results/` |
| `hadoop/benchmark.py` | Scalability benchmark 0.25x–16x: Streaming vs Java vs pandas, combiner on/off |
| `mongo/load_mongo.py`, `mongo/queries.py`, `mongo/queries.js` | MongoDB load, indexes, analytical queries (Python and mongosh) |
| `agent/llm_client.py` | OpenAI-compatible gateway client (`build_llm_client`, `complete`, `chat_stream`, `chat_tools`) |
| `agent/tools.py`, `agent/graph.py` | 9 agent tools and the LangGraph StateGraph (planner → tools → analyst, fallback) |
| `agent/server.py` | FastAPI: dashboard endpoints + `/api/chat` (server-sent events) |
| `agent/eval_copilot.py` | Copilot evaluation (8 questions with known answers) |
| `web/` | Next.js 16 dashboard (8 pages + copilot drawer) |
| `docs/results/` | All measured outputs (profile, job counters, benchmark, query timings, copilot eval) |

## Run it

Prerequisites: Docker (colima), Homebrew `openjdk@17`, Hadoop 3.5.0 extracted to `~/opt/hadoop-3.5.0`,
Python 3.11 venv in `.venv` (`pip install pandas pymongo fastapi "uvicorn[standard]" "openai>=1.55" langgraph python-dotenv`),
Node 20+. Put the LLM settings in `.env` (never commit it):

```
LLM_BASE_URL=https://<your-openai-compatible-gateway>
LLM_API_KEY=<your-api-key>   # see .env.example
CHAT_MODEL=<model-name>
MONGO_URI=mongodb://localhost:27017
MONGO_DB=delaylens
```

```bash
./scripts/run_all.sh          # MongoDB container + Hadoop daemons + clean + 33 MapReduce jobs + benchmark + load + queries
./scripts/start_app.sh        # API on :8000, dashboard on :3000
# or step by step:
./hadoop/start-hadoop.sh
.venv/bin/python scripts/01_profile_clean.py
.venv/bin/python hadoop/run_pipeline.py
.venv/bin/python mongo/load_mongo.py && .venv/bin/python mongo/queries.py
cd agent && ../.venv/bin/python -m uvicorn server:app --port 8000
cd web && npm run dev
```

Useful URLs: NameNode http://localhost:9870 · YARN http://localhost:8088 · JobHistory http://localhost:19888 ·
API docs http://localhost:8000/docs · Dashboard http://localhost:3000 · demo question http://localhost:3000/copilot?q=...

Demo commands for the viva:

```bash
source hadoop/env.sh && jps                                   # 5 Hadoop daemons
hdfs dfs -ls -R /delaylens | head                             # data and job outputs on HDFS
hdfs fsck /delaylens/raw -files -blocks | head                # 16 MB blocks
hdfs dfs -cat /delaylens/out/kpi_order_shipping_mode/part-*   # a MapReduce result
docker exec -i delaylens-mongo mongosh delaylens --quiet < mongo/queries.js
cd agent && ../.venv/bin/python graph.py "Run a live Hadoop job: late % by state for the USCA market"
```

## Key results

* 65,752 orders (180,519 lines), Jan 2015 – Jan 2018: **54.8% late**, 23.0% early, 17.8% on time, 4.3% canceled.
* Shipping mode drives lateness: First Class promised 1 day, always takes 2 → 95.3% late; Second Class 76.7%;
  Same Day 46.2% (orders after 12:00 always late, before 12:00 never); Standard Class 38.1%.
* Regions (49.5%–57.6%), markets (54.1%–55.3%), categories, segments, weekdays barely differ.
* Promise what-if (Hadoop scenario jobs): First Class 2d + Second Class 4d + Same Day 12:00 cutoff → **30.3%**; + Standard 5d → 18.9%.
* 11,674 open orders ($6.58M) sit in segments that are late ≥ 75% of the time.
* Hadoop vs MongoDB and Java vs Streaming outputs match exactly; copilot answered 8/8 test questions correctly.

## Viva cheat-sheet

* **Why MapReduce here?** Many group-by aggregations over the same records; map tasks run per HDFS block in parallel;
  the combiner pre-aggregates on the map side (shuffle shrinks from MB to KB).
* **Why is the reducer also the combiner?** The value is a vector of sums: addition is associative and commutative.
* **Why Job A (order roll-up)?** The file is per order line; delivery facts repeat on every line. Rolling up by order_id
  gives order-level KPIs (65,752 orders), otherwise multi-line orders would be over-weighted.
* **Why 16 MB blocks?** So the 45 MB file splits into 3 blocks / 3 map tasks and parallelism is visible on one node.
* **Why is pandas faster in the benchmark?** One machine, small data: each MapReduce job pays ~20 s of JVM/YARN
  start-up. MapReduce wins when data no longer fits one machine's memory/disk or the cluster has many nodes.
* **Why MongoDB?** Orders are nested documents (embedded items); KPI outputs have different shapes per dimension;
  aggregation pipelines + indexes answer ad-hoc questions in milliseconds for the dashboard and the agent.
* **What makes the copilot "agentic"?** The LLM plans which tools to call, sees the results, can call more tools
  (up to 4 rounds), and can launch a new MapReduce job; LangGraph makes the loop explicit and inspectable.
* **How do you stop hallucinated numbers?** Tools return the data; the analyst prompt allows only numbers present in
  tool results; arguments are whitelisted; answers name their source job; an evaluation set checks the figures.
* **Why no ML model?** Lateness follows fixed promise rules per shipping mode; a what-if simulation explains and fixes
  it more directly than a classifier.

## Documents

| File | What it is |
| --- | --- |
| `docs/DelayLens_BDA_Case_Study_Report.pdf` | Case study report (cover page + 10 sections) |
| `docs/DelayLens_Presentation.pptx` / `.pdf` / `.html` | 10-slide presentation (PowerPoint, PDF, and an HTML deck with arrow-key navigation) |
| `docs/DelayLens_Viva_Preparation_Guide.pdf` | Viva guide: all 33 Hadoop jobs explained, diagrams, 64 questions with model answers |

Secrets: copy `.env.example` to `.env` and add your own LLM gateway settings. `.env` is git-ignored and no key is stored in this repository.
