from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio

from app.main import app
from app.user.deps.auth import get_current_user


class _PlatformOrderIngestionPermissionUser:
    id: int = 999
    username: str = "test-user"
    is_active: bool = True
    permissions = [
        "page.platform_order_ingestion.read",
        "page.platform_order_ingestion.write",
    ]


@pytest.fixture(autouse=True)
def _override_platform_order_ingestion_user():
    app.dependency_overrides[get_current_user] = lambda: _PlatformOrderIngestionPermissionUser()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)



async def _seed_store(session, *, store_id: int, platform: str) -> None:
    await session.execute(
        text(
            """
            INSERT INTO stores (id, platform, store_code, store_name, active)
            VALUES (:id, :platform, :store_code, :store_name, TRUE)
            ON CONFLICT (id) DO UPDATE
              SET platform = EXCLUDED.platform,
                  store_code = EXCLUDED.store_code,
                  store_name = EXCLUDED.store_name,
                  active = TRUE
            """
        ),
        {
            "id": store_id,
            "platform": platform,
            "store_code": f"{platform}-MOCK-{store_id}",
            "store_name": f"{platform}-MOCK-{store_id}",
        },
    )
    await session.commit()


@pytest.mark.parametrize(
    ("platform", "store_id"),
    [
        ("pdd", 8701),
        ("jd", 8702),
        ("taobao", 8703),
    ],
)
async def test_unified_mock_authorize_marks_store_pull_ready(client, session, platform, store_id):
    await _seed_store(session, store_id=store_id, platform=platform.upper())

    resp = await client.post(
        f"/oms/platform-order-ingestion/mock/stores/{store_id}/authorize",
        json={
            "platform": platform,
            "granted_identity_display": f"{platform}-mock-display",
            "access_token": f"{platform}-access-token",
            "refresh_token": f"{platform}-refresh-token",
            "expires_in_days": 365,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["platform"] == platform
    assert data["store_id"] == store_id
    assert data["credential_status"] == "valid"
    assert data["connection_status"] == "connected"
    assert data["pull_ready"] is True
    assert data["status_reason"] == "mock_authorized"

    status_resp = await client.get(f"/oms/stores/{store_id}/platform-order-ingestion/status")
    assert status_resp.status_code == 200, status_resp.text
    status_data = status_resp.json()["data"]
    assert status_data["pull_ready"] is True
    assert status_data["credential"]["credential_status"] == "valid"
    assert status_data["connection"]["status_reason"] == "mock_authorized"


@pytest.mark.parametrize(
    ("platform", "store_id", "orders_table", "items_table", "order_fk"),
    [
        ("pdd", 8711, "pdd_orders", "pdd_order_items", "pdd_order_id"),
        ("jd", 8712, "jd_orders", "jd_order_items", "jd_order_id"),
        ("taobao", 8713, "taobao_orders", "taobao_order_items", "taobao_order_id"),
    ],
)
async def test_unified_mock_ingests_native_orders(client, session, platform, store_id, orders_table, items_table, order_fk):
    await _seed_store(session, store_id=store_id, platform=platform.upper())

    resp = await client.post(
        f"/oms/platform-order-ingestion/mock/stores/{store_id}/orders/ingest",
        json={
            "platform": platform,
            "scenario": "mixed",
            "count": 4,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["platform"] == platform
    assert data["store_id"] == store_id
    assert data["count"] == 4
    assert len(data["rows"]) == 4
    assert {row["scenario"] for row in data["rows"]} == {
        "normal",
        "address_missing",
        "item_abnormal",
        "combo",
    }
    assert all(row["native_order_id"] for row in data["rows"])

    native_order_ids = [int(row["native_order_id"]) for row in data["rows"]]
    native_order_ids_sql = ",".join(str(x) for x in native_order_ids)

    orders_count = (
        await session.execute(
            text(f"SELECT count(*) FROM {orders_table} WHERE id IN ({native_order_ids_sql})")
        )
    ).scalar_one()
    assert int(orders_count) == 4

    items_count = (
        await session.execute(
            text(
                f"""
                SELECT count(*)
                  FROM {items_table} i
                  JOIN {orders_table} o ON o.id = i.{order_fk}
                 WHERE o.id IN ({native_order_ids_sql})
                """
            )
        )
    ).scalar_one()
    assert int(items_count) == 8

    combo_items_count = (
        await session.execute(
            text(
                f"""
                SELECT count(*)
                  FROM {items_table} i
                  JOIN {orders_table} o ON o.id = i.{order_fk}
                 WHERE o.id IN ({native_order_ids_sql})
                   AND coalesce(jsonb_exists(i.raw_item_payload, 'combo_components'), false)
                """
            )
        )
    ).scalar_one()
    assert int(combo_items_count) >= 1


async def test_unified_mock_rejects_store_platform_mismatch(client, session):
    await _seed_store(session, store_id=8721, platform="PDD")

    resp = await client.post(
        "/oms/platform-order-ingestion/mock/stores/8721/authorize",
        json={
            "platform": "jd",
            "access_token": "bad-token",
        },
    )
    assert resp.status_code == 400, resp.text
    assert "store platform mismatch" in resp.text


async def test_unified_mock_clear_orders_can_clear_auth_state(client, session):
    store_id = 8731
    await _seed_store(session, store_id=store_id, platform="JD")

    authorize_resp = await client.post(
        f"/oms/platform-order-ingestion/mock/stores/{store_id}/authorize",
        json={
            "platform": "jd",
            "access_token": "jd-token",
            "refresh_token": "jd-refresh",
        },
    )
    assert authorize_resp.status_code == 200, authorize_resp.text

    ingest_resp = await client.post(
        f"/oms/platform-order-ingestion/mock/stores/{store_id}/orders/ingest",
        json={
            "platform": "jd",
            "scenario": "normal",
            "count": 2,
        },
    )
    assert ingest_resp.status_code == 200, ingest_resp.text

    clear_resp = await client.request(
        "DELETE",
        f"/oms/platform-order-ingestion/mock/stores/{store_id}/orders",
        json={
            "platform": "jd",
            "clear_connection": True,
            "clear_credential": True,
        },
    )
    assert clear_resp.status_code == 200, clear_resp.text

    data = clear_resp.json()["data"]
    assert data["deleted_orders"] == 2
    assert data["deleted_items"] == 4
    assert data["deleted_connection_rows"] == 1
    assert data["deleted_credential_rows"] == 1
