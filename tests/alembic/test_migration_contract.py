import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_alembic_single_head_and_stocks_batch_code_not_null(session: AsyncSession):
    """
    Alembic 迁移合约测试（收敛到当前真实设计）

    目标：
    1. 确保 Alembic 是单头（alembic_version 只有一条）
    2. 确保 stocks.batch_code 字段为当前世界的批次维度，
       且迁移后保证所有行 batch_code 均为 NOT NULL
    """

    # 1) alembic_version 表应存在且仅一行（单 head）
    result = await session.execute(text("SELECT COUNT(*) FROM alembic_version"))
    assert int(result.scalar_one()) == 1

    # 2) 验证 stocks.batch_code 非空（当前批次模型）
    result2 = await session.execute(text("SELECT COUNT(*) FROM stocks WHERE batch_code IS NULL"))
    assert int(result2.scalar_one()) == 0
