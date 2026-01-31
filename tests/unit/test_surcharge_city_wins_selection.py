# tests/unit/test_surcharge_city_wins_selection.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

from app.services.shipping_quote.surcharge_select import extract_dest_scope_key, select_surcharges_city_wins
from app.services.shipping_quote.types import Dest


@dataclass
class DummySurcharge:
    id: int
    name: str
    condition_json: Dict[str, Any]


def _s_dest_province(province: str) -> Dict[str, Any]:
    return {"dest": {"scope": "province", "province": province}}


def _s_dest_city(province: str, city: str) -> Dict[str, Any]:
    return {"dest": {"scope": "city", "province": province, "city": city}}


def _s_old_dest_province_list(province: str) -> Dict[str, Any]:
    return {"dest": {"province": [province]}}


def _s_old_dest_city_list(province: str, city: str) -> Dict[str, Any]:
    return {"dest": {"province": [province], "city": [city]}}


def test_extract_dest_scope_key_new_and_old_shapes():
    assert extract_dest_scope_key(_s_dest_province("广东省")) == ("province", "广东省", None)
    assert extract_dest_scope_key(_s_dest_city("广东省", "深圳市")) == ("city", "广东省", "深圳市")

    # old list shape (length=1) is accepted
    assert extract_dest_scope_key(_s_old_dest_province_list("广东省")) == ("province", "广东省", None)
    assert extract_dest_scope_key(_s_old_dest_city_list("广东省", "深圳市")) == ("city", "广东省", "深圳市")

    # invalid shapes => None
    assert extract_dest_scope_key({"dest": {"scope": "city", "province": "广东省"}}) is None
    assert extract_dest_scope_key({"dest": {"province": ["广东省", "河北省"]}}) is None


def test_city_wins_suppresses_province_for_same_province():
    dest = Dest(province="广东省", city="深圳市", district=None)
    reasons: List[str] = []

    # 同省：province + city 同时命中 -> city wins, province suppressed
    s_prov = DummySurcharge(id=10, name="广东全省附加", condition_json=_s_dest_province("广东省"))
    s_city = DummySurcharge(id=11, name="深圳附加", condition_json=_s_dest_city("广东省", "深圳市"))

    final = select_surcharges_city_wins(matched=[s_prov, s_city], dest=dest, reasons=reasons)

    ids = [s.id for s in final]
    assert 11 in ids
    assert 10 not in ids  # 被抑制

    # reasons 应包含模式提示
    assert any("city wins" in r for r in reasons)


def test_duplicate_key_keeps_lowest_id_and_records_reason():
    dest = Dest(province="广东省", city="深圳市", district=None)
    reasons: List[str] = []

    # 同 key 的 city 规则重复：只取 id 更小的
    s_city_a = DummySurcharge(id=5, name="深圳附加A", condition_json=_s_dest_city("广东省", "深圳市"))
    s_city_b = DummySurcharge(id=9, name="深圳附加B", condition_json=_s_dest_city("广东省", "深圳市"))

    final = select_surcharges_city_wins(matched=[s_city_b, s_city_a], dest=dest, reasons=reasons)

    assert [s.id for s in final] == [5]
    assert any("duplicate_key" in r for r in reasons)


def test_unkeyed_rules_are_kept():
    dest = Dest(province="广东省", city="深圳市", district=None)
    reasons: List[str] = []

    # unkeyed：没有 dest key 的规则（例如 flag_any），应该保留叠加
    s_flag = DummySurcharge(id=1, name="异形件附加", condition_json={"flag_any": ["irregular"]})

    # keyed：城市命中
    s_city = DummySurcharge(id=2, name="深圳附加", condition_json=_s_dest_city("广东省", "深圳市"))

    final = select_surcharges_city_wins(matched=[s_flag, s_city], dest=dest, reasons=reasons)

    ids = [s.id for s in final]
    assert 1 in ids
    assert 2 in ids
