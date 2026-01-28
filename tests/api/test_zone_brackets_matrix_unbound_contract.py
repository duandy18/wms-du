# tests/api/test_zone_brackets_matrix_unbound_contract.py
from __future__ import annotations

import pytest
import httpx

from tests.api._helpers_pricing_matrix import (
    login_admin_headers,
    ensure_provider_id,
    ensure_scheme_id,
    create_zones,
)


@pytest.mark.asyncio
async def test_zone_brackets_matrix_exposes_unbound_zones_no_fallback(client: httpx.AsyncClient) -> None:
    """
    目标：当 zones 未绑定 segment_template_id 时
    - groups 必须为空
    - unbound_zones 必须显式返回全部 zones（不兜底，不猜结构）
    """
    headers = await login_admin_headers(client)
    provider_id = await ensure_provider_id(client, headers)
    scheme_id = await ensure_scheme_id(client, headers, provider_id, name="UT-MATRIX-UNBOUND")

    zone_ids = await create_zones(
        client,
        headers,
        scheme_id,
        zones=[
            {"name": "UT-ZONE-A", "active": True, "provinces": ["海南省"]},
            {"name": "UT-ZONE-B", "active": True, "provinces": ["青海省"]},
        ],
    )
    assert len(zone_ids) == 2

    r = await client.get(f"/pricing-schemes/{scheme_id}/zone-brackets-matrix", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["ok"] is True
    assert data["scheme_id"] == scheme_id
    assert data["groups"] == []

    unbound = data["unbound_zones"]
    assert isinstance(unbound, list)
    assert len(unbound) == 2
    for z in unbound:
        assert z["scheme_id"] == scheme_id
        assert z.get("segment_template_id") is None
