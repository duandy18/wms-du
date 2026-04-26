from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.services._helpers import ensure_store

pytestmark = pytest.mark.asyncio


async def _login_admin_headers(client: AsyncClient) -> dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _pick_any_item_id(session: AsyncSession) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT id
                FROM items
                ORDER BY id ASC
                LIMIT 1
                """
            )
        )
    ).first()
    assert row is not None, "expected at least one item in baseline"
    return int(row[0])


async def _seed_order(session: AsyncSession) -> tuple[int, int, int]:
    platform = "PDD"
    store_code = "1"
    uniq = uuid4().hex[:10]
    ext_order_no = f"OUT-VIEW-{uniq}"

    item_id = await _pick_any_item_id(session)

    store_id = await ensure_store(
        session,
        platform=platform,
        store_code=store_code,
        name=f"UT-{platform}-{store_code}",
    )

    row = await session.execute(
        text(
            """
            INSERT INTO orders (
                platform,
                store_code,
                store_id,
                ext_order_no,
                status,
                buyer_name,
                buyer_phone,
                order_amount,
                pay_amount,
                created_at,
                updated_at
            )
            VALUES (
                :platform,
                :store_code,
                :store_id,
                :ext_order_no,
                'CREATED',
                '张三',
                '13800000000',
                100.00,
                95.00,
                now(),
                now()
            )
            ON CONFLICT ON CONSTRAINT uq_orders_platform_store_ext DO UPDATE
              SET store_id = EXCLUDED.store_id,
                  updated_at = now()
            RETURNING id
            """
        ),
        {
            "platform": platform,
            "store_code": store_code,
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

    await session.commit()
    return order_id, order_line_id, item_id


async def test_order_outbound_view_reads_orders_and_order_lines_only(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    order_id, order_line_id, item_id = await _seed_order(session)

    resp = await client.get(f"/oms/orders/{order_id}/outbound-view", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["ok"] is True
    assert data["order"]["id"] == order_id
    assert data["order"]["platform"] == "PDD"
    assert data["order"]["store_code"] == "1"
    assert data["order"]["status"] == "CREATED"

    assert isinstance(data["lines"], list)
    assert len(data["lines"]) == 1
    ln = data["lines"][0]
    assert ln["id"] == order_line_id
    assert ln["order_id"] == order_id
    assert ln["item_id"] == item_id
    assert ln["req_qty"] == 2
