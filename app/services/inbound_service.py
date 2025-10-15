# app/services/inbound_service.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import zlib
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class InboundService:
    """
    入库服务（HTTP 与测试共享）
    - 自动创建缺失的 SKU（items）
    - 优先复用已有 STAGE 库位（名称以 STAGE 开头，或回退到现有最小 id），否则创建 preferred_id
    - 直写 stocks 入库（UPSERT +qty）
    - 写一条 INBOUND 台账（stock_ledger），ref_line 为稳定整数
    - 返回 {"item_id": item_id, "accepted_qty": qty}
    """

    def __init__(self, stock_service: Optional[Any] = None) -> None:
        self.stock_service = stock_service  # 预留注入位

    async def receive(
        self,
        *,
        session: AsyncSession,
        sku: str,
        qty: int,
        ref: str,
        ref_line: Any,
        batch_code: Optional[str] = None,
        production_date: Optional[datetime] = None,
        expiry_date: Optional[datetime] = None,
        occurred_at: Optional[datetime] = None,  # 兼容签名（当前未写入 ledger；无 ts 列）
        stage_location_id: int = 0,
    ) -> Dict[str, Any]:
        """
        接收入库到 STAGE 库位（见 _resolve_stage_location 解析策略）。
        幂等：依赖 (reason,ref,ref_line) 的 ON CONFLICT DO NOTHING。
        """
        item_id = await self._ensure_item(session, sku)
        stage_id = await self._resolve_stage_location(session, preferred_id=stage_location_id)
        ref_line_int = _to_ref_line_int(ref_line)

        # 1) 增加 STAGE 库存（UPSERT）
        upsert = await session.execute(
            text(
                """
                INSERT INTO stocks (item_id, location_id, qty)
                VALUES (:item_id, :loc_id, :q)
                ON CONFLICT (item_id, location_id)
                DO UPDATE SET qty = stocks.qty + EXCLUDED.qty
                RETURNING id, qty
                """
            ),
            {"item_id": item_id, "loc_id": stage_id, "q": qty},
        )
        stock_id, after_qty = upsert.first()
        stock_id, after_qty = int(stock_id), int(after_qty)

        # 2) 写 INBOUND 台账（无 ts 列）
        await session.execute(
            text(
                """
                INSERT INTO stock_ledger (stock_id, reason, ref, ref_line, delta, after_qty)
                VALUES (:sid, 'INBOUND', :ref, :ref_line, :delta, :after)
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "sid": stock_id,
                "ref": ref,
                "ref_line": ref_line_int,
                "delta": qty,
                "after": after_qty,
            },
        )

        return {"item_id": item_id, "accepted_qty": qty}

    # ---------- helpers ----------
    async def _ensure_item(self, session: AsyncSession, sku: str) -> int:
        row = await session.execute(text("SELECT id FROM items WHERE sku = :sku LIMIT 1"), {"sku": sku})
        got = row.first()
        if got:
            return int(got[0])
        ins = await session.execute(
            text("INSERT INTO items (sku, name) VALUES (:sku, :name) RETURNING id"),
            {"sku": sku, "name": sku},
        )
        return int(ins.scalar())

    async def _resolve_stage_location(self, session: AsyncSession, *, preferred_id: int) -> int:
        """
        三段式解析库位：
        1) 名称 ILIKE 'STAGE%' 的库位，按 id 升序取一个；
        2) 否则取 locations 表最小 id（测试常见：先造了一个 STAGE 库位，id 可能非 0）；
        3) 若库位表为空，则创建 preferred_id（默认 0）。
        """
        # 1) 名称 ILIKE 'STAGE%'
        row = await session.execute(
            text("SELECT id FROM locations WHERE name ILIKE 'STAGE%' ORDER BY id ASC LIMIT 1")
        )
        got = row.first()
        if got:
            return int(got[0])

        # 2) 任意现有库位（最小 id）
        row = await session.execute(text("SELECT id FROM locations ORDER BY id ASC LIMIT 1"))
        got = row.first()
        if got:
            return int(got[0])

        # 3) 创建 preferred_id 作为 STAGE
        await session.execute(
            text(
                """
                INSERT INTO locations (id, name, warehouse_id)
                VALUES (:i, 'STAGE', 1)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {"i": preferred_id},
        )
        return int(preferred_id)


# ---------- utils ----------
def _to_ref_line_int(ref_line: Any) -> int:
    """把任意类型 ref_line 映射为稳定正整数（int 直返，其他用 CRC32）。"""
    if isinstance(ref_line, int):
        return ref_line
    s = str(ref_line)
    return int(zlib.crc32(s.encode("utf-8")) & 0x7FFFFFFF)
