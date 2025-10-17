# app/main.py
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi import FastAPI

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


# （可选）全局异常转 JSON。即便不加，步骤 1 的路由局部 try/except 也能确保 JSON。
@app.exception_handler(Exception)
async def _unhandled_exc(_req: Request, exc: Exception):
    return JSONResponse(
        status_code=500, content={"detail": "INTERNAL_SERVER_ERROR", "error": str(exc)}
    )


app.include_router(api_router)
    # ✅（可选）安装慢 SQL 监听；若相关模块不存在，会自动跳过，不影响运行
    try:
        from app.db.session import async_engine  # 假设项目使用 AsyncEngine
        from app.infra.sql_tap import install as install_sql_tap

        install_sql_tap(async_engine.sync_engine)
    except Exception:
        # 静默跳过，避免对现有部署产生硬依赖
        pass

    return app


@app.get("/ping")
async def ping():
    return {"pong": True}
