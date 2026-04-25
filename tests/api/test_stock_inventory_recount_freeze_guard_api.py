from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.utils.ensure_minimal import set_stock_qty


pytestmark = pytest.mark.asyncio
UTC = timezone.utc


def _norm_utc_iso(v: str) -> str:
    return str(v).replace("Z", "+00:00")


def _extract_freeze_guard_detail(body: dict) -> dict | None:
    # 1) FastAPI 原生 HTTPException 直出：{"detail": {...}}
    detail = body.get("detail")
    if isinstance(detail, dict) and detail.get("error_code") == "count_doc_frozen_for_warehouse":
        return detail

    # 2) 某些路径可能直接平铺 error_code
    if body.get("error_code") == "count_doc_frozen_for_warehouse":
        return body

    # 3) 统一问题响应壳：{"http_status":409, "details":[...], "context":{...}}
    details = body.get("details")
    if isinstance(details, list):
        for entry in details:
            if not isinstance(entry, dict):
                continue
            if entry.get("error_code") == "count_doc_frozen_for_warehouse":
                return entry
            if entry.get("reason") == "count_doc_frozen_for_warehouse":
                return {"error_code": entry["reason"], **entry}

    return None


async def _login_admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _pick_active_warehouse_id(session: AsyncSession) -> int:
    row = await session.execute(
        text(
            """
            SELECT id
              FROM warehouses
             WHERE COALESCE(active, true) = true
             ORDER BY id
             LIMIT 1
            """
        )
    )
    wid = row.scalar_one_or_none()
    assert wid is not None, "no active warehouse found"
    return int(wid)


async def _pick_enabled_item_with_base_uom(session: AsyncSession) -> dict[str, object]:
    row = (
        await session.execute(
            text(
                """
                SELECT DISTINCT ON (i.id)
                  i.id AS item_id,
                  u.id AS item_uom_id
                FROM items i
                JOIN item_uoms u
                  ON u.item_id = i.id
                WHERE COALESCE(i.enabled, true) = true
                ORDER BY
                  i.id ASC,
                  CASE
                    WHEN COALESCE(u.is_inbound_default, false) THEN 0
                    WHEN COALESCE(u.is_base, false) THEN 1
                    ELSE 2
                  END,
                  u.id ASC
                LIMIT 1
                """
            )
        )
    ).mappings().first()
    assert row is not None, "no enabled item with item_uom found"
    return dict(row)


async def _seed_positive_stock(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: str,
    qty: int,
    ref: str,
) -> None:
    _ = ref
    await set_stock_qty(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_code=str(batch_code),
        qty=int(qty),
    )


@pytest.mark.asyncio
async def test_stock_inventory_recount_returns_409_when_count_doc_frozen(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    warehouse_id = await _pick_active_warehouse_id(session)
    picked = await _pick_enabled_item_with_base_uom(session)

    item_id = int(picked["item_id"])
    batch_code = f"UT-RECOUNT-FROZEN-{uuid4().hex[:8].upper()}"

    await _seed_positive_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        batch_code=batch_code,
        qty=5,
        ref=f"ut:recount:freeze-guard:seed:{batch_code}",
    )
    await session.commit()

    snapshot_at = datetime(2030, 1, 4, 8, 0, 0, tzinfo=UTC)
    r_create = await client.post(
        "/inventory-adjustment/count-docs",
        json={
            "warehouse_id": int(warehouse_id),
            "snapshot_at": snapshot_at.isoformat(),
            "remark": "UT-RECOUNT-FROZEN-GUARD",
        },
        headers=headers,
    )
    assert r_create.status_code == 201, r_create.text
    created = r_create.json()
    doc_id = int(created["id"])

    r_freeze = await client.post(
        f"/inventory-adjustment/count-docs/{doc_id}/freeze",
        headers=headers,
    )
    assert r_freeze.status_code == 200, r_freeze.text
    frozen = r_freeze.json()
    assert frozen["status"] == "FROZEN", frozen

    r = await client.post(
        "/stock/inventory/recount",
        headers=headers,
        json={
            "item_id": int(item_id),
            "warehouse_id": int(warehouse_id),
            "lot_code": batch_code,
            "actual": 5,
            "ctx": {"device_id": "UT-COUNT-RECOUNT"},
        },
    )
    assert r.status_code == 409, r.text
    body = r.json()

    detail = _extract_freeze_guard_detail(body)
    assert detail is not None, body
    assert detail["error_code"] == "count_doc_frozen_for_warehouse", body

    # 统一壳与直出 detail 的字段形状可能略有差异：
    # 能断言的强字段尽量断言；缺失时不硬绑死包体细节。
    if "warehouse_id" in detail:
        assert int(detail["warehouse_id"]) == int(warehouse_id), body
    if "count_doc_id" in detail:
        assert int(detail["count_doc_id"]) == int(doc_id), body
    if "count_no" in detail:
        assert str(detail["count_no"]) == str(created["count_no"]), body
    if "snapshot_at" in detail:
        assert _norm_utc_iso(str(detail["snapshot_at"])) == snapshot_at.isoformat(), body

    if "http_status" in body:
        assert int(body["http_status"]) == 409, body

@pytest.mark.asyncio
async def test_stock_inventory_recount_rejects_retired_batch_code_alias(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/stock/inventory/recount",
        json={
            "item_id": 910001,
            "warehouse_id": 1,
            "batch_code": "UT-RECOUNT-RETIRED-ALIAS",
            "actual": 1,
        },
    )

    assert response.status_code == 422, response.text
