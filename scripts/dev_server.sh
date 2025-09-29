#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8000}"

# 清理端口（如果被占用）
PIDS=$(lsof -ti :$PORT || true)
if [ -n "$PIDS" ]; then
  echo "杀掉占用 $PORT 的进程: $PIDS"
  kill -9 $PIDS
fi

echo "启动 uvicorn 在端口 $PORT ..."
uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload > uvicorn.log 2>&1 & echo $! > uvicorn.pid
echo "✅ 已启动 (PID=$(cat uvicorn.pid))，日志写入 uvicorn.log"
