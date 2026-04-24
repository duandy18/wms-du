# tests/api/test_wms_receiving_batch_no_lot_code_contract_api.py
from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _login_admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/users/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


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
    warehouse_id = row.scalar_one_or_none()
    assert warehouse_id is not None, "no active warehouse found"
    return int(warehouse_id)


async def _pick_enabled_item_with_uom(session: AsyncSession) -> dict[str, object]:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  i.id AS item_id,
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


async def _force_supplier_required_item_policy(
    session: AsyncSession,
    *,
    item_id: int,
) -> None:
    """
    本测试要验证 batch_no -> lot_code_input -> lot_id 的供应商批号链路。

    为避免 baseline item policy 随机落到 INTERNAL_ONLY / NONE，这里只在测试事务内
    把被测 item 提升为 SUPPLIER_ONLY + REQUIRED。
    """
    await session.execute(
        text(
            """
            UPDATE items
               SET lot_source_policy = 'SUPPLIER_ONLY'::lot_source_policy,
                   expiry_policy = 'REQUIRED'::expiry_policy,
                   derivation_allowed = TRUE,
                   uom_governance_enabled = TRUE
             WHERE id = :item_id
            """
        ),
        {"item_id": int(item_id)},
    )


async def _load_operation_line(
    session: AsyncSession,
    *,
    receipt_no: str,
) -> dict[str, object]:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  o.id AS operation_id,
                  o.receipt_no_snapshot,
                  ol.id AS operation_line_id,
                  ol.batch_no,
                  ol.lot_id,
                  ol.qty_base
                FROM wms_inbound_operations o
                JOIN wms_inbound_operation_lines ol
                  ON ol.wms_inbound_operation_id = o.id
                WHERE o.receipt_no_snapshot = :receipt_no
                ORDER BY o.id DESC, ol.id ASC
                LIMIT 1
                """
            ),
            {"receipt_no": str(receipt_no)},
        )
    ).mappings().first()

    assert row is not None, f"operation line not found for receipt_no={receipt_no}"
    return dict(row)


async def _load_event_line(
    session: AsyncSession,
    *,
    receipt_no: str,
) -> dict[str, object]:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  e.id AS event_id,
                  e.event_no,
                  e.trace_id,
                  e.source_ref,
                  iel.id AS event_line_id,
                  iel.lot_code_input,
                  iel.lot_id,
                  iel.qty_base
                FROM wms_events e
                JOIN inbound_event_lines iel
                  ON iel.event_id = e.id
                WHERE e.event_type = 'INBOUND'
                  AND e.source_ref = :receipt_no
                ORDER BY e.id DESC, iel.line_no ASC
                LIMIT 1
                """
            ),
            {"receipt_no": str(receipt_no)},
        )
    ).mappings().first()

    assert row is not None, f"inbound event line not found for receipt_no={receipt_no}"
    return dict(row)


