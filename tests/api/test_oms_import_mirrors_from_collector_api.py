from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.oms.order_facts.services import collector_import_service
from app.oms.order_facts.services.collector_export_client import (
    CollectorExportNotFound,
    CollectorExportUpstreamError,
)


pytestmark = pytest.mark.asyncio


async def _clear_mirrors(session) -> None:
    await session.execute(text("DELETE FROM oms_pdd_order_mirror_lines"))
    await session.execute(text("DELETE FROM oms_taobao_order_mirror_lines"))
    await session.execute(text("DELETE FROM oms_jd_order_mirror_lines"))
    await session.execute(text("DELETE FROM oms_pdd_order_mirrors"))
    await session.execute(text("DELETE FROM oms_taobao_order_mirrors"))
    await session.execute(text("DELETE FROM oms_jd_order_mirrors"))
    await session.commit()


async def _ensure_store(session, *, platform: str, store_code: str) -> int:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO stores (
                  platform,
                  store_code,
                  store_name,
                  active
                )
                VALUES (
                  :platform,
                  :store_code,
                  :store_name,
                  true
                )
                ON CONFLICT (platform, store_code) DO UPDATE
                SET
                  store_name = EXCLUDED.store_name,
                  active = EXCLUDED.active
                RETURNING id
                """
            ),
            {
                "platform": platform,
                "store_code": store_code,
                "store_name": f"{platform}-{store_code}",
            },
        )
    ).mappings().one()
    await session.commit()
    return int(row["id"])


def _collector_payload(
    *,
    platform: str,
    collector_order_id: int,
    collector_store_code: str,
    platform_order_no: str,
    merchant_sku: str,
) -> dict[str, Any]:
    return {
        "collector_order_id": collector_order_id,
        "collector_store_id": collector_order_id + 1000,
        "collector_store_code": collector_store_code,
        "collector_store_name": f"{platform}-collector-store",
        "platform": platform,
        "platform_order_no": platform_order_no,
        "platform_status": "WAIT_SELLER_SEND_GOODS",
        "source_updated_at": "2026-04-28T08:00:00+00:00",
        "pulled_at": "2026-04-28T08:01:00+00:00",
        "last_synced_at": "2026-04-28T08:02:00+00:00",
        "receiver": {"name": "张三", "phone": "13800138000"},
        "amounts": {"pay_amount": "86.00"},
        "platform_fields": {"source": "collector-export"},
        "raw_refs": {"detail": {"ok": True}},
        "lines": [
            {
                "collector_line_id": collector_order_id + 2000,
                "collector_order_id": collector_order_id,
                "platform_order_no": platform_order_no,
                "merchant_sku": merchant_sku,
                "platform_item_id": f"{platform}-ITEM-1",
                "platform_sku_id": f"{platform}-SKU-1",
                "title": f"{platform} 测试商品",
                "quantity": 2,
                "unit_price": "43.00",
                "line_amount": "86.00",
                "platform_fields": {"line_source": "collector-export"},
                "raw_item_payload": {"merchant_sku": merchant_sku},
            }
        ],
    }


async def test_pdd_import_from_collector_writes_platform_order_mirror(
    client,
    session,
    monkeypatch,
) -> None:
    await _clear_mirrors(session)

    suffix = uuid4().hex[:8]
    store_code = f"PDD-COLLECTOR-{suffix}"
    wms_store_id = await _ensure_store(session, platform="pdd", store_code=store_code)

    async def fake_fetch_collector_export_order(*, platform: str, collector_order_id: int) -> dict[str, Any]:
        assert platform == "pdd"
        assert collector_order_id == 990001
        return _collector_payload(
            platform="pdd",
            collector_order_id=collector_order_id,
            collector_store_code=store_code,
            platform_order_no=f"PDD-COLLECTOR-ORDER-{suffix}",
            merchant_sku="PDD-FSKU-COLLECTOR",
        )

    monkeypatch.setattr(
        collector_import_service,
        "fetch_collector_export_order",
        fake_fetch_collector_export_order,
    )

    resp = await client.post(
        "/oms/pdd/platform-order-mirrors/import-from-collector",
        json={"collector_order_id": 990001},
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["ok"] is True
    assert body["imported"] is True
    assert body["platform"] == "pdd"
    mirror_id = int(body["mirror_id"])

    detail = await client.get(f"/oms/pdd/platform-order-mirrors/{mirror_id}")
    assert detail.status_code == 200, detail.text

    data = detail.json()["data"]
    assert data["collector_order_id"] == 990001
    assert data["wms_store_id"] == wms_store_id
    assert data["receiver"]["name"] == "张三"
    assert data["lines"][0]["merchant_sku"] == "PDD-FSKU-COLLECTOR"


async def test_taobao_import_from_collector_uses_platform_separated_endpoint(
    client,
    session,
    monkeypatch,
) -> None:
    await _clear_mirrors(session)

    suffix = uuid4().hex[:8]
    store_code = f"TAOBAO-COLLECTOR-{suffix}"
    await _ensure_store(session, platform="taobao", store_code=store_code)

    async def fake_fetch_collector_export_order(*, platform: str, collector_order_id: int) -> dict[str, Any]:
        assert platform == "taobao"
        return _collector_payload(
            platform="taobao",
            collector_order_id=collector_order_id,
            collector_store_code=store_code,
            platform_order_no=f"TB-COLLECTOR-ORDER-{suffix}",
            merchant_sku="TB-FSKU-COLLECTOR",
        )

    monkeypatch.setattr(
        collector_import_service,
        "fetch_collector_export_order",
        fake_fetch_collector_export_order,
    )

    resp = await client.post(
        "/oms/taobao/platform-order-mirrors/import-from-collector",
        json={"collector_order_id": 990002},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["platform"] == "taobao"


async def test_import_from_collector_maps_not_found_to_404(
    client,
    monkeypatch,
) -> None:
    async def fake_fetch_collector_export_order(*, platform: str, collector_order_id: int) -> dict[str, Any]:
        raise CollectorExportNotFound("collector export order not found")

    monkeypatch.setattr(
        collector_import_service,
        "fetch_collector_export_order",
        fake_fetch_collector_export_order,
    )

    resp = await client.post(
        "/oms/jd/platform-order-mirrors/import-from-collector",
        json={"collector_order_id": 999999},
    )
    assert resp.status_code == 404, resp.text
    assert "collector export order not found" in resp.text


async def test_import_from_collector_maps_upstream_error_to_502(
    client,
    monkeypatch,
) -> None:
    async def fake_fetch_collector_export_order(*, platform: str, collector_order_id: int) -> dict[str, Any]:
        raise CollectorExportUpstreamError("collector unavailable")

    monkeypatch.setattr(
        collector_import_service,
        "fetch_collector_export_order",
        fake_fetch_collector_export_order,
    )

    resp = await client.post(
        "/oms/pdd/platform-order-mirrors/import-from-collector",
        json={"collector_order_id": 990003},
    )
    assert resp.status_code == 502, resp.text
    assert "collector unavailable" in resp.text
