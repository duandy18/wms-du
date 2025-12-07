# tests/services/test_putaway_service.py
from datetime import date, timedelta
from typing import List, Tuple

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 测试辅助：按项目实际路径导入
from tests.helpers.inventory import ensure_wh_loc_item

from app.models.enums import MovementType
from app.services.putaway_service import PutawayService
from app.services.stock_service import StockService  # 直接入库以满足审计契约（带日期与批次码）

pytestmark = pytest.mark.grp_core


async def _get_slot_qty(session: AsyncSession, *, wh: int, item: int, code: str) -> int:
    row = await session.execute(
        text(
            """
            SELECT qty
              FROM stocks
             WHERE warehouse_id = :wh
               AND item_id      = :item
               AND batch_code   = :code
             LIMIT 1
            """
        ),
        {"wh": wh, "item": item, "code": code},
    )
    val = row.scalar()
    return int(val or 0)


async def _list_putaway_ledger(
    session: AsyncSession,
    *,
    ref: str,
) -> List[Tuple[int, int]]:
    """
    返回该 ref 下所有 PUTAWAY 台账的 (delta, ref_line)，按 ref_line 排序。
    """
    rows = await session.execute(
        text(
            """
            SELECT delta, ref_line
              FROM stock_ledger
             WHERE reason = :reason
               AND ref    = :ref
             ORDER BY ref_line ASC, id ASC
            """
        ),
        {"reason": MovementType.PUTAWAY.value, "ref": ref},
    )
    return [(int(r[0]), int(r[1])) for r in rows.fetchall()]


@pytest.mark.asyncio
async def test_putaway_binds_location_and_is_idempotent(session: AsyncSession):
    """
    Putaway 两腿：SRC→DST 搬 3；幂等：同 ref/left_ref_line 再次提交不变。

    审计契约对齐：
      - 出库（左腿，delta<0）：必须提供 batch_code
      - 入库（右腿，delta>0）：必须提供 batch_code 且提供 production_date 或 expiry_date（至少其一）

    v2 世界观下：
      - StockService 只在 (warehouse_id, item_id, batch_code) 槽位上调整库存 + 写台账；
      - location_id 仅用于“作业含义”和路径规划，不再直接体现在 stocks 表结构里。
      - 本测试验证：
          * 仓维度库存不丢失；
          * PUTAWAY 产生一对 (-qty, +qty) 台账；
          * 重复调用时台账不重复写入（幂等）。
    """
    wh, src, dst, item, code = 1, 900, 1, 6006, "PA-DEMO-6006"
    putaway_ref = "PA-MV-1"

    # 1) 基线实体：仓 + 两个库位 + 商品
    await ensure_wh_loc_item(session, wh=wh, loc=src, item=item, code="SRC-900", name="SRC-900")
    await ensure_wh_loc_item(session, wh=wh, loc=dst, item=item, code="DST-001", name="DST-001")
    await session.commit()

    # 2) 仓维度入库 3（RECEIPT），显式带批次 + 日期，满足审计契约
    prod = date.today()
    exp = date.today() + timedelta(days=365)

    await StockService().adjust(
        session=session,
        item_id=item,
        warehouse_id=wh,  # v2：以仓维度为主
        delta=3,
        reason=MovementType.RECEIPT,
        ref="IN-PA",
        batch_code=code,
        production_date=prod,
        expiry_date=exp,
    )
    await session.commit()

    qty_before = await _get_slot_qty(session, wh=wh, item=item, code=code)
    assert qty_before == 3, "入库后仓维度库存应为 3"

    # 3) Putaway：SRC→DST 搬 3
    res1 = await PutawayService().putaway(
        session=session,
        item_id=item,
        from_location_id=src,
        to_location_id=dst,
        qty=3,
        ref=putaway_ref,
        batch_code=code,
        production_date=prod,
        expiry_date=exp,
        left_ref_line=1,  # 左腿=1，右腿=2
    )
    await session.commit()

    assert res1["status"] == "OK"
    assert res1["moved"] == 3

    # 仓维度库存总量不变（只是“移库”，不应额外凭空增减）
    qty_after_first = await _get_slot_qty(session, wh=wh, item=item, code=code)
    assert qty_after_first == 3

    # PUTAWAY 台账应当正好两条：-3（左腿） / +3（右腿），ref_line 分别为 1 / 2
    legs = await _list_putaway_ledger(session, ref=putaway_ref)
    assert legs == [(-3, 1), (3, 2)]

    # 4) 幂等：同 ref + left_ref_line 再调用一次，不应产生新的 PUTAWAY 台账
    res2 = await PutawayService().putaway(
        session=session,
        item_id=item,
        from_location_id=src,
        to_location_id=dst,
        qty=3,
        ref=putaway_ref,
        batch_code=code,
        production_date=prod,
        expiry_date=exp,
        left_ref_line=1,
    )
    await session.commit()

    # 结果仍应标记 moved=3（业务视角），但 DB 层不再新增 PUTAWAY 台账（依赖 ledger 唯一约束 + adjust 幂等）
    assert res2["status"] == "OK"
    assert res2["moved"] == 3

    qty_after_second = await _get_slot_qty(session, wh=wh, item=item, code=code)
    assert qty_after_second == 3, "幂等调用不应改变仓维度库存"

    legs_after = await _list_putaway_ledger(session, ref=putaway_ref)
    assert legs_after == legs, "第二次调用不应产生额外 PUTAWAY 台账行"
