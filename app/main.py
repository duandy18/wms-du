# app/main.py
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("wmsdu")

# 通过环境变量控制 dev 路由挂载：
#   WMS_ENV=dev  → 包含 /dev/... 系列接口
#   其他（test/prod 等）→ 不挂 dev 路由
WMS_ENV = os.getenv("WMS_ENV", "dev").lower()
IS_DEV_ENV = WMS_ENV == "dev"

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


@app.exception_handler(Exception)
async def _unhandled_exc(_req: Request, exc: Exception):
    logger.exception("UNHANDLED_EXC: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "INTERNAL_ERROR"})


@app.exception_handler(RequestValidationError)
async def _validation_exc(_req: Request, exc: RequestValidationError):
    safe = exc.errors()
    return JSONResponse(status_code=422, content={"detail": safe})


@app.exception_handler(HTTPException)
async def _http_exc(_req: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# Auto-heal 执行
from app.api.routers.autoheal_execute import router as autoheal_execute_router
from app.api.routers.channel_inventory import router as channel_inventory_router
from app.api.routers.count import router as count_router

# ===========================
#     观测 / 数据诊断
# ===========================
from app.api.routers.debug_trace import router as debug_trace_router

# dev 用：ledger seed 测试场景（dev-only）
from app.api.routers.dev_seed_ledger import router as dev_seed_ledger_router

# DevConsole（dev-only）
from app.api.routers.devconsole_orders import router as devconsole_orders_router

# Fake Platform（本地模拟平台事件）
from app.api.routers.fake_platform import router as fake_platform_router

# ===========================
#        财务分析
# ===========================
from app.api.routers.finance_overview import router as finance_overview_router

# Flow + Replay
from app.api.routers.flow_replay import router as flow_replay_router

# 智能层（insights / anomaly / ageing / autoheal / predict）
from app.api.routers.intelligence import router as intelligence_router
from app.api.routers.item_barcodes import router as item_barcodes_router
from app.api.routers.items import router as items_router

# ===========================
#   Phase 3.x 新增：台账 / 智能 / 生命周期
# ===========================
# 多维对账 v2
from app.api.routers.ledger_reconcile_v2 import router as ledger_reconcile_v2_router

# 台账时间线
from app.api.routers.ledger_timeline import router as ledger_timeline_router

# 生命周期（订单 / 批次）
from app.api.routers.lifecycle import router as lifecycle_router
from app.api.routers.metrics import router as metrics_router
from app.api.routers.orders import router as orders_router
from app.api.routers.orders_fulfillment_v2 import router as orders_fulfillment_v2_router

# 订单发货 SLA 统计
from app.api.routers.orders_sla_stats import router as orders_sla_stats_router

# 订单统计（数量 / 趋势）
from app.api.routers.orders_stats import router as orders_stats_router

# 新版出库主路由：/outbound/ship/commit 真正扣库存
from app.api.routers.outbound import router as outbound_router
from app.api.routers.outbound_ops import router as outbound_ops_router  # legacy

# 发货费用计算 / 发货审计 路由（/ship/calc, /ship/confirm）
from app.api.routers.outbound_ship import router as outbound_ship_router
from app.api.routers.pdd_auth import router as pdd_auth_router
from app.api.routers.permissions import router as permissions_router
from app.api.routers.pick import router as pick_router

# 拣货任务（新：出库通过 pick_task + commit_ship）
from app.api.routers.pick_tasks import router as pick_tasks_router
from app.api.routers.platform_shops import router as platform_shops_router

# 采购单 & 报表
from app.api.routers.purchase_orders import router as purchase_orders_router
from app.api.routers.purchase_reports import router as purchase_reports_router

# 收货任务（新：所有入库经由收货任务 commit）
from app.api.routers.receive_tasks import router as receive_tasks_router

# soft reserve 主链路
from app.api.routers.reserve_soft import router as reserve_soft_router

# 退货任务（新：采购退货经由退货任务 commit）
from app.api.routers.return_tasks import router as return_tasks_router
from app.api.routers.roles import router as roles_router

# ===========================
#        核心操作
# ===========================
from app.api.routers.scan import router as scan_router
from app.api.routers.shipping_providers import router as shipping_providers_router
from app.api.routers.shipping_records import router as shipping_records_router  # 新增：发货账本详情
from app.api.routers.shipping_reports import router as shipping_reports_router
from app.api.routers.snapshot import router as snapshot_router

# Snapshot v3 相关
from app.api.routers.snapshot_v3 import router as snapshot_v3_router

# 库存诊断工具（v1）
from app.api.routers.stock_batch import router as stock_batch_router
from app.api.routers.stock_ledger import router as stock_ledger_router

# ===========================
#        基础配置
# ===========================
from app.api.routers.stores import router as stores_router
from app.api.routers.suppliers import router as suppliers_router

# RBAC
from app.api.routers.user import router as user_router
from app.api.routers.warehouses import router as warehouses_router

# ===========================
#          挂载路由
# ===========================
# 核心操作
app.include_router(scan_router)
app.include_router(count_router)
app.include_router(pick_router)
app.include_router(orders_router)
app.include_router(orders_fulfillment_v2_router)

# 出库：/outbound/ship/commit = OutboundService（扣库存 + ledger + 软预占消费）
app.include_router(outbound_router)

# 发货：/ship/calc + /ship/confirm = ShipService（费用计算 + 发货审计）
app.include_router(outbound_ship_router)

# 旧版出库操作（已 410，占位用）
app.include_router(outbound_ops_router)

# 采购相关（采购单 + 收货任务 + 退货任务 + 报表 + 软预占）
app.include_router(purchase_orders_router)
app.include_router(purchase_reports_router)
app.include_router(receive_tasks_router)
app.include_router(return_tasks_router)
app.include_router(reserve_soft_router)
app.include_router(pick_tasks_router)  # 拣货任务

# 配置
app.include_router(stores_router)
app.include_router(warehouses_router)
app.include_router(platform_shops_router)
app.include_router(pdd_auth_router)
app.include_router(items_router)
app.include_router(item_barcodes_router)
app.include_router(suppliers_router)
app.include_router(shipping_providers_router)
app.include_router(shipping_reports_router)  # 发货成本报表
app.include_router(shipping_records_router)  # 发货账本详情

# 观测 / 诊断 v1
app.include_router(debug_trace_router)
app.include_router(channel_inventory_router)
app.include_router(metrics_router)
app.include_router(snapshot_router)

# 库存诊断 v1
app.include_router(stock_batch_router)
app.include_router(stock_ledger_router)

# 订单统计
app.include_router(orders_stats_router)
app.include_router(orders_sla_stats_router)

# RBAC
app.include_router(user_router)
app.include_router(roles_router)
app.include_router(permissions_router)

# Phase 3.x：台账 & 智能 & 生命周期 新增路由
app.include_router(ledger_reconcile_v2_router)
app.include_router(ledger_timeline_router)
app.include_router(snapshot_v3_router)
app.include_router(flow_replay_router)
app.include_router(lifecycle_router)
app.include_router(intelligence_router)
app.include_router(autoheal_execute_router)

# 财务分析
app.include_router(finance_overview_router)

# dev-only 路由：只在 WMS_ENV=dev 时挂载
if IS_DEV_ENV:
    app.include_router(devconsole_orders_router)
    app.include_router(dev_seed_ledger_router)
    app.include_router(fake_platform_router)


def _dump_routes_at_start():
    routes = []
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = sorted(list(getattr(r, "methods", []) or []))
        name = getattr(r, "name", "")
        if isinstance(path, str):
            routes.append((path, methods, name))
    print(f"[ROUTES@START] ({len(routes)} total)")
    for r in routes:
        print(" ", r)


_dump_routes_at_start()


@app.get("/")
async def root():
    return {"name": "WMS-DU", "version": "1.1.0"}


@app.get("/ping")
async def ping():
    return {"status": "ok"}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
