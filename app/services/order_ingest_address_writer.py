# app/services/order_ingest_address_writer.py
from __future__ import annotations

from typing import Any, Mapping, Optional, Set

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _get_order_address_columns(session: AsyncSession) -> Set[str]:
    """
    动态探测 order_address 表有哪些列（避免不同环境/历史迁移差异）。
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT column_name
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND table_name = 'order_address'
                """
            )
        )
    ).all()
    return {str(r[0]) for r in rows}


def _pick_str(addr: Mapping[str, Any], *keys: str) -> Optional[str]:
    for k in keys:
        v = addr.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


async def upsert_order_address(
    session: AsyncSession,
    *,
    order_id: int,
    address: Optional[Mapping[str, Any]],
) -> None:
    """
    把 address 快照写入 order_address（用于审计/解释/对账）。
    - 不依赖具体 unique/constraint 名称
    - 先删后插：保证每单只有一条 address 快照
    """
    if not address:
        return

    cols = await _get_order_address_columns(session)
    if not cols:
        # 表不存在或无列（极端情况）：直接跳过
        return

    # 只写表里存在的字段，且字段名与现有路由输入对齐
    values: dict[str, Any] = {"order_id": int(order_id)}

    # 常见字段（orders.py 的 OrderAddrIn）
    if "receiver_name" in cols:
        values["receiver_name"] = _pick_str(address, "receiver_name", "name")
    if "receiver_phone" in cols:
        values["receiver_phone"] = _pick_str(address, "receiver_phone", "phone", "mobile")

    if "province" in cols:
        values["province"] = _pick_str(address, "province")
    if "city" in cols:
        values["city"] = _pick_str(address, "city")
    if "district" in cols:
        values["district"] = _pick_str(address, "district")
    if "detail" in cols:
        values["detail"] = _pick_str(address, "detail", "address_detail", "address")

    if "zipcode" in cols:
        values["zipcode"] = _pick_str(address, "zipcode", "zip")

    # 先删后插（幂等、简单、与事务模型一致）
    await session.execute(
        text("DELETE FROM order_address WHERE order_id = :oid"),
        {"oid": int(order_id)},
    )

    # 构造 insert
    insert_cols = [k for k in values.keys() if k in cols or k == "order_id"]
    placeholders = [f":{k}" for k in insert_cols]

    await session.execute(
        text(
            f"""
            INSERT INTO order_address ({", ".join(insert_cols)})
            VALUES ({", ".join(placeholders)})
            """
        ),
        values,
    )
