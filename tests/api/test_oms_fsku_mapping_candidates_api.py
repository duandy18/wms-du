from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text


pytestmark = pytest.mark.asyncio


async def _clear_rows(session) -> None:
    await session.execute(text("DELETE FROM merchant_code_fsku_bindings"))
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
                  upper(:platform),
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


async def _create_published_fsku(session, *, code: str, name: str) -> int:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO fskus (
                  code,
                  name,
                  shape,
                  status,
                  published_at,
                  created_at,
                  updated_at
                )
                VALUES (
                  :code,
                  :name,
                  'single',
                  'published',
                  now(),
                  now(),
                  now()
                )
                RETURNING id
                """
            ),
            {"code": code, "name": name},
        )
    ).mappings().one()
    await session.commit()
    return int(row["id"])


async def _create_pdd_mirror_with_lines(
    session,
    *,
    store_code: str,
    order_no: str,
    bound_code: str,
    unbound_code: str,
) -> None:
    mirror = (
        await session.execute(
            text(
                """
                INSERT INTO oms_pdd_order_mirrors (
                  collector_order_id,
                  collector_store_id,
                  collector_store_code,
                  collector_store_name,
                  platform_order_no,
                  platform_status
                )
                VALUES (
                  810001,
                  820001,
                  :store_code,
                  'PDD 候选测试店铺',
                  :order_no,
                  'WAIT_SELLER_SEND_GOODS'
                )
                RETURNING id
                """
            ),
            {"store_code": store_code, "order_no": order_no},
        )
    ).mappings().one()

    mirror_id = int(mirror["id"])

    await session.execute(
        text(
            """
            INSERT INTO oms_pdd_order_mirror_lines (
              mirror_id,
              collector_line_id,
              collector_order_id,
              platform_order_no,
              merchant_sku,
              platform_item_id,
              platform_sku_id,
              title,
              quantity,
              line_amount
            )
            VALUES
              (:mirror_id, 910001, 810001, :order_no, :bound_code, 'PDD-ITEM-1', 'PDD-SKU-1', '已绑定商品', 2, 86.00),
              (:mirror_id, 910002, 810001, :order_no, :unbound_code, 'PDD-ITEM-2', 'PDD-SKU-2', '未绑定商品', 1, 43.00),
              (:mirror_id, 910003, 810001, :order_no, NULL, 'PDD-ITEM-3', 'PDD-SKU-3', '缺少商家编码商品', 1, 12.00)
            """
        ),
        {
            "mirror_id": mirror_id,
            "order_no": order_no,
            "bound_code": bound_code,
            "unbound_code": unbound_code,
        },
    )

    await session.commit()


async def test_pdd_fsku_mapping_candidates_return_binding_status(client, session) -> None:
    await _clear_rows(session)

    suffix = uuid4().hex[:8]
    store_code = f"PDD-FSKU-MAP-{suffix}"
    bound_code = f"PDD-BOUND-{suffix}"
    unbound_code = f"PDD-UNBOUND-{suffix}"

    await _ensure_store(session, platform="pdd", store_code=store_code)
    fsku_id = await _create_published_fsku(
        session,
        code=f"FSKU-CANDIDATE-{suffix}",
        name="候选测试 FSKU",
    )

    await _create_pdd_mirror_with_lines(
        session,
        store_code=store_code,
        order_no=f"PDD-FSKU-MAP-ORDER-{suffix}",
        bound_code=bound_code,
        unbound_code=unbound_code,
    )

    await session.execute(
        text(
            """
            INSERT INTO merchant_code_fsku_bindings (
              platform,
              store_code,
              merchant_code,
              fsku_id,
              reason,
              created_at,
              updated_at
            )
            VALUES (
              'PDD',
              :store_code,
              :merchant_code,
              :fsku_id,
              'candidate test',
              now(),
              now()
            )
            """
        ),
        {
            "store_code": store_code,
            "merchant_code": bound_code,
            "fsku_id": fsku_id,
        },
    )
    await session.commit()

    resp = await client.get(
        "/oms/pdd/fsku-mapping/candidates",
        params={"store_code": store_code},
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["total"] == 3

    by_code = {row["merchant_code"]: row for row in data["items"]}

    bound = by_code[bound_code]
    assert bound["is_bound"] is True
    assert bound["mapping_status"] == "bound"
    assert bound["fsku_id"] == fsku_id
    assert bound["fsku_code"] == f"FSKU-CANDIDATE-{suffix}"
    assert bound["fsku_name"] == "候选测试 FSKU"

    unbound = by_code[unbound_code]
    assert unbound["is_bound"] is False
    assert unbound["mapping_status"] == "unbound"

    missing = by_code[None]
    assert missing["is_bound"] is False
    assert missing["mapping_status"] == "missing_merchant_code"


async def test_pdd_fsku_mapping_candidates_can_filter_only_unbound(client, session) -> None:
    await _clear_rows(session)

    suffix = uuid4().hex[:8]
    store_code = f"PDD-FSKU-MAP-FILTER-{suffix}"
    bound_code = f"PDD-BOUND-FILTER-{suffix}"
    unbound_code = f"PDD-UNBOUND-FILTER-{suffix}"

    await _ensure_store(session, platform="pdd", store_code=store_code)
    fsku_id = await _create_published_fsku(
        session,
        code=f"FSKU-CANDIDATE-FILTER-{suffix}",
        name="候选过滤 FSKU",
    )
    await _create_pdd_mirror_with_lines(
        session,
        store_code=store_code,
        order_no=f"PDD-FSKU-MAP-FILTER-ORDER-{suffix}",
        bound_code=bound_code,
        unbound_code=unbound_code,
    )

    await session.execute(
        text(
            """
            INSERT INTO merchant_code_fsku_bindings (
              platform,
              store_code,
              merchant_code,
              fsku_id,
              reason,
              created_at,
              updated_at
            )
            VALUES (
              'PDD',
              :store_code,
              :merchant_code,
              :fsku_id,
              'candidate test',
              now(),
              now()
            )
            """
        ),
        {
            "store_code": store_code,
            "merchant_code": bound_code,
            "fsku_id": fsku_id,
        },
    )
    await session.commit()

    resp = await client.get(
        "/oms/pdd/fsku-mapping/candidates",
        params={"store_code": store_code, "only_unbound": "true"},
    )
    assert resp.status_code == 200, resp.text

    items = resp.json()["data"]["items"]
    statuses = {row["mapping_status"] for row in items}

    assert "bound" not in statuses
    assert "unbound" in statuses
    assert "missing_merchant_code" in statuses


async def test_fsku_mapping_candidate_routes_are_platform_separated(client, session) -> None:
    await _clear_rows(session)

    suffix = uuid4().hex[:8]
    store_code = f"PDD-FSKU-MAP-ISO-{suffix}"
    await _ensure_store(session, platform="pdd", store_code=store_code)
    await _create_pdd_mirror_with_lines(
        session,
        store_code=store_code,
        order_no=f"PDD-FSKU-MAP-ISO-ORDER-{suffix}",
        bound_code=f"PDD-BOUND-ISO-{suffix}",
        unbound_code=f"PDD-UNBOUND-ISO-{suffix}",
    )

    pdd_resp = await client.get(
        "/oms/pdd/fsku-mapping/candidates",
        params={"store_code": store_code},
    )
    assert pdd_resp.status_code == 200, pdd_resp.text
    assert pdd_resp.json()["data"]["total"] == 3

    taobao_resp = await client.get(
        "/oms/taobao/fsku-mapping/candidates",
        params={"store_code": store_code},
    )
    assert taobao_resp.status_code == 200, taobao_resp.text
    assert taobao_resp.json()["data"]["total"] == 0
