from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text


pytestmark = pytest.mark.asyncio


async def _clear_mirrors(session) -> None:
    await session.execute(text("DELETE FROM oms_pdd_order_mirror_lines"))
    await session.execute(text("DELETE FROM oms_taobao_order_mirror_lines"))
    await session.execute(text("DELETE FROM oms_jd_order_mirror_lines"))
    await session.execute(text("DELETE FROM oms_pdd_order_mirrors"))
    await session.execute(text("DELETE FROM oms_taobao_order_mirrors"))
    await session.execute(text("DELETE FROM oms_jd_order_mirrors"))
    await session.commit()


async def _ensure_store(session, *, platform: str, store_code: str, store_name: str) -> int:
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
                "store_name": store_name,
            },
        )
    ).mappings().one()
    await session.commit()
    return int(row["id"])


def _payload(
    *,
    platform: str,
    collector_order_id: int,
    collector_line_id: int,
    collector_store_code: str,
    platform_order_no: str,
    merchant_sku: str,
) -> dict:
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
        "receiver": {
            "name": "张三",
            "phone": "13800138000",
            "province": "浙江省",
            "city": "杭州市",
            "address": "文三路 1 号",
        },
        "amounts": {
            "pay_amount": "86.00",
        },
        "platform_fields": {
            "source": "collector-export-contract",
        },
        "raw_refs": {
            "summary": {"platform_order_no": platform_order_no},
        },
        "lines": [
            {
                "collector_line_id": collector_line_id,
                "collector_order_id": collector_order_id,
                "platform_order_no": platform_order_no,
                "merchant_sku": merchant_sku,
                "platform_item_id": f"{platform}-ITEM-1",
                "platform_sku_id": f"{platform}-SKU-1",
                "title": f"{platform} 测试商品",
                "quantity": "2",
                "unit_price": "43.00",
                "line_amount": "86.00",
                "platform_fields": {
                    "line_source": "collector-export-contract",
                },
                "raw_item_payload": {
                    "merchant_sku": merchant_sku,
                },
            }
        ],
    }


async def test_import_pdd_platform_order_mirror_is_idempotent(client, session) -> None:
    await _clear_mirrors(session)

    suffix = uuid4().hex[:8]
    store_code = f"PDD-MIRROR-{suffix}"
    wms_store_id = await _ensure_store(
        session,
        platform="pdd",
        store_code=store_code,
        store_name="PDD 镜像测试店铺",
    )

    payload = _payload(
        platform="pdd",
        collector_order_id=910001,
        collector_line_id=920001,
        collector_store_code=store_code,
        platform_order_no=f"PDD-MIRROR-ORDER-{suffix}",
        merchant_sku="PDD-FSKU-1",
    )

    first = await client.post("/oms/pdd/platform-order-mirrors/import", json=payload)
    assert first.status_code == 200, first.text

    body = first.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["platform"] == "pdd"
    assert data["collector_order_id"] == 910001
    assert data["wms_store_id"] == wms_store_id
    assert data["platform_order_no"] == payload["platform_order_no"]
    assert data["receiver"]["name"] == "张三"
    assert data["amounts"]["pay_amount"] == "86.00"
    assert len(data["lines"]) == 1
    assert data["lines"][0]["merchant_sku"] == "PDD-FSKU-1"

    mirror_id = int(data["id"])

    payload["platform_status"] = "UPDATED"
    payload["lines"][0]["title"] = "PDD 测试商品 - 已更新"

    second = await client.post("/oms/pdd/platform-order-mirrors/import", json=payload)
    assert second.status_code == 200, second.text
    data2 = second.json()["data"]

    assert int(data2["id"]) == mirror_id
    assert data2["platform_status"] == "UPDATED"
    assert len(data2["lines"]) == 1
    assert data2["lines"][0]["title"] == "PDD 测试商品 - 已更新"

    detail = await client.get(f"/oms/pdd/platform-order-mirrors/{mirror_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["id"] == mirror_id

    listing = await client.get("/oms/pdd/platform-order-mirrors")
    assert listing.status_code == 200, listing.text
    assert any(int(row["id"]) == mirror_id for row in listing.json()["data"])


async def test_import_taobao_platform_order_mirror(client, session) -> None:
    await _clear_mirrors(session)

    suffix = uuid4().hex[:8]
    store_code = f"TAOBAO-MIRROR-{suffix}"
    await _ensure_store(
        session,
        platform="taobao",
        store_code=store_code,
        store_name="淘宝镜像测试店铺",
    )

    payload = _payload(
        platform="taobao",
        collector_order_id=910002,
        collector_line_id=920002,
        collector_store_code=store_code,
        platform_order_no=f"TB-MIRROR-ORDER-{suffix}",
        merchant_sku="TB-FSKU-1",
    )

    resp = await client.post("/oms/taobao/platform-order-mirrors/import", json=payload)
    assert resp.status_code == 200, resp.text

    data = resp.json()["data"]
    assert data["platform"] == "taobao"
    assert data["lines"][0]["merchant_sku"] == "TB-FSKU-1"


async def test_import_jd_platform_order_mirror(client, session) -> None:
    await _clear_mirrors(session)

    suffix = uuid4().hex[:8]
    store_code = f"JD-MIRROR-{suffix}"
    await _ensure_store(
        session,
        platform="jd",
        store_code=store_code,
        store_name="京东镜像测试店铺",
    )

    payload = _payload(
        platform="jd",
        collector_order_id=910003,
        collector_line_id=920003,
        collector_store_code=store_code,
        platform_order_no=f"JD-MIRROR-ORDER-{suffix}",
        merchant_sku="JD-FSKU-1",
    )

    resp = await client.post("/oms/jd/platform-order-mirrors/import", json=payload)
    assert resp.status_code == 200, resp.text

    data = resp.json()["data"]
    assert data["platform"] == "jd"
    assert data["lines"][0]["merchant_sku"] == "JD-FSKU-1"


async def test_import_rejects_path_payload_platform_mismatch(client, session) -> None:
    await _clear_mirrors(session)

    payload = _payload(
        platform="taobao",
        collector_order_id=910004,
        collector_line_id=920004,
        collector_store_code="MISMATCH-STORE",
        platform_order_no="MISMATCH-ORDER",
        merchant_sku="MISMATCH-FSKU",
    )

    resp = await client.post("/oms/pdd/platform-order-mirrors/import", json=payload)
    assert resp.status_code == 422, resp.text
    assert "payload platform mismatch" in resp.text
