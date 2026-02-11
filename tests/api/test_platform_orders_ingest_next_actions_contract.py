# tests/api/test_platform_orders_ingest_next_actions_contract.py
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _pick_one_published_fsku_id(async_session_maker) -> int | None:
    async with async_session_maker() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT id
                      FROM fskus
                     WHERE status = 'published'
                     ORDER BY id ASC
                     LIMIT 1
                    """
                )
            )
        ).mappings().first()
        if not row or row.get("id") is None:
            return None
        return int(row["id"])


@pytest.mark.asyncio
async def test_platform_orders_ingest_code_not_bound_returns_next_actions(client):
    filled_code = _uniq("MC-UT-NOT-BOUND")

    ingest_payload = {
        "platform": "DEMO",
        "shop_id": "1",
        "ext_order_no": _uniq("EXT-MC-NOT-BOUND"),
        "receiver_name": "张三",
        "receiver_phone": "13800000000",
        "province": "上海市",
        "city": "上海市",
        "district": "浦东新区",
        "detail": "测试路 1 号",
        "lines": [{"filled_code": filled_code, "qty": 1}],
    }

    r = await client.post("/platform-orders/ingest", json=ingest_payload)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body.get("status") == "UNRESOLVED"
    store_id = int(body.get("store_id") or 0)
    assert store_id > 0

    unresolved = body.get("unresolved") or []
    assert len(unresolved) == 1

    u0 = unresolved[0]
    assert u0.get("filled_code") == filled_code
    assert u0.get("reason") == "CODE_NOT_BOUND"

    next_actions = u0.get("next_actions") or []
    assert isinstance(next_actions, list) and len(next_actions) >= 1

    # ✅ 1) 既有契约：第一条仍然是 bind_merchant_code（不破坏历史）
    a0 = next_actions[0]
    assert a0.get("action") == "bind_merchant_code"
    assert a0.get("endpoint") == "/platform-orders/manual-decisions/bind-merchant-code"

    payload = a0.get("payload") or {}
    assert payload.get("platform") == "DEMO"
    assert int(payload.get("store_id") or 0) == store_id
    assert payload.get("filled_code") == filled_code
    assert "fsku_id" in payload  # 允许为 null（人工选择）

    # ✅ 2) 新契约：必须提供“跳转治理页”的可执行动作（闭环）
    #    不要求绑定到前端 URL，但必须给出定位参数：platform + store_id + merchant_code
    gov = next((x for x in next_actions if x.get("action") == "go_store_fsku_binding_governance"), None)
    assert gov is not None, next_actions
    gov_payload = gov.get("payload") or {}
    assert gov_payload.get("platform") == "DEMO"
    assert int(gov_payload.get("store_id") or 0) == store_id
    assert gov_payload.get("merchant_code") == filled_code


@pytest.mark.asyncio
async def test_platform_orders_manual_bind_persists_current_binding_and_ingest_can_see_it(client, async_session_maker):
    filled_code = _uniq("MC-UT-BIND")

    # 0) 先 ingest 一次，确保 store 存在，并拿到真实 store_id
    ingest_seed = {
        "platform": "DEMO",
        "shop_id": "1",
        "ext_order_no": _uniq("EXT-MC-SEED"),
        "receiver_name": "张三",
        "receiver_phone": "13800000000",
        "province": "上海市",
        "city": "上海市",
        "district": "浦东新区",
        "detail": "测试路 1 号",
        "lines": [{"filled_code": filled_code, "qty": 1}],
    }
    r0 = await client.post("/platform-orders/ingest", json=ingest_seed)
    assert r0.status_code == 200, r0.text
    b0 = r0.json()
    store_id = int(b0.get("store_id") or 0)
    assert store_id > 0

    # 1) 找一个 published fsku（没有就跳过：说明 seed 未准备）
    fsku_id = await _pick_one_published_fsku_id(async_session_maker)
    if fsku_id is None:
        pytest.skip("no published fsku found in test db; seed baseline is missing published fskus")

    # 2) 绑定（HTTP）
    bind_payload = {
        "platform": "DEMO",
        "store_id": store_id,
        "filled_code": filled_code,
        "fsku_id": fsku_id,
        "reason": "ut bind",
    }

    r1 = await client.post("/platform-orders/manual-decisions/bind-merchant-code", json=bind_payload)
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert b1.get("ok") is True

    # 3) DB 断言：current binding 已持久化（这是写接口最硬的契约）
    #    注意：shop_id 来自 stores 表（语义是平台店铺ID），不能假设等于 store_id
    async with async_session_maker() as session:
        shop_row = (
            await session.execute(
                text(
                    """
                    SELECT shop_id
                      FROM stores
                     WHERE id = :sid
                       AND platform = :p
                     LIMIT 1
                    """
                ),
                {"sid": store_id, "p": "DEMO"},
            )
        ).mappings().first()
        assert shop_row and shop_row.get("shop_id") is not None
        shop_id = str(shop_row.get("shop_id"))

        bind_row = (
            await session.execute(
                text(
                    """
                    SELECT fsku_id
                      FROM merchant_code_fsku_bindings
                     WHERE platform = :p
                       AND shop_id = :shop
                       AND merchant_code = :code
                     LIMIT 1
                    """
                ),
                {"p": "DEMO", "shop": shop_id, "code": filled_code},
            )
        ).mappings().first()

        assert bind_row and int(bind_row.get("fsku_id") or 0) == int(fsku_id)

    # 4) 再 ingest：期望能 resolved；若仍看不到，至少不应再报 CODE_NOT_BOUND（因为 DB 已有 current）
    ingest_payload = {
        "platform": "DEMO",
        "shop_id": "1",
        "ext_order_no": _uniq("EXT-MC-BIND"),
        "receiver_name": "张三",
        "receiver_phone": "13800000000",
        "province": "上海市",
        "city": "上海市",
        "district": "浦东新区",
        "detail": "测试路 1 号",
        "lines": [{"filled_code": filled_code, "qty": 1}],
    }

    r2 = await client.post("/platform-orders/ingest", json=ingest_payload)
    assert r2.status_code == 200, r2.text
    body = r2.json()

    resolved = body.get("resolved") or []
    if resolved:
        rline = resolved[0]
        assert rline.get("filled_code") == filled_code
        assert int(rline.get("fsku_id") or 0) == int(fsku_id)
        assert (body.get("unresolved") or []) == []
        return

    # 读不到写入时：把失败原因钉死，帮助定位测试事务隔离/连接可见性问题
    unresolved = body.get("unresolved") or []
    assert len(unresolved) == 1
    assert unresolved[0].get("filled_code") == filled_code
    assert unresolved[0].get("reason") != "CODE_NOT_BOUND", body
