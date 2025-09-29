#!/bin/bash
# 通用启动脚本：./run.sh [port]
# 默认端口：8000

PORT=${1:-8000}   # 没传参数就默认 8000

# 查找占用端口的进程
pid=$(lsof -ti:$PORT)

if [ -n "$pid" ]; then
  echo "端口 $PORT 已被进程 $pid 占用，正在结束进程..."
  kill -9 $pid
  echo "已结束进程 $pid"
fi

echo "启动 uvicorn 服务，端口 $PORT ..."
# 后台启动 uvicorn，日志输出到 uvicorn.log
uvicorn apps.api.main:app --reload

# 等待 2 秒，让服务启动
sleep 2

URL="http://127.0.0.1:$PORT/docs"
echo "打开接口文档：$URL"

# 根据系统环境自动打开浏览器
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL"
elif command -v gnome-open >/dev/null 2>&1; then
  gnome-open "$URL"
elif command -v open >/dev/null 2>&1; then
  open "$URL"
else
  echo "请手动在浏览器中访问 $URL"
fi

# 跟随 uvicorn 日志
tail -f uvicorn.log
