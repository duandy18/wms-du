# app/jobs/shipping_delivery_sync.py
from __future__ import annotations

from app.jobs.shipping_delivery_sync_config import INTERNAL_FINAL_STATUSES, PLATFORM_STATUS_MAP
from app.jobs.shipping_delivery_sync_runner import main, run_cli, run_once
from app.jobs.shipping_delivery_sync_types import PlatformOrderStatus

__all__ = [
    "INTERNAL_FINAL_STATUSES",
    "PLATFORM_STATUS_MAP",
    "PlatformOrderStatus",
    "run_once",
    "main",
    "run_cli",
]


if __name__ == "__main__":
    run_cli()
