#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
uvicorn app:app --host 0.0.0.0 --port ${DASHBOARD_PORT:-5002} --log-level info
