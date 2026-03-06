# tests/unit/test_surcharge_city_wins_selection.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.services.shipping_quote.surcharge_select import extract_dest_scope_key, select_surcharges_city_wins
from app.services.shipping_quote.types import Dest


@dataclass
class DummySurcharge:
    id: int
    name: str
    scope: str = ""
    province_code: Optional[str] = None
    city_code: Optional[str] = None
    province_name: Optional[str] = None
    city_name: Optional[str] = None
    priority: int = 100


def _s_dest_province(province: str, *, id: int, name: str, priority: int = 100) -> DummySurcharge:
    return DummySurcharge(
        id=id,
        name=name,
        scope="province",
        province_name=province,
        priority=priority,
    )


def _s_dest_city(province: str, city: str, *, id: int, name: str, priority: int = 100) -> DummySurcharge:
    return DummySurcharge(
        id=id,
        name=name,
        scope="city",
        province_name=province,
        city_name=city,
        priority=priority,
    )


def _s_unkeyed(name: str, *, id: int, priority: int = 100) -> DummySurcharge:
    return DummySurcharge(
        id=id,
        name=name,
        scope="always",
        priority=priority,
    )


def test_extract_dest_scope_key_structured_shapes():
    assert extract_dest_scope_key(_s_dest_province("广东省", id=1, name="广东全省附加")) == ("province", "广东省", None)
    assert extract_dest_scope_key(_s_dest_city("广东省", "深圳市", id=2, name="深圳附加")) == ("city", "广东省", "深圳市")

    # invalid structured shape => None
    assert (
        extract_dest_scope_key(
            DummySurcharge(
                id=3,
                name="坏城市规则",
                scope="city",
                province_name="广东省",
                city_name=None,
            )
        )
        is None
    )
    assert extract_dest_scope_key(_s_unkeyed("异形件附加", id=4)) is None


def test_city_wins_suppresses_province_for_same_province():
    dest = Dest(province="广东省", city="深圳市", district=None)
    reasons: List[str] = []

    s_prov = _s_dest_province("广东省", id=10, name="广东全省附加")
    s_city = _s_dest_city("广东省", "深圳市", id=11, name="深圳附加")

    final = select_surcharges_city_wins(matched=[s_prov, s_city], dest=dest, reasons=reasons)

    ids = [s.id for s in final]
    assert 11 in ids
    assert 10 not in ids
    assert any("city wins" in r for r in reasons)


def test_duplicate_key_keeps_lowest_priority_then_lowest_id_and_records_reason():
    dest = Dest(province="广东省", city="深圳市", district=None)
    reasons: List[str] = []

    # 同 key：priority 更小者优先
    s_city_high = _s_dest_city("广东省", "深圳市", id=9, name="深圳附加B", priority=200)
    s_city_low = _s_dest_city("广东省", "深圳市", id=5, name="深圳附加A", priority=100)

    final = select_surcharges_city_wins(matched=[s_city_high, s_city_low], dest=dest, reasons=reasons)
    assert [s.id for s in final] == [5]
    assert any("duplicate_key" in r for r in reasons)

    # priority 相同时，id 更小者优先
    reasons2: List[str] = []
    s_city_a = _s_dest_city("广东省", "深圳市", id=7, name="深圳附加C", priority=100)
    s_city_b = _s_dest_city("广东省", "深圳市", id=3, name="深圳附加D", priority=100)

    final2 = select_surcharges_city_wins(matched=[s_city_a, s_city_b], dest=dest, reasons=reasons2)
    assert [s.id for s in final2] == [3]
    assert any("duplicate_key" in r for r in reasons2)


def test_unkeyed_rules_are_kept():
    dest = Dest(province="广东省", city="深圳市", district=None)
    reasons: List[str] = []

    s_flag = _s_unkeyed("异形件附加", id=1)
    s_city = _s_dest_city("广东省", "深圳市", id=2, name="深圳附加")

    final = select_surcharges_city_wins(matched=[s_flag, s_city], dest=dest, reasons=reasons)

    ids = [s.id for s in final]
    assert 1 in ids
    assert 2 in ids
