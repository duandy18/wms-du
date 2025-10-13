# app/services/inbound_service.py
from __future__ import annotations

from datetime import date
from typing import Optional, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.batch import Batch
from app.models.stock import Stock
from app.models.stock_ledger import StockLedger


class InboundService:
    # ---------------- helpers: model capability probes ----------------

    @staticmethod
    def _batch_code_attr():
        """Return the SA column attr for batch code, supporting Batch.code / Batch.batch_code."""
        code_attr = getattr(Batch, "code", None) or getattr(Batch, "batch_code", None)
        if code_attr is None:
            raise AssertionError("Batch model must define `code` or `batch_code` column")
        return code_attr

    @staticmethod
    def _stocks_support_batch() -> bool:
        """Does Stock have a batch_id column?"""
        return hasattr(Stock, "batch_id")

    @staticmethod
    def _ledger_attr_map() -> Dict[str, str]:
        """
        Map logical ledger fields -> actual attribute names that exist on StockLedger.
        We try several common variants and pick the first that exists.
        NOTE: we intentionally DO NOT support 'stock_id' to avoid mismatches with DB schema.
        """
        def pick(*names: str) -> Optional[str]:
            for n in names:
                if hasattr(StockLedger, n):
                    return n
            return None

        return {
            "op":        pick("op", "operation", "action", "reason"),   # 操作/事由字段
            "item_id":   "item_id" if hasattr(StockLedger, "item_id") else None,
            "location_id": "location_id" if hasattr(StockLedger, "location_id") else None,
            "batch_id":  "batch_id" if hasattr(StockLedger, "batch_id") else None,
            # 不再写入 stock_id —— 即使 ORM 里有也忽略
            "delta":     "delta" if hasattr(StockLedger, "delta") else None,
            "ref":       "ref" if hasattr(StockLedger, "ref") else None,
            "ref_line":  ("ref_line" if hasattr(StockLedger, "ref_line")
                          else ("refline" if hasattr(StockLedger, "refline")
                                else ("line" if hasattr(StockLedger, "line") else None))),
            "after_qty": "after_qty" if hasattr(StockLedger, "after_qty") else None,
        }

    @staticmethod
    def _make_ledger(**logical_fields: Any) -> StockLedger:
        """
        Create a StockLedger instance by mapping logical field names to actual model attributes.
        Unknown / missing attributes are ignored safely.
        """
        attrmap = InboundService._ledger_attr_map()
        obj = StockLedger()
        for k, v in logical_fields.items():
            real = attrmap.get(k)
            if real is not None and hasattr(obj, real):
                setattr(obj, real, v)
        return obj

    # ---------------- helpers: stocks upsert ----------------

    async def _select_stock_row(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        location_id: int,
        batch_id: Optional[int],
    ) -> Optional[Stock]:
        q = select(Stock).where(
            Stock.item_id == item_id,
            Stock.location_id == location_id,
        )
        if self._stocks_support_batch():
            q = q.where(Stock.batch_id == batch_id)

        q = q.with_for_update()
        res = await session.execute(q)
        return res.scalar_one_or_none()

    async def _upsert_stock_delta(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        location_id: int,
        batch_id: Optional[int],
        delta: int,
    ) -> Stock:
        s = await self._select_stock_row(
            session, item_id=item_id, location_id=location_id, batch_id=batch_id
        )

        if s is None:
            kwargs = dict(item_id=item_id, location_id=location_id, qty=0)
            if self._stocks_support_batch():
                kwargs["batch_id"] = batch_id
            s = Stock(**kwargs)  # type: ignore[arg-type]
            session.add(s)
            await session.flush()

        s.qty = s.qty + delta
        if s.qty < 0:
            raise ValueError("NEGATIVE_STOCK")
        await session.flush()
        return s

    # ---------------- domain: batch ----------------

    async def ensure_batch(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        code: str,
        production_date: Optional[date],
        expiry_date: Optional[date],
    ) -> Batch:
        code_attr = self._batch_code_attr()

        res = await session.execute(
            select(Batch).where(Batch.item_id == item_id, code_attr == code)
        )
        b = res.scalar_one_or_none()
        if b:
            # 校验日期一致性（如你不需要可删）
            if (
                (expiry_date and b.expiry_date and expiry_date != b.expiry_date)
                or (production_date and b.production_date and production_date != b.production_date)
            ):
                raise ValueError("BATCH_EXPIRY_CONFLICT")
            return b

        b = Batch(item_id=item_id, production_date=production_date, expiry_date=expiry_date)
        setattr(b, code_attr.key, code)
        session.add(b)
        await session.flush()
        return b

    # ---------------- domain: inbound ----------------

    async def receive(
        self,
        session: AsyncSession,
        *,
        sku: str,
        qty: int,
        batch_code: str,
        production_date: Optional[date],
        expiry_date: Optional[date],
        ref: str,
        ref_line: str,
    ):
        # 1) item
        res = await session.execute(select(Item).where(Item.sku == sku))
        item = res.scalar_one_or_none()
        if not item:
            raise ValueError("SKU_NOT_FOUND")

        # 2) batch
        batch = await self.ensure_batch(
            session,
            item_id=item.id,
            code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
        )

        # 3) 暂存区入账
        tmp_location = 0
        s = await self._upsert_stock_delta(
            session,
            item_id=item.id,
            location_id=tmp_location,
            batch_id=getattr(batch, "id", None),
            delta=qty,
        )

        # 4) 记账（仅设置存在的字段；不写 stock_id）
        ledger = self._make_ledger(
            op="INBOUND",
            item_id=item.id,
            location_id=tmp_location,
            batch_id=getattr(batch, "id", None),
            delta=qty,
            ref=ref,
            ref_line=ref_line,
            after_qty=getattr(s, "qty", None),
        )
        session.add(ledger)
        await session.flush()

        return {"item_id": item.id, "batch_id": batch.id, "accepted_qty": qty}

    async def putaway(
        self,
        session: AsyncSession,
        *,
        sku: str,
        batch_code: str,
        qty: int,
        to_location_id: int,
        ref: str,
        ref_line: str,
    ):
        # 1) item
        res = await session.execute(select(Item).where(Item.sku == sku))
        item = res.scalar_one_or_none()
        if not item:
            raise ValueError("SKU_NOT_FOUND")

        # 2) batch
        code_attr = self._batch_code_attr()
        res = await session.execute(
            select(Batch).where(Batch.item_id == item.id, code_attr == batch_code)
        )
        batch = res.scalar_one_or_none()
        if not batch:
            raise ValueError("BATCH_NOT_FOUND")

        tmp_location = 0

        # 3) 扣暂存
        s_out = await self._upsert_stock_delta(
            session,
            item_id=item.id,
            location_id=tmp_location,
            batch_id=getattr(batch, "id", None),
            delta=-qty,
        )
        # 4) 加到目标位
        s_in = await self._upsert_stock_delta(
            session,
            item_id=item.id,
            location_id=to_location_id,
            batch_id=getattr(batch, "id", None),
            delta=qty,
        )

        # 5) 记两条流水（不写 stock_id）
        ledger_out = self._make_ledger(
            op="PUTAWAY",
            item_id=item.id,
            location_id=tmp_location,
            batch_id=getattr(batch, "id", None),
            delta=-qty,
            ref=ref,
            ref_line=f"{ref_line}-out",
            after_qty=getattr(s_out, "qty", None),
        )
        ledger_in = self._make_ledger(
            op="PUTAWAY",
            item_id=item.id,
            location_id=to_location_id,
            batch_id=getattr(batch, "id", None),
            delta=qty,
            ref=ref,
            ref_line=f"{ref_line}-in",
            after_qty=getattr(s_in, "qty", None),
        )
        session.add(ledger_out)
        session.add(ledger_in)
        await session.flush()

        return {
            "item_id": item.id,
            "batch_id": batch.id,
            "to_location_id": to_location_id,
            "moved_qty": qty,
        }
