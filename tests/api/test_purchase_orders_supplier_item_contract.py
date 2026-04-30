# tests/api/test_purchase_orders_supplier_item_contract.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple
from uuid import uuid4

import pytest
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests._problem import as_problem


async def _login_admin_headers(client: httpx.AsyncClient) -> Dict[str, str]:
    """
    项目里很多 API 都需要 Bearer token（即使某些路由没显式 Depends(get_current_user)，也可能有全局依赖）。
    这里统一走 admin 登录，保证测试稳定。
    """
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _get_items(client: httpx.AsyncClient, headers: Dict[str, str], qs: str = "") -> List[Dict[str, Any]]:
    url = f"/items{qs}"
    r = await client.get(url, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    return data


async def _pick_any_uom_id(session: AsyncSession, *, item_id: int) -> int:
    """
    unit_governance 二阶段：以 item_uoms 为真相源。
    终态：PO 创建必须显式给 uom_id + qty_input（不做兼容）。
    """
    r1 = await session.execute(
        text(
            """
            SELECT id
              FROM item_uoms
             WHERE item_id = :i AND is_base = true
             ORDER BY id
             LIMIT 1
            """
        ),
        {"i": int(item_id)},
    )
    got = r1.scalar_one_or_none()
    if got is not None:
        return int(got)

    r2 = await session.execute(
        text(
            """
            SELECT id
              FROM item_uoms
             WHERE item_id = :i
             ORDER BY id
             LIMIT 1
            """
        ),
        {"i": int(item_id)},
    )
    got2 = r2.scalar_one_or_none()
    assert got2 is not None, {"msg": "item has no item_uoms", "item_id": int(item_id)}
    return int(got2)


async def _insert_supplier(
    session: AsyncSession,
    *,
    active: bool,
    name_prefix: str,
) -> Tuple[int, str]:
    suffix = uuid4().hex[:10].upper()
    code = f"{name_prefix}-{suffix}".upper()
    name = f"{name_prefix}-{suffix}"

    await session.execute(
        text(
            """
            SELECT setval(
              pg_get_serial_sequence('suppliers', 'id'),
              COALESCE((SELECT MAX(id) FROM suppliers), 0) + 1,
              false
            )
            """
        )
    )

    row = await session.execute(
        text(
            """
            INSERT INTO suppliers(name, code, active)
            VALUES (:name, :code, :active)
            RETURNING id, name
            """
        ),
        {
            "name": name,
            "code": code,
            "active": bool(active),
        },
    )
    got = row.mappings().one()
    return int(got["id"]), str(got["name"])


async def _insert_item_for_supplier(
    session: AsyncSession,
    *,
    supplier_id: int,
    sku_prefix: str,
) -> int:
    sku = f"{sku_prefix}-{uuid4().hex[:10]}".upper()
    name = f"UT-{sku}"

    row = await session.execute(
        text(
            """
            INSERT INTO items(
              name, sku, enabled, supplier_id,
              lot_source_policy, expiry_policy, derivation_allowed, uom_governance_enabled,
              shelf_life_value, shelf_life_unit
            )
            VALUES(
              :name, :sku, TRUE, :supplier_id,
              'INTERNAL_ONLY'::lot_source_policy, 'NONE'::expiry_policy, TRUE, TRUE,
              NULL, NULL
            )
            RETURNING id
            """
        ),
        {
            "name": name,
            "sku": sku,
            "supplier_id": int(supplier_id),
        },
    )
    item_id = int(row.scalar_one())

    await session.execute(
        text(
            """
            INSERT INTO item_uoms(
              item_id, uom, ratio_to_base, display_name,
              is_base, is_purchase_default, is_inbound_default, is_outbound_default
            )
            VALUES(
              :item_id, 'PCS', 1, 'PCS',
              TRUE, TRUE, TRUE, TRUE
            )
            ON CONFLICT ON CONSTRAINT uq_item_uoms_item_uom
            DO UPDATE SET
              ratio_to_base = EXCLUDED.ratio_to_base,
              display_name = EXCLUDED.display_name,
              is_base = EXCLUDED.is_base,
              is_purchase_default = EXCLUDED.is_purchase_default,
              is_inbound_default = EXCLUDED.is_inbound_default,
              is_outbound_default = EXCLUDED.is_outbound_default
            """
        ),
        {"item_id": int(item_id)},
    )

    return int(item_id)


def _assert_po_head_contract(data: Dict[str, Any]) -> None:
    assert "id" in data, data
    assert isinstance(data["id"], int), data

    assert "po_no" in data, data
    po_no = str(data.get("po_no") or "").strip()
    assert po_no, data
    assert po_no.startswith("PO-"), data


def _assert_po_line_plan_contract_m5(line: Dict[str, Any]) -> None:
    """
    Phase M-5：PO 行单位合同（结构化）
    - qty_ordered_base（唯一计划事实口径）
    - qty_ordered_input + purchase_ratio_to_base_snapshot（计划解释器）
    """
    for k in (
        "qty_ordered_base",
        "qty_ordered_input",
        "purchase_ratio_to_base_snapshot",
    ):
        assert k in line, line
        assert isinstance(line[k], int), line

    ordered_base = int(line["qty_ordered_base"])
    qty_input = int(line["qty_ordered_input"])
    ratio = int(line["purchase_ratio_to_base_snapshot"])

    assert ordered_base >= 0, line
    assert qty_input > 0, line
    assert ratio >= 1, line
    assert ordered_base == qty_input * ratio, line


@pytest.mark.asyncio
async def test_items_filter_by_supplier_id_returns_only_supplier_items(client: httpx.AsyncClient) -> None:
    """
    合同：/items 支持 supplier_id 过滤，并返回严格子集。
    依赖：tests/fixtures/base_seed.sql 已将 (3001,3002,4002) 绑定 supplier_id=1。
    """
    headers = await _login_admin_headers(client)

    all_items = await _get_items(client, headers)
    assert len(all_items) >= 1

    s1_items = await _get_items(client, headers, "?supplier_id=1&enabled=true")
    # ✅ 至少 2 个，避免后续链路测试数据稀缺
    assert len(s1_items) >= 2

    # ✅ 返回的每个 item 都必须 supplier_id=1 且 enabled=true
    for it in s1_items:
        assert it.get("supplier_id") == 1
        assert it.get("enabled") is True


@pytest.mark.asyncio
async def test_create_po_rejects_nonexistent_item(client: httpx.AsyncClient) -> None:
    """
    合同：创建 PO 时，item_id 不存在 -> 400 且 message 可解释。
    终态：行必须带 uom_id + qty_input（不做兼容）。
    """
    headers = await _login_admin_headers(client)

    payload = {
        "warehouse_id": 1,
        "supplier_id": 1,
        "purchaser": "UT",
        "purchase_time": "2026-01-14T10:00:00Z",
        "lines": [{"line_no": 1, "item_id": 9999, "uom_id": 1, "qty_input": 1}],
    }
    r = await client.post("/purchase-orders/", json=payload, headers=headers)
    assert r.status_code == 400, r.text
    p = as_problem(r.json())
    assert "不存在" in (p.get("message") or "")


@pytest.mark.asyncio
async def test_create_po_rejects_item_supplier_mismatch(client: httpx.AsyncClient) -> None:
    """
    合同：创建 PO 时，item.supplier_id 与 po.supplier_id 不一致 -> 400。
    使用真实样本：item_id=1 的 supplier_id=3。
    终态：行必须带 uom_id + qty_input（不做兼容）。
    """
    headers = await _login_admin_headers(client)

    payload = {
        "warehouse_id": 1,
        "supplier_id": 1,
        "purchaser": "UT",
        "purchase_time": "2026-01-14T10:00:00Z",
        "lines": [{"line_no": 1, "item_id": 1, "uom_id": 1, "qty_input": 1}],
    }
    r = await client.post("/purchase-orders/", json=payload, headers=headers)
    assert r.status_code == 400, r.text
    p = as_problem(r.json())
    assert "不属于当前供应商" in (p.get("message") or "")


@pytest.mark.asyncio
async def test_create_po_rejects_inactive_supplier(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    """
    合同：新建采购单只能使用 active=true 的供应商。
    停用供应商即使存在，也不能用于新建 PO。
    """
    headers = await _login_admin_headers(client)

    supplier_id, _supplier_name = await _insert_supplier(
        session,
        active=False,
        name_prefix="UT-INACTIVE-SUP",
    )
    item_id = await _insert_item_for_supplier(
        session,
        supplier_id=supplier_id,
        sku_prefix="UT-INACTIVE-ITEM",
    )
    await session.commit()

    uom_id = await _pick_any_uom_id(session, item_id=item_id)

    payload = {
        "warehouse_id": 1,
        "supplier_id": int(supplier_id),
        "purchaser": "UT",
        "purchase_time": "2026-01-14T10:00:00Z",
        "lines": [{"line_no": 1, "item_id": int(item_id), "uom_id": int(uom_id), "qty_input": 1}],
    }

    r = await client.post("/purchase-orders/", json=payload, headers=headers)
    assert r.status_code == 400, r.text
    p = as_problem(r.json())
    assert "已停用" in (p.get("message") or "")


@pytest.mark.asyncio
async def test_update_po_rejects_inactive_supplier(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    """
    合同：更新采购单时，如果切换供应商，也只能使用 active=true 的供应商。
    已存在历史 PO 的读取不受影响；这里仅约束写入。
    """
    headers = await _login_admin_headers(client)

    s1_items = await _get_items(client, headers, "?supplier_id=1&enabled=true")
    assert len(s1_items) >= 1
    active_item_id = int(s1_items[0]["id"])
    active_uom_id = await _pick_any_uom_id(session, item_id=active_item_id)

    create_payload = {
        "warehouse_id": 1,
        "supplier_id": 1,
        "purchaser": "UT",
        "purchase_time": "2026-01-14T10:00:00Z",
        "lines": [{"line_no": 1, "item_id": active_item_id, "uom_id": int(active_uom_id), "qty_input": 1}],
    }
    created_resp = await client.post("/purchase-orders/", json=create_payload, headers=headers)
    assert created_resp.status_code == 200, created_resp.text
    created = created_resp.json()
    po_id = int(created["id"])

    inactive_supplier_id, _supplier_name = await _insert_supplier(
        session,
        active=False,
        name_prefix="UT-INACTIVE-UPD-SUP",
    )
    inactive_item_id = await _insert_item_for_supplier(
        session,
        supplier_id=inactive_supplier_id,
        sku_prefix="UT-INACTIVE-UPD-ITEM",
    )
    await session.commit()

    inactive_uom_id = await _pick_any_uom_id(session, item_id=inactive_item_id)

    update_payload = {
        "warehouse_id": 1,
        "supplier_id": int(inactive_supplier_id),
        "purchaser": "UT-UPDATED",
        "purchase_time": "2026-01-15T10:00:00Z",
        "lines": [
            {
                "line_no": 1,
                "item_id": int(inactive_item_id),
                "uom_id": int(inactive_uom_id),
                "qty_input": 1,
            }
        ],
    }

    r = await client.put(f"/purchase-orders/{po_id}", json=update_payload, headers=headers)
    assert r.status_code == 400, r.text
    p = as_problem(r.json())
    assert "已停用" in (p.get("message") or "")


@pytest.mark.asyncio
async def test_create_po_success_with_supplier_items(client: httpx.AsyncClient, session: AsyncSession) -> None:
    """
    合同：供应商=1 且 item.supplier_id=1 的商品可以创建 PO 成功。
    我们从 /items?supplier_id=1&enabled=true 动态取一个 item_id，避免写死。
    终态：行必须带 uom_id + qty_input（不做兼容）。
    """
    headers = await _login_admin_headers(client)

    s1_items = await _get_items(client, headers, "?supplier_id=1&enabled=true")
    assert len(s1_items) >= 1
    item_id = int(s1_items[0]["id"])

    uom_id = await _pick_any_uom_id(session, item_id=item_id)

    payload = {
        "warehouse_id": 1,
        "supplier_id": 1,
        "purchaser": "UT",
        "purchase_time": "2026-01-14T10:00:00Z",
        "lines": [{"line_no": 1, "item_id": item_id, "uom_id": int(uom_id), "qty_input": 2}],
    }
    r = await client.post("/purchase-orders/", json=payload, headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    _assert_po_head_contract(data)

    assert data.get("supplier_id") == 1
    assert isinstance(data.get("lines"), list)
    assert len(data["lines"]) == 1

    line = data["lines"][0]
    assert int(line["item_id"]) == item_id

    _assert_po_line_plan_contract_m5(line)
    assert int(line["qty_ordered_base"]) == 2 * int(line["purchase_ratio_to_base_snapshot"])
