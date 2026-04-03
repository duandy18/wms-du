from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.wms.outbound.contracts.outbound_atomic import OutboundAtomicCreateIn


def test_outbound_atomic_accepts_direct_minimal():
    payload = OutboundAtomicCreateIn.model_validate(
        {
            "warehouse_id": 1,
            "source_type": "direct",
            "receiver": {
                "name": "Andy",
                "province": "上海市",
                "city": "上海市",
                "address": "浦东新区测试路 1 号",
            },
            "lines": [
                {
                    "item_id": 101,
                    "qty": 2,
                }
            ],
        }
    )
    assert payload.source_type == "direct"
    assert payload.receiver.name == "Andy"
    assert payload.lines[0].item_id == 101


def test_outbound_atomic_requires_source_ref_for_upstream():
    with pytest.raises(ValidationError):
        OutboundAtomicCreateIn.model_validate(
            {
                "warehouse_id": 1,
                "source_type": "upstream",
                "receiver": {
                    "name": "Andy",
                    "province": "上海市",
                    "city": "上海市",
                    "address": "浦东新区测试路 1 号",
                },
                "lines": [
                    {
                        "item_id": 101,
                        "qty": 2,
                    }
                ],
            }
        )


def test_outbound_atomic_receiver_requires_core_address_fields():
    with pytest.raises(ValidationError):
        OutboundAtomicCreateIn.model_validate(
            {
                "warehouse_id": 1,
                "source_type": "direct",
                "receiver": {
                    "name": "Andy",
                    "city": "上海市",
                    "address": "浦东新区测试路 1 号",
                },
                "lines": [
                    {
                        "item_id": 101,
                        "qty": 2,
                    }
                ],
            }
        )


def test_outbound_atomic_line_requires_item_id_or_barcode():
    with pytest.raises(ValidationError):
        OutboundAtomicCreateIn.model_validate(
            {
                "warehouse_id": 1,
                "source_type": "direct",
                "receiver": {
                    "name": "Andy",
                    "province": "上海市",
                    "city": "上海市",
                    "address": "浦东新区测试路 1 号",
                },
                "lines": [
                    {
                        "qty": 2,
                    }
                ],
            }
        )
