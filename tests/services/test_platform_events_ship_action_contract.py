# tests/services/test_platform_events_ship_action_contract.py
from __future__ import annotations

import pytest

from app.oms.services.platform_events_actions import do_ship


@pytest.mark.asyncio
async def test_platform_ship_event_no_longer_commits_wms_stock() -> None:
    with pytest.raises(ValueError) as exc:
        await do_ship(
            session=None,
            platform="PDD",
            raw_event={
                "lines": [
                    {
                        "item_id": 3001,
                        "warehouse_id": 1,
                        "batch_code": "LEGACY-BATCH",
                        "qty": 1,
                    }
                ]
            },
            mapped={},
            task={
                "ref": "ORD:PDD:1:UT-PLATFORM-SHIP-RETIRED",
                "shop_id": "1",
                "lines": [
                    {
                        "item_id": 3001,
                        "warehouse_id": 1,
                        "batch_code": "LEGACY-BATCH",
                        "qty": 1,
                    }
                ],
            },
            trace_id="TRACE-UT-PLATFORM-SHIP-RETIRED",
        )

    assert "platform_ship_stock_commit_retired" in str(exc.value)
    assert "lot_id" in str(exc.value)
