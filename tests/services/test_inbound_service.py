# tests/services/test_inbound_service.py
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 测试辅助：按项目实际路径导入
from tests.helpers.inventory import ensure_wh_loc_item, qty_by_code

from app.models.enums import MovementType
from app.services.stock_service import StockService

UTC = timezone.utc
pytestmark = pytest.mark.grp_core


@pytest.mark.asyncio
async def test_inbound_creates_batch_and_increases_stock(session: AsyncSession):
    """
    入库：批次化落账 + 返回 on_hand_after（通过读数校验）
    事务边界：造数→commit；读后→commit；业务→begin
    审计契约：入库必须提供 batch_code 且 production_date 或 expiry_date 至少其一

    Phase 4D：
    - 库存真相在 stocks_lot（lot-world），因此本用例改为：
      * 先创建 SUPPLIER lot（lot_code=code, expiry_date=exp）
      * 再用 StockService.adjust_lot 入库（写 stocks_lot + ledger(lot_id)）
      * 最终用 qty_by_code（lot-world 口径）断言 qty=6
    """
    wh, loc, item, code = 1, 1, 5001, "INB-DEMO-BATCH"

    # 造数：仓库/库位/商品（测试工具内部仍使用 loc 维度造底层数据）
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)
    await session.commit()  # 造数完成，关闭隐式事务

    # 入库 6（提供 batch_code + expiry_date 满足审计契约）
    ref = f"IN-{int(datetime.now(UTC).timestamp())}"
    exp = date.today() + timedelta(days=365)

    # Phase 4D/Phase M：lots 必须冻结 item_*_snapshot（NOT NULL）→ 必须从 items 真相源读取
    lot_row = (
        await session.execute(
            text(
                """
                INSERT INTO lots(
                    warehouse_id,
                    item_id,
                    lot_code_source,
                    lot_code,
                    source_receipt_id,
                    source_line_no,
                    production_date,
                    expiry_date,
                    expiry_source,
                    -- required snapshots (NOT NULL)
                    item_lot_source_policy_snapshot,
                    item_expiry_policy_snapshot,
                    item_derivation_allowed_snapshot,
                    item_uom_governance_enabled_snapshot,
                    -- optional snapshots (nullable)
                    item_has_shelf_life_snapshot,
                    item_shelf_life_value_snapshot,
                    item_shelf_life_unit_snapshot,
                    item_uom_snapshot,
                    item_case_ratio_snapshot,
                    item_case_uom_snapshot
                )
                SELECT
                    :w,
                    :i,
                    'SUPPLIER',
                    :code,
                    NULL,
                    NULL,
                    CURRENT_DATE,
                    :exp,
                    'EXPLICIT',
                    it.lot_source_policy,
                    it.expiry_policy,
                    it.derivation_allowed,
                    it.uom_governance_enabled,
                    it.has_shelf_life,
                    it.shelf_life_value,
                    it.shelf_life_unit,
                    it.uom,
                    it.case_ratio,
                    it.case_uom
                  FROM items it
                 WHERE it.id = :i
                ON CONFLICT (warehouse_id, item_id, lot_code_source, lot_code)
                WHERE lot_code_source = 'SUPPLIER'
                DO UPDATE SET expiry_date = EXCLUDED.expiry_date
                RETURNING id
                """
            ),
            {"w": int(wh), "i": int(item), "code": str(code), "exp": exp},
        )
    ).first()
    assert lot_row is not None, "failed to ensure lot"
    lot_id = int(lot_row[0])

    await session.commit()  # 防止外层隐式事务
    async with session.begin():
        _ = await StockService().adjust_lot(
            session=session,
            item_id=item,
            warehouse_id=wh,  # ✅ v2：以仓库为主维度
            lot_id=lot_id,
            delta=6,
            reason=MovementType.RECEIPT,
            ref=ref,
            occurred_at=datetime.now(UTC),
            batch_code=code,  # 展示码（lot_code）
            expiry_date=exp,  # 传有效期（或传 production_date 亦可）
        )

    # 校验：批次化落账，on_hand_after == 6
    await session.commit()
    assert await qty_by_code(session, item=item, loc=loc, code=code) == 6
