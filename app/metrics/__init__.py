# app/metrics/__init__.py
"""
Prometheus-based metrics helpers for WMS-DU.

当前目录下的子模块：
- routing: 多仓路由相关指标（fallback 比例、路由失败、仓利用率等）

对外统一导出常用计数器：
- ERRS
- EVENTS

tests/quick/test_* 中会用到：
    from app.metrics import ERRS, EVENTS
"""

from __future__ import annotations

# routing 模块中应当定义了 ERRS / EVENTS 等指标计数器
try:
    from .routing import ERRS, EVENTS  # type: ignore[attr-defined]
except Exception:  # 防止在某些极端情况下导入失败
    # 为了不影响应用启动，这里给出兜底的哑实现，避免 ImportError。
    # 在正常场景下，应确保 routing 中定义了这两个对象。
    class _DummyMetric:
        def inc(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

        def observe(self, *args, **kwargs):
            pass

    ERRS = _DummyMetric()  # type: ignore[assignment]
    EVENTS = _DummyMetric()  # type: ignore[assignment]

__all__ = ["ERRS", "EVENTS"]
