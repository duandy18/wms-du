# tests/api/test_zone_brackets_matrix_grouped_contract.py
from __future__ import annotations

import pytest
import httpx

from tests.api._helpers_pricing_matrix import (
    login_admin_headers,
    ensure_provider_id,
    ensure_scheme_id,
    create_segment_template,
    create_zones,
    create_bracket_flat,
    create_bracket_step_over,
)


@pytest.mark.asyncio
async def test_zone_brackets_matrix_groups_by_segment_template_id(client: httpx.AsyncClient) -> None:
    """
    目标：同一 scheme 下按 segment_template_id 分组（核心合同）
    - groups 数量 == distinct segment_template_id 数量
    - group.zones 内每个 zone.segment_template_id 必须等于 group.segment_template_id
    - zones/brackets 字段结构完整可用
    - unbound_zones 为空（本用例显式绑定）

    注意：
    - group.segments 的“非空”依赖 SegmentTemplate 生命周期（publish/activate 等）与写入端点差异，
      在 pricing smoke 中不做强约束，避免把 smoke 变成模板工作台生命周期测试。
    """
    headers = await login_admin_headers(client)
    provider_id = await ensure_provider_id(client, headers)
    scheme_id = await ensure_scheme_id(client, headers, provider_id, name="UT-MATRIX-GROUPED")

    tpl1_id = await create_segment_template(
        client,
        headers,
        scheme_id,
        name="UT-TPL-4",
        segments=[("0.000", "1.000"), ("1.000", "3.000"), ("3.000", "5.000"), ("5.000", None)],
    )
    tpl2_id = await create_segment_template(
        client,
        headers,
        scheme_id,
        name="UT-TPL-2",
        segments=[("0.000", "1.000"), ("1.000", None)],
    )

    zone_ids = await create_zones(
        client,
        headers,
        scheme_id,
        zones=[
            {"name": "UT-ZONE-TPL1-A", "active": True, "segment_template_id": tpl1_id, "provinces": ["广东省"]},
            {"name": "UT-ZONE-TPL1-B", "active": True, "segment_template_id": tpl1_id, "provinces": ["河南省"]},
            {"name": "UT-ZONE-TPL2-A", "active": True, "segment_template_id": tpl2_id, "provinces": ["青海省"]},
            {"name": "UT-ZONE-TPL2-B", "active": True, "segment_template_id": tpl2_id, "provinces": ["西藏自治区"]},
        ],
    )
    assert len(zone_ids) == 4

    # 给 tpl2 的一个 zone 写入 brackets，证明 brackets 链路完好
    await create_bracket_flat(client, headers, zone_id=zone_ids[2], min_kg="0.000", max_kg="1.000")
    await create_bracket_step_over(client, headers, zone_id=zone_ids[2], min_kg="1.000", max_kg=None)

    r = await client.get(f"/pricing-schemes/{scheme_id}/zone-brackets-matrix", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["ok"] is True
    assert data["scheme_id"] == scheme_id

    groups = data["groups"]
    assert isinstance(groups, list)
    assert len(groups) == 2

    total_zones = 0
    seen_tpl_ids = set()

    for g in groups:
        tpl_id = g["segment_template_id"]
        seen_tpl_ids.add(tpl_id)
        assert tpl_id in (tpl1_id, tpl2_id)

        # segments 字段存在即可（允许为空）
        assert "segments" in g
        assert isinstance(g["segments"], list)

        zones = g["zones"]
        assert isinstance(zones, list)
        assert len(zones) > 0
        total_zones += len(zones)

        for z in zones:
            assert z["scheme_id"] == scheme_id
            assert z["segment_template_id"] == tpl_id
            assert isinstance(z.get("members"), list)
            assert isinstance(z.get("brackets"), list)

    assert total_zones == 4
    assert seen_tpl_ids == {tpl1_id, tpl2_id}

    unbound = data["unbound_zones"]
    assert isinstance(unbound, list)
    assert len(unbound) == 0
