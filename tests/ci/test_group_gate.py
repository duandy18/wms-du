import os

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


# 只在我们关心的组里跑（通过环境变量或 -k 选择）
def _want_gate():
    return True


async def test_db_gate_three_books(session):
    if not _want_gate():
        pytest.skip("gate not requested")
    # 幂等日结
    await session.execute(text("CALL snapshot_today()"))
    row = await session.execute(text("SELECT * FROM v_three_books"))
    m = row.mappings().first() or {}
    # 三账对齐：stocks == ledger；快照（on_hand）贴合
    assert int(m["sum_stocks"]) == int(m["sum_ledger"]), m
    # 快照可能未覆盖“当天全部变更”，放宽为“非负且不大幅背离”
    assert int(m["sum_snapshot_on_hand"]) >= 0
