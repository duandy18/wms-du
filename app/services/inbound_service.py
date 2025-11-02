# app/services/inbound_service.py
from __future__ import annotations

import zlib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class InboundService:
    """
    入库服务（HTTP 与测试共享 · v1.0 强契约）
    - 校验：sku 非空、qty>0
    - 自动创建缺失的 SKU（items）、仓/库位（默认优先使用 preferred_id 作为 STAGE）
    - 直写 stocks：UPSERT +qty（stage 库位）
    - 写一条 INBOUND 台账（stock_ledger），带 item_id/ref_line/occurred_at/after_qty（UTC）
    - 幂等：若已存在 (reason='INBOUND', ref, ref_line) 台账，则直接返回 idempotent=True，不再写入
    - 提交策略：commit=True 时内部提交；否则由上层统一事务
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
        batch_code: str | None = None,           # 预留：v1.1 批次
        production_date: datetime | None = None, # 预留
        expiry_date: datetime | None = None,     # 预留
        occurred_at: datetime | None = None,
        stage_location_id: int = 0,              # 优先作为 STAGE 库位使用；0 表示“尽力使用/创建”
        commit: bool = True,
    ) -> dict[str, Any]:
        if not sku or not str(sku).strip():
            raise ValueError("sku 不能为空")
        if int(qty) <= 0:
            raise ValueError("qty 必须大于 0")

        item_id = await self._ensure_item(session, sku)
        stage_id = await self._resolve_stage_location(session, preferred_id=int(stage_location_id))
        ref_line_int = _to_ref_line_int(ref_line)

        # 幂等：同一 (reason, ref, ref_line) 只接受一次
        if await self._inbound_ledger_exists(session, ref=ref, ref_line=ref_line_int):
            return {"item_id": item_id, "accepted_qty": 0, "idempotent": True}

        # stocks：UPSERT +qty（返回 id 与更新后的 qty）
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
            {"item_id": item_id, "loc_id": stage_id, "q": int(qty)},
        )
        row = upsert.first()
        if not row:
            raise RuntimeError("入库失败：未能写入/更新 stocks")
        stock_id, after_qty = int(row[0]), int(row[1])

        ts = occurred_at or datetime.now(UTC)

        # 台账：INBOUND（带 after_qty 与 UTC 时间）
        # 重要：使用 CAST(:param AS type) 避免 asyncpg 对同一参数推断出不同类型（text vs varchar），
        # 同时确保绑定参数被 SQLAlchemy 正确识别（不会出现 parameters=()）。
        await session.execute(
            text(
                """
                INSERT INTO stock_ledger
                    (stock_id, item_id, reason, ref, ref_line, delta, after_qty, occurred_at)
                SELECT
                    CAST(:sid      AS integer),
                    CAST(:item     AS integer),
                    'INBOUND',
                    CAST(:ref      AS text),
                    CAST(:ref_line AS integer),
                    CAST(:delta    AS integer),
                    CAST(:after    AS integer),
                    CAST(:ts       AS timestamptz)
                WHERE NOT EXISTS (
                    SELECT 1 FROM stock_ledger sl
                    WHERE sl.reason   = 'INBOUND'
                      AND sl.ref      = CAST(:ref      AS text)
                      AND sl.ref_line = CAST(:ref_line AS integer)
                      AND sl.item_id  = CAST(:item     AS integer)
                      AND sl.stock_id = CAST(:sid      AS integer)
                )
                """
            ),
            {
                "sid": stock_id,
                "item": item_id,
                "ref": ref,
                "ref_line": ref_line_int,
                "delta": int(qty),
                "after": after_qty,
                "ts": ts,
            },
        )

        if commit:
            await session.commit()

        return {"item_id": item_id, "accepted_qty": int(qty), "idempotent": False}

    # ---------------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------------

    async def _ensure_item(self, session: AsyncSession, sku: str) -> int:
        r = await session.execute(text("SELECT id FROM items WHERE sku = :sku LIMIT 1"), {"sku": sku})
        got = r.first()
        if got:
            return int(got[0])

        # 尝试把 id=1 留作首个商品（便于演示/脚本）
        r = await session.execute(text("SELECT 1 FROM items WHERE id = 1"))
        id1_taken = r.first() is not None
        if not id1_taken:
            try:
                ins1 = await session.execute(
                    text("INSERT INTO items (id, sku, name) VALUES (1, :sku, :name) RETURNING id"),
                    {"sku": sku, "name": sku},
                )
                return int(ins1.scalar())
            except Exception:
                # 并发/约束导致失败则继续走普通插入
                pass

        ins = await session.execute(
            text("INSERT INTO items (sku, name) VALUES (:sku, :name) RETURNING id"),
            {"sku": sku, "name": sku},
        )
        return int(ins.scalar())

    async def _ensure_warehouse1(self, session: AsyncSession) -> int:
        # 确保有一个默认仓（id=1），若无则就地创建
        r = await session.execute(text("SELECT id FROM warehouses WHERE id=1"))
        got = r.first()
        if got:
            return 1
        await session.execute(text("INSERT INTO warehouses (id, name) VALUES (1, 'AUTO-WH') ON CONFLICT DO NOTHING"))
        return 1

    async def _resolve_stage_location(self, session: AsyncSession, *, preferred_id: int) -> int:
        """
        选择/创建 STAGE 库位优先级：
        1) preferred_id 存在 → 直接使用
        2) 名称 ILIKE 'STAGE%' 的最小 id
        3) 任意 locations 的最小 id
        4) 若都没有，则创建 {id=preferred_id or 1, name='STAGE', warehouse_id=1}
        """
        if preferred_id > 0:
            r = await session.execute(text("SELECT id FROM locations WHERE id = :i LIMIT 1"), {"i": preferred_id})
            got = r.first()
            if got:
                return int(got[0])

        r = await session.execute(text("SELECT id FROM locations WHERE name ILIKE 'STAGE%' ORDER BY id ASC LIMIT 1"))
        got = r.first()
        if got:
            return int(got[0])

        r = await session.execute(text("SELECT id FROM locations ORDER BY id ASC LIMIT 1"))
        got = r.first()
        if got:
            return int(got[0])

        # 创建默认仓与 STAGE 库位
        wid = await self._ensure_warehouse1(session)
        loc_id = preferred_id if preferred_id > 0 else 1
        await session.execute(
            text(
                "INSERT INTO locations (id, name, warehouse_id) "
                "VALUES (:i, 'STAGE', :w) ON CONFLICT (id) DO NOTHING"
            ),
            {"i": loc_id, "w": wid},
        )
        return int(loc_id)

    async def _inbound_ledger_exists(self, session: AsyncSession, *, ref: str, ref_line: int) -> bool:
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
    # 统一 31bit 正整数
    return int(zlib.crc32(s.encode("utf-8")) & 0x7FFFFFFF)
