from __future__ import annotations

from typing import Any

import pytest

from app.oms.order_facts.services import collector_export_client as subject


pytestmark = pytest.mark.asyncio


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict[str, Any],
        *,
        text: str | None = None,
    ) -> None:
        self.status_code = int(status_code)
        self._payload = payload
        self.text = text if text is not None else str(payload)

    def json(self) -> dict[str, Any]:
        return self._payload


def _clear_collector_env(monkeypatch: pytest.MonkeyPatch) -> None:
    subject._reset_service_token_cache_for_tests()
    monkeypatch.delenv("COLLECTOR_API_BASE_URL", raising=False)
    monkeypatch.delenv("COLLECTOR_API_TOKEN", raising=False)
    monkeypatch.delenv("COLLECTOR_CLIENT_ID", raising=False)
    monkeypatch.delenv("COLLECTOR_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("COLLECTOR_TOKEN_REFRESH_MARGIN_SECONDS", raising=False)


async def test_fetch_orders_uses_client_credentials_token_and_caches_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_collector_env(monkeypatch)
    monkeypatch.setenv("COLLECTOR_API_BASE_URL", "http://collector.test")
    monkeypatch.setenv("COLLECTOR_CLIENT_ID", "wms-api")
    monkeypatch.setenv("COLLECTOR_CLIENT_SECRET", "client-secret-001")

    calls: list[tuple[str, str, dict[str, Any] | None, dict[str, str] | None]] = []

    class _FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
            calls.append(("POST", url, json, None))
            assert url == "http://collector.test/oauth/token"
            assert json == {
                "grant_type": "client_credentials",
                "client_id": "wms-api",
                "client_secret": "client-secret-001",
            }
            return _FakeResponse(
                200,
                {
                    "access_token": "service-token-001",
                    "token_type": "bearer",
                    "expires_in": 1800,
                    "scope": "collector.export.read",
                },
            )

        async def get(
            self,
            url: str,
            *,
            headers: dict[str, str],
            params: dict[str, Any] | None = None,
        ) -> _FakeResponse:
            calls.append(("GET", url, params, headers))
            assert headers == {"Authorization": "Bearer service-token-001"}

            if url.endswith("/collector/export/pdd/orders"):
                assert params == {
                    "limit": 2,
                    "offset": 0,
                    "since": "2026-04-28T00:00:00+08:00",
                    "until": "2026-04-29T00:00:00+08:00",
                }
                return _FakeResponse(
                    200,
                    {
                        "ok": True,
                        "data": [{"collector_order_id": 1001}],
                    },
                )

            if url.endswith("/collector/export/pdd/orders/1001"):
                return _FakeResponse(
                    200,
                    {
                        "ok": True,
                        "data": {"collector_order_id": 1001},
                    },
                )

            raise AssertionError(f"unexpected GET url: {url}")

    monkeypatch.setattr(subject.httpx, "AsyncClient", _FakeAsyncClient)

    rows = await subject.fetch_collector_export_orders(
        platform="pdd",
        limit=2,
        offset=0,
        since="2026-04-28T00:00:00+08:00",
        until="2026-04-29T00:00:00+08:00",
    )
    assert rows == [{"collector_order_id": 1001}]

    detail = await subject.fetch_collector_export_order(
        platform="pdd",
        collector_order_id=1001,
    )
    assert detail == {"collector_order_id": 1001}

    assert [call[0] for call in calls].count("POST") == 1
    assert [call[0] for call in calls].count("GET") == 2


async def test_fetch_orders_falls_back_to_static_collector_api_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_collector_env(monkeypatch)
    monkeypatch.setenv("COLLECTOR_API_BASE_URL", "http://collector.test")
    monkeypatch.setenv("COLLECTOR_API_TOKEN", "static-token-001")

    calls: list[tuple[str, str, dict[str, Any] | None, dict[str, str] | None]] = []

    class _FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
            raise AssertionError(f"token endpoint must not be called: {url} {json}")

        async def get(
            self,
            url: str,
            *,
            headers: dict[str, str],
            params: dict[str, Any] | None = None,
        ) -> _FakeResponse:
            calls.append(("GET", url, params, headers))
            assert url == "http://collector.test/collector/export/pdd/orders"
            assert headers == {"Authorization": "Bearer static-token-001"}
            assert params == {"limit": 1, "offset": 0}
            return _FakeResponse(
                200,
                {
                    "ok": True,
                    "data": [{"collector_order_id": 2001}],
                },
            )

    monkeypatch.setattr(subject.httpx, "AsyncClient", _FakeAsyncClient)

    rows = await subject.fetch_collector_export_orders(
        platform="pdd",
        limit=1,
        offset=0,
    )

    assert rows == [{"collector_order_id": 2001}]
    assert len(calls) == 1


async def test_incomplete_client_credentials_raise_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_collector_env(monkeypatch)
    monkeypatch.setenv("COLLECTOR_CLIENT_ID", "wms-api")

    with pytest.raises(subject.CollectorExportUpstreamError) as exc:
        await subject.fetch_collector_export_orders(
            platform="pdd",
            limit=1,
            offset=0,
        )

    assert "COLLECTOR_CLIENT_ID and COLLECTOR_CLIENT_SECRET" in str(exc.value)
