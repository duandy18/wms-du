from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.wms.inbound.contracts.inbound_atomic import InboundAtomicCreateIn


def test_inbound_atomic_accepts_direct_minimal():
    payload = InboundAtomicCreateIn.model_validate(
        {
            "warehouse_id": 1,
            "source_type": "direct",
            "lines": [
                {
                    "item_id": 101,
                    "qty": 2,
                }
            ],
        }
    )
    assert payload.source_type == "direct"
    assert payload.lines[0].item_id == 101
    assert payload.lines[0].qty == 2


def test_inbound_atomic_requires_source_ref_for_upstream():
    with pytest.raises(ValidationError):
        InboundAtomicCreateIn.model_validate(
            {
                "warehouse_id": 1,
                "source_type": "upstream",
                "lines": [
                    {
                        "item_id": 101,
                        "qty": 2,
                    }
                ],
            }
        )


def test_inbound_atomic_line_requires_item_id_or_barcode():
    with pytest.raises(ValidationError):
        InboundAtomicCreateIn.model_validate(
            {
                "warehouse_id": 1,
                "source_type": "direct",
                "lines": [
                    {
                        "qty": 2,
                    }
                ],
            }
        )


def test_inbound_atomic_line_qty_must_be_positive():
    with pytest.raises(ValidationError):
        InboundAtomicCreateIn.model_validate(
            {
                "warehouse_id": 1,
                "source_type": "direct",
                "lines": [
                    {
                        "item_id": 101,
                        "qty": 0,
                    }
                ],
            }
        )
