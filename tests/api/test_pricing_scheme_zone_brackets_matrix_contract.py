# tests/api/test_pricing_scheme_zone_brackets_matrix_contract.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import pytest
import httpx

from tests.api._helpers_pricing_matrix import (
    login_admin_headers,
    ensure_provider_id,
    ensure_scheme_id,
    create_zone,
    create_bracket_step_over,
)


def _pick_id_any(obj: Any) -> Optional[int]:
    if not isinstance(obj, dict):
        return None

    # 常见形态：{ok:true,data:{id:...}}
    if "data" in obj and isinstance(obj["data"], dict):
        got = _pick_id_any(obj["data"])
        if got is not None:
            return got

    for k in ("id", "template_id", "segment_template_id"):
        if k in obj and obj[k] is not None:
            try:
                return int(obj[k])
            except Exception:
                pass
    return None


def _items_payload_variants(items: List[Dict[str, Any]]) -> List[Any]:
    # 兼容不同后端写法：直接 list / 包一层 items / 包一层 data
    return [items, {"items": items}, {"data": items}]


async def _put_template_items(
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    template_id: int,
    segments: List[Tuple[str, Optional[str]]],
) -> None:
    """
    ✅ 新合同：publish 需要 items >= 1，且 items 必须满足连续性校验。
    这里用确定性的 PUT /segment-templates/{id}/items 写入 items，并确保 active=true。
    """
    items: List[Dict[str, Any]] = []
    for i, (mn, mx) in enumerate(segments):
        items.append({"ord": i, "min_kg": mn, "max_kg": mx, "active": True})

    # 真实 endpoint（你后端已固定）
    path = f"/segment-templates/{template_id}/items"

    last: Optional[httpx.Response] = None
    for payload in _items_payload_variants(items):
        r = await client.put(path, headers=headers, json=payload)
        last = r
        if r.status_code in (200, 201):
            return

        # 422/409/400：可能 payload shape 不对，继续尝试其它形态
        continue

    pytest.fail(
        f"cannot write segment template items for template_id={template_id}. "
        f"last_status={getattr(last,'status_code',None)} last_body={getattr(last,'text','')}"
    )


async def _publish_template(
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    template_id: int,
) -> None:
    r = await client.post(f"/segment-templates/{template_id}:publish", headers=headers, json={})
    assert r.status_code in (200, 201), r.text


async def _create_published_template(
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    scheme_id: int,
    name: str,
    segments: List[Tuple[str, Optional[str]]],
) -> int:
    """
    ✅ 新合同：Zone 绑定模板必须为 published。
    流程：create(draft) -> put items -> publish
    """
    r = await client.post(
        f"/pricing-schemes/{scheme_id}/segment-templates",
        headers=headers,
        json={"name": name},
    )
    assert r.status_code in (200, 201), r.text
    data = r.json()
    tid = _pick_id_any(data)
    assert tid is not None, f"cannot resolve template_id from response: {data}"

    await _put_template_items(client, headers, tid, segments=segments)
    await _publish_template(client, headers, tid)
    return tid


