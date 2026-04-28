from __future__ import annotations

import os
from typing import Any

import httpx


class CollectorExportError(RuntimeError):
    pass


class CollectorExportNotFound(CollectorExportError):
    pass


class CollectorExportUpstreamError(CollectorExportError):
    pass


_SUPPORTED_PLATFORMS = {"pdd", "taobao", "jd"}


def _collector_base_url() -> str:
    return (os.getenv("COLLECTOR_API_BASE_URL") or "http://127.0.0.1:8001").rstrip("/")


def _collector_token() -> str | None:
    token = (os.getenv("COLLECTOR_API_TOKEN") or "").strip()
    return token or None


def _collector_timeout_seconds() -> float:
    raw = (os.getenv("COLLECTOR_API_TIMEOUT_SECONDS") or "10").strip()
    try:
        value = float(raw)
    except ValueError:
        return 10.0
    return value if value > 0 else 10.0


def _norm_platform(platform: str) -> str:
    plat = (platform or "").strip().lower()
    if plat not in _SUPPORTED_PLATFORMS:
        raise CollectorExportError(f"unsupported platform: {platform!r}")
    return plat


def _headers() -> dict[str, str]:
    token = _collector_token()
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
            resp = await client.get(url, headers=_headers(), params=params)
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
) -> list[dict[str, Any]]:
    plat = _norm_platform(platform)
    body = await _collector_get_json(
        path=f"/collector/export/{plat}/orders",
        params={"limit": int(limit), "offset": int(offset)},
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
