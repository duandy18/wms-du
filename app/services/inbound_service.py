from datetime import date
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.models.item import Item
from app.models.batch import Batch
from app.models.stock import Stock
from app.models.stock_ledger import StockLedger

class InboundService:
    async def ensure_batch(
        self, session: AsyncSession, *, item_id: int, code: str,
        production_date: date | None, expiry_date: date | None
    ) -> Batch:
        q = await session.execute(
            select(Batch).where(Batch.item_id == item_id, Batch.code == code)
        )
        b = q.scalar_one_or_none()
        if b:
            # 防止效期冲突：同 item+code 的效期不可矛盾
            if (expiry_date and b.expiry_date and expiry_date != b.expiry_date) or \
               (production_date and b.production_date and production_date != b.production_date):
                raise ValueError("BATCH_EXPIRY_CONFLICT")
            return b
        b = Batch(item_id=item_id, code=code, production_date=production_date, expiry_date=expiry_date)
        session.add(b)
        await session.flush()
        return b

    async def _upsert_stock_delta(
        self, session: AsyncSession, *, item_id: int, location_id: int, batch_id: int | None, delta: int
    ) -> Stock:
        q = await session.execute(
            select(Stock).where(
                Stock.item_id == item_id,
                Stock.location_id == location_id,
                Stock.batch_id == batch_id,
            ).with_for_update()
        )
        s = q.scalar_one_or_none()
        if s is None:
            s = Stock(item_id=item_id, location_id=location_id, batch_id=batch_id, qty=0)
            session.add(s)
            await session.flush()
        s.qty = s.qty + delta
        if s.qty < 0:
            raise ValueError("NEGATIVE_STOCK")
        await session.flush()
        return s

    async def receive(
        self, session: AsyncSession, *, sku: str, qty: int,
        batch_code: str, production_date: date | None, expiry_date: date | None,
        ref: str, ref_line: str
    ):
        # 1) item
        q = await session.execute(select(Item).where(Item.sku == sku))
        item = q.scalar_one_or_none()
        if not item:
            raise ValueError("SKU_NOT_FOUND")

        # 2) batch & 防效期冲突
        batch = await self.ensure_batch(
            session, item_id=item.id, code=batch_code,
            production_date=production_date, expiry_date=expiry_date
        )

        # 3) 暂存区（0 号库位）入账：INBOUND
        tmp_location = 0
        stock = await self._upsert_stock_delta(
            session, item_id=item.id, location_id=tmp_location, batch_id=batch.id, delta=qty
        )

        # 4) 记账（ledger 幂等：ref+line 唯一）
        session.add(StockLedger(
            op="INBOUND", item_id=item.id, location_id=tmp_location,
            batch_id=batch.id, delta=qty, ref=ref, ref_line=ref_line
        ))
        await session.flush()

        return {"item_id": item.id, "batch_id": batch.id, "accepted_qty": qty}

    async def putaway(
        self, session: AsyncSession, *, sku: str, batch_code: str, qty: int,
        to_location_id: int, ref: str, ref_line: str
    ):
        # 1) 找 item, batch
        q = await session.execute(select(Item).where(Item.sku == sku))
        item = q.scalar_one_or_none()
        if not item:
            raise ValueError("SKU_NOT_FOUND")
        q = await session.execute(select(Batch).where(Batch.item_id == item.id, Batch.code == batch_code))
        batch = q.scalar_one_or_none()
        if not batch:
            raise ValueError("BATCH_NOT_FOUND")

        # 2) 从暂存(0)扣减 → 目标库位增加；两条 ledger
        tmp_location = 0
        await self._upsert_stock_delta(
            session, item_id=item.id, location_id=tmp_location, batch_id=batch.id, delta=-qty
        )
        await self._upsert_stock_delta(
            session, item_id=item.id, location_id=to_location_id, batch_id=batch.id, delta=qty
        )

        session.add(StockLedger(
            op="PUTAWAY", item_id=item.id, location_id=tmp_location,
            batch_id=batch.id, delta=-qty, ref=ref, ref_line=f"{ref_line}-out"
        ))
        session.add(StockLedger(
            op="PUTAWAY", item_id=item.id, location_id=to_location_id,
            batch_id=batch.id, delta=qty, ref=ref, ref_line=f"{ref_line}-in"
        ))
        await session.flush()

        return {"item_id": item.id, "batch_id": batch.id, "to_location_id": to_location_id, "moved_qty": qty}
