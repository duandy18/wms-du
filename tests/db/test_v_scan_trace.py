import pytest
from sqlalchemy import text

pytestmark = pytest.mark.grp_scan


@pytest.mark.asyncio
async def test_v_scan_trace_view_exists(session):
    sql = text(
        """
        SELECT table_name
        FROM information_schema.views
        WHERE table_schema='public' AND table_name='v_scan_trace'
    """
    )
    rows = (await session.execute(sql)).fetchall()
    assert rows, "v_scan_trace view should exist"


@pytest.mark.asyncio
async def test_v_scan_trace_columns(session):
    sql = text(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name='v_scan_trace'
    """
    )
    cols = {r[0] for r in (await session.execute(sql)).fetchall()}
    expect = {
        "scan_ref",
        "event_id",
        "occurred_at",
        "source",
        "device_id",
        "operator",
        "mode",
        "barcode",
        "input_json",
        "output_json",
        "ledger_id",
        "ref_line",
        "reason",
        "delta",
        "after_qty",
        "item_id",
        "warehouse_id",
        "location_id",
        "batch_id",
        "batch_code",
        "ledger_occurred_at",
    }
    missing = expect - cols
    assert not missing, f"missing columns: {missing}"


@pytest.mark.asyncio
async def test_v_scan_trace_recent_has_rows_or_zero(session):
    sql = text(
        """
        SELECT COUNT(*) FROM v_scan_trace
        WHERE occurred_at >= now() - interval '1 day'
    """
    )
    n = (await session.execute(sql)).scalar_one()
    assert n >= 0
