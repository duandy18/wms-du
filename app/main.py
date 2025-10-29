# app/main.py
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("wmsdu")

app = FastAPI(title="WMS-DU API", version="1.0.0")

# === CORS ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === 全局异常兜底 ===
@app.exception_handler(Exception)
async def _unhandled_exc(_req: Request, exc: Exception):
    logger.exception("UNHANDLED EXC: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "INTERNAL_SERVER_ERROR"})

# === 1) 初始化 async_sessionmaker 并挂到 app.state ===
def _mount_async_sessionmaker() -> None:
    db_url = os.environ.get("DATABASE_URL", "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms")
    async_url = db_url.replace("+psycopg", "+asyncpg") if "+psycopg" in db_url else db_url
    engine = create_async_engine(async_url, future=True, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app.state.async_sessionmaker = maker
    logger.info("async_sessionmaker mounted on app.state")

# === 2) 显式导入所有模型，完成 ORM 映射注册（避免字符串关系名找不到） ===
def _import_all_models() -> None:
    # 把你项目内会参与关系映射的模型都导入一遍，顺序无所谓；失败不应静默
    import importlib

    model_modules = [
        "app.models.item",
        "app.models.order_item",       # 提供 OrderItem，解决 Item.relationship('OrderItem') 引用
        "app.models.order",          # ✅ 新增
        "app.models.location",
        "app.models.warehouse",
        "app.models.stock",
        "app.models.batch",
        "app.models.stock_ledger",
        "app.models.stock_snapshot",
        # 如有其它模型（users/roles/events 等），可按需补上：
        # "app.models.user",
        # "app.models.role",
        # "app.models.event_error_log",
        # "app.models.outbound_commit",
    ]
    for mod in model_modules:
        try:
            importlib.import_module(mod)
        except Exception as e:
            # 对于不存在的模块，仅记录告警，不让应用崩
            logger.warning("Model import skipped or failed: %s (%s)", mod, e)

# 挂载会话工厂与模型注册
_mount_async_sessionmaker()
_import_all_models()

# === 3) 只用 routers：显式导入 + 显式挂载 ===
from app.routers.stock_ledger import router as stock_ledger_router  # noqa: E402
from app.routers.admin_snapshot import router as snapshot_router    # noqa: E402

app.include_router(stock_ledger_router)
app.include_router(snapshot_router)

# === 探活 ===
@app.get("/ping")
async def ping():
    return {"status": "ok"}

# === 启动时打印路由表 ===
@app.on_event("startup")
async def _print_routes():
    for r in app.router.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None)
        if path:
            logger.info("ROUTE: %s %s", methods, path)
