# app/services/inbound_service.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import zlib
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession


class InboundService:
    """
    入库服务（HTTP 与测试共享）
    - 自动创建缺失的 SKU（items）
    - 自动创建 STAGE 库位（location_id=0）
    - 直写 stocks 进行入库（UPSERT +qty）
    - 写一条 INBOUND 台账（stock_ledger），ref_line 为稳定整数
    - 返回 {"item_id": item_id, "accepted_qty": qty}
    """

    def __init__(self, stock_service: Optional[Any] = None) -> None:
        # 预留：目前直写 SQL，不依赖 StockService；保留注入位便于将来切换
        self.stock_service = stock_service

    # ---------------- public API ----------------
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
        occurred_at: Optional[datetime] = None,  # 兼容签名，当前未入库到 ledger（无 ts 列）
        stage_location_id: int = 0,
    ) -> Dict[str, Any]:
        """
        接收入库到 STAGE（默认 location_id=0）。
        - 若 items 中无 sku，自动创建；
        - 若 locations 无 STAGE，自动创建；
        - stocks 增加 qty，并写一条 INBOUND 台账（ref_line 稳定整数映射，ON CONFLICT DO NOTHING 保证幂等）。
        """
        item_id = await self._ensure_item(session, sku)
        await self._ensure_stage_location(session, stage_location_id)

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
            {"item_id": item_id, "loc_id": stage_location_id, "q": qty},
        )
        stock_id, after_qty = upsert.first()
        stock_id, after_qty = int(stock_id), int(after_qty)

        # 2) 写 INBOUND 台账（无 ts 列；幂等用 (reason,ref,ref_line)）
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

    # ---------------- helpers ----------------
    async def _ensure_item(self, session: AsyncSession, sku: str) -> int:
        # 已有则直接返回
        row = await session.execute(
            text("SELECT id FROM items WHERE sku = :sku LIMIT 1"),
            {"sku": sku},
        )
        got = row.first()
        if got:
            return int(got[0])

        # 无则建（name 同 sku）
        ins = await session.execute(
            text("INSERT INTO items (sku, name) VALUES (:sku, :name) RETURNING id"),
            {"sku": sku, "name": sku},
        )
        return int(ins.scalar())

    async def _ensure_stage_location(self, session: AsyncSession, loc_id: int) -> None:
        row = await session.execute(
            text("SELECT 1 FROM locations WHERE id = :i LIMIT 1"), {"i": loc_id}
        )
        if row.first():
            return
        await session.execute(
            text(
                """
                INSERT INTO locations (id, name, warehouse_id)
                VALUES (:i, :name, 1)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {"i": loc_id, "name": "STAGE"},
        )


# ---------- utils ----------
def _to_ref_line_int(ref_line: Any) -> int:
    """
    把 ref_line（可能是 str/int/其它）转换为稳定的正整数：
    - int 直接返回；
    - 其他类型（含 str）使用 CRC32，保证同值同结果。
    """
    if isinstance(ref_line, int):
        return ref_line
    s = str(ref_line)
    return int(zlib.crc32(s.encode("utf-8")) & 0x7FFFFFFF)
