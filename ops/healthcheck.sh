#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
#  WMS-DU Healthcheck (v1.0  强契约)
#  - 严格校验所有核心接口
#  - 任一接口非 2xx 即退出
# ============================================================

: "${WMS_PORT:=8000}"
: "${WMS_HOST:=127.0.0.1}"
BASE="http://${WMS_HOST}:${WMS_PORT}"

_green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
_red()   { printf '\033[0;31m%s\033[0m\n' "$*"; }
_gray()  { printf '\033[0;90m%s\033[0m\n' "$*"; }

_check() {
  local name=$1 path=$2
  _gray "→ ${name} (${path})"
  local start end code
  start=$(date +%s%3N)
  set +e
  local resp
  resp=$(curl -s -w "\n%{http_code}" "${BASE}${path}")
  code=$(echo "$resp" | tail -n1)
  set -e
  end=$(date +%s%3N)
  local cost=$((end - start))
  if [[ "$code" =~ ^2 ]]; then
    _green "✓ ${name} OK (${cost} ms)"
  else
    _red "✗ ${name} FAILED (HTTP ${code})"
    echo "Response:"
    echo "$resp" | head -n -1
    exit 1
  fi
}

echo "== WMS-DU Healthcheck @ ${BASE} =="

_check "Ping"                "/ping"
_check "Stores Visible"      "/stores/1/visible"
_check "Snapshot Inventory"  "/snapshot/inventory"

echo
_green "✅ All core endpoints healthy."
