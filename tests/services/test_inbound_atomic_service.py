from __future__ import annotations

import pytest

from app.wms.inbound.contracts.inbound_atomic import InboundAtomicCreateIn
from app.wms.inbound.services import inbound_atomic_service as svc


@pytest.mark.asyncio
async def test_create_inbound_atomic_barcode_only_not_implemented_yet():
    payload = InboundAtomicCreateIn.model_validate(
        {
            "warehouse_id": 1,
            "source_type": "direct",
            "lines": [
                {
                    "barcode": "690000000001",
                    "qty": 2,
                }
            ],
        }
    )

    with pytest.raises(NotImplementedError, match="barcode-only resolution is not implemented yet"):
        await svc.create_inbound_atomic(None, payload)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_create_inbound_atomic_happy_path_with_repo_mocks(monkeypatch):
    payload = InboundAtomicCreateIn.model_validate(
        {
            "warehouse_id": 1,
            "source_type": "direct",
            "source_biz_type": "manual_adjust",
            "source_ref": None,
            "remark": "test",
            "lines": [
                {
                    "item_id": 101,
                    "qty": 2,
                    "lot_code": "LOT-001",
                }
            ],
        }
    )

    class DummyPolicy:
        item_id = 101
        lot_source_policy = "SUPPLIER_ONLY"
        expiry_policy = "NONE"
        shelf_life_value = None
        shelf_life_unit = None
        derivation_allowed = False
        uom_governance_enabled = False

    async def fake_get_item_policy_by_id(session, *, item_id: int):
        assert item_id == 101
        return DummyPolicy()

    async def fake_resolve_inbound_lot(
        session,
        *,
        warehouse_id: int,
        item_policy,
        lot_code: str | None,
    ):
        assert warehouse_id == 1
        assert item_policy.item_id == 101
        assert lot_code == "LOT-001"
        return 9001

    async def fake_apply_inbound_stock(
        session,
        *,
        warehouse_id: int,
        item_id: int,
        lot_id: int,
        qty: int,
        ref: str,
        ref_line: int,
        occurred_at,
        batch_code: str | None,
        trace_id: str,
        source_type: str,
        source_biz_type: str | None,
        source_ref: str | None,
        remark: str | None,
    ):
        assert warehouse_id == 1
        assert item_id == 101
        assert lot_id == 9001
        assert qty == 2
        assert ref_line == 1
        assert batch_code == "LOT-001"
        assert source_type == "direct"
        assert source_biz_type == "manual_adjust"
        assert source_ref is None
        assert remark == "test"
        assert trace_id.startswith("IN-ATOMIC-")
        return {"ok": True}

    monkeypatch.setattr(svc, "get_item_policy_by_id", fake_get_item_policy_by_id)
    monkeypatch.setattr(svc, "resolve_inbound_lot", fake_resolve_inbound_lot)
    monkeypatch.setattr(svc, "apply_inbound_stock", fake_apply_inbound_stock)

    out = await svc.create_inbound_atomic(None, payload)  # type: ignore[arg-type]

    assert out.ok is True
    assert out.warehouse_id == 1
    assert out.source_type == "direct"
    assert out.source_biz_type == "manual_adjust"
    assert out.trace_id.startswith("IN-ATOMIC-")
    assert len(out.rows) == 1
    assert out.rows[0].item_id == 101
    assert out.rows[0].qty == 2
    assert out.rows[0].lot_id == 9001
    assert out.rows[0].lot_code == "LOT-001"
