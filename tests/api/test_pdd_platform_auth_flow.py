# tests/api/test_pdd_platform_auth_flow.py
"""
PDD 平台授权链路（模拟版本）集成测试：

覆盖范围：
- POST /platform-shops/credentials  手工录入平台凭据 -> 写入 store_tokens
- GET  /platform-shops/{platform}/{shop_id}  查询授权状态（从 store_tokens 读）
- PddAdapter.build_fetch_preview  能看到 has_token=True，证明 StoreTokenService 生效
- build_fetch_preview 走 PSKU 单入口：platform_sku_ids -> ext_sku_ids（来源于 mirror.raw_payload）

注意：
- mirror 表落库键为 (platform, store_id, platform_sku_id)
- 对外合同仍使用 shop_id（字符串店铺标识）做平台授权查询
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.pdd import PddAdapter
from app.api.deps import get_session
from app.main import app
from app.models.store import Store
from app.models.store_token import StoreToken


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session() -> AsyncSession:
    """
    直接复用后端的 get_session 依赖，保证和生产代码同一个 AsyncSession 源。
    """
    async for session in get_session():
        try:
            yield session
        finally:
            await session.close()


@pytest.fixture
async def async_client() -> AsyncClient:
    """
    基于 FastAPI app 的 AsyncClient，用于打 HTTP 路由。

    注意：httpx 新版本已经不支持 AsyncClient(app=...)，
    需要显式使用 ASGITransport。
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manual_credentials_write_and_query_and_pdd_preview(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    场景：

    1) 用手工凭据模拟一条 PDD 店铺：POST /platform-shops/credentials

    2) 通过 GET /platform-shops/{platform}/{shop_id} 查询授权状态，
       确认已经在 store_tokens 里有记录，且 source=MANUAL。

    3) 写入 platform_sku_mirror（PSKU mirror-first），提供 raw_payload 中的 pdd_sku_id（ext id）。

    4) 使用 PddAdapter.build_fetch_preview（PSKU 单入口），确认 has_token=True，
       且 ext_sku_ids 来自 mirror.raw_payload。
    """
    platform = "PDD"
    shop_id = "CUST001_TEST"
    fake_token = "PASS-XYZ-123"

    # ---- 1) 手工录入一条“假 PDD 店铺”的凭据 ----
    resp = await async_client.post(
        "/platform-shops/credentials",
        json={
            "platform": platform,
            "shop_id": shop_id,
            "access_token": fake_token,
            "status": "ACTIVE",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["platform"] == platform
    assert data["shop_id"] == shop_id
    store_id = data["store_id"]
    assert store_id > 0
    assert data["source"] == "MANUAL"
    assert data["access_token_preview"].startswith("PASS")

    # ---- 2) 查询平台店铺状态（从 store_tokens 读取） ----
    resp2 = await async_client.get(f"/platform-shops/{platform}/{shop_id}")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["ok"] is True
    data2 = body2["data"]
    assert data2["platform"] == platform
    assert data2["shop_id"] == shop_id
    assert data2["store_id"] == store_id
    assert data2["status"] == "ACTIVE"
    assert data2["source"] == "MANUAL"

    # ---- 2.1) 验证底层确实写入了 stores / store_tokens ----
    res_store = await db_session.execute(select(Store).where(Store.id == store_id))
    store_row = res_store.scalar_one_or_none()
    assert store_row is not None
    assert store_row.platform == platform
    assert store_row.shop_id == shop_id

    res_token = await db_session.execute(
        select(StoreToken).where(
            StoreToken.store_id == store_id,
            StoreToken.platform == "pdd",
        )
    )
    token_row = res_token.scalar_one_or_none()
    assert token_row is not None
    assert token_row.access_token == fake_token
    assert token_row.refresh_token == "MANUAL"

    # ---- 3) 写入 mirror：提供 raw_payload 中的 pdd_sku_id（ext id） ----
    platform_sku_ids = ["PSKU-101", "PSKU-102", "PSKU-103"]
    ext_ids = ["101", "102", "103"]
    now = datetime.now(timezone.utc)

    for psid, ext in zip(platform_sku_ids, ext_ids, strict=True):
        raw = json.dumps({"pdd_sku_id": ext}, ensure_ascii=False)
        await db_session.execute(
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
                  raw_payload=excluded.raw_payload,
                  source=excluded.source,
                  observed_at=excluded.observed_at,
                  updated_at=now();
                """
            ),
            {
                "platform": "PDD",
                "store_id": int(store_id),
                "platform_sku_id": psid,
                "sku_name": None,
                "spec": None,
                "raw_payload": raw,
                "source": "unit_test",
                "observed_at": now,
            },
        )
    await db_session.commit()

    # ---- 4) 用 PddAdapter.build_fetch_preview 验证 has_token=True（PSKU 单入口） ----
    adapter = PddAdapter()
    preview = await adapter.build_fetch_preview(
        db_session,
        store_id=store_id,
        platform_sku_ids=platform_sku_ids,
        platform="PDD",
    )

    assert preview["store_id"] == store_id
    assert preview["creds_ready"] in (True, False)
    assert preview["has_token"] is True
    assert preview["platform"] == "PDD"
    assert preview["platform_sku_ids"] == platform_sku_ids
    assert preview["ext_sku_ids"] == ext_ids
    assert isinstance(preview["signature"], str)
    assert preview["signature"] == "pdd-signature-placeholder"

    # Cleanup（尽量不污染后续测试）
    await db_session.execute(
        text(
            """
            delete from platform_sku_mirror
             where platform=:platform and store_id=:store_id and platform_sku_id = any(:ids)
            """
        ),
        {"platform": "PDD", "store_id": int(store_id), "ids": list(platform_sku_ids)},
    )
    await db_session.commit()
