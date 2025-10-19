# app/main.py
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.endpoints import api_router

app = FastAPI(title="WMS-DU API", version="0.1.0")

# CORS：联调前端用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# （可选）全局异常转 JSON
@app.exception_handler(Exception)
async def _unhandled_exc(_req: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "INTERNAL_SERVER_ERROR", "error": str(exc)},
    )


# 路由注册：同时挂在根路径与 /api，兼容两种访问方式
app.include_router(api_router)
app.include_router(api_router, prefix="/api")

# （可选）安装慢 SQL 监听；若相关模块不存在，会自动跳过，不影响运行
try:
    # 如果你的项目是同步引擎，这里按需改为 sync_engine
    from app.db.session import async_engine
    from app.infra.sql_tap import install as install_sql_tap

    # 若 sql_tap 的 install 需要 sync 引擎，请替换为你项目的实际对象
    install_sql_tap(async_engine)  # 或 async_engine.sync_engine
except Exception:
    # 静默跳过，避免对现有部署产生硬依赖
    pass


@app.get("/ping")
async def ping():
    return {"pong": True}
