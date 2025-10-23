#!/usr/bin/env bash
set -euo pipefail
ports=(
  "${API_HOST_PORT:-8001}"
  "${PROM_HOST_PORT:-9090}"
  "${GRAFANA_HOST_PORT:-3000}"
  "${REDIS_HOST_PORT:-6379}"
  "5433"
)
names=("API" "Prometheus" "Grafana" "Redis" "Postgres(wms-du-db)")
for i in "${!ports[@]}"; do
  p="${ports[$i]}"; n="${names[$i]}"
  if sudo lsof -iTCP:$p -sTCP:LISTEN -nP >/dev/null 2>&1; then
    echo "[占用] $n 端口 $p 被以下进程/容器占用："
    sudo lsof -iTCP:$p -sTCP:LISTEN -nP || true
    docker ps --format 'table {{.ID}}\t{{.Names}}\t{{.Ports}}' | grep -E ":$p->|:$p " || true
    echo
  else
    echo "[空闲] $n 端口 $p 空闲"
  fi
done
