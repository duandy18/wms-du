# app/main.py
from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.problem import make_problem

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("wmsdu")

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


def _new_trace_id() -> str:
    return f"t_{uuid.uuid4().hex[:12]}"


def _problem_from_http_exc(req: Request, exc: HTTPException) -> Dict[str, Any]:
    """
    统一将 HTTPException.detail 翻译为 Problem 形状（蓝皮书 v1）。
    兼容历史形态：
    - str
    - list（例如 RequestValidationError safe list）
    - {"code","message"}
    - {"error_code","message",...}（已是 Problem）
    """
    status_code = int(exc.status_code)
    trace_id = _new_trace_id()

    ctx: Dict[str, Any] = {
        "path": getattr(req.url, "path", ""),
        "method": req.method,
    }

    d = exc.detail

    # 1) 已是 Problem（优先原样补齐 http_status/trace_id/context）
    if isinstance(d, dict) and "error_code" in d and "message" in d:
        out = dict(d)
        out.setdefault("http_status", status_code)
        out.setdefault("trace_id", trace_id)
        if isinstance(out.get("context"), dict):
            merged = dict(ctx)
            merged.update(out["context"])
            out["context"] = merged
        else:
            out["context"] = ctx
        return out

    # 2) 旧形态：{code,message} → Problem
    if isinstance(d, dict) and "code" in d and "message" in d:
        return make_problem(
            status_code=status_code,
            error_code=str(d.get("code") or "HTTP_ERROR"),
            message=str(d.get("message") or "请求被拒绝"),
            context=ctx,
            trace_id=trace_id,
        )

    # 3) detail=list：当作 validation 详情
    if isinstance(d, list):
        details: List[Dict[str, Any]] = []
        for i, e in enumerate(d):
            if isinstance(e, dict):
                details.append(
                    {
                        "type": "validation",
                        "path": f"validation[{i}]",
                        "reason": str(e.get("msg") or e.get("type") or "invalid"),
                    }
                )
            else:
                details.append({"type": "validation", "path": f"validation[{i}]", "reason": str(e)})
        return make_problem(
            status_code=status_code,
            error_code="request_validation_error",
            message="请求参数不合法",
            context=ctx,
            details=details,
            trace_id=trace_id,
        )

    # 4) detail=str / 其它：兜底为 state
    msg = str(d) if d is not None else "请求被拒绝"
    return make_problem(
        status_code=status_code,
        error_code="http_error",
        message=msg,
        context=ctx,
        details=[{"type": "state", "reason": msg}],
        trace_id=trace_id,
    )


@app.exception_handler(Exception)
async def _unhandled_exc(req: Request, exc: Exception):
    trace_id = _new_trace_id()
    logger.exception("UNHANDLED_EXC[%s]: %s", trace_id, exc)
    content = make_problem(
        status_code=500,
        error_code="internal_error",
        message="系统异常，请稍后重试",
        context={"path": getattr(req.url, "path", ""), "method": req.method},
        trace_id=trace_id,
    )
    return JSONResponse(status_code=500, content=content)


@app.exception_handler(RequestValidationError)
async def _validation_exc(req: Request, exc: RequestValidationError):
    raw = exc.errors()
    details: List[Dict[str, Any]] = []
    for i, e in enumerate(raw):
        if not isinstance(e, dict):
            continue
        details.append(
            {
                "type": "validation",
                "path": f"validation[{i}]",
                "reason": str(e.get("msg") or e.get("type") or "invalid"),
            }
        )

    content = make_problem(
        status_code=422,
        error_code="request_validation_error",
        message="请求参数不合法",
        context={"path": getattr(req.url, "path", ""), "method": req.method},
        details=details,
        trace_id=_new_trace_id(),
    )
    return JSONResponse(status_code=422, content=content)


@app.exception_handler(HTTPException)
async def _http_exc(req: Request, exc: HTTPException):
    content = _problem_from_http_exc(req, exc)
    return JSONResponse(status_code=int(exc.status_code), content=content)


# ---------------------------------------------------------------------------
# routers imports
# ---------------------------------------------------------------------------
from app.api.routers.autoheal_execute import router as autoheal_execute_router
from app.api.routers.count import router as count_router
from app.api.routers.debug_trace import router as debug_trace_router
from app.api.routers.dev_seed_ledger import router as dev_seed_ledger_router
from app.api.routers.devconsole_orders import router as devconsole_orders_router
from app.api.routers.fake_platform import router as fake_platform_router
from app.api.routers.finance_overview import router as finance_overview_router
from app.api.routers.flow_replay import router as flow_replay_router
from app.api.routers.inbound_receipts import router as inbound_receipts_router
from app.api.routers.intelligence import router as intelligence_router
from app.api.routers.item_barcodes import router as item_barcodes_router
from app.api.routers.items import router as items_router
from app.api.routers.ledger_reconcile_v2 import router as ledger_reconcile_v2_router
from app.api.routers.ledger_timeline import router as ledger_timeline_router
from app.api.routers.lifecycle import router as lifecycle_router
from app.api.routers.metrics import router as metrics_router
from app.api.routers.orders import router as orders_router
from app.api.routers.orders_sla_stats import router as orders_sla_stats_router
from app.api.routers.orders_stats import router as orders_stats_router
from app.api.routers.outbound import router as outbound_router
from app.api.routers.outbound_ops import router as outbound_ops_router
from app.api.routers.outbound_ship import router as outbound_ship_router
from app.api.routers.pdd_auth import router as pdd_auth_router
from app.api.routers.permissions import router as permissions_router
from app.api.routers.pick import router as pick_router
from app.api.routers.pick_tasks import router as pick_tasks_router
from app.api.routers.platform_orders_ingest import router as platform_orders_ingest_router
from app.api.routers.print_jobs import router as print_jobs_router
from app.api.routers.platform_shops import router as platform_shops_router
from app.api.routers.pricing_integrity_ops import router as pricing_integrity_ops_router
from app.api.routers.purchase_orders import router as purchase_orders_router
from app.api.routers.purchase_reports import router as purchase_reports_router
from app.api.routers.receive_tasks import router as receive_tasks_router
from app.api.routers.return_tasks import router as return_tasks_router
from app.api.routers.roles import router as roles_router

