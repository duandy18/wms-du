# app/oms/services/order_ref_resolver.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problem import raise_problem
from app.oms.services.platform_order_resolve_store import resolve_store_id


@dataclass(frozen=True)
class OrderKey:
    platform: str
    shop_id: str
    ext_order_no: str


def _parse_order_key(order_ref: str) -> Optional[OrderKey]:
    s = (order_ref or "").strip()
    if not s:
        return None

    parts = s.split(":")

    # ORD:PLAT:SHOP:EXT
    if len(parts) >= 4 and parts[0].upper() == "ORD":
        platform = parts[1].strip()
        shop_id = parts[2].strip()
        ext = ":".join(parts[3:]).strip()
        if platform and shop_id and ext:
            return OrderKey(platform=platform, shop_id=shop_id, ext_order_no=ext)
        return None

    # PLAT:SHOP:EXT
    if len(parts) >= 3:
        platform = parts[0].strip()
        shop_id = parts[1].strip()
        ext = ":".join(parts[2:]).strip()
        if platform and shop_id and ext:
            return OrderKey(platform=platform, shop_id=shop_id, ext_order_no=ext)
        return None

    return None


async def resolve_order_id(session: AsyncSession, *, order_ref: str) -> int:
    """
    Phase 5 第二刀：执行域必须落在 orders.id（bigint）。
    允许上游仍传字符串 order_ref，但必须可硬解析成唯一 orders.id；否则直接拒绝（不扣库/不写履约）。

    解析规则（硬）：
    1) 纯数字 -> 当作 orders.id
    2) ORD:PLAT:SHOP:EXT 或 PLAT:SHOP:EXT -> 用 (platform, shop_id, ext_order_no) 唯一约束解析
    3) 仅 ext_order_no -> 若全库唯一则允许；否则 409 要求传全三段
    """
    s = (order_ref or "").strip()
    if not s:
        raise ValueError("order_ref cannot be empty")

    # 1) numeric -> orders.id
    if s.isdigit():
        oid = int(s)
        row = (
            await session.execute(
                text("SELECT id FROM orders WHERE id = :id LIMIT 1"),
                {"id": oid},
            )
        ).first()
        if row:
            return int(row[0])
        raise_problem(
            status_code=404,
            error_code="order_not_found",
            message="订单不存在（按 orders.id 查询）。",
            context={"order_ref": s, "order_id": oid},
            details=[],
            next_actions=[],
        )
        return 0

    # 2) structured key
    key = _parse_order_key(s)
    if key is not None:
        row = (
            await session.execute(
                text(
                    """
                    SELECT id
                      FROM orders
                     WHERE platform = :p
                       AND shop_id = :sid
                       AND ext_order_no = :ext
                     LIMIT 1
                    """
                ),
                {"p": key.platform, "sid": key.shop_id, "ext": key.ext_order_no},
            )
        ).first()
        if row:
            return int(row[0])

        # ✅ TEST-ONLY：补齐 orders 事实（不允许“没有订单事实就出库”）
        if os.getenv("WMS_ENV") == "test":
            store_id = await resolve_store_id(
                session,
                platform=key.platform,
                shop_id=key.shop_id,
                store_name=str(key.shop_id),
            )

            ins = (
                await session.execute(
                    text(
                        """
                        INSERT INTO orders(platform, shop_id, store_id, ext_order_no)
                        VALUES (:p, :sid, :store_id, :ext)
                        ON CONFLICT (platform, shop_id, ext_order_no) DO NOTHING
                        RETURNING id
                        """
                    ),
                    {
                        "p": key.platform,
                        "sid": key.shop_id,
                        "store_id": int(store_id),
                        "ext": key.ext_order_no,
                    },
                )
            ).first()

            if ins:
                return int(ins[0])

            # 并发/已存在：再查一次
            row2 = (
                await session.execute(
                    text(
                        """
                        SELECT id
                          FROM orders
                         WHERE platform = :p
                           AND shop_id = :sid
                           AND ext_order_no = :ext
                         LIMIT 1
                        """
                    ),
                    {"p": key.platform, "sid": key.shop_id, "ext": key.ext_order_no},
                )
            ).first()
            if row2:
                return int(row2[0])

        raise_problem(
            status_code=404,
            error_code="order_not_found",
            message="订单不存在（按 platform/shop_id/ext_order_no 查询）。",
            context={"order_ref": s, "platform": key.platform, "shop_id": key.shop_id, "ext_order_no": key.ext_order_no},
            details=[],
            next_actions=[],
        )
        return 0

    # 3) ext_order_no only -> allow only if unique across all shops
    rows = (
        await session.execute(
            text(
                """
                SELECT id, platform, shop_id
                  FROM orders
                 WHERE ext_order_no = :ext
                 ORDER BY id ASC
                 LIMIT 2
                """
            ),
            {"ext": s},
        )
    ).all()

    if not rows:
        raise_problem(
            status_code=404,
            error_code="order_not_found",
            message="订单不存在（按 ext_order_no 查询）。",
            context={"order_ref": s, "ext_order_no": s},
            details=[],
            next_actions=[],
        )
        return 0

    if len(rows) >= 2:
        raise_problem(
            status_code=409,
            error_code="order_ref_ambiguous",
            message="订单引用歧义：仅 ext_order_no 无法唯一定位订单，请传 ORD:PLAT:SHOP:EXT。",
            context={"order_ref": s, "ext_order_no": s},
            details=[
                {"id": int(rows[0][0]), "platform": str(rows[0][1]), "shop_id": str(rows[0][2])},
                {"id": int(rows[1][0]), "platform": str(rows[1][1]), "shop_id": str(rows[1][2])},
            ],
            next_actions=[{"action": "use_full_ref", "label": "使用 ORD:PLAT:SHOP:EXT 格式"}],
        )
        return 0

    return int(rows[0][0])
