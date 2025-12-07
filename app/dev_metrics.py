# app/dev_metrics.py
import os

from fastapi import APIRouter, HTTPException

from app.metrics import ERRS, EVENTS, LAT, OUTB

router = APIRouter()


def _dev_enabled() -> bool:
    # 仅在本地/CI显示开启
    return (
        os.getenv("WMS_ENABLE_DEV_METRICS", "") == "1" or os.getenv("GITHUB_ACTIONS", "") == "true"
    )


@router.post("/__dev__/emit")
def emit():
    if not _dev_enabled():
        raise HTTPException(status_code=403, detail="DEV_METRICS_DISABLED")
    EVENTS.labels("tmall", "shop-1", "PAID").inc()
    EVENTS.labels("tmall", "shop-1", "ALLOCATED").inc()
    EVENTS.labels("tmall", "shop-1", "SHIPPED").inc()
    ERRS.labels("tmall", "shop-1", "ILLEGAL_TRANSITION").inc()
    OUTB.labels("tmall", "shop-1").inc()
    LAT.labels("tmall", "shop-1", "SHIPPED").observe(0.123)
    return {"ok": True}
