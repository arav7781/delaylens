#!/usr/bin/env bash
# Starts the FastAPI + LangGraph backend (port 8000) and the Next.js dashboard (port 3000).
set -euo pipefail
cd "$(dirname "$0")/.."
(cd agent && ../.venv/bin/python -m uvicorn server:app --port 8000 > ../agent/api.log 2>&1 &)
(cd web && npm run dev > ../web/dev.log 2>&1 &)
echo "API http://localhost:8000/docs   Dashboard http://localhost:3000"
