#!/usr/bin/env bash
# scripts/kill_uvicorn.sh
# 一键清理占用 8000/8080 的 uvicorn 进程

PORTS=("8000" "8080")

for p in "${PORTS[@]}"; do
  echo ">> 检查端口 $p ..."
  # 查找占用该端口的 PID
  PIDS=$(lsof -ti :$p)
  if [ -n "$PIDS" ]; then
    echo "发现进程: $PIDS (端口 $p)"
    kill -9 $PIDS
    echo "已杀掉 $p 上的进程"
  else
    echo "端口 $p 空闲"
  fi
done

echo "✅ 清理完成"
