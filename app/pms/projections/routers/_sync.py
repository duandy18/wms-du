# app/pms/projections/routers/_sync.py
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException

from app.integrations.pms.projection_sync import PmsProjectionSyncError


async def run_pms_projection_sync(
    sync_call: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    try:
        run = await sync_call()
    except (RuntimeError, PmsProjectionSyncError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"PMS projection sync failed: {exc}") from exc

    return {"run": run}


__all__ = ["run_pms_projection_sync"]
