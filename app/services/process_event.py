# app/services/process_event.py
import time
from app.metrics import EVENTS, LAT, IDEMP
from app.domain.events_enums import EventState

async def process_event(session, *, platform, shop_id, state, handler, idempotent=False):
    t0 = time.perf_counter()
    try:
        if idempotent:
            IDEMP.labels(platform, shop_id).inc()
            return  # 命中幂等直接返回（不重复执行）

        await handler(session)
        EVENTS.labels(platform, shop_id, EventState(state).value).inc()
    finally:
        LAT.labels(platform, shop_id, EventState(state).value).observe(time.perf_counter() - t0)
