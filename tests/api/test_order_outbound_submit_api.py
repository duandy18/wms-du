from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.stock.services.lots import ensure_internal_lot_singleton, ensure_lot_full
from app.wms.stock.services.stock_adjust import adjust_lot_impl
from tests.services._helpers import ensure_store

pytestmark = pytest.mark.asyncio
UTC = timezone.utc


async def _login_admin_headers(client: AsyncClient) -> dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _pick_any_item_id(session: AsyncSession) -> tuple[int, bool]:
    """
    返回：
    - item_id
    - requires_expiry
    """
    row = (
        await session.execute(
            text(
                """
                SELECT id, expiry_policy::text
                FROM items
                ORDER BY
                  CASE WHEN expiry_policy::text = 'NONE' THEN 0 ELSE 1 END,
                  id ASC
                LIMIT 1
                """
            )
        )
    ).first()
    assert row is not None, "expected at least one item in baseline"
    item_id = int(row[0])
    requires_expiry = str(row[1]).strip().upper() == "REQUIRED"
    return item_id, requires_expiry


async def _seed_order_and_stock(session: AsyncSession) -> tuple[int, int, int, int, int]:
    platform = "PDD"
    shop_id = "1"
    warehouse_id = 1
    uniq = uuid4().hex[:10]
    ext_order_no = f"OUT-API-{uniq}"

    item_id, requires_expiry = await _pick_any_item_id(session)

    store_id = await ensure_store(
        session,
        platform=platform,
        shop_id=shop_id,
        name=f"UT-{platform}-{shop_id}",
    )

    await session.execute(
        text(
            """
            INSERT INTO warehouses (id, name)
            VALUES (:w, 'WH-UT')
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"w": int(warehouse_id)},
    )

    row = await session.execute(
        text(
            """
            INSERT INTO orders (
                platform,
                shop_id,
                store_id,
                ext_order_no,
                status,
                created_at,
                updated_at
            )
            VALUES (
                :platform,
                :shop_id,
                :store_id,
                :ext_order_no,
                'CREATED',
                now(),
                now()
            )
            ON CONFLICT ON CONSTRAINT uq_orders_platform_shop_ext DO UPDATE
              SET store_id = EXCLUDED.store_id,
                  updated_at = now()
            RETURNING id
            """
        ),
        {
            "platform": platform,
            "shop_id": shop_id,
            "store_id": int(store_id),
            "ext_order_no": ext_order_no,
        },
    )
    order_id = int(row.scalar_one())

    row2 = await session.execute(
        text(
            """
            INSERT INTO order_lines (
                order_id,
                item_id,
                req_qty
            )
            VALUES (
                :order_id,
                :item_id,
                :req_qty
            )
            RETURNING id
            """
        ),
        {
            "order_id": int(order_id),
            "item_id": int(item_id),
            "req_qty": 2,
        },
    )
    order_line_id = int(row2.scalar_one())

    batch_code: str | None = None
    production_date: date | None = None
    expiry_date: date | None = None

    if requires_expiry:
        batch_code = f"UT-OUT-{warehouse_id}-{item_id}-{uniq}"
        production_date = date(2030, 1, 1)
        expiry_date = production_date + timedelta(days=365)
        lot_id = await ensure_lot_full(
            session,
            item_id=int(item_id),
            warehouse_id=int(warehouse_id),
            lot_code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
        )
    else:
        lot_id = await ensure_internal_lot_singleton(
            session,
            item_id=int(item_id),
            warehouse_id=int(warehouse_id),
            source_receipt_id=None,
            source_line_no=None,
        )

    await adjust_lot_impl(
        session=session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_id=int(lot_id),
        delta=10,
        reason="UT_ORDER_OUTBOUND_API_SEED",
        ref=f"ut:order_outbound_api_seed:{uniq}",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        meta=None,
        batch_code=batch_code,
        production_date=production_date,
        expiry_date=expiry_date,
        trace_id=None,
        utc_now=lambda: datetime.now(UTC),
        shadow_write_stocks=False,
    )

    await session.commit()
    return order_id, order_line_id, warehouse_id, int(lot_id), int(item_id)


async def test_order_outbound_submit_writes_event_and_ledger(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)

    order_id, order_line_id, warehouse_id, lot_id, item_id = await _seed_order_and_stock(session)

    resp = await client.post(
        f"/wms/outbound/orders/{order_id}/submit",
        headers=headers,
        json={
            "warehouse_id": warehouse_id,
            "remark": "UT order outbound submit",
            "lines": [
                {
                    "order_line_id": order_line_id,
                    "item_id": item_id,
                    "qty_outbound": 2,
                    "lot_id": lot_id,
                    "lot_code": None,
                    "remark": "line remark",
                }
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["status"] == "OK"
    assert data["event_type"] == "OUTBOUND"
    assert data["source_type"] == "ORDER"
    assert data["warehouse_id"] == warehouse_id
    assert data["lines_count"] == 1
    event_id = int(data["event_id"])

    ev = (
        await session.execute(
            text(
                """
                SELECT event_type, source_type, warehouse_id
                FROM wms_events
                WHERE id = :id
                LIMIT 1
                """
            ),
            {"id": event_id},
        )
    ).first()
    assert ev is not None
    assert ev[0] == "OUTBOUND"
    assert ev[1] == "ORDER"
    assert int(ev[2]) == warehouse_id

    line = (
        await session.execute(
            text(
                """
                SELECT order_line_id, item_id, qty_outbound, lot_id
                FROM outbound_event_lines
                WHERE event_id = :event_id
                ORDER BY ref_line ASC
                LIMIT 1
                """
            ),
            {"event_id": event_id},
        )
    ).first()
    assert line is not None
    assert int(line[0]) == order_line_id
    assert int(line[1]) == item_id
    assert int(line[2]) == 2
    assert int(line[3]) == lot_id

    led = (
        await session.execute(
            text(
                """
                SELECT reason, delta, warehouse_id, item_id, lot_id, event_id
                FROM stock_ledger
                WHERE event_id = :event_id
                ORDER BY id ASC
                LIMIT 1
                """
            ),
            {"event_id": event_id},
        )
    ).first()
    assert led is not None
    assert led[0] == "OUTBOUND_SHIP"
    assert int(led[1]) == -2
    assert int(led[2]) == warehouse_id
    assert int(led[3]) == item_id
    assert int(led[4]) == lot_id
    assert int(led[5]) == event_id

    qty_now = (
        await session.execute(
            text(
                """
                SELECT qty
                FROM stocks_lot
                WHERE warehouse_id = :w
                  AND item_id = :i
                  AND lot_id = :l
                LIMIT 1
                """
            ),
            {"w": warehouse_id, "i": item_id, "l": lot_id},
        )
    ).scalar_one()
    assert int(qty_now) == 8

    opts = await client.get(
        "/oms/orders/outbound-options",
        headers=headers,
        params={"q": str(order_id)},
    )
    assert opts.status_code == 200, opts.text
    opts_data = opts.json()
    assert opts_data["items"] == []


async def test_order_outbound_submit_rejects_duplicate_submit_with_409(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)

    order_id, order_line_id, warehouse_id, lot_id, item_id = await _seed_order_and_stock(session)

    payload = {
        "warehouse_id": warehouse_id,
        "remark": "UT order outbound duplicate submit",
        "lines": [
            {
                "order_line_id": order_line_id,
                "item_id": item_id,
                "qty_outbound": 2,
                "lot_id": lot_id,
                "lot_code": None,
                "remark": "line remark",
            }
        ],
    }

    first = await client.post(
        f"/wms/outbound/orders/{order_id}/submit",
        headers=headers,
        json=payload,
    )
    assert first.status_code == 200, first.text

    second = await client.post(
        f"/wms/outbound/orders/{order_id}/submit",
        headers=headers,
        json=payload,
    )
    assert second.status_code == 409, second.text
    body = second.json()
    assert "order_line_already_completed" in str(body)