async def _load_ledger_row(
    session: AsyncSession,
    *,
    event_id: int,
    item_id: int,
    warehouse_id: int,
) -> dict[str, object]:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  event_id,
                  ref,
                  ref_line,
                  item_id,
                  warehouse_id,
                  lot_id,
                  delta,
                  reason,
                  reason_canon,
                  sub_reason
                FROM stock_ledger
                WHERE event_id = :event_id
                  AND item_id = :item_id
                  AND warehouse_id = :warehouse_id
                ORDER BY id ASC
                LIMIT 1
                """
            ),
            {
                "event_id": int(event_id),
                "item_id": int(item_id),
                "warehouse_id": int(warehouse_id),
            },
        )
    ).mappings().first()

    assert row is not None, f"stock ledger row not found for event_id={event_id}"
    return dict(row)


async def _load_lot_code(
    session: AsyncSession,
    *,
    lot_id: int,
) -> str | None:
    row = await session.execute(
        text("SELECT lot_code FROM lots WHERE id = :lot_id"),
        {"lot_id": int(lot_id)},
    )
    value = row.scalar_one_or_none()
    return str(value) if value is not None else None


@pytest.mark.asyncio
async def test_wms_receiving_batch_no_maps_to_event_lot_code_input_and_lot_id(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    """
    WMS receiving 合同护栏：

    页面/操作提交合同：
      - 继续使用 batch_no

    事件事实层：
      - 写入 inbound_event_lines.lot_code_input

    结构事实层：
      - wms_inbound_operation_lines.lot_id / inbound_event_lines.lot_id / stock_ledger.lot_id 必须一致
      - stock_ledger 不落 batch_no / batch_code 字符串事实
    """
    headers = await _login_admin_headers(client)

    warehouse_id = await _pick_active_warehouse_id(session)
    picked = await _pick_enabled_item_with_uom(session)
    item_id = int(picked["item_id"])
    item_uom_id = int(picked["item_uom_id"])

    await _force_supplier_required_item_policy(session, item_id=item_id)
    await session.commit()

    create_payload = {
        "warehouse_id": int(warehouse_id),
        "remark": "UT-BATCH-NO-GUARD",
        "lines": [
            {
                "item_id": item_id,
                "item_uom_id": item_uom_id,
                "planned_qty": 3,
                "item_name_snapshot": "前端传入文案应被后端快照覆盖",
                "item_spec_snapshot": "前端规格",
                "uom_name_snapshot": "前端单位",
                "remark": "UT-BATCH-NO-GUARD-LINE",
            }
        ],
    }

    create_response = await client.post(
        "/inbound-receipts/manual",
        json=create_payload,
        headers=headers,
    )
    assert create_response.status_code == 200, create_response.text
    receipt = create_response.json()

    receipt_id = int(receipt["id"])
    receipt_no = str(receipt["receipt_no"])
    assert receipt["status"] == "DRAFT", receipt

    release_response = await client.post(
        f"/inbound-receipts/{receipt_id}/release",
        json={},
        headers=headers,
    )
    assert release_response.status_code == 200, release_response.text
    assert release_response.json()["status"] == "RELEASED"

    batch_no = f"UT-RCV-BATCH-{uuid4().hex[:8].upper()}"
    production_date = date.today()
    expiry_date = production_date + timedelta(days=90)

    submit_payload = {
        "receipt_no": receipt_no,
        "remark": "UT receiving batch_no guard submit",
        "lines": [
            {
                "receipt_line_no": 1,
                "entries": [
                    {
                        "qty_inbound": 2,
                        "barcode_input": None,
                        "actual_item_uom_id": item_uom_id,
                        "batch_no": batch_no,
                        "production_date": production_date.isoformat(),
                        "expiry_date": expiry_date.isoformat(),
                        "remark": "UT batch_no entry",
                    }
                ],
            }
        ],
    }

    submit_response = await client.post(
        "/wms/receiving",
        json=submit_payload,
        headers=headers,
    )
    assert submit_response.status_code == 200, submit_response.text
    submit_body = submit_response.json()

    assert submit_body["receipt_no_snapshot"] == receipt_no, submit_body
    assert isinstance(submit_body["lines"], list) and len(submit_body["lines"]) == 1, submit_body

    out_line = submit_body["lines"][0]
    assert out_line["batch_no"] == batch_no, out_line
    assert out_line["lot_id"] is not None, out_line

    operation_line = await _load_operation_line(session, receipt_no=receipt_no)
    event_line = await _load_event_line(session, receipt_no=receipt_no)

    assert operation_line["batch_no"] == batch_no
    assert event_line["lot_code_input"] == batch_no

    assert operation_line["lot_id"] is not None
    assert event_line["lot_id"] is not None
    assert int(operation_line["lot_id"]) == int(event_line["lot_id"]) == int(out_line["lot_id"])

    assert int(operation_line["qty_base"]) == int(event_line["qty_base"]) == int(out_line["qty_base"])

    lot_code = await _load_lot_code(session, lot_id=int(out_line["lot_id"]))
    assert lot_code == batch_no

    ledger = await _load_ledger_row(
        session,
        event_id=int(event_line["event_id"]),
        item_id=item_id,
        warehouse_id=warehouse_id,
    )

    assert int(ledger["lot_id"]) == int(out_line["lot_id"])
    assert int(ledger["delta"]) == int(out_line["qty_base"])
    assert str(ledger["reason_canon"]) == "RECEIPT"
    assert str(ledger["sub_reason"]) == "INBOUND_OPERATION"
