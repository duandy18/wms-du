import pytest

pytest.skip(
    "legacy snapshot run tests (SnapshotService.run 已下线，v2 仅保留实时视图)",
    allow_module_level=True,
)

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.outbound_service import ship_commit
from app.services.scan_handlers.pick_handler import handle_pick
from app.services.scan_handlers.receive_handler import handle_receive
from app.services.snapshot_service import SnapshotService


async def _qty(session: AsyncSession, item_id: int, wh: int, code: str) -> int:
    r = await session.execute(
        text(
            "SELECT COALESCE(qty_on_hand, qty) FROM stocks WHERE item_id=:i AND warehouse_id=:w AND batch_code=:c"
        ),
        {"i": item_id, "w": wh, "c": code},
    )
    return int(r.scalar_one_or_none() or 0)


@pytest.mark.asyncio
async def test_smoke_end2end(session: AsyncSession):
    # 入库 +1
    await handle_receive(
        session,
        item_id=1,
        warehouse_id=1,
        qty=1,
        ref="SMK-1",
        batch_code="NEAR",
        production_date=date.today(),
        expiry_date=None,
    )
    # 拣货 -1
    await handle_pick(session, item_id=1, warehouse_id=1, qty=1, ref="SMK-2", batch_code="NEAR")

    # OMS 出库（应当幂等）——使用与前面相同的 item/warehouse/batch
    await ship_commit(
        session,
        order_id="SMK-3",
        lines=[
            {
                "item_id": 1,
                "warehouse_id": 1,
                "batch_code": "NEAR",
                "qty": 1,
            }
        ],
        warehouse_code="WH-1",
    )
    await ship_commit(
        session,
        order_id="SMK-3",
        lines=[
            {
                "item_id": 1,
                "warehouse_id": 1,
                "batch_code": "NEAR",
                "qty": 1,
            }
        ],
        warehouse_code="WH-1",
    )

    # 快照
    res = await SnapshotService.run(session)
    assert res["rows"] >= 1
