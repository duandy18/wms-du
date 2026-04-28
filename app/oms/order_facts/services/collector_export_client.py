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


async def fetch_collector_export_order(
    *,
    platform: str,
    collector_order_id: int,
) -> dict[str, Any]:
    plat = (platform or "").strip().lower()
    if plat not in {"pdd", "taobao", "jd"}:
        raise CollectorExportError(f"unsupported platform: {platform!r}")

    url = f"{_collector_base_url()}/collector/export/{plat}/orders/{int(collector_order_id)}"

    headers: dict[str, str] = {}
    token = _collector_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=_collector_timeout_seconds()) as client:
            resp = await client.get(url, headers=headers)
    except httpx.RequestError as exc:
        raise CollectorExportUpstreamError(f"collector request failed: {exc}") from exc

    if resp.status_code == 404:
        raise CollectorExportNotFound(f"collector export order not found: platform={plat} id={int(collector_order_id)}")

    if resp.status_code >= 400:
        raise CollectorExportUpstreamError(
            f"collector export request failed: status={resp.status_code} body={resp.text}"
        )

    body = resp.json()
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        raise CollectorExportUpstreamError("collector export response missing data object")

    return data
