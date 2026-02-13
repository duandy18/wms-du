# app/services/order_ingest_orders_writer.py
from __future__ import annotations

import json
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_utils import to_dec_str

_VALID_SCOPES = {"PROD", "DRILL"}


def _norm_scope(scope: Optional[str]) -> str:
    sc = (scope or "").strip().upper() or "PROD"
    if sc not in _VALID_SCOPES:
        raise ValueError("scope must be PROD|DRILL")
    return sc


async def insert_order_or_get_idempotent(
    session: AsyncSession,
    *,
    scope: str = "PROD",
    platform: str,
    shop_id: str,
    ext_order_no: str,
    occurred_at,
    buyer_name: Optional[str],
    buyer_phone: Optional[str],
    order_amount,
    pay_amount,
    # NOTE: items 在 orders 插入阶段不使用，但上层为了保持调用一致会传入；这里显式接收以避免 TypeError
    items: Sequence[Mapping[str, Any]] = (),
    extras: Optional[Mapping[str, Any]],
    trace_id: Optional[str],
    orders_has_extras: bool,
    order_ref: str,
) -> dict:
    """
    写 orders：
    - 若插入成功：返回 {"status": "OK_NEW", "id": int}
    - 若幂等命中：返回 {"status": "IDEMPOTENT", "id": int|None, "ref": order_ref}
      并且在 trace_id 非空时补写 orders.trace_id（仅在原值为空时填充）
    """
    _ = items  # 明确不使用，避免 lint 误报（也保持行为不变）

    sc = _norm_scope(scope)

    if orders_has_extras:
        sql_ins_orders = text(
            """
            INSERT INTO orders (
                scope,
                platform,
                shop_id,
                ext_order_no,
                status,
                buyer_name,
                buyer_phone,
                order_amount,
                pay_amount,
                created_at,
                updated_at,
                extras,
                trace_id
            )
            VALUES (
                :sc,
                :p, :s, :o,
                'CREATED',
                :bn, :bp,
                :oa, :pa,
                :at, :at,
                :ex,
                :tid
            )
            ON CONFLICT ON CONSTRAINT uq_orders_platform_shop_ext DO NOTHING
            RETURNING id
            """
        )
        bind_orders = {
            "sc": sc,
            "p": platform,
            "s": shop_id,
            "o": ext_order_no,
            "bn": buyer_name,
            "bp": buyer_phone,
            "oa": to_dec_str(order_amount),
            "pa": to_dec_str(pay_amount),
            "at": occurred_at,
            "ex": json.dumps(extras or {}, ensure_ascii=False),
            "tid": trace_id,
        }
    else:
        sql_ins_orders = text(
            """
            INSERT INTO orders (
                scope,
                platform,
                shop_id,
                ext_order_no,
                status,
                buyer_name,
                buyer_phone,
                order_amount,
                pay_amount,
                created_at,
                updated_at,
                trace_id
            )
            VALUES (
                :sc,
                :p, :s, :o,
                'CREATED',
                :bn, :bp,
                :oa, :pa,
                :at, :at,
                :tid
            )
            ON CONFLICT ON CONSTRAINT uq_orders_platform_shop_ext DO NOTHING
            RETURNING id
            """
        )
        bind_orders = {
            "sc": sc,
            "p": platform,
            "s": shop_id,
            "o": ext_order_no,
            "bn": buyer_name,
            "bp": buyer_phone,
            "oa": to_dec_str(order_amount),
            "pa": to_dec_str(pay_amount),
            "at": occurred_at,
            "tid": trace_id,
        }

    rec = await session.execute(sql_ins_orders, bind_orders)
    new_id = rec.scalar()
    if new_id is None:
        # 已有同键订单：查 id 并为旧数据补 trace_id（仅在 trace_id 为空时填充）
        row = (
            await session.execute(
                text(
                    """
                    SELECT id
                      FROM orders
                     WHERE scope=:sc
                       AND platform=:p
                       AND shop_id=:s
                       AND ext_order_no=:o
                     LIMIT 1
                    """
                ),
                {"sc": sc, "p": platform, "s": shop_id, "o": ext_order_no},
            )
        ).first()
        order_id = int(row[0]) if row else None
        if order_id is not None and trace_id:
            await session.execute(
                text(
                    """
                    UPDATE orders
                       SET trace_id = COALESCE(trace_id, :tid)
                     WHERE id = :oid
                    """
                ),
                {"oid": order_id, "tid": trace_id},
            )

        return {
            "status": "IDEMPOTENT",
            "id": order_id,
            "ref": order_ref,
        }

    return {"status": "OK_NEW", "id": int(new_id)}
