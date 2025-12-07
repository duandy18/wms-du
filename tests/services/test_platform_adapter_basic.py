import pytest

from app.services.platform_adapter import PDDAdapter, _normalize_lines


@pytest.mark.asyncio
async def test_pdd_adapter_parse_event_basic():
    adapter = PDDAdapter()

    raw = {
        "platform": "pdd",
        "order_sn": "PDD123",
        "status": "PAID",
        "shop_id": "S1",
        "lines": [
            {"item_id": 3001, "qty": 2},
            {"itemId": 3002, "quantity": 3},
        ],
    }

    parsed = await adapter.parse_event(raw)

    assert parsed["platform"] == "pdd"
    assert parsed["order_id"] == "PDD123"
    assert parsed["status"] == "PAID"
    assert parsed["shop_id"] == "S1"
    # 原始 lines 透传
    assert parsed["lines"] is raw["lines"]
    # raw 整体透传
    assert parsed["raw"] is raw


@pytest.mark.asyncio
async def test_pdd_adapter_to_outbound_task_normalizes_lines():
    adapter = PDDAdapter()

    parsed = {
        "platform": "pdd",
        "order_id": "PDD123",
        "status": "PAID",
        "shop_id": "S1",
        "raw": {"order_sn": "PDD123"},
        "lines": [
            {"item_id": 3001, "qty": 2},
            {"itemId": 3002, "quantity": 3},
            {"goods_id": 3003, "num": "4"},
            # 垃圾数据：缺 item/qty → 应忽略
            {"foo": "bar"},
        ],
    }

    task = await adapter.to_outbound_task(parsed)

    # 基本字段
    assert task["platform"] == "pdd"
    assert task["ref"] == "PDD123"
    assert task["state"] == "PAID"
    assert task["shop_id"] == "S1"
    assert task["payload"] == parsed["raw"]

    # lines：只保留有 item/qty 的行，忽略垃圾行
    lines = sorted(task["lines"], key=lambda x: x["item_id"])
    assert lines == [
        {"item_id": 3001, "qty": 2},
        {"item_id": 3002, "qty": 3},
        {"item_id": 3003, "qty": 4},
    ]

    # ship_lines：need_location=True 的情况下，因无 location_id，应全部过滤掉
    assert task["ship_lines"] == []


def test_normalize_lines_with_location():
    raw_lines = [
        {"item_id": 3001, "qty": 2, "location_id": 10},
        {"itemId": 3001, "quantity": 3, "loc_id": 10},
        {"goods_id": 3002, "num": 1, "bin_id": 20},
        # 缺 location → 在 need_location 模式应被过滤
        {"item_id": 9999, "qty": 1},
        # qty <= 0 → 过滤
        {"item_id": 8888, "qty": 0, "location_id": 30},
    ]

    normalized = sorted(
        _normalize_lines(raw_lines, need_location=True),
        key=lambda x: (x["item_id"], x["location_id"]),
    )

    assert normalized == [
        {"item_id": 3001, "location_id": 10, "qty": 2},
        {"item_id": 3001, "location_id": 10, "qty": 3},
        {"item_id": 3002, "location_id": 20, "qty": 1},
    ]


def test_normalize_lines_without_location():
    raw_lines = [
        {"item_id": 3001, "qty": 2, "location_id": 10},
        {"itemId": 3002, "quantity": 3, "loc_id": 10},
        {"goods_id": 3003, "num": "4"},
        # qty <= 0 → 过滤
        {"item_id": 9999, "qty": 0},
    ]

    normalized = sorted(
        _normalize_lines(raw_lines, need_location=False),
        key=lambda x: x["item_id"],
    )

    assert normalized == [
        {"item_id": 3001, "qty": 2},
        {"item_id": 3002, "qty": 3},
        {"item_id": 3003, "qty": 4},
    ]
