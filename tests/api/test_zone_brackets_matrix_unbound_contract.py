# tests/api/test_zone_brackets_matrix_unbound_contract.py
from __future__ import annotations

import pytest
import httpx

from tests.api._helpers_pricing_matrix import (
    login_admin_headers,
    ensure_provider_id,
    ensure_scheme_id,
    create_zones,
    create_segment_template,
)


@pytest.mark.asyncio
async def test_zone_brackets_matrix_unbound_zones_contract_is_deprecated_under_zone_template_required(client: httpx.AsyncClient) -> None:
    """
    新合同（硬约束版）：
    - Zone 必须绑定 segment_template_id
    - 因此 “unbound_zones（未绑定模板的 zones）” 这条合同已退役
    - matrix 仍可保留 unbound_zones 字段，但应恒为空
    """
    headers = await login_admin_headers(client)
    provider_id = await ensure_provider_id(client, headers)
    scheme_id = await ensure_scheme_id(client, headers, provider_id, name="UT-MATRIX-UNBOUND-DEPRECATED")

    # 创建一个模板并附带最小 items（segments）用于 matrix 输出
    tpl_id = await create_segment_template(
        client,
        headers,
        scheme_id,
        name="UT-TPL-ONE",
        segments=[("0.000", "1.000"), ("1.000", None)],
    )

    zone_ids = await create_zones(
        client,
        headers,
        scheme_id,
        zones=[
            {"name": "UT-ZONE-A", "active": True, "provinces": ["海南省"], "segment_template_id": tpl_id},
            {"name": "UT-ZONE-B", "active": True, "provinces": ["青海省"], "segment_template_id": tpl_id},
        ],
    )
    assert len(zone_ids) == 2

    r = await client.get(f"/pricing-schemes/{scheme_id}/zone-brackets-matrix", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["ok"] is True
    assert data["scheme_id"] == scheme_id

    # 由于两个 zone 都绑定同一模板，应该只有一个 group
    assert isinstance(data["groups"], list)
    assert len(data["groups"]) == 1
    assert data["groups"][0]["segment_template_id"] == tpl_id

    # 新合同下 unbound_zones 恒为空
    unbound = data["unbound_zones"]
    assert isinstance(unbound, list)
    assert len(unbound) == 0
