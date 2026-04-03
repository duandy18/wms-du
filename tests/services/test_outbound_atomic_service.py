from __future__ import annotations

import pytest

from app.wms.outbound.contracts.outbound_atomic import OutboundAtomicCreateIn
from app.wms.outbound.services.outbound_atomic_service import create_outbound_atomic


@pytest.mark.asyncio
async def test_create_outbound_atomic_raises_not_implemented_for_current_apply_stage():
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

    with pytest.raises(NotImplementedError, match="outbound atomic execution is not implemented yet"):
        await create_outbound_atomic(None, payload)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_create_outbound_atomic_barcode_only_not_implemented_yet():
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
                    "barcode": "690000000001",
                    "qty": 2,
                }
            ],
        }
    )

    with pytest.raises(NotImplementedError, match="barcode-only resolution is not implemented yet"):
        await create_outbound_atomic(None, payload)  # type: ignore[arg-type]
