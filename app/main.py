from __future__ import annotations
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# 业务 API 路由（如果没有可暂时注释掉）
try:
    from app.api.endpoints import api_router
except Exception:
    api_router = None

# —— 原有 metrics 路由（保留，继续提供 /metrics） —— #
from app.metrics import router as metrics_router  # prometheus_client 未装会抛错

# —— 可选：开发/CI 样本端点（由环境变量控制是否启用） —— #
try:
    from app.dev_metrics import router as dev_metrics_router
except Exception:
    dev_metrics_router = None

# —— Phase 2.8：可观测性接入 —— #
# Prometheus 中间件（记录 http_requests_total / http_request_duration_seconds）
from app.obs.metrics import PrometheusMiddleware
# OpenTelemetry：FastAPI +（可选）SQLAlchemy + Redis + Celery 的 trace
from app.obs.otel import setup_tracing

app = FastAPI(title="WMS-DU API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# —— Phase 2.8：挂 Prometheus 中间件（排除 /metrics 的采样在 otel 里已处理） —— #
app.add_middleware(PrometheusMiddleware)

# —— Phase 2.8：初始化 OpenTelemetry（此处尚无 engine，可先仅注入 FastAPI；DB 可在创建 Engine 处再次调用 setup_tracing(sqlalchemy_engine=engine) 补充） —— #
setup_tracing(app=app)

@app.exception_handler(Exception)
async def _unhandled_exc(_req: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "INTERNAL_SERVER_ERROR", "error": str(exc)})

# 业务 API（如果存在）
if api_router is not None:
    app.include_router(api_router)
    app.include_router(api_router, prefix="/api")

# /metrics（沿用你已有的 metrics 路由）
app.include_router(metrics_router)

# /__dev__/emit（仅在 dev_metrics 可导入时挂载；是否允许调用由端点内部检查）
if dev_metrics_router is not None:
    app.include_router(dev_metrics_router)

@app.get("/ping")
async def ping():
    return {"pong": True}
