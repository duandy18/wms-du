# app/api/routers/webhooks.py
from __future__ import annotations

import json
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Body, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.services.process_event import process_platform_events

router = APIRouter(prefix="/webhook", tags=["webhook"])


def _normalize_events(platform: str, raw: Any) -> List[Dict[str, Any]]:
    """允许传单个对象或数组；字符串/bytes 时先 JSON 解析；补全 platform 字段。"""
    data = raw
    if isinstance(raw, (str, bytes)):
        data = json.loads(raw)
    if isinstance(data, dict):
        events = [data]
    elif isinstance(data, list):
        events = data
    else:
        raise ValueError("invalid webhook payload")
    for e in events:
        if isinstance(e, dict):
            e.setdefault("platform", platform.lower())
        else:
            raise ValueError("event item must be object")
    return events


@router.post("/{platform}")
async def webhook_platform(
    platform: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    body: Any = Body(None),
):
    payload = body if body is not None else (await request.body()).decode("utf-8")
    events = _normalize_events(platform, payload)
    await process_platform_events(events=events, session=session, app_state=request.app.state)
    return JSONResponse({"ok": True, "received": len(events), "platform": platform.lower()})


@router.post("/pdd")
async def webhook_pdd(
    request: Request,
    session: AsyncSession = Depends(get_session),
    body: Any = Body(None),
):
    payload = body if body is not None else (await request.body()).decode("utf-8")
    events = _normalize_events("pdd", payload)
    await process_platform_events(events=events, session=session, app_state=request.app.state)
    return JSONResponse({"ok": True, "received": len(events), "platform": "pdd"})


@router.post("/taobao")
async def webhook_taobao(
    request: Request,
    session: AsyncSession = Depends(get_session),
    body: Any = Body(None),
):
    payload = body if body is not None else (await request.body()).decode("utf-8")
    events = _normalize_events("taobao", payload)
    await process_platform_events(events=events, session=session, app_state=request.app.state)
    return JSONResponse({"ok": True, "received": len(events), "platform": "taobao"})
