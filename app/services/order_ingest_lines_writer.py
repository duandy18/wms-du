# app/services/order_ingest_lines_writer.py
from __future__ import annotations

from typing import Any, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _to_int(x: Any) -> int:
    try:
        return int(x)
    except Exception:
        return 0


def _extract_req_qty(items: Sequence[Mapping[str, Any]]) -> dict[int, int]:
    """
    标准化口径行事实（order_lines）：
    - 聚合维度：item_id
    - 值：req_qty（订单要求数量，整单履约判断口径）

    规则：
    - 忽略 item_id<=0 或 qty<=0
    - 同 item_id 累加 qty
    """
    out: dict[int, int] = {}
    for it in items or ():
        item_id = _to_int(it.get("item_id"))
        qty = _to_int(it.get("qty"))
        if item_id <= 0 or qty <= 0:
            continue
        out[item_id] = int(out.get(item_id, 0)) + int(qty)
    return out


async def insert_order_lines(
    session: AsyncSession,
    *,
    order_id: int,
    items: Sequence[Mapping[str, Any]],
) -> int:
    """
    写 order_lines（幂等）：

    注意：order_lines 目前没有 (order_id, item_id) 唯一约束。
    所以采取“先删后插”的幂等策略，避免重复写入。

    返回：本次插入的行数（req_qty 聚合后的 item 行数）。
    """
    lines = _extract_req_qty(items)
    if not lines:
        return 0

    oid = int(order_id)

    # 1) 幂等：清理旧行（该订单维度）
    await session.execute(
        text("DELETE FROM order_lines WHERE order_id = :oid"),
        {"oid": oid},
    )

    # 2) 重新插入标准化行事实
    for item_id, req_qty in lines.items():
        await session.execute(
            text(
                """
                INSERT INTO order_lines(order_id, item_id, req_qty)
                VALUES (:oid, :iid, :q)
                """
            ),
            {"oid": oid, "iid": int(item_id), "q": int(req_qty)},
        )

    return len(lines)
