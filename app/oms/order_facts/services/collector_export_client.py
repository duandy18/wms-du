from __future__ import annotations

import os
import time
from typing import Any

import httpx


class CollectorExportError(RuntimeError):
    pass


class CollectorExportNotFound(CollectorExportError):
    pass


class CollectorExportUpstreamError(CollectorExportError):
    pass


_SUPPORTED_PLATFORMS = {"pdd", "taobao", "jd"}

_SERVICE_ACCESS_TOKEN: str | None = None
_SERVICE_ACCESS_TOKEN_EXPIRES_AT: float = 0.0


def _collector_base_url() -> str:
    return (os.getenv("COLLECTOR_API_BASE_URL") or "http://127.0.0.1:8001").rstrip("/")


def _collector_static_token() -> str | None:
    token = (os.getenv("COLLECTOR_API_TOKEN") or "").strip()
    return token or None


def _collector_client_id() -> str | None:
    value = (os.getenv("COLLECTOR_CLIENT_ID") or "").strip()
    return value or None


def _collector_client_secret() -> str | None:
    value = (os.getenv("COLLECTOR_CLIENT_SECRET") or "").strip()
    return value or None


def _collector_timeout_seconds() -> float:
    raw = (os.getenv("COLLECTOR_API_TIMEOUT_SECONDS") or "10").strip()
    try:
        value = float(raw)
    except ValueError:
        return 10.0
    return value if value > 0 else 10.0


def _collector_token_refresh_margin_seconds() -> float:
    raw = (os.getenv("COLLECTOR_TOKEN_REFRESH_MARGIN_SECONDS") or "60").strip()
    try:
        value = float(raw)
    except ValueError:
        return 60.0
    return value if value >= 0 else 60.0


def _norm_platform(platform: str) -> str:
    plat = (platform or "").strip().lower()
    if plat not in _SUPPORTED_PLATFORMS:
        raise CollectorExportError(f"unsupported platform: {platform!r}")
    return plat


def _client_credentials_configured() -> bool:
    return bool(_collector_client_id() or _collector_client_secret())


def _reset_service_token_cache_for_tests() -> None:
    global _SERVICE_ACCESS_TOKEN, _SERVICE_ACCESS_TOKEN_EXPIRES_AT

    _SERVICE_ACCESS_TOKEN = None
    _SERVICE_ACCESS_TOKEN_EXPIRES_AT = 0.0


def _cached_service_token_is_valid() -> bool:
    if not _SERVICE_ACCESS_TOKEN:
        return False

    return time.time() < (_SERVICE_ACCESS_TOKEN_EXPIRES_AT - _collector_token_refresh_margin_seconds())


async def _fetch_service_access_token() -> str:
    client_id = _collector_client_id()
    client_secret = _collector_client_secret()

    if not client_id or not client_secret:
        raise CollectorExportUpstreamError(
            "collector client credentials are incomplete: "
            "set COLLECTOR_CLIENT_ID and COLLECTOR_CLIENT_SECRET"
        )

    url = f"{_collector_base_url()}/oauth/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }

    try:
        async with httpx.AsyncClient(timeout=_collector_timeout_seconds()) as client:
            resp = await client.post(url, json=payload)
    except httpx.RequestError as exc:
        raise CollectorExportUpstreamError(f"collector token request failed: {exc}") from exc

    if resp.status_code >= 400:
        raise CollectorExportUpstreamError(
            f"collector token request failed: status={resp.status_code} body={resp.text}"
        )

    body = resp.json()
    if not isinstance(body, dict):
        raise CollectorExportUpstreamError("collector token response is not an object")

    access_token = str(body.get("access_token") or "").strip()
    if not access_token:
        raise CollectorExportUpstreamError("collector token response missing access_token")

    try:
        expires_in = int(body.get("expires_in") or 0)
    except (TypeError, ValueError):
        expires_in = 0

    if expires_in <= 0:
        raise CollectorExportUpstreamError("collector token response has invalid expires_in")

    global _SERVICE_ACCESS_TOKEN, _SERVICE_ACCESS_TOKEN_EXPIRES_AT
    _SERVICE_ACCESS_TOKEN = access_token
    _SERVICE_ACCESS_TOKEN_EXPIRES_AT = time.time() + expires_in

    return access_token


async def _collector_token() -> str | None:
    if _client_credentials_configured():
        if _cached_service_token_is_valid():
            return _SERVICE_ACCESS_TOKEN

        return await _fetch_service_access_token()

    return _collector_static_token()


async def _headers() -> dict[str, str]:
    token = await _collector_token()
    if not token:
        return {}

    return {"Authorization": f"Bearer {token}"}


async def _collector_get_json(
    *,
    path: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{_collector_base_url()}{path}"

    try:
        async with httpx.AsyncClient(timeout=_collector_timeout_seconds()) as client:
            resp = await client.get(url, headers=await _headers(), params=params)
    except httpx.RequestError as exc:
        raise CollectorExportUpstreamError(f"collector request failed: {exc}") from exc

    if resp.status_code == 404:
        raise CollectorExportNotFound(f"collector export resource not found: path={path}")

    if resp.status_code >= 400:
        raise CollectorExportUpstreamError(
            f"collector export request failed: status={resp.status_code} body={resp.text}"
        )

    body = resp.json()
    if not isinstance(body, dict):
        raise CollectorExportUpstreamError("collector export response is not an object")

    return body


async def fetch_collector_export_orders(
    *,
    platform: str,
    limit: int,
    offset: int,
    since: str | None = None,
    until: str | None = None,
) -> list[dict[str, Any]]:
    plat = _norm_platform(platform)
    params: dict[str, Any] = {
        "limit": int(limit),
        "offset": int(offset),
    }
    if since:
        params["since"] = since
    if until:
        params["until"] = until

    body = await _collector_get_json(
        path=f"/collector/export/{plat}/orders",
        params=params,
    )

    data = body.get("data")
    if not isinstance(data, list):
        raise CollectorExportUpstreamError("collector export list response missing data array")

    return [item for item in data if isinstance(item, dict)]


async def fetch_collector_export_order(
    *,
    platform: str,
    collector_order_id: int,
) -> dict[str, Any]:
    plat = _norm_platform(platform)
    body = await _collector_get_json(
        path=f"/collector/export/{plat}/orders/{int(collector_order_id)}",
    )

    data = body.get("data")
    if not isinstance(data, dict):
        raise CollectorExportUpstreamError("collector export response missing data object")

    return data
