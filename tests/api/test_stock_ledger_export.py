# tests/api/test_stock_ledger_export.py
import csv
import io
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_ledger_export_csv(session, stock_service, item_loc_fixture):
    item_id, location_id = item_loc_fixture

    # 造数：+10 / -4
    await stock_service.adjust(
        session=session,
        item_id=item_id,
        location_id=location_id,
        delta=10,
        reason="INBOUND",
        ref="PO-EXP-1",
        batch_code="B20251006-E",
        production_date=date(2025, 9, 1),
        expiry_date=date(2026, 9, 1),
    )
    await stock_service.adjust(
        session=session,
        item_id=item_id,
        location_id=location_id,
        delta=-4,
        reason="OUTBOUND",
        ref="SO-EXP-1",
        batch_code="B20251006-E",
    )

    # 调用导出接口（按批次过滤）
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/stock/ledger/export", json={"batch_code": "B20251006-E", "limit": 1000}
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        assert "attachment; filename=" in resp.headers.get("content-disposition", "")

        # 解析 CSV
        rows = list(csv.reader(io.StringIO(resp.text)))
        assert rows, "empty csv"
        header = rows[0]
        assert header == [
            "id",
            "stock_id",
            "batch_id",
            "delta",
            "reason",
            "ref",
            "created_at",
            "after_qty",
        ]

        data = rows[1:]
        deltas = [int(r[3]) for r in data]
        reasons = [r[4] for r in data]
        refs = [r[5] for r in data]

        # 内容应包含 +10 和 -4 两条，且 reason/ref 匹配
        assert 10 in deltas and -4 in deltas
        assert "INBOUND" in reasons and "OUTBOUND" in reasons
        assert "PO-EXP-1" in refs and "SO-EXP-1" in refs
