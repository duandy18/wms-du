# app/services/inbound_service.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
import zlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class InboundService:
    """
    入库服务（HTTP 与测试共享）
    - 自动创建缺失的 SKU（items）
    - 优先使用 preferred_id（默认 0）作为 STAGE；若不存在再回退 ILIKE 'STAGE%' → 最小 id → 创建 preferred_id
    - 直写 stocks 入库（UPSERT +qty）
    - 写一条 INBOUND 台账（stock_ledger），含 item_id/ref_line/occurred_at
    - 幂等：若已存在 (reason,ref,ref_line) 台账，则直接返回 idempotent=True
    """

    def __init__(self, stock_service: Any | None = None) -> None:
        self.stock_service = stock_service

    async def receive(
        self,
        *,
        session: AsyncSession,
        sku: str,
        qty: int,
        ref: str,
        ref_line: Any,
        batch_code: str | None = None,
        production_date: datetime | None = None,
        expiry_date: datetime | None = None,
        occurred_at: datetime | None = None,
        stage_location_id: int = 0,
    ) -> dict[str, Any]:
        item_id = await self._ensure_item(session, sku)
        stage_id = await self._resolve_stage_location(session, preferred_id=stage_location_id)
        ref_line_int = _to_ref_line_int(ref_line)

        if await self._inbound_ledger_exists(session, ref=ref, ref_line=ref_line_int):
            return {"item_id": item_id, "accepted_qty": 0, "idempotent": True}

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

        ts = occurred_at or datetime.now(UTC)

        # ★ 关键：一并写入 item_id
        await session.execute(
            text(
                """
                INSERT INTO stock_ledger (stock_id, item_id, reason, ref, ref_line, delta, after_qty, occurred_at)
                VALUES (:sid, :item, 'INBOUND', :ref, :ref_line, :delta, :after, :ts)
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "sid": stock_id,
                "item": item_id,
                "ref": ref,
                "ref_line": ref_line_int,
                "delta": qty,
                "after": after_qty,
                "ts": ts,
            },
        )

        return {"item_id": item_id, "accepted_qty": qty, "idempotent": False}

    async def _ensure_item(self, session: AsyncSession, sku: str) -> int:
        row = await session.execute(
            text("SELECT id FROM items WHERE sku = :sku LIMIT 1"),
            {"sku": sku},
        )
        got = row.first()
        if got:
            return int(got[0])

        row = await session.execute(text("SELECT 1 FROM items WHERE id = 1"))
        id1_taken = row.first() is not None
        if not id1_taken:
            try:
                ins1 = await session.execute(
                    text("INSERT INTO items (id, sku, name) VALUES (1, :sku, :name) RETURNING id"),
                    {"sku": sku, "name": sku},
                )
                return int(ins1.scalar())
            except Exception:
                pass

        ins = await session.execute(
            text("INSERT INTO items (sku, name) VALUES (:sku, :name) RETURNING id"),
            {"sku": sku, "name": sku},
        )
        return int(ins.scalar())

    async def _resolve_stage_location(self, session: AsyncSession, *, preferred_id: int) -> int:
        row = await session.execute(
            text("SELECT id FROM locations WHERE id = :i LIMIT 1"), {"i": preferred_id}
        )
        got = row.first()
        if got:
            return int(got[0])

        row = await session.execute(
            text("SELECT id FROM locations WHERE name ILIKE 'STAGE%' ORDER BY id ASC LIMIT 1")
        )
        got = row.first()
        if got:
            return int(got[0])

        row = await session.execute(text("SELECT id FROM locations ORDER BY id ASC LIMIT 1"))
        got = row.first()
        if got:
            return int(got[0])

        await session.execute(
            text(
                "INSERT INTO locations (id, name, warehouse_id) "
                "VALUES (:i, 'STAGE', 1) ON CONFLICT (id) DO NOTHING"
            ),
            {"i": preferred_id},
        )
        return int(preferred_id)

    async def _inbound_ledger_exists(
        self, session: AsyncSession, *, ref: str, ref_line: int
    ) -> bool:
        r = await session.execute(
            text(
                """
                SELECT 1
                  FROM stock_ledger
                 WHERE reason = 'INBOUND'
                   AND ref    = :ref
                   AND ref_line = :line
                 LIMIT 1
                """
            ),
            {"ref": ref, "line": ref_line},
        )
        return r.first() is not None


def _to_ref_line_int(ref_line: Any) -> int:
    if isinstance(ref_line, int):
        return ref_line
    s = str(ref_line)
    return int(zlib.crc32(s.encode("utf-8")) & 0x7FFFFFFF)
