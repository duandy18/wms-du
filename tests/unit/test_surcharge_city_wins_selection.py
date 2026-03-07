# tests/unit/test_surcharge_city_wins_selection.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.services.shipping_quote.surcharge_select import (
    extract_dest_scope_key,
    select_covering_surcharge,
    select_surcharges_city_wins,
)
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


def _s_dest_province(province: str, *, id: int, name: str) -> DummySurcharge:
    return DummySurcharge(
        id=id,
        name=name,
        scope="province",
        province_name=province,
    )


def _s_dest_city(province: str, city: str, *, id: int, name: str) -> DummySurcharge:
    return DummySurcharge(
        id=id,
        name=name,
        scope="city",
        province_name=province,
        city_name=city,
    )


def test_extract_dest_scope_key_structured_shapes():
    assert extract_dest_scope_key(_s_dest_province("广东省", id=1, name="广东全省附加")) == ("province", "广东省", None)
    assert extract_dest_scope_key(_s_dest_city("广东省", "深圳市", id=2, name="深圳附加")) == ("city", "广东省", "深圳市")

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


def test_city_wins_over_province():
    dest = Dest(province="广东省", city="深圳市", district=None)
    reasons: List[str] = []

    s_prov = _s_dest_province("广东省", id=10, name="广东全省附加")
    s_city = _s_dest_city("广东省", "深圳市", id=11, name="深圳附加")

    chosen = select_covering_surcharge(matched=[s_prov, s_city], dest=dest, reasons=reasons)

    assert chosen is not None
    assert chosen.id == 11


def test_same_scope_duplicate_keeps_lowest_id_and_records_reason():
    dest = Dest(province="广东省", city="深圳市", district=None)
    reasons: List[str] = []

    s_city_b = _s_dest_city("广东省", "深圳市", id=9, name="深圳附加B")
    s_city_a = _s_dest_city("广东省", "深圳市", id=5, name="深圳附加A")

    chosen = select_covering_surcharge(matched=[s_city_b, s_city_a], dest=dest, reasons=reasons)

    assert chosen is not None
    assert chosen.id == 5
    assert any("surcharge_conflict_same_scope" in r for r in reasons)


def test_compat_wrapper_returns_single_row_list():
    dest = Dest(province="广东省", city="深圳市", district=None)
    reasons: List[str] = []

    s_prov = _s_dest_province("广东省", id=1, name="广东附加")
    s_city = _s_dest_city("广东省", "深圳市", id=2, name="深圳附加")

    final = select_surcharges_city_wins(matched=[s_prov, s_city], dest=dest, reasons=reasons)

    assert [s.id for s in final] == [2]
