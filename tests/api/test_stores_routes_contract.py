from datetime import datetime

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio

try:
    import httpx

    from app.api.deps import get_current_user
    from app.api.routers import stores as stores_router
    from app.main import app
except Exception:
    httpx = None
    app = None
    stores_router = None
    get_current_user = None


class _TestUser:
    """
    测试用的假用户对象。

    注意：这里只是为了绕过 get_current_user 的 token 校验；
    真正的权限检查我们在测试里已经 monkeypatch 为 no-op。
    """

    id: int = 999
    username: str = "test-user"
    is_active: bool = True


@pytest.mark.asyncio
async def test_stores_create_bind_and_default(session, monkeypatch):
    if httpx is None or app is None or stores_router is None or get_current_user is None:
        pytest.skip("httpx or app unavailable")

    # —— 1) 覆盖 get_current_user：让 FastAPI 认为已经有登录用户 ——
    #
    # app.dependency_overrides 会在依赖解析阶段生效，
    # 避免 get_current_user 因缺少 token 返回 401。
    #
    app.dependency_overrides[get_current_user] = lambda: _TestUser()

    # —— 2) 覆盖 stores._check_perm：跳过 RBAC 实际检查 ——
    #
    # 生产环境 /stores 已经接入 RBAC（config.store.read/write），
    # 本测试关注的是“合同级别行为”（建店、绑定、默认仓、详情聚合），
    # 不验证权限本身。
    #
    monkeypatch.setattr(
        stores_router,
        "_check_perm",
        lambda db, current_user, required: None,
    )

    try:
        # 确保有两个仓（幂等）
        await session.execute(
            text("INSERT INTO warehouses (id,name) VALUES (1,'WH-1') ON CONFLICT (id) DO NOTHING")
        )
        await session.execute(
            text("INSERT INTO warehouses (id,name) VALUES (2,'WH-2') ON CONFLICT (id) DO NOTHING")
        )
        await session.commit()

        # 1) 建档：/stores
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "platform": "PDD",
                "shop_id": "UT-SHOP-STORES-01",
                "name": "拼多多自营-合同测试",
            }
            r = await client.post("/stores", json=payload)
            assert r.status_code == 200
            resp = r.json()
            assert resp["ok"] is True
            store_id = resp["data"]["store_id"]
            assert resp["data"]["platform"] == "PDD"
            assert resp["data"]["shop_id"] == "UT-SHOP-STORES-01"

            # 2) 绑定两个仓：/stores/{id}/warehouses/bind
            r2 = await client.post(
                f"/stores/{store_id}/warehouses/bind",
                json={"warehouse_id": 1, "is_default": True, "priority": 10},
            )
            assert r2.status_code == 200 and r2.json()["ok"] is True

            r3 = await client.post(
                f"/stores/{store_id}/warehouses/bind",
                json={"warehouse_id": 2, "is_default": False, "priority": 50},
            )
            assert r3.status_code == 200 and r3.json()["ok"] is True

            # 3) 读取默认仓：/stores/{id}/default-warehouse
            r4 = await client.get(f"/stores/{store_id}/default-warehouse")
            assert r4.status_code == 200
            wid = r4.json()["data"]["warehouse_id"]
            assert wid == 1

            # 4) 再读详情（JSON 聚合）：/stores/{id}
            r5 = await client.get(f"/stores/{store_id}")
            assert r5.status_code == 200
            detail = r5.json()["data"]
            assert detail["platform"] == "PDD"
            assert detail["shop_id"] == "UT-SHOP-STORES-01"

            # bindings 至少包含两个仓，且第一个是默认仓
            bindings = detail["bindings"]
            assert isinstance(bindings, list) and len(bindings) >= 2
            assert bindings[0]["warehouse_id"] == 1 and bindings[0]["is_default"] is True
    finally:
        # 清理 dependency override，避免影响其他测试
        if app is not None and get_current_user is not None:
            app.dependency_overrides.pop(get_current_user, None)
