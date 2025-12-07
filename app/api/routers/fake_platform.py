# app/api/routers/fake_platform.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, constr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session

router = APIRouter(prefix="/fake-platform", tags=["fake-platform"])

PlatformStr = constr(min_length=1, max_length=32)


def build_order_ref(platform: str, shop_id: str, ext_order_no: str) -> str:
    plat = platform.upper()
    return f"ORD:{plat}:{shop_id}:{ext_order_no}"


# ---------------------------------------------------------------------------
# 1) 手工写入订单状态事件：ORDER_STATUS → platform_events
# ---------------------------------------------------------------------------


class FakeOrderStatusIn(BaseModel):
    platform: PlatformStr = Field(..., description="平台标识，例如 PDD / JD")
    shop_id: str = Field(..., min_length=1, description="店铺 ID")
    ext_order_no: str = Field(..., min_length=1, description="平台订单号 / 外部订单号")

    platform_status: str = Field(
        ...,
        description="平台订单状态（原始文案/状态码），以后会映射为内部 DELIVERED / RETURNED / LOST 等",
    )
    delivered_at: Optional[datetime] = Field(
        None,
        description="（可选）平台侧签收时间；提供时会用于 shipping_records.delivery_time",
    )

    # 允许附加任意字段，最后会一起写入 payload JSONB
    extras: Dict[str, Any] = Field(
        default_factory=dict,
        description="（可选）附加字段，将原样写入 payload，例如 order_status_desc / refund_status 等",
    )


class FakeOrderStatusOut(BaseModel):
    ok: bool = True
    id: int
    platform: str
    shop_id: str
    ext_order_no: str
    platform_status: str
    dedup_key: Optional[str] = None
    occurred_at: datetime


@router.post(
    "/order-status",
    response_model=FakeOrderStatusOut,
    summary="写入一条 ORDER_STATUS 平台事件（用于本地模拟平台状态）",
)
async def fake_order_status(
    body: FakeOrderStatusIn,
    session: AsyncSession = Depends(get_session),
):
    """
    用于在本地开发环境中模拟“平台订单状态变更”事件。

    它会：
    - 将一条记录写入 platform_events：
        * platform      = body.platform
        * shop_id       = body.shop_id
        * event_type    = 'ORDER_STATUS'
        * event_id      = "0"（Fake 事件，无真实 event_store 记录）
        * status        = 'NEW'
        * payload       = JSON 字符串（你的 JSONB encoder 期待这样）
        * dedup_key     = 由数据库 GENERATED ALWAYS 生成，本路由不插入该列
    - 返回 event 的 id / dedup_key 等信息。
    """
    import json

    plat = body.platform.upper()
    shop_id = body.shop_id
    ext_order_no = body.ext_order_no

    # 完整业务引用（当前没直接用到，方便你以后扩展）
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

    # ✅ 关键：你的 JSONB encoder 期望字符串，这里统一 dumps
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
                    "event_id": "0",  # TEXT NOT NULL，用字符串 "0" 占位
                    "status": "NEW",
                    "payload": payload_str,  # JSON 字符串，交给 JSONB encoder
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


# ---------------------------------------------------------------------------
# 2) 快速查看最近的 platform_events（调试用）
# ---------------------------------------------------------------------------


class PlatformEventRow(BaseModel):
    id: int
    platform: str
    shop_id: str
    event_type: str
    status: str
    dedup_key: Optional[str] = None
    occurred_at: datetime
    payload: Dict[str, Any]


class PlatformEventListOut(BaseModel):
    ok: bool = True
    rows: List[PlatformEventRow]


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
    """
    用于在本地快速查看 platform_events 当前有哪些事件，方便调试：

    - 默认按 occurred_at DESC + id DESC 排序
    - 可按 platform / shop_id / event_type 过滤
    """
    conditions: List[str] = ["1=1"]
    params: Dict[str, Any] = {}

    if platform:
        conditions.append("platform = :platform")
        params["platform"] = platform.upper()
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

    import json

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