@pytest.mark.asyncio
async def test_zone_brackets_matrix_groups_by_segment_template_id_contract(client: httpx.AsyncClient) -> None:
    """
    合同目标（自建数据版，完全不依赖固定 scheme_id）：
    - groups[] 按 segment_template_id 分组
    - 每个 group 带 segments（行结构真相：来自 template items）+ zones（含 members + brackets）
    - zones 内的 segment_template_id 必须与 group.segment_template_id 一致
    - unbound_zones[] 在新合同下应恒为空（Zone 必绑模板）
    """
    headers = await login_admin_headers(client)
    provider_id = await ensure_provider_id(client, headers)

    uniq = uuid4().hex[:8]
    scheme_id = await ensure_scheme_id(client, headers, provider_id, name=f"UT_MX_GROUPS_{uniq}")

    # 1) 创建两套模板（create -> put items -> publish）
    tpl1 = await _create_published_template(client, headers, scheme_id, name=f"UT_TPL_A_{uniq}", segments=[("0", "1"), ("1", None)])
    tpl2 = await _create_published_template(client, headers, scheme_id, name=f"UT_TPL_B_{uniq}", segments=[("0", "2"), ("2", None)])

    # 2) 创建 4 个 zones：2 个绑 tpl1，2 个绑 tpl2
    z1 = await create_zone(client, headers, scheme_id, name=f"UT_Z_A1_{uniq}", provinces=["北京市"], segment_template_id=tpl1)
    z2 = await create_zone(client, headers, scheme_id, name=f"UT_Z_A2_{uniq}", provinces=["天津市"], segment_template_id=tpl1)
    z3 = await create_zone(client, headers, scheme_id, name=f"UT_Z_B1_{uniq}", provinces=["河北省"], segment_template_id=tpl2)
    z4 = await create_zone(client, headers, scheme_id, name=f"UT_Z_B2_{uniq}", provinces=["河南省"], segment_template_id=tpl2)

    # 3) 给每个 zone 写一条 bracket，确保 brackets 字段存在且可解析
    await create_bracket_step_over(client, headers, z1, "0", "1")
    await create_bracket_step_over(client, headers, z2, "0", "1")
    await create_bracket_step_over(client, headers, z3, "0", "2")
    await create_bracket_step_over(client, headers, z4, "0", "2")

    resp = await client.get(f"/pricing-schemes/{scheme_id}/zone-brackets-matrix", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["ok"] is True
    assert data["scheme_id"] == scheme_id

    groups = data["groups"]
    assert isinstance(groups, list)
    assert len(groups) == 2

    total_zone_n = 0
    tpl_ids = set()

    for g in groups:
        tpl_id = g["segment_template_id"]
        tpl_ids.add(tpl_id)
        assert tpl_id in {tpl1, tpl2}

        assert isinstance(g.get("template_name"), str) and g["template_name"]
        assert isinstance(g.get("template_status"), str) and g.get("template_status")
        assert isinstance(g.get("template_is_active"), bool)

        segments = g["segments"]
        assert isinstance(segments, list)
        assert len(segments) > 0

        for s in segments:
            assert "ord" in s
            assert "min_kg" in s
            assert "max_kg" in s

        zones = g["zones"]
        assert isinstance(zones, list)
        assert len(zones) > 0
        total_zone_n += len(zones)

        for z in zones:
            assert z["scheme_id"] == scheme_id
            assert z["segment_template_id"] == tpl_id
            assert isinstance(z.get("members"), list)
            assert "brackets" in z
            assert isinstance(z["brackets"], list)

            for b in z["brackets"]:
                assert "min_kg" in b
                assert "max_kg" in b
                assert "pricing_mode" in b
                assert "price_json" in b

    assert total_zone_n == 4
    assert tpl_ids == {tpl1, tpl2}

    # ✅ 新合同：Zone 必绑模板，因此 unbound_zones 应恒为空
    unbound = data["unbound_zones"]
    assert isinstance(unbound, list)
    assert len(unbound) == 0


@pytest.mark.asyncio
async def test_zone_brackets_matrix_unbound_zones_contract_is_deprecated_under_zone_template_required(client: httpx.AsyncClient) -> None:
    """
    新合同目标（硬约束版）：
    - Zone 创建必须绑定 segment_template_id
    - 因此 matrix 仍可保留 unbound_zones 字段，但其语义已退役，应恒为空
    - 本用例用 3 个 zones 验证：unbound_zones == [] 且 groups 正常产出
    """
    headers = await login_admin_headers(client)
    provider_id = await ensure_provider_id(client, headers)

    uniq = uuid4().hex[:8]
    scheme_id = await ensure_scheme_id(client, headers, provider_id, name=f"UT_MX_UNBOUND_DEPRECATED_{uniq}")

    # 创建 1 套模板（create -> put items -> publish）
    tpl = await _create_published_template(client, headers, scheme_id, name=f"UT_TPL_ONLY_{uniq}", segments=[("0", "1"), ("1", None)])

    # 创建 3 个 zones，全部绑定同一模板（新合同下不允许 unbound）
    await create_zone(client, headers, scheme_id, name=f"UT_U1_{uniq}", provinces=["北京市"], segment_template_id=tpl)
    await create_zone(client, headers, scheme_id, name=f"UT_U2_{uniq}", provinces=["天津市"], segment_template_id=tpl)
    await create_zone(client, headers, scheme_id, name=f"UT_U3_{uniq}", provinces=["河北省"], segment_template_id=tpl)

    resp = await client.get(f"/pricing-schemes/{scheme_id}/zone-brackets-matrix", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["ok"] is True
    assert data["scheme_id"] == scheme_id

    groups = data["groups"]
    assert isinstance(groups, list)
    assert len(groups) == 1
    assert groups[0]["segment_template_id"] == tpl
    assert isinstance(groups[0]["segments"], list) and len(groups[0]["segments"]) > 0
    assert isinstance(groups[0]["zones"], list) and len(groups[0]["zones"]) == 3

    unbound = data["unbound_zones"]
    assert isinstance(unbound, list)
    assert len(unbound) == 0