from app.api.routers.shipping_providers import router as shipping_providers_router
from app.api.routers.shipping_provider_contacts import router as shipping_provider_contacts_router
from app.api.routers.shipping_provider_pricing_schemes.router import (
    router as shipping_provider_pricing_schemes_router,
)
from app.api.routers.shipping_quote import router as shipping_quote_router
from app.api.routers.shipping_records import router as shipping_records_router
from app.api.routers.shipping_reports import router as shipping_reports_router
from app.api.routers.snapshot import router as snapshot_router
from app.api.routers.snapshot_v3 import router as snapshot_v3_router
from app.api.routers.stock_batch import router as stock_batch_router
from app.api.routers.stock_ledger import router as stock_ledger_router

from app.api.routers.internal_outbound import router as internal_outbound_router

from app.api.routers.meta import router as meta_router
from app.api.routers.psku_governance import router as psku_governance_router
from app.api.routers.stores import router as stores_router
from app.api.routers.suppliers import router as suppliers_router
from app.api.routers.supplier_contacts import router as supplier_contacts_router

from app.api.routers.user import router as user_router
from app.api.routers.warehouses import router as warehouses_router

from app.api.routers.geo_cn import router as geo_router

from app.api.routers.orders_fulfillment_debug_routes import (
    router as orders_fulfillment_debug_router,
)

from app.api.routers.shop_product_bundles import router as shop_product_bundles_router

# ---------------------------------------------------------------------------
# scan routes
# ---------------------------------------------------------------------------
from app.api.routers import scan_routes_count_commit, scan_routes_entrypoint

scan_router = APIRouter(tags=["scan"])
scan_routes_entrypoint.register(scan_router)
scan_routes_count_commit.register(scan_router)

# ---------------------------------------------------------------------------
# orders_fulfillment_v2 routes
# ---------------------------------------------------------------------------
from app.api.routers import (
    orders_fulfillment_v2_routes_1_reserve,
    orders_fulfillment_v2_routes_2_pick,
    orders_fulfillment_v2_routes_3_ship,
    orders_fulfillment_v2_routes_4_ship_with_waybill,
)

orders_fulfillment_v2_router = APIRouter(prefix="/orders", tags=["orders-fulfillment-v2"])
orders_fulfillment_v2_routes_1_reserve.register(orders_fulfillment_v2_router)
orders_fulfillment_v2_routes_2_pick.register(orders_fulfillment_v2_router)
orders_fulfillment_v2_routes_3_ship.register(orders_fulfillment_v2_router)
orders_fulfillment_v2_routes_4_ship_with_waybill.register(orders_fulfillment_v2_router)

# ===========================
# mount routers
# ===========================
app.include_router(scan_router)
app.include_router(count_router)
app.include_router(pick_router)

app.include_router(platform_orders_ingest_router)

app.include_router(orders_router)
app.include_router(orders_fulfillment_v2_router)

app.include_router(orders_fulfillment_debug_router)

app.include_router(outbound_router)
app.include_router(outbound_ship_router)
app.include_router(internal_outbound_router)
app.include_router(outbound_ops_router)

app.include_router(purchase_orders_router)
app.include_router(purchase_reports_router)
app.include_router(receive_tasks_router)
app.include_router(inbound_receipts_router)
app.include_router(return_tasks_router)
app.include_router(pick_tasks_router)
app.include_router(print_jobs_router)

app.include_router(meta_router)
app.include_router(psku_governance_router)
app.include_router(stores_router)
app.include_router(shop_product_bundles_router)

app.include_router(warehouses_router)
app.include_router(platform_shops_router)
app.include_router(pdd_auth_router)
app.include_router(items_router)
app.include_router(item_barcodes_router)

app.include_router(suppliers_router)
app.include_router(supplier_contacts_router)

app.include_router(shipping_providers_router)
app.include_router(shipping_provider_contacts_router)
app.include_router(shipping_provider_pricing_schemes_router)
app.include_router(geo_router)
app.include_router(pricing_integrity_ops_router)
app.include_router(shipping_quote_router)
app.include_router(shipping_reports_router)
app.include_router(shipping_records_router)

app.include_router(debug_trace_router)
app.include_router(metrics_router)
app.include_router(snapshot_router)

app.include_router(stock_batch_router)
app.include_router(stock_ledger_router)

app.include_router(orders_stats_router)
app.include_router(orders_sla_stats_router)

app.include_router(user_router)
app.include_router(roles_router)
app.include_router(permissions_router)

app.include_router(ledger_reconcile_v2_router)
app.include_router(ledger_timeline_router)
app.include_router(snapshot_v3_router)
app.include_router(flow_replay_router)
app.include_router(lifecycle_router)
app.include_router(intelligence_router)
app.include_router(autoheal_execute_router)

app.include_router(finance_overview_router)

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


if IS_DEV_ENV:
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
