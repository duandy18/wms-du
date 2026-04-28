from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.oms.deps import stores_order_sim_testset_guard as order_sim_guard
from app.oms.services import platform_order_ingest_universe_guard as ingest_guard


@pytest.mark.asyncio
async def test_order_sim_guard_returns_conflict_when_item_is_out_of_test_set(monkeypatch):
    async def fake_load_test_set_id(_session, *, set_code: str) -> int:
        assert set_code == "DEFAULT"
        return 1

    async def fake_load_test_set_member_item_ids(_session, *, set_id: int, item_ids: list[int]) -> set[int]:
        assert set_id == 1
        assert item_ids == [1, 2]
        return {1}

    monkeypatch.setattr(order_sim_guard, "_load_test_set_id", fake_load_test_set_id)
    monkeypatch.setattr(order_sim_guard, "_load_test_set_member_item_ids", fake_load_test_set_member_item_ids)

    out_dict = {
        "resolved": [
            {
                "expanded_items": [
                    {"item_id": 1},
                    {"item_id": 2},
                ]
            }
        ]
    }

    with pytest.raises(HTTPException) as exc:
        await order_sim_guard.assert_order_sim_all_items_in_test_set(
            session=object(),
            out_dict=out_dict,
            platform="DEMO",
            store_code="1",
            store_id=1,
        )

    assert exc.value.status_code == 409
    problem = exc.value.detail
    assert problem["error_code"] == "conflict"
    assert problem["context"]["out_of_set_item_ids"] == [2]
    assert problem["context"]["resolved_item_ids"] == [1, 2]


@pytest.mark.asyncio
async def test_platform_order_ingest_guard_returns_conflict_when_test_item_enters_non_test_store(monkeypatch):
    monkeypatch.setenv("TEST_STORE_ID", "TEST-STORE")

    class FakeItemTestSetService:
        class NotFound(ValueError):
            pass

        class InTestSet(ValueError):
            pass

        def __init__(self, _session):
            pass

        async def assert_items_not_in_test_set(self, *, item_ids: list[int], set_code: str = "DEFAULT") -> None:
            assert item_ids == [1]
            assert set_code == "DEFAULT"
            raise self.InTestSet("items in test_set[DEFAULT]: [1]")

    monkeypatch.setattr(ingest_guard, "ItemTestSetService", FakeItemTestSetService)

    with pytest.raises(HTTPException) as exc:
        await ingest_guard.enforce_no_test_items_in_non_test_store(
            object(),
            store_code="PROD-STORE",
            store_id=100,
            item_ids=[1],
            source="unit-test",
        )

    assert exc.value.status_code == 409
    problem = exc.value.detail
    assert problem["error_code"] == "conflict"
    assert "测试商品不能进入非测试店铺" in problem["message"]
    assert problem["context"]["store_code"] == "PROD-STORE"
    assert problem["context"]["test_store_code"] == "TEST-STORE"
    assert problem["context"]["test_item_ids"] == [1]
