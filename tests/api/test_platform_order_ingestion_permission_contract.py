from __future__ import annotations

import pytest

from app.main import app
from app.user.deps.auth import get_current_user

pytestmark = pytest.mark.asyncio


class _NoPlatformOrderIngestionPermissionUser:
    id: int = 999
    username: str = "no-platform-order-ingestion-permission"
    is_active: bool = True
    permissions: list[str] = []


class _ReadOnlyPlatformOrderIngestionUser:
    id: int = 998
    username: str = "platform-order-ingestion-read-only"
    is_active: bool = True
    permissions = ["page.platform_order_ingestion.read"]


async def test_pull_job_list_requires_platform_order_ingestion_read(client):
    app.dependency_overrides[get_current_user] = lambda: _NoPlatformOrderIngestionPermissionUser()
    try:
        resp = await client.get("/oms/platform-order-ingestion/pull-jobs")
        assert resp.status_code == 403, resp.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def test_pull_job_create_requires_platform_order_ingestion_write(client):
    app.dependency_overrides[get_current_user] = lambda: _ReadOnlyPlatformOrderIngestionUser()
    try:
        resp = await client.post(
            "/oms/platform-order-ingestion/pull-jobs",
            json={
                "platform": "pdd",
                "store_id": 1,
                "job_type": "manual",
                "page_size": 50,
            },
        )
        assert resp.status_code == 403, resp.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def test_mock_authorize_requires_platform_order_ingestion_write(client):
    app.dependency_overrides[get_current_user] = lambda: _ReadOnlyPlatformOrderIngestionUser()
    try:
        resp = await client.post(
            "/oms/platform-order-ingestion/mock/stores/1/authorize",
            json={
                "platform": "pdd",
                "expires_in_days": 365,
                "pull_ready": True,
            },
        )
        assert resp.status_code == 403, resp.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)
