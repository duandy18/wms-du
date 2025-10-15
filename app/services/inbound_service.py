# app/services/inbound_service.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Dict, Any

from sqlalchemy import select, text, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import Stock
from app.models.stock_ledger import StockLedger
from app.models.item import Item
from app.models.location import Location
from app.models.warehouse import Warehouse

REASON_INBOUND = "INBOUND"


class InboundService:
    def __init__(self, stock_service: "StockService"):
        self.stock_service = stock_service

    @staticmethod
    def _col(model, name: str):
        return getattr(model, name, None)

    async def _resolve_item_id_by_sku(self, session: AsyncSession, sku: str) -> Optional[int]:
        return await session.scalar(select(Item.id).where(Item.sku == sku))

    async def _ensure_stage_location_id(self, session: AsyncSession) -> int:
        """
        确保存在可用“暂存(STAGE)”库位；若无则最小化创建。
        关键：对没有 identity/serial 的历史表，显式给 id，避免 NOT NULL 触发。
        规则：
          - 默认仓 id=1，不存在则先插入
          - 暂存位 id=0，避免与普通货位冲突，且容易识别
          - 若库位已存在，直接返回最小 id
        """
        # 1) 若表里已有任何库位，直接返回一个（优先有 code='STAGE'，否则最小 id）
        col_code = self._col(Location, "code")
        if col_code is not None:
            stage_id = await session.scalar(select(Location.id).where(col_code == "STAGE").limit(1))
            if stage_id is not None:
                return int(stage_id)

        any_loc = await session.scalar(select(Location.id).order_by(Location.id.asc()).limit(1))
        if any_loc is not None:
            return int(any_loc)

        # 2) 没有库位时，确保有默认仓（id=1）
        wh_id = await session.scalar(select(Warehouse.id).where(Warehouse.id == 1).limit(1))
        if wh_id is None:
            # 显式 id 插入，避免需要自增
            kw: Dict[str, Any] = {"id": 1}
            if self._col(Warehouse, "code") is not None:
                kw["code"] = "DEFAULT"
            if self._col(Warehouse, "name") is not None:
                kw["name"] = "Default Warehouse"
            # 直接 raw SQL，绕开模型的 autoincrement 假设
            cols = ", ".join(kw.keys())
            vals = ", ".join(f":{k}" for k in kw.keys())
            await session.execute(text(f"INSERT INTO warehouses ({cols}) VALUES ({vals}) ON CONFLICT (id) DO NOTHING"), kw)

        # 3) 插入 STAGE 库位（id=0）
        loc_kwargs: Dict[str, Any] = {"id": 0, "warehouse_id": 1}
        # code/name 有就填；没有就只填 name
        if self._col(Location, "code") is not None:
            loc_kwargs["code"] = "STAGE"
        if self._col(Location, "name") is not None:
            loc_kwargs["name"] = "Inbound Stage"
        # 直接 raw SQL，兼容最小字段集
        cols = ", ".join(loc_kwargs.keys())
        vals = ", ".join(f":{k}" for k in loc_kwargs.keys())
        await session.execute(
            text(f"INSERT INTO locations ({cols}) VALUES ({vals}) ON CONFLICT (id) DO NOTHING"),
            loc_kwargs,
        )
        # 返回 id=0
        return 0

    async def _bump_and_get(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        location_id: int,
        delta: int | float,
        batch_code: Optional[str],
        production_date: Optional[datetime],
        expiry_date: Optional[datetime],
    ) -> Stock:
        """
        统一调库存：优先调用 stock_service 的实现；若不存在则降级为内置方式。
        """
        if hasattr(self.stock_service, "_bump_stock_and_get"):
            return await getattr(self.stock_service, "_bump_stock_and_get")(
                session=session,
                item_id=item_id,
                location_id=location_id,
                delta=delta,
                batch_code=batch_code,
                production_date=production_date,
                expiry_date=expiry_date,
            )
        if hasattr(self.stock_service, "bump_stock_and_get"):
            return await getattr(self.stock_service, "bump_stock_and_get")(
                session=session,
                item_id=item_id,
                location_id=location_id,
                delta=delta,
                batch_code=batch_code,
                production_date=production_date,
                expiry_date=expiry_date,
            )
        # 最小实现（只维护 qty + 批次列）
        stock = await session.scalar(
            select(Stock).where(Stock.item_id == item_id, Stock.location_id == location_id).limit(1)
        )
        if stock is None:
            stock = Stock(item_id=item_id, location_id=location_id, qty=0)
            if hasattr(Stock, "batch_code") and batch_code is not None:
                stock.batch_code = batch_code
            if hasattr(Stock, "production_date"):
                stock.production_date = production_date
            if hasattr(Stock, "expiry_date"):
                stock.expiry_date = expiry_date
            session.add(stock)
            await session.flush()
        if hasattr(stock, "qty"):
            stock.qty = (stock.qty or 0) + delta
        await session.flush()
        return stock

    async def receive(
        self,
        session: AsyncSession,
        *,
        qty: int | float,
        ref: str,
        ref_line: str,
        sku: Optional[str] = None,
        item_id: Optional[int] = None,
        location_id: Optional[int] = None,
        batch_code: Optional[str] = None,
        production_date: Optional[datetime] = None,
        expiry_date: Optional[datetime] = None,
        occurred_at: Optional[datetime] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """
        强约束版：
        - 幂等键： (reason=INBOUND, ref, ref_line)
        - 台账固定字段： stock_id, reason, after_qty, delta, occurred_at, ref, ref_line
        - 仍保留 PG advisory_xact_lock + 保存点
        """
        if qty <= 0:
            raise ValueError("QTY_MUST_BE_POSITIVE")

        # 解析物料与库位
        if item_id is None:
            if not sku:
                raise ValueError("SKU_OR_ITEM_ID_REQUIRED")
            item_id = await self._resolve_item_id_by_sku(session, sku)
            if not item_id:
                raise ValueError("SKU_NOT_FOUND")
        if location_id is None:
            location_id = await self._ensure_stage_location_id(session)

        occurred_at = occurred_at or datetime.now(timezone.utc)

        # PG：事务级 advisory 锁，按幂等键聚合
        dialect = session.bind.dialect.name if session.bind is not None else ""
        if dialect.startswith("postgres"):
            key = f"{REASON_INBOUND}|{ref}|{ref_line}"
            await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": key})

        # 幂等：若已存在同键台账，直接返回
        existing = await session.scalar(
            select(StockLedger)
            .where(
                and_(
                    StockLedger.reason == REASON_INBOUND,
                    StockLedger.ref == ref,
                    StockLedger.ref_line == ref_line,
                )
            )
            .limit(1)
        )
        if existing:
            stock_now = await session.get(Stock, existing.stock_id) if getattr(existing, "stock_id", None) else None
            accepted_qty = getattr(existing, "delta", None) or qty
            return {
                "idempotent": True,
                "item_id": item_id,
                "accepted_qty": accepted_qty,
                "ledger_id": existing.id,
                "stock_id": getattr(existing, "stock_id", None),
                "after_qty": getattr(existing, "after_qty", None),
                "delta": getattr(existing, "delta", None),
                "ref": getattr(existing, "ref", ref),
                "ref_line": getattr(existing, "ref_line", ref_line),
                "reason": REASON_INBOUND,
                "stock_qty_now": (stock_now.qty if stock_now else None),
            }

        # 调整库存 & 获取最新数量
        stock = await self._bump_and_get(
            session=session,
            item_id=item_id,
            location_id=location_id,
            delta=qty,
            batch_code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
        )
        after_qty = stock.qty

        # 固定字段写入台账（保存点内）
        try:
            async with session.begin_nested():
                ledger = StockLedger(
                    stock_id=stock.id,
                    reason=REASON_INBOUND,
                    after_qty=after_qty,
                    delta=qty,
                    occurred_at=occurred_at,
                    ref=ref,
                    ref_line=ref_line,
                )
                session.add(ledger)
                await session.flush()
        except IntegrityError:
            # 唯一键/并发冲突时，回读幂等记录
            existing = await session.scalar(
                select(StockLedger)
                .where(
                    and_(
                        StockLedger.reason == REASON_INBOUND,
                        StockLedger.ref == ref,
                        StockLedger.ref_line == ref_line,
                    )
                )
                .limit(1)
            )
            stock_now = await session.get(Stock, existing.stock_id) if existing and existing.stock_id else None
            return {
                "idempotent": True,
                "item_id": item_id,
                "accepted_qty": qty,
                "ledger_id": existing.id if existing else None,
                "stock_id": existing.stock_id if existing else None,
                "after_qty": existing.after_qty if existing else None,
                "delta": existing.delta if existing else None,
                "ref": ref,
                "ref_line": ref_line,
                "reason": REASON_INBOUND,
                "stock_qty_now": (stock_now.qty if stock_now else None),
            }

        # 正常返回
        return {
            "idempotent": False,
            "item_id": item_id,
            "accepted_qty": qty,
            "ledger_id": ledger.id,  # type: ignore[name-defined]
            "stock_id": stock.id,
            "after_qty": after_qty,
            "delta": qty,
            "ref": ref,
            "ref_line": ref_line,
            "reason": REASON_INBOUND,
            "stock_qty_now": stock.qty,
        }
