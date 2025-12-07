# app/observability/hooks.py
from __future__ import annotations

import functools
import time
from contextlib import contextmanager
from typing import Awaitable, Callable, Optional

from app.metrics import ERRS, EVENTS, LAT, OUTB


def record_event(
    platform: str, shop_id: str, state: str, duration_sec: Optional[float] = None
) -> None:
    """
    记录一次“事件推进”（如 PAID/ALLOCATED/SHIPPED/VOID），可选带时长。
    """
    EVENTS.labels(platform, shop_id, state).inc()
    if duration_sec is not None:
        LAT.labels(platform, shop_id, state).observe(duration_sec)


def record_error(platform: str, shop_id: str, code: str) -> None:
    """
    记录一次错误（非法跃迁/乱序/限流/上游失败/校验失败等）。
    """
    ERRS.labels(platform, shop_id, code).inc()


def record_outbound(platform: str, shop_id: str) -> None:
    """
    记录一次出库提交成功。
    """
    OUTB.labels(platform, shop_id).inc()


@contextmanager
def track_latency(platform: str, shop_id: str, state: str):
    """
    同步代码计时：
        with track_latency(p, s, "ALLOCATED"):
            do_something()
    """
    t0 = time.perf_counter()
    try:
        yield
    finally:
        LAT.labels(platform, shop_id, state).observe(time.perf_counter() - t0)


def instrument_async(
    platform_getter: Callable[..., str],
    shop_getter: Callable[..., str],
    state_getter: Callable[..., str],
):
    """
    装饰器（异步）：自动计时 + 成功计数；异常时计错误码。
    用法：
        @instrument_async(lambda *a, **k: k["platform"],
                          lambda *a, **k: k["shop_id"],
                          lambda *a, **k: k["new_state"])
        async def handle_event(...): ...
    """

    def deco(fn: Callable[..., Awaitable]):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            p = platform_getter(*args, **kwargs)
            s = shop_getter(*args, **kwargs)
            st = state_getter(*args, **kwargs)
            t0 = time.perf_counter()
            try:
                res = await fn(*args, **kwargs)
                record_event(p, s, st, time.perf_counter() - t0)
                return res
            except Exception as e:
                code = getattr(e, "code", None) or type(e).__name__
                record_error(p, s, str(code))
                raise

        return wrapper

    return deco
