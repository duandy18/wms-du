#!/usr/bin/env bash
set -Eeuo pipefail
: "${WMS_PORT:=8000}"

echo "[ping]";          curl -fsS "http://127.0.0.1:${WMS_PORT}/ping" | jq .
echo "[visible:1]";    curl -fsS "http://127.0.0.1:${WMS_PORT}/stores/1/visible" | jq .
echo "[snapshot/run]"; curl -fsS -X POST "http://127.0.0.1:${WMS_PORT}/snapshot/run" | jq .
echo "OK"
