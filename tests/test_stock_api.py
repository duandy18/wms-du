# tests/test_stock_api.py
from tests.factories import make_item, make_location


def test_post_adjust_and_query(client, db):
    item = make_item(db)
    loc = make_location(db, wh_id=2, code="B-01")

    # 调整 +12
    r = client.post(
        "/stock/adjust",
        json={
            "item_id": item.id,
            "location_id": loc.id,
            "delta": 12,
            "reason": "PO-1",
            "ref": "PO-1-L1",
            "allow_negative": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["before_quantity"] == 0
    assert body["delta"] == 12
    assert body["new_quantity"] == 12

    # 查询（按 item）
    r = client.get(f"/stock/query?item_id={item.id}")
    assert r.status_code == 200
    data = r.json()
    assert any(row["quantity"] == 12 for row in data["rows"])  # 明细
    assert any(s["on_hand"] == 12 for s in data["summary"])  # 聚合

    # 出库 -7
    r = client.post(
        "/stock/adjust",
        json={
            "item_id": item.id,
            "location_id": loc.id,
            "delta": -7,
            "reason": "SO-1",
            "ref": "SO-1-L1",
            "allow_negative": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["before_quantity"] == 12
    assert body["delta"] == -7
    assert body["new_quantity"] == 5

    # 负库存保护（应 409）
    r = client.post(
        "/stock/adjust",
        json={
            "item_id": item.id,
            "location_id": loc.id,
            "delta": -9,
            "allow_negative": False,
        },
    )
    assert r.status_code == 409
