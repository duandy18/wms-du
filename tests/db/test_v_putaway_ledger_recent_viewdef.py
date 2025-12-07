import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_viewdef_uses_v_stocks_enriched(session: AsyncSession):
    row = await session.execute(
        text(
            """
        SELECT pg_get_viewdef('public.v_putaway_ledger_recent'::regclass, true)
    """
        )
    )
    ddl = row.scalar_one()
    # 视图应当基于 v_stocks_enriched，而不是直接引用 stocks
    assert "v_stocks_enriched" in ddl
    assert "JOIN v_stocks_enriched" in ddl or "from v_stocks_enriched" in ddl.lower()
