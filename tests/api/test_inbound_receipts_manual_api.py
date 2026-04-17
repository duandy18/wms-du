from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


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


async def _pick_enabled_item_with_uom(session: AsyncSession) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  i.id AS item_id,
                  i.name AS item_name,
                  i.spec AS item_spec,
                  u.id AS item_uom_id,
                  COALESCE(NULLIF(u.display_name, ''), u.uom) AS uom_name,
                  u.ratio_to_base AS ratio_to_base
                FROM items i
                JOIN item_uoms u
                  ON u.item_id = i.id
                WHERE COALESCE(i.enabled, true) = true
                ORDER BY
                  CASE WHEN u.is_inbound_default THEN 0 WHEN u.is_base THEN 1 ELSE 2 END,
                  i.id,
                  u.id
                LIMIT 1
                """
            )
        )
    ).mappings().first()
    assert row is not None, "no enabled item with uom found"
    return dict(row)


async def _pick_mismatched_item_and_uom(session: AsyncSession) -> tuple[int, int]:
    first = await _pick_enabled_item_with_uom(session)

    row = (
        await session.execute(
            text(
                """
                SELECT
                  i.id AS item_id,
                  u.id AS item_uom_id
                FROM items i
                JOIN item_uoms u
                  ON u.item_id = i.id
                WHERE COALESCE(i.enabled, true) = true
                  AND i.id <> :item_id
                ORDER BY i.id, u.id
                LIMIT 1
                """
            ),
            {"item_id": int(first["item_id"])},
        )
    ).mappings().first()

    assert row is not None, "need at least two enabled items with uoms for mismatch test"
    return int(first["item_id"]), int(row["item_uom_id"])


def _assert_manual_line_snapshot(
    line: dict[str, Any],
    *,
    picked: dict[str, Any],
) -> None:
    assert line["item_id"] == int(picked["item_id"]), line
    assert line["item_uom_id"] == int(picked["item_uom_id"]), line

    # ✅ 即使前端传错文案，后端也应以后端真实主数据回填 snapshot
    assert line["item_name_snapshot"] == str(picked["item_name"]), line
    assert line["item_spec_snapshot"] == picked["item_spec"], line
    assert line["uom_name_snapshot"] == str(picked["uom_name"]), line

    ratio = Decimal(str(picked["ratio_to_base"]))
    assert Decimal(str(line["ratio_to_base_snapshot"])) == ratio, line


@pytest.mark.asyncio
async def test_manual_receipt_create_read_progress_release_contract(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    warehouse_id = await _pick_active_warehouse_id(session)
    picked = await _pick_enabled_item_with_uom(session)

    payload = {
        "warehouse_id": int(warehouse_id),
        "remark": "UT-MANUAL-RECEIPT",
        "lines": [
            {
                "item_id": int(picked["item_id"]),
                "item_uom_id": int(picked["item_uom_id"]),
                "planned_qty": "12",
                # 故意传错：应由后端真实主数据覆盖
                "item_name_snapshot": "错误商品名",
                "item_spec_snapshot": "错误规格",
                "uom_name_snapshot": "错误单位",
                "remark": "UT-LINE-1",
            }
        ],
    }

    r = await client.post("/inbound-receipts/manual", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["source_type"] == "MANUAL", body
    assert body["status"] == "DRAFT", body
    assert body["warehouse_id"] == int(warehouse_id), body
    assert body["source_doc_id"] is None, body
    assert body["source_doc_no_snapshot"] is None, body
    assert body["released_at"] is None, body

    receipt_id = int(body["id"])
    assert receipt_id > 0, body
    assert isinstance(body["lines"], list) and len(body["lines"]) == 1, body
    _assert_manual_line_snapshot(body["lines"][0], picked=picked)

    r2 = await client.get(f"/inbound-receipts/{receipt_id}", headers=headers)
    assert r2.status_code == 200, r2.text
    detail = r2.json()
    assert detail["id"] == receipt_id, detail
    assert detail["status"] == "DRAFT", detail
    assert isinstance(detail["lines"], list) and len(detail["lines"]) == 1, detail
    _assert_manual_line_snapshot(detail["lines"][0], picked=picked)

    r3 = await client.get(f"/inbound-receipts/{receipt_id}/progress", headers=headers)
    assert r3.status_code == 200, r3.text
    progress = r3.json()

    assert progress["receipt_id"] == receipt_id, progress
    assert progress["receipt_no"] == body["receipt_no"], progress
    assert isinstance(progress["lines"], list) and len(progress["lines"]) == 1, progress

    p0 = progress["lines"][0]
    assert p0["line_no"] == 1, progress
    assert Decimal(str(p0["planned_qty"])) == Decimal("12"), progress
    assert Decimal(str(p0["received_qty"])) == Decimal("0"), progress
    assert Decimal(str(p0["remaining_qty"])) == Decimal("12"), progress

    r4 = await client.post(f"/inbound-receipts/{receipt_id}/release", json={}, headers=headers)
    assert r4.status_code == 200, r4.text
    released = r4.json()
    assert released["receipt_id"] == receipt_id, released
    assert released["status"] == "RELEASED", released
    assert released["released_at"], released

    # ✅ 幂等：重复发布仍返回 RELEASED
    r5 = await client.post(f"/inbound-receipts/{receipt_id}/release", json={}, headers=headers)
    assert r5.status_code == 200, r5.text
    released2 = r5.json()
    assert released2["receipt_id"] == receipt_id, released2
    assert released2["status"] == "RELEASED", released2
    assert released2["released_at"], released2

    r6 = await client.get(f"/inbound-receipts/{receipt_id}", headers=headers)
    assert r6.status_code == 200, r6.text
    detail2 = r6.json()
    assert detail2["status"] == "RELEASED", detail2
    assert detail2["released_at"], detail2
    _assert_manual_line_snapshot(detail2["lines"][0], picked=picked)


@pytest.mark.asyncio
async def test_manual_receipt_create_rejects_missing_warehouse(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    picked = await _pick_enabled_item_with_uom(session)

    payload = {
        "warehouse_id": 99999999,
        "remark": "UT-MANUAL-MISSING-WH",
        "lines": [
            {
                "item_id": int(picked["item_id"]),
                "item_uom_id": int(picked["item_uom_id"]),
                "planned_qty": "5",
                "item_name_snapshot": str(picked["item_name"]),
                "item_spec_snapshot": picked["item_spec"],
                "uom_name_snapshot": str(picked["uom_name"]),
            }
        ],
    }

    r = await client.post("/inbound-receipts/manual", json=payload, headers=headers)
    assert r.status_code == 404, r.text
    body = r.json()
    assert body["http_status"] == 404, body
    assert body["context"]["path"] == "/inbound-receipts/manual", body
    reasons = [str(x.get("reason") or "") for x in body.get("details", [])]
    assert "warehouse_not_found" in reasons, body


@pytest.mark.asyncio
async def test_manual_receipt_create_rejects_item_uom_item_mismatch(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    warehouse_id = await _pick_active_warehouse_id(session)
    item_id, mismatched_uom_id = await _pick_mismatched_item_and_uom(session)

    payload = {
        "warehouse_id": int(warehouse_id),
        "remark": "UT-MANUAL-UOM-MISMATCH",
        "lines": [
            {
                "item_id": int(item_id),
                "item_uom_id": int(mismatched_uom_id),
                "planned_qty": "3",
                "item_name_snapshot": "随便写",
                "item_spec_snapshot": "随便写",
                "uom_name_snapshot": "随便写",
            }
        ],
    }

    r = await client.post("/inbound-receipts/manual", json=payload, headers=headers)
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["http_status"] == 409, body
    assert body["context"]["path"] == "/inbound-receipts/manual", body
    reasons = [str(x.get("reason") or "") for x in body.get("details", [])]
    assert any(x.startswith("item_uom_item_mismatch:") for x in reasons), body
