# tests/api/test_outbound_reason_contract.py
import asyncio

import pytest
from sqlalchemy import text

# 允许独立运行：只做“口径护栏”校验，不强求一定要有数据
pytestmark = pytest.mark.asyncio

ALLOWED = {"PICK", "PUTAWAY", "INBOUND", "COUNT", "ADJUST"}


async def _fetch_reasons(session):
    # 兼容空库/空表环境：若表不存在直接返回空集合
    try:
        rec = await session.execute(text("SELECT reason FROM stock_ledger"))
        return {row[0] for row in rec.fetchall() if row and row[0] is not None}
    except Exception:
        return set()


async def _table_exists(session, name: str) -> bool:
    try:
        sql = text("SELECT to_regclass(:n)")
        rec = await session.execute(sql, {"n": name})
        return rec.scalar() is not None
    except Exception:
        return False


@pytest.mark.asyncio
async def test_ledger_reason_is_atomic_only(session):
    """
    口径护栏：ledger.reason 只允许原子动作，不允许 OUTBOUND/SHIPMENT 等流程词汇。
    这条测试不依赖其它用例的执行顺序，读当前库即判。
    """
    # 没有表直接通过（由其他迁移/合约测试保障表存在性）
    if not await _table_exists(session, "stock_ledger"):
        pytest.skip("stock_ledger does not exist in this environment")

    reasons = await _fetch_reasons(session)
    # 空数据也算通过（不制造干扰）；一旦有数据，必须全部在允许集合内
    illegal = {r for r in reasons if r is not None and r not in ALLOWED}
    assert (
        not illegal
    ), f"Found non-atomic ledger.reason values: {sorted(illegal)}; allowed={sorted(ALLOWED)}"


@pytest.mark.asyncio
async def test_no_outbound_wording_in_reason(session):
    """
    口径护栏：严禁出现 OUTBOUND/SHIPMENT 这类“流程词”写入 ledger.reason。
    """
    if not await _table_exists(session, "stock_ledger"):
        pytest.skip("stock_ledger does not exist in this environment")

    rec = await session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM stock_ledger
            WHERE reason ILIKE 'OUTBOUND%%' OR reason ILIKE 'SHIPMENT%%'
        """
        )
    )
    cnt = rec.scalar() or 0
    assert (
        cnt == 0
    ), f"ledger.reason must be atomic; found {cnt} rows with OUTBOUND/SHIPMENT-like reasons"
