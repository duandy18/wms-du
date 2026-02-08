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
    合同：/platform-skus/mirror 在 mirror 有数据时，必须返回 mirror 的 sku_name。
    """
    client = TestClient(app)
    token = login(client)

    payload = {"ut": True}

    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                insert into platform_sku_mirror(
                  platform, store_id, platform_sku_id,
                  sku_name, spec, raw_payload, source, observed_at,
                  created_at, updated_at
                ) values (
                  :platform, :store_id, :platform_sku_id,
                  :sku_name, :spec, (:raw_payload)::jsonb, :source, :observed_at,
                  now(), now()
                )
                on conflict (platform, store_id, platform_sku_id)
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
                "store_id": 1,
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

    resp = client.get(
        "/platform-skus/mirror?platform=PDD&shop_id=1&platform_sku_id=SKU-UT-MIRROR-001",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data.get("platform") == "PDD"
    assert data.get("shop_id") == 1
    assert data.get("platform_sku_id") == "SKU-UT-MIRROR-001"

    lines = data.get("lines") or []
    assert len(lines) >= 1
    assert lines[0].get("item_name") == "UT_MIRROR_NAME"
    assert lines[0].get("spec") == "UT_SPEC"

    db2 = SessionLocal()
    try:
        db2.execute(
            text(
                """
                delete from platform_sku_mirror
                 where platform=:platform and store_id=:store_id and platform_sku_id=:platform_sku_id
                """
            ),
            {"platform": "PDD", "store_id": 1, "platform_sku_id": "SKU-UT-MIRROR-001"},
        )
        db2.commit()
    finally:
        db2.close()
