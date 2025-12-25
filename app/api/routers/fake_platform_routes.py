# app/api/routers/fake_platform_routes.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.fake_platform_helpers import build_order_ref, normalize_platform
from app.api.routers.fake_platform_schemas import (
    FakeOrderStatusIn,
    FakeOrderStatusOut,
    PlatformEventListOut,
    PlatformEventRow,
)


def register(router: APIRouter) -> None:
    @router.post(
        "/order-status",
        response_model=FakeOrderStatusOut,
        summary="写入一条 ORDER_STATUS 平台事件（用于本地模拟平台状态）",
    )
    async def fake_order_status(
        body: FakeOrderStatusIn,
        session: AsyncSession = Depends(get_session),
    ):
        plat = body.platform.upper()
        shop_id = body.shop_id
        ext_order_no = body.ext_order_no

        order_ref = build_order_ref(plat, shop_id, ext_order_no)
        _ = order_ref

        payload: Dict[str, Any] = {
            "ext_order_no": ext_order_no,
            "platform_status": body.platform_status,
        }
        if body.delivered_at is not None:
            dt = body.delivered_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            payload["delivered_at"] = dt.isoformat()
        if body.extras:
            payload["extras"] = dict(body.extras)

        payload_str = json.dumps(payload, ensure_ascii=False)
        occurred_at = datetime.now(timezone.utc)

        sql = text(
            """
            INSERT INTO platform_events (platform, shop_id, event_type, event_id, status, payload, occurred_at)
            VALUES (:platform, :shop_id, :event_type, :event_id, :status, :payload, :occurred_at)
            RETURNING id, platform, shop_id, event_type, status, dedup_key, occurred_at, payload
            """
        )

        row = (
            (
                await session.execute(
                    sql,
                    {
                        "platform": plat,
                        "shop_id": shop_id,
                        "event_type": "ORDER_STATUS",
                        "event_id": "0",
                        "status": "NEW",
                        "payload": payload_str,
                        "occurred_at": occurred_at,
                    },
                )
            )
            .mappings()
            .first()
        )

        await session.commit()

        return FakeOrderStatusOut(
            ok=True,
            id=int(row["id"]),
            platform=str(row["platform"]),
            shop_id=str(row["shop_id"]),
            ext_order_no=ext_order_no,
            platform_status=body.platform_status,
            dedup_key=row.get("dedup_key"),
            occurred_at=row["occurred_at"],
        )

    @router.get(
        "/events",
        response_model=PlatformEventListOut,
        summary="查看最近的 platform_events（调试 Fake Platform 用）",
    )
    async def list_platform_events(
        platform: Optional[str] = Query(None, description="平台标识（可选）"),
        shop_id: Optional[str] = Query(None, description="店铺 ID（可选）"),
        event_type: Optional[str] = Query(None, description="事件类型，如 ORDER_STATUS"),
        limit: int = Query(50, ge=1, le=200),
        session: AsyncSession = Depends(get_session),
    ):
        conditions: List[str] = ["1=1"]
        params: Dict[str, Any] = {}

        plat_norm = normalize_platform(platform)
        if plat_norm:
            conditions.append("platform = :platform")
            params["platform"] = plat_norm
        if shop_id:
            conditions.append("shop_id = :shop_id")
            params["shop_id"] = shop_id
        if event_type:
            conditions.append("event_type = :event_type")
            params["event_type"] = event_type

        where_sql = " AND ".join(conditions)
        params["limit"] = limit

        sql = text(
            f"""
            SELECT
              id,
              platform,
              shop_id,
              event_type,
              status,
              dedup_key,
              occurred_at,
              payload
            FROM platform_events
            WHERE {where_sql}
            ORDER BY occurred_at DESC, id DESC
            LIMIT :limit
            """
        )

        rows = (await session.execute(sql, params)).mappings().all()

        normalized_rows: List[PlatformEventRow] = []
        for r in rows:
            raw_payload = r["payload"]
            if isinstance(raw_payload, str):
                try:
                    payload_obj = json.loads(raw_payload)
                except Exception:
                    payload_obj = {"_raw": raw_payload}
            elif isinstance(raw_payload, dict):
                payload_obj = raw_payload
            else:
                payload_obj = {"_raw": raw_payload}

            normalized_rows.append(
                PlatformEventRow(
                    id=int(r["id"]),
                    platform=str(r["platform"]),
                    shop_id=str(r["shop_id"]),
                    event_type=str(r["event_type"]),
                    status=str(r["status"]),
                    dedup_key=r.get("dedup_key"),
                    occurred_at=r["occurred_at"],
                    payload=payload_obj,
                )
            )

        return PlatformEventListOut(ok=True, rows=normalized_rows)
