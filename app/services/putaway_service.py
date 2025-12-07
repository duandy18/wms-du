# app/services/putaway_service.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService


class SameLocationError(ValueError):
    """业务异常：源库位与目标库位相同，不应执行搬运。"""

    def __init__(self, location_id: int):
        super().__init__(f"source and target locations are the same: {location_id}")
        self.location_id = location_id


class PutawayService:
    """
    上架 / 搬运服务（核心库存原子能力）

    重要说明：
    - 当前“无 location 概念”仅适用于 /scan 通路；
    - 系统内部（inventory_ops、RMA、quick tests 等）仍需要“从 A → B 搬运”能力；
    - 因此 PutawayService 本身必须保持可用，不应被 disable。

    使用场景：
      • RMA / 调拨 / 运维修正
      • 后台批量库存迁移
      • tests/quick/test_putaway_* 系列用于保证正确性

    执行逻辑（原子两腿）：
      1) 左腿：从 from_location 扣减 delta=-qty
      2) 右腿：向 to_location 增加 delta=+qty
      3) 幂等：基于 (ref, ref_line) 保证两腿不重复落账
    """

    def __init__(self, stock: Optional[StockService] = None) -> None:
        self.stock = stock or StockService()

    async def putaway(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        from_location_id: int,
        to_location_id: int,
        qty: int,
        ref: str,
        batch_code: str,
        production_date: Optional[datetime] = None,
        expiry_date: Optional[datetime] = None,
        left_ref_line: int = 1,
    ) -> Dict[str, Any]:
        if qty <= 0:
            raise ValueError("qty must be > 0")

        if from_location_id == to_location_id:
            raise SameLocationError(from_location_id)

        if not batch_code or not str(batch_code).strip():
            raise ValueError("putaway 操作必须提供 batch_code")

        if production_date is None and expiry_date is None:
            raise ValueError("putaway 操作必须提供 production_date 或 expiry_date 至少其一")

        # 左腿：源位扣减
        await self.stock.adjust(
            session=session,
            item_id=item_id,
            location_id=from_location_id,
            delta=-qty,
            reason=MovementType.PUTAWAY,
            ref=ref,
            ref_line=left_ref_line,
            batch_code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
        )

        # 右腿：目标位增加
        await self.stock.adjust(
            session=session,
            item_id=item_id,
            location_id=to_location_id,
            delta=qty,
            reason=MovementType.PUTAWAY,
            ref=ref,
            ref_line=left_ref_line + 1,
            batch_code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
        )

        return {
            "moved": qty,
            "from": from_location_id,
            "to": to_location_id,
        }
