#!/usr/bin/env bash
set -euo pipefail
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
