# app/routers/webhooks.py
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.process_event import process_platform_events

router = APIRouter(prefix="/webhook", tags=["webhook"])


# ---- 会话依赖（与 admin_snapshot / orders 一致的“三段兜底”策略） ----
try:
    from app.deps import get_async_session as _get_session  # type: ignore
except Exception:  # noqa: BLE001
    try:
        from app.db import get_async_session as _get_session  # type: ignore
    except Exception:  # noqa: BLE001
        async def _get_session(request: Request) -> AsyncSession:  # type: ignore[override]
            maker = getattr(request.app.state, "async_sessionmaker", None)
            if maker is None:
                raise RuntimeError(
                    "No async sessionmaker available. "
                    "Provide app.deps.get_async_session / app.db.get_async_session "
                    "or set app.state.async_sessionmaker in app.main."
                )
            async with maker() as session:  # type: ignore[func-returns-value]
                yield session


# ---- 工具：把输入规范化为 List[dict] ----
def _normalize_events(platform: str, raw: Any) -> List[Dict[str, Any]]:
    """
    入参可能是：
      - 对象：{...}
      - 数组：[{}, {}, ...]
      - 表单/字符串：JSON 字符串
    统一转成 List[dict]，并补 platform 字段。
    """
    def _ensure_dict(x: Any) -> Dict[str, Any]:
        if isinstance(x, dict):
            return x
        raise ValueError("event must be object")

    events: List[Dict[str, Any]] = []
    data = raw
    if isinstance(raw, (str, bytes)):
        data = json.loads(raw)

    if isinstance(data, list):
        events = [_ensure_dict(e) for e in data]
    else:
        events = [_ensure_dict(data)]

    for e in events:
        e.setdefault("platform", platform.lower())
    return events


# ---- 通用入口：/webhook/{platform} ----
@router.post("/{platform}")
async def webhook_platform(
    platform: str,
    request: Request,
    session: AsyncSession = Depends(_get_session),
    body: Any = Body(None),
):
    """
    通用平台回调：
    - {platform} 例如：pdd / taobao / jd / douyin / xhs …
    - body 可以是对象、数组、或 JSON 字符串
    """
    # 优先使用 Body 反序列化，若为空则从 Request 读原文
    payload: Any = body
    if payload is None:
        payload = await request.body()
        payload = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload

    events = _normalize_events(platform, payload)

    # 丢给强契约事件通道（平台适配 → 状态分类 → reserve/cancel/ship）
    await process_platform_events(events=events, session=session, app_state=request.app.state)

    # 返回统一 ACK
    return JSONResponse({"ok": True, "received": len(events), "platform": platform.lower()})


# ---- 语义化别名：/webhook/pdd /webhook/taobao …（可选） ----

@router.post("/pdd")
async def webhook_pdd(
    request: Request, session: AsyncSession = Depends(_get_session), body: Any = Body(None)
):
    payload = body if body is not None else (await request.body()).decode("utf-8")
    events = _normalize_events("pdd", payload)
    await process_platform_events(events=events, session=session, app_state=request.app.state)
    return JSONResponse({"ok": True, "received": len(events), "platform": "pdd"})


@router.post("/taobao")
async def webhook_taobao(
    request: Request, session: AsyncSession = Depends(_get_session), body: Any = Body(None)
):
    payload = body if body is not None else (await request.body()).decode("utf-8")
    events = _normalize_events("taobao", payload)
    await process_platform_events(events=events, session=session, app_state=request.app.state)
    return JSONResponse({"ok": True, "received": len(events), "platform": "taobao"})
