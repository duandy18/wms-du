# app/main.py
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.http_problem_handlers import register_exception_handlers
from app.router_mount import mount_routers

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("wmsdu")

WMS_ENV = os.getenv("WMS_ENV", "dev").lower()
IS_DEV_ENV = WMS_ENV == "dev"

# ✅ 测试入口应显式注入 PYTEST_RUNNING=1（比依赖 PYTEST_CURRENT_TEST 更可靠）
PYTEST_RUNNING = os.getenv("PYTEST_RUNNING") == "1"

# ✅ 允许在非 dev 环境（例如 test）显式开启 dev 路由，以满足 tests/api/* 对 /dev/* 的契约依赖
DEV_ROUTES_ENABLED = IS_DEV_ENV or (os.getenv("WMS_ENABLE_DEV_ROUTES") == "1")

# ✅ 路由 dump：仅 dev 环境且显式开启才打印；pytest 下强制禁用
DUMP_ROUTES = (os.getenv("WMS_DUMP_ROUTES") == "1") and IS_DEV_ENV and (not PYTEST_RUNNING)

app = FastAPI(
    title="WMS-DU",
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册异常处理（Problem 形状）
register_exception_handlers(app)

# 挂载路由（dev 路由是否启用由 DEV_ROUTES_ENABLED 决定）
mount_routers(app, enable_dev_routes=DEV_ROUTES_ENABLED)


def _dump_routes_at_start() -> None:
    routes: List[tuple[str, List[str], str]] = []
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = sorted(list(getattr(r, "methods", []) or []))
        name = getattr(r, "name", "")
        if isinstance(path, str):
            routes.append((path, methods, name))
    print(f"[ROUTES@START] ({len(routes)} total)")
    for rr in routes:
        print(" ", rr)


if DUMP_ROUTES:
    _dump_routes_at_start()


@app.get("/")
async def root() -> Dict[str, Any]:
    return {"name": "WMS-DU", "version": "1.1.0"}


@app.get("/ping")
async def ping() -> Dict[str, Any]:
    return {"status": "ok"}


@app.get("/healthz")
async def healthz() -> Dict[str, Any]:
    return {"status": "ok"}
