# app/services/_deprecated/inventory_adjust_legacy.py

"""
====================================================================================
⚠️  LEGACY INVENTORY ENGINE — DO NOT USE IN NEW CODE  ⚠️
====================================================================================

说明：
- 本文件是 WMS-DU v1 / v2 过渡阶段的“旧库存引擎”。
- 其内部逻辑会：
    * 直接增减 stocks 表
    * 直接修改 batches
    * 手工写入（或未写入） ledger
- 与 v2 架构完全冲突（v2 统一通过 StockService.adjust 写 ledger）。

状态：
- 保留本文件仅为兼容历史测试、历史数据回放。
- 🚫 新业务代码禁止 import 本模块。
- ✔ 现役库存引擎为：StockService.adjust + SnapshotService。

未来动作（Phase：Cleanup Schema）：
- 检查旧数据
- 清理旧字段 & 旧行为
- 最终删除本模块
====================================================================================
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.batch import Batch
from app.models.enums import MovementType

# 旧库存模型
from app.models.stock import Stock
from app.services.ledger_writer import LedgerWriter


class LegacyInventoryAdjust:
    """
    旧时代库存调整工具（v1/v2 early phase）

    NOTE:
    - 仅供历史测试或遗留任务使用。
    - 若需库存调整，请使用 StockService.adjust。
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.ledger = LedgerWriter(session)

    # -------------------------------------------------------------------------
    async def inbound(
        self,
        *,
        item_id: int,
        warehouse_id: int,
        batch_code: str,
        qty: int,
        ref: str,
    ) -> dict:
        """
        旧 inbound（手工加库存 + 手工写 ledger）

        说明：
        - v2 架构请使用 InboundService + StockService.adjust。
        """
        if qty <= 0:
            raise ValueError("inbound qty must be > 0")

        now = datetime.now(timezone.utc)

        # 找 batch，不存在则创建
        row = await self.session.execute(
            sa.select(Batch).where(
                Batch.item_id == item_id,
                Batch.warehouse_id == warehouse_id,
                Batch.batch_code == batch_code,
            )
        )
        batch = row.scalar_one_or_none()
        if batch is None:
            batch = Batch(
                item_id=item_id,
                warehouse_id=warehouse_id,
                batch_code=batch_code,
                created_at=now,
            )
            self.session.add(batch)
            await self.session.flush()

        # stock += qty
        row = await self.session.execute(
            sa.select(Stock).where(
                Stock.item_id == item_id,
                Stock.warehouse_id == warehouse_id,
                Stock.batch_code == batch_code,
            )
        )
        stock = row.scalar_one_or_none()
        if stock is None:
            stock = Stock(
                item_id=item_id,
                warehouse_id=warehouse_id,
                batch_code=batch_code,
                qty=qty,
            )
            self.session.add(stock)
        else:
            stock.qty += qty

        # 手工写台账
        await self.ledger.write(
            item_id=item_id,
            warehouse_id=warehouse_id,
            batch_code=batch_code,
            delta=qty,
            reason=MovementType.INBOUND,
            ref=ref,
            occurred_at=now,
        )

        return {"ok": True, "qty": qty, "ref": ref}

    # -------------------------------------------------------------------------
    async def fefo_outbound(
        self,
        *,
        item_id: int,
        warehouse_id: int,
        qty: int,
        ref: str,
    ) -> dict:
        """
        旧 FEFO 出库逻辑（完全历史逻辑，用于早期阶段）

        - v2 架构请使用：
            PickService（扫码拣货）
            OutboundService.commit（订单出库）
        """

        if qty <= 0:
            raise ValueError("qty must be > 0")

        # FEFO 排序：按批次创建时间排序（旧 FEFO，不看 expiry_date）
        row = await self.session.execute(
            sa.select(Stock)
            .where(
                Stock.item_id == item_id,
                Stock.warehouse_id == warehouse_id,
                Stock.qty > 0,
            )
            .order_by(Stock.batch_code)
        )
        stocks = row.scalars().all()

        remain = qty
        now = datetime.now(timezone.utc)

        for stk in stocks:
            if remain <= 0:
                break
            take = min(stk.qty, remain)
            stk.qty -= take
            remain -= take

            await self.ledger.write(
                item_id=item_id,
                warehouse_id=warehouse_id,
                batch_code=stk.batch_code,
                delta=-take,
                reason=MovementType.OUTBOUND,
                ref=ref,
                occurred_at=now,
            )

        if remain > 0:
            raise ValueError(f"insufficient stock: remain={remain}")

        return {"ok": True, "qty": qty, "ref": ref}
