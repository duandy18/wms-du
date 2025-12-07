# tests/api/test_pdd_platform_auth_flow.py
"""
PDD 平台授权链路（模拟版本）集成测试：

覆盖范围：
- POST /platform-shops/credentials  手工录入平台凭据 -> 写入 store_tokens
- GET  /platform-shops/{platform}/{shop_id}  查询授权状态（从 store_tokens 读）
- PddAdapter.build_fetch_preview  能看到 has_token=True，证明 StoreTokenService 生效
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
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
):
    """
    场景：

    1) 用手工凭据模拟一条 PDD 店铺：
       POST /platform-shops/credentials

    2) 通过 GET /platform-shops/{platform}/{shop_id} 查询授权状态，
       确认已经在 store_tokens 里有记录，且 source=MANUAL。

    3) 使用 PddAdapter.build_fetch_preview，确认 has_token=True，
       证明 StoreTokenService -> PddAdapter 这条链路打通。
    """

    # ---- 1) 手工录入一条“假 PDD 店铺”的凭据 ----
    platform = "PDD"
    shop_id = "CUST001_TEST"
    fake_token = "PASS-XYZ-123"

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

    # ---- 2.1) 验证底层确实写入了 store_tokens / stores ----
    # 查 stores
    res_store = await db_session.execute(select(Store).where(Store.id == store_id))
    store_row = res_store.scalar_one_or_none()
    assert store_row is not None
    assert store_row.platform == platform  # 大写 PDD
    assert store_row.shop_id == shop_id

    # 查 store_tokens
    res_token = await db_session.execute(
        select(StoreToken).where(
            StoreToken.store_id == store_id,
            StoreToken.platform == "pdd",  # 小写 pdd
        )
    )
    token_row = res_token.scalar_one_or_none()
    assert token_row is not None
    assert token_row.access_token == fake_token
    assert token_row.refresh_token == "MANUAL"

    # ---- 3) 用 PddAdapter.build_fetch_preview 验证 has_token=True ----
    adapter = PddAdapter()
    preview = await adapter.build_fetch_preview(
        db_session,
        store_id=store_id,
        item_ids=[101, 102, 103],
    )

    # 预览结构校验
    assert preview["store_id"] == store_id
    assert preview["creds_ready"] in (True, False)  # 现在 app_key/app_secret 未必配好
    assert preview["has_token"] is True  # 这是我们最关心的：已经吃到 token 了
    assert preview["ext_sku_ids"] == ["101", "102", "103"]
    assert isinstance(preview["signature"], str)
    assert preview["signature"] == "pdd-signature-placeholder"
