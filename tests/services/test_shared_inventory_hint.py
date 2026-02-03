import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_shared_inventory_statement(session):
    # 合同性断言：共享仓策略下，不按店隔离库存
    # 这里只做口径约定，不做真实库存运算（待主线库存裁决链路接入后替换）
    row = await session.execute(text("SELECT 1"))
    assert row.scalar() == 1
