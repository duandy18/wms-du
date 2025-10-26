# app/main.py
from __future__ import annotations

import logging
import traceback
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ★ 在创建 FastAPI 实例之前：集中导入所有模型并完成映射校验
from app.db.base import init_models
init_models()

logger = logging.getLogger("wmsdu")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

app = FastAPI(title="WMS-DU API", version="0.3.2")

# ---- CORS（按你前端联调域名，可自行增减） ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- 全局异常（保持简单可观测） ----
@app.exception_handler(Exception)
async def _unhandled_exc(_req: Request, exc: Exception):
    logger.error("UNHANDLED: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "INTERNAL_SERVER_ERROR", "error": str(exc)},
    )

# ---- 业务聚合路由（如果有的话） ----
try:
    from app.api.endpoints import api_router  # 你现有的聚合路由
    app.include_router(api_router)
    app.include_router(api_router, prefix="/api")
    logger.info("Mounted api_router (with and without /api prefix).")
except Exception:
    logger.info("api_router not mounted (module not found).")

# ---- Prometheus /metrics ----
try:
    from app.metrics import router as metrics_router
    app.include_router(metrics_router)
    logger.info("Mounted metrics_router at /metrics.")
except Exception:
    logger.warning("metrics_router not mounted (module not found).")

# ---- Dev Metrics（可选） ----
try:
    from app.dev_metrics import router as dev_metrics_router
    app.include_router(dev_metrics_router)
    logger.info("Mounted dev_metrics_router.")
except Exception:
    logger.info("dev_metrics_router not mounted (module not found).")

# ---- Stores 路由（重点） ----
def _mount_store_router():
    try:
        from app.routers.store import router as store_router  # 不在 app/api/ 下
        app.include_router(store_router)
        logger.info("✅ Mounted store_router (/stores/*).")
        return True
    except Exception as e:
        logger.error("❌ Failed to mount store_router: %s", e)
        logger.error("Traceback:\n%s", traceback.format_exc())
        return False

_mount_store_router()

@app.get("/ping")
async def ping():
    return {"pong": True}

# ---- 启动时列出所有已注册路由（调通后可删） ----
@app.on_event("startup")
async def _print_routes():
    paths = []
    for r in app.router.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None)
        if path:
            logger.info("ROUTE: %s %s", methods, path)
            paths.append(path)
    if "/stores/{store_id}/refresh" not in paths:
        logger.warning("⚠ stores routes not visible. See above errors. Check __init__.py and imports.")
