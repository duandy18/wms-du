# tests/services/test_ledger_writer.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inbound_service import InboundService

UTC = timezone.utc


@pytest.mark.asyncio
async def test_ledger_conservation(session: AsyncSession):
    wh, loc, item, code = 1, 1, 7631, "LGD-7631"
    await session.execute(
        text("INSERT INTO warehouses (id,name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING")
    )
    await session.execute(
        text(
            "INSERT INTO locations (id,warehouse_id,code,name) VALUES (1,1,'LOC-1','LOC-1') ON CONFLICT (id) DO NOTHING"
        )
    )
    await session.execute(
        text(
            "INSERT INTO items (id,sku,name) VALUES (:i,:s,:n) ON CONFLICT (id) DO UPDATE SET sku=EXCLUDED.sku, name=EXCLUDED.name"
        ),
        {"i": item, "s": f"SKU-{item}", "n": f"ITEM-{item}"},
    )
    await session.commit()

    ref = f"IN-LGD-{int(datetime.now(UTC).timestamp())}"
    svc = InboundService()
    async with session.begin():
        _ = await svc.receive(
            session=session,
            item_id=item,
            location_id=loc,
            qty=3,
            ref=ref,
            occurred_at=datetime.now(UTC),
            batch_code=code,
            expiry_date=(date.today() + timedelta(days=365)),
        )

    row = await session.execute(text("SELECT COUNT(*) FROM stock_ledger WHERE ref=:r"), {"r": ref})
    assert int(row.scalar_one()) >= 1
