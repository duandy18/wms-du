# app/worker.py
from __future__ import annotations
import os
from celery import Celery

# 配置 Broker/Result Backend（容器里用 redis 服务，宿主机运行时可用 REDIS_URL/CELERY_RESULT_BACKEND 覆盖）
BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RESULT_URL = os.getenv("CELERY_RESULT_BACKEND", os.getenv("RESULT_URL", "redis://localhost:6379/1"))

# 创建 Celery 应用，并显式包含任务模块，确保 worker 启动时加载 wms.process_event
celery = Celery(
    "wms",
    broker=BROKER_URL,
    backend=RESULT_URL,
    include=["app.tasks"],           # ← 关键：显式注册任务模块
)

def _route_by_shop(name, args, kwargs, options, task=None, **kw):
    """按 (platform, shop_id) 分区路由，保证同分区顺序消费。"""
    p = (kwargs.get("platform") or "").lower()
    s = (kwargs.get("shop_id") or "")
    if p and s:
        return {"queue": f"events.{p}.{s}"}
    return None

# 一些推荐的运行期配置
celery.conf.task_routes = (_route_by_shop,)
celery.conf.task_acks_late = True
celery.conf.worker_prefetch_multiplier = 1
celery.conf.broker_transport_options = {"visibility_timeout": 3600}

# 再次确保在模块导入期加载任务定义（防止某些环境下 include 未生效）
try:
    import app.tasks  # noqa: F401
except Exception:
    # 如果本地调试时还未创建 tasks 文件，不影响导入
    pass
