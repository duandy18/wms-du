# tests/api/test_platform_sku_mirror_priority_contract.py
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import SessionLocal
from app.main import app
from tests.api._helpers_shipping_quote import login


def test_platform_sku_list_prefers_mirror_when_present(_db_clean_and_seed) -> None:
    """
    合同：/stores/{store_id}/platform-skus 在 mirror 有数据时，必须优先返回 mirror 的 sku_name。

    注意：
    - 不依赖 binding/fsku/item 的存在，避免把“读模型优先级合同”绑到其它域对象上。
    - 只要求 store_id=1（你的本地调试已证明可用）。
    """
    client = TestClient(app)
    token = login(client)

    payload = {"ut": True}

    # Arrange: 写入 mirror（用 sync SessionLocal，确保与 API 同库）
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                insert into platform_sku_mirror(
                  platform, shop_id, platform_sku_id,
                  sku_name, spec, raw_payload, source, observed_at,
                  created_at, updated_at
                ) values (
                  :platform, :shop_id, :platform_sku_id,
                  :sku_name, :spec, (:raw_payload)::jsonb, :source, :observed_at,
                  now(), now()
                )
                on conflict (platform, shop_id, platform_sku_id)
                do update set
                  sku_name=excluded.sku_name,
                  spec=excluded.spec,
                  raw_payload=excluded.raw_payload,
                  source=excluded.source,
                  observed_at=excluded.observed_at,
                  updated_at=now();
                """
            ),
            {
                "platform": "PDD",
                "shop_id": 1,
                "platform_sku_id": "SKU-UT-MIRROR-001",
                "sku_name": "UT_MIRROR_NAME",
                "spec": "UT_SPEC",
                "raw_payload": json.dumps(payload, ensure_ascii=False),
                "source": "unit_test",
                "observed_at": datetime.now(timezone.utc),
            },
        )
        db.commit()
    finally:
        db.close()

    # Act
    resp = client.get(
        "/stores/1/platform-skus?with_binding=1&limit=50&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Assert: 找到我们插入的那条 key，sku_name 必须来自 mirror
    hit = None
    for it in data.get("items", []):
        if (
            it.get("platform") == "PDD"
            and it.get("shop_id") == 1
            and it.get("platform_sku_id") == "SKU-UT-MIRROR-001"
        ):
            hit = it
            break

    assert hit is not None, f"mirror row not returned: items={data.get('items')}"
    assert hit["sku_name"] == "UT_MIRROR_NAME"

    # Cleanup（尽量不污染后续测试）
    db2 = SessionLocal()
    try:
        db2.execute(
            text(
                """
                delete from platform_sku_mirror
                where platform=:platform and shop_id=:shop_id and platform_sku_id=:platform_sku_id
                """
            ),
            {"platform": "PDD", "shop_id": 1, "platform_sku_id": "SKU-UT-MIRROR-001"},
        )
        db2.commit()
    finally:
        db2.close()
