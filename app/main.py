# app/main.py
from __future__ import annotations

import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# 统一装配口：仅从 app/api/router.py 引入总路由
from app.api.router import api_router

# 业务异常与处理器（来自 app/api/errors.py）
try:
    from app.api.errors import BizError, biz_error_handler  # 自定义业务异常与返回格式
except Exception:  # 兼容无该模块的场景
    BizError = None
    biz_error_handler = None

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("wmsdu")

app = FastAPI(title="WMS-DU API", version="1.1.0")

# CORS：按你的前端默认端口配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局异常兜底（未捕获异常 → 500）
@app.exception_handler(Exception)
async def _unhandled_exc(_req: Request, exc: Exception):
    logger.exception("UNHANDLED EXC: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "INTERNAL_SERVER_ERROR"})

# 只挂总路由（api_router 会统一 include app/api/routers/* 下的所有 router）
app.include_router(api_router)

# 注册业务异常处理器（若存在）
if BizError and biz_error_handler:
    app.add_exception_handler(BizError, biz_error_handler)

# 探活
@app.get("/ping")
async def ping():
    return {"status": "ok"}
