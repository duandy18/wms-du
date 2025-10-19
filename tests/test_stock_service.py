# tests/test_stock_service.py
import pytest

from tests.factories import make_item, make_location

from app.services.stock_service import StockService


def test_adjust_increase_and_decrease(db):
    item = make_item(db)
    loc = make_location(db)
    svc = StockService(db)

    # +10 入库
    item_id, before_qty, delta, new_qty = svc.adjust_sync(
        item_id=item.id, location_id=loc.id, delta=10
    )
    assert item_id == item.id
    assert before_qty == 0
    assert delta == 10
    assert new_qty == 10

    # -3 出库
    item_id, before_qty, delta, new_qty = svc.adjust_sync(
        item_id=item.id, location_id=loc.id, delta=-3
    )
    assert item_id == item.id
    assert before_qty == 10
    assert delta == -3
    assert new_qty == 7


def test_negative_guard(db):
    item = make_item(db)
    loc = make_location(db)
    svc = StockService(db)

    svc.adjust_sync(item_id=item.id, location_id=loc.id, delta=2)
    with pytest.raises(ValueError):
        svc.adjust(item_id=item.id, location_id=loc.id, delta=-5, allow_negative=False)


def test_multi_location_summary(db):
    item = make_item(db)
    loc1 = make_location(db, wh_id=1, code="A-01")
    loc2 = make_location(db, wh_id=1, code="A-02")
    svc = StockService(db)

    svc.adjust_sync(item_id=item.id, location_id=loc1.id, delta=5)
    svc.adjust_sync(item_id=item.id, location_id=loc2.id, delta=8)

    pairs = svc.summarize_by_item(item_id=item.id, warehouse_id=1)
    # pairs: List[Tuple[item_id, sum]]
    assert pairs and pairs[0][0] == item.id and int(pairs[0][1]) == 13
