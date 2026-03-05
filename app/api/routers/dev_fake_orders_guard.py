# app/api/routers/dev_fake_orders_guard.py
from __future__ import annotations

import os

from fastapi import HTTPException


def _dev_guard_or_404() -> None:
    env = os.getenv("WMS_ENV", "dev").lower()
    if env != "dev":
        raise HTTPException(status_code=404, detail="Not found")


def dev_only_guard() -> None:
    _dev_guard_or_404()
