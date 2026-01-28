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


async def _create_template_only(
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    scheme_id: int,
    name: str,
) -> int:
    r = await client.post(
        f"/pricing-schemes/{scheme_id}/segment-templates",
        headers=headers,
        json={"name": name},
    )
    assert r.status_code in (200, 201), r.text
    data = r.json()
    tid = _pick_id_any(data)
    assert tid is not None, f"cannot resolve template_id from response: {data}"
    return tid


def _items_payload_variants(items: List[Dict[str, Any]]) -> List[Any]:
    # 兼容不同后端写法：直接 list / 包一层 items / 包一层 data
    return [items, {"items": items}, {"data": items}]


async def _ensure_template_items_active(
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    template_id: int,
    segments: List[Tuple[str, Optional[str]]],
) -> None:
    """
    ✅ 关键：matrix 的 segments 来自 segment_template_items 且会过滤 active=False。
    由于当前 create_template 接口只创建模板本体，不创建 items，
    所以这里必须再走“items 写入口”把 items 写进去，并确保 active=true。

    我们不猜你的 items 写入口实际路径，而是对一组常见路径做探测式写入：
    - /segment-templates/{id}/items
    - /segment-templates/{id}/items:replace
    - /segment-templates/{id}/items:upsert
    - /segment-templates/{id}/items/batch
    直到任意一个返回 200/201/204 即视为成功。
    """
    items: List[Dict[str, Any]] = []
    for i, (mn, mx) in enumerate(segments):
        items.append({"ord": i, "min_kg": mn, "max_kg": mx, "active": True})

    candidates = [
        ("POST", f"/segment-templates/{template_id}/items"),
        ("PUT", f"/segment-templates/{template_id}/items"),
        ("POST", f"/segment-templates/{template_id}/items:replace"),
        ("PUT", f"/segment-templates/{template_id}/items:replace"),
        ("POST", f"/segment-templates/{template_id}/items:upsert"),
        ("PUT", f"/segment-templates/{template_id}/items:upsert"),
        ("POST", f"/segment-templates/{template_id}/items/batch"),
        ("PUT", f"/segment-templates/{template_id}/items/batch"),
    ]

    last: Optional[httpx.Response] = None
    for method, path in candidates:
        for payload in _items_payload_variants(items):
            if method == "POST":
                r = await client.post(path, headers=headers, json=payload)
            else:
                r = await client.put(path, headers=headers, json=payload)
            last = r

            # 404：说明路径不对，继续探测下一个 path
            if r.status_code == 404:
                continue

            # 200/201/204：视为成功
            if r.status_code in (200, 201, 204):
                return

            # 422/409/400：可能是 payload shape 不对或语义冲突，继续尝试同路径其它 payload 或其它路径
            continue

    # 如果所有候选都失败，明确报错，方便你定位真实 endpoint
    pytest.fail(
        f"cannot write segment template items for template_id={template_id}. "
        f"last_status={getattr(last,'status_code',None)} last_body={getattr(last,'text','')}"
    )


@pytest.mark.asyncio
async def test_zone_brackets_matrix_groups_by_segment_template_id_contract(client: httpx.AsyncClient) -> None:
    """
    合同目标（自建数据版，完全不依赖固定 scheme_id）：
    - groups[] 按 segment_template_id 分组
    - 每个 group 带 segments（行结构真相：来自 template items）+ zones（含 members + brackets）
    - zones 内的 segment_template_id 必须与 group.segment_template_id 一致
    - unbound_zones[] 显式暴露（本用例期望为空）
    """
    headers = await login_admin_headers(client)
    provider_id = await ensure_provider_id(client, headers)

    uniq = uuid4().hex[:8]
    scheme_id = await ensure_scheme_id(client, headers, provider_id, name=f"UT_MX_GROUPS_{uniq}")

    # 1) 创建两套模板（仅创建模板本体）
    tpl1 = await _create_template_only(client, headers, scheme_id, name=f"UT_TPL_A_{uniq}")
    tpl2 = await _create_template_only(client, headers, scheme_id, name=f"UT_TPL_B_{uniq}")

    # 2) 为每套模板写入 active items（否则 matrix segments 会为空）
    await _ensure_template_items_active(client, headers, tpl1, segments=[("0", "1"), ("1", None)])
    await _ensure_template_items_active(client, headers, tpl2, segments=[("0", "2"), ("2", None)])

    # 3) 创建 4 个 zones：2 个绑 tpl1，2 个绑 tpl2（确保 unbound_zones 为空）
    z1 = await create_zone(client, headers, scheme_id, name=f"UT_Z_A1_{uniq}", provinces=["北京市"], segment_template_id=tpl1)
    z2 = await create_zone(client, headers, scheme_id, name=f"UT_Z_A2_{uniq}", provinces=["天津市"], segment_template_id=tpl1)
    z3 = await create_zone(client, headers, scheme_id, name=f"UT_Z_B1_{uniq}", provinces=["河北省"], segment_template_id=tpl2)
    z4 = await create_zone(client, headers, scheme_id, name=f"UT_Z_B2_{uniq}", provinces=["河南省"], segment_template_id=tpl2)

    # 4) 给每个 zone 写一条 bracket，确保 brackets 字段存在且可解析
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
        assert len(segments) > 0  # ✅ items 写入后，matrix 必须输出 segments

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

    unbound = data["unbound_zones"]
    assert isinstance(unbound, list)
    assert len(unbound) == 0


@pytest.mark.asyncio
async def test_zone_brackets_matrix_exposes_unbound_zones_contract(client: httpx.AsyncClient) -> None:
    """
    合同目标（自建数据版）：
    - zones 未绑定 segment_template_id 时：
      groups 必须为空
      unbound_zones 必须显式暴露全部未绑定 zones（不兜底、不猜测）
    """
    headers = await login_admin_headers(client)
    provider_id = await ensure_provider_id(client, headers)

    uniq = uuid4().hex[:8]
    scheme_id = await ensure_scheme_id(client, headers, provider_id, name=f"UT_MX_UNBOUND_{uniq}")

    await create_zone(client, headers, scheme_id, name=f"UT_U1_{uniq}", provinces=["北京市"], segment_template_id=None)
    await create_zone(client, headers, scheme_id, name=f"UT_U2_{uniq}", provinces=["天津市"], segment_template_id=None)
    await create_zone(client, headers, scheme_id, name=f"UT_U3_{uniq}", provinces=["河北省"], segment_template_id=None)

    resp = await client.get(f"/pricing-schemes/{scheme_id}/zone-brackets-matrix", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["ok"] is True
    assert data["scheme_id"] == scheme_id

    groups = data["groups"]
    assert isinstance(groups, list)
    assert len(groups) == 0

    unbound = data["unbound_zones"]
    assert isinstance(unbound, list)
    assert len(unbound) == 3

    for z in unbound:
        assert z["scheme_id"] == scheme_id
        assert z.get("segment_template_id") is None
