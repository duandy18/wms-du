# app/worker.py
# Phase 2.8 · Celery Worker（OTel + Prometheus 指标 + Beat 调度 + 测试态 send_task 同步执行）
from __future__ import annotations
import os
from typing import Any, Dict

from celery import Celery
from celery.result import EagerResult
from celery.signals import worker_ready, task_prerun, task_postrun

# —— 可观测性 —— #
from app.obs.otel import setup_tracing        # OTel tracing
from app.obs.metrics import celery_active_tasks  # Prometheus gauge

BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RESULT_URL = os.getenv("CELERY_RESULT_BACKEND", os.getenv("RESULT_URL", "redis://localhost:6379/1"))

# 注册任务模块（app.tasks 内含 wms.process_event 与 consistency_job）
celery = Celery("wms", broker=BROKER_URL, backend=RESULT_URL, include=["app.tasks"])


def _route_by_shop(name, args, kwargs, options, task=None, **kw):
    p = (kwargs.get("platform") or "").lower()
    s = (kwargs.get("shop_id") or "")
    if p and s:
        return {"queue": f"events.{p}.{s}"}
    return None


# 基本配置
celery.conf.task_routes = (_route_by_shop,)
celery.conf.task_acks_late = True
celery.conf.worker_prefetch_multiplier = 1
celery.conf.broker_transport_options = {"visibility_timeout": 3600}

# === Beat 调度：每 10 分钟跑一次一致性巡检（默认 dry-run） ===
celery.conf.beat_schedule = {
    "consistency-every-10m": {
        "task": "app.tasks.consistency_job",
        "schedule": 600.0,         # 每 10 分钟
        "args": (True, False),     # dry_run=True, auto_fix=False
    },
}

# === 测试/CI：任务在本进程直接执行，避免等待外部 worker ===
_TESTING = bool(os.getenv("PYTEST_CURRENT_TEST")) or os.getenv("CELERY_ALWAYS_EAGER") == "1"
if _TESTING:
    # 让 task.delay()/task.apply_async() 走本进程
    celery.conf.task_always_eager = True
    celery.conf.task_eager_propagates = True
    celery.conf.task_store_eager_result = True  # 允许 .get() 读取结果

    # ★ 关键：send_task 默认不会受 always_eager 影响，这里对本 app 的任务做同步执行
    _orig_send_task = celery.send_task

    def _sync_send_task(name: str, args: Any | None = None, kwargs: Dict[str, Any] | None = None, **opts):
        task = celery.tasks.get(name)
        if task is None:
            # 非本 app 的任务，仍然用原生 send_task（例如跨进程/跨服务时）
            return _orig_send_task(name, args=args, kwargs=kwargs, **opts)
        # 同步执行，返回 EagerResult，测试里 .get(timeout=..) 可直接取到
        res = task.apply(args=args or (), kwargs=kwargs or {}, throw=True)
        if isinstance(res, EagerResult):
            return res
        # 兜底：构造一个 EagerResult 兼容对象
        return EagerResult(id=res.id, result=res.result, state=res.state, traceback=None)

    celery.send_task = _sync_send_task  # monkey-patch

# import 以注册所有任务
try:
    import app.tasks  # noqa: F401
except Exception:
    pass


@worker_ready.connect
def _on_worker_ready(**_):
    # 仅在真实 worker 场景下启用 OTel；测试态不强求
    try:
        setup_tracing()
    except Exception:
        pass


@task_prerun.connect
def _on_task_start(task_id=None, task=None, args=None, kwargs=None, **_):
    try:
        celery_active_tasks.inc()
    except Exception:
        pass


@task_postrun.connect
def _on_task_end(task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **_):
    try:
        celery_active_tasks.dec()
    except Exception:
        pass
