#!/bin/bash
# 一键停止 uvicorn 服务（所有端口）

# 查找所有 uvicorn 进程
pids=$(ps aux | grep "[u]vicorn apps.api.main:app" | awk '{print $2}')

if [ -z "$pids" ]; then
  echo "没有发现正在运行的 uvicorn 服务。"
  exit 0
fi

echo "发现以下 uvicorn 进程：$pids"
for pid in $pids; do
  echo "结束进程 $pid..."
  kill -9 $pid
done

echo "所有 uvicorn 服务已停止。"
