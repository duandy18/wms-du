from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.user.deps.auth import get_current_user
from app.main import app
from app.oms.platforms.pdd import router_pull as pdd_router_pull
from app.oms.platforms.pdd.contracts import PddOrderSummary
from app.oms.platforms.pdd.service_pull import PddPullCheckResult


class _TestUser:
    id: int = 999
    username: str = "test-user"
    is_active: bool = True


pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_post_store_pdd_test_pull_returns_real_pull_ok(client, session, monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _TestUser()

    original_check_pull_ready = pdd_router_pull.PddPullService.check_pull_ready

    async def _fake_check_pull_ready(
        self,
        *,
        session,
        store_id: int,
        start_confirm_at: str | None = None,
        end_confirm_at: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ):
        assert store_id == 123
        assert start_confirm_at == "2026-03-29 00:00:00"
        assert end_confirm_at == "2026-03-29 23:59:59"
        assert page == 1
        assert page_size == 50

        return PddPullCheckResult(
            platform="pdd",
            store_id=123,
            auth_source="oauth",
            connection_status="connected",
            credential_status="valid",
            reauth_required=False,
            pull_ready=True,
            status="ready",
            status_reason="real_pull_ok",
            last_authorized_at="2026-03-29T00:00:00+00:00",
            last_pull_checked_at="2026-03-29T00:10:00+00:00",
            last_error_at=None,
            orders_count=1,
            page=1,
            page_size=50,
            has_more=False,
            orders=[
                PddOrderSummary(
                    platform_order_id="PDD-ORDER-001",
                    order_status=1,
                    confirm_at="2026-03-29 12:00:00",
                    receiver_name_masked="张**",
                    receiver_phone_masked="138****0000",
                    receiver_address_summary_masked="上海市上海市浦东新区世纪大道***号",
                    buyer_memo="尽快发货",
                    items_count=2,
                    raw_order={},
                )
            ],
            start_confirm_at="2026-03-29 00:00:00",
            end_confirm_at="2026-03-29 23:59:59",
        )

    monkeypatch.setattr(
        pdd_router_pull.PddPullService,
        "check_pull_ready",
        _fake_check_pull_ready,
    )

    try:
        resp = await client.post(
            "/oms/stores/123/pdd/test-pull",
            json={
                "start_confirm_at": "2026-03-29 00:00:00",
                "end_confirm_at": "2026-03-29 23:59:59",
                "page": 1,
                "page_size": 50,
            },
        )
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["ok"] is True
        data = body["data"]

        assert data["platform"] == "pdd"
        assert data["store_id"] == 123
        assert data["status"] == "ready"
        assert data["status_reason"] == "real_pull_ok"
        assert data["orders_count"] == 1
        assert data["page"] == 1
        assert data["page_size"] == 50
        assert data["has_more"] is False
        assert data["start_confirm_at"] == "2026-03-29 00:00:00"
        assert data["end_confirm_at"] == "2026-03-29 23:59:59"
        assert isinstance(data["orders"], list)
        assert len(data["orders"]) == 1
        assert data["orders"][0]["platform_order_id"] == "PDD-ORDER-001"
    finally:
        monkeypatch.setattr(
            pdd_router_pull.PddPullService,
            "check_pull_ready",
            original_check_pull_ready,
        )
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_post_store_pdd_test_pull_invalid_time_window(client, session, monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _TestUser()

    original_check_pull_ready = pdd_router_pull.PddPullService.check_pull_ready

    async def _fake_check_pull_ready(
        self,
        *,
        session,
        store_id: int,
        start_confirm_at: str | None = None,
        end_confirm_at: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ):
        raise pdd_router_pull.PddPullServiceError(
            "end_confirm_at must be greater than start_confirm_at"
        )

    monkeypatch.setattr(
        pdd_router_pull.PddPullService,
        "check_pull_ready",
        _fake_check_pull_ready,
    )

    try:
        resp = await client.post(
            "/oms/stores/124/pdd/test-pull",
            json={
                "start_confirm_at": "2026-03-29 00:00:00",
                "end_confirm_at": "2026-03-28 23:59:59",
                "page": 1,
                "page_size": 50,
            },
        )
        assert resp.status_code == 400, resp.text
        assert "end_confirm_at must be greater than start_confirm_at" in resp.text
    finally:
        monkeypatch.setattr(
            pdd_router_pull.PddPullService,
            "check_pull_ready",
            original_check_pull_ready,
        )
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_post_store_pdd_test_pull_invalid_page_size(client, session, monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _TestUser()

    original_check_pull_ready = pdd_router_pull.PddPullService.check_pull_ready

    async def _fake_check_pull_ready(
        self,
        *,
        session,
        store_id: int,
        start_confirm_at: str | None = None,
        end_confirm_at: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ):
        raise pdd_router_pull.PddPullServiceError("page_size must be <= 100")

    monkeypatch.setattr(
        pdd_router_pull.PddPullService,
        "check_pull_ready",
        _fake_check_pull_ready,
    )

    try:
        resp = await client.post(
            "/oms/stores/125/pdd/test-pull",
            json={
                "start_confirm_at": "2026-03-29 00:00:00",
                "end_confirm_at": "2026-03-29 23:59:59",
                "page": 1,
                "page_size": 150,
            },
        )
        assert resp.status_code == 400, resp.text
        assert "page_size must be <= 100" in resp.text
    finally:
        monkeypatch.setattr(
            pdd_router_pull.PddPullService,
            "check_pull_ready",
            original_check_pull_ready,
        )
        app.dependency_overrides.pop(get_current_user, None)
