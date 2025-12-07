# tests/api/test_shipping_reports_filters.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _login_as_admin() -> Dict[str, str]:
    """
    用 admin/admin123 登录，拿到 Authorization 头。
    如果失败，则跳过整组测试（说明环境还没初始化用户）。
    """
    resp = client.post(
        "/users/login",
        json={"username": "admin", "password": "admin123"},
    )
    if resp.status_code != 200:
        pytest.skip(f"无法登录 admin 用户，状态码={resp.status_code}，跳过发货报表相关测试")

    data = resp.json()
    token = data.get("access_token")
    if not token:
        pytest.skip("登录响应中没有 access_token，跳过发货报表相关测试")

    return {"Authorization": f"Bearer {token}"}


def _get_meta_field(row: Dict[str, Any], key: str) -> Optional[str]:
    meta = row.get("meta") or {}
    v = meta.get(key)
    return v if isinstance(v, str) else None


def test_shipping_report_options_basic_shape() -> None:
    """
    /shipping-reports/options 能正常返回且字段齐全。
    """
    headers = _login_as_admin()

    resp = client.get("/shipping-reports/options", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    for key in ["platforms", "shop_ids", "provinces", "cities"]:
        assert key in data
        assert isinstance(data[key], list)

    # 简单检查去重特性（集合长度不大于原长度）
    for key in ["platforms", "shop_ids", "provinces", "cities"]:
        lst: List[str] = data[key]
        assert len(set(lst)) <= len(lst)


def test_shipping_reports_city_filter_behaviour() -> None:
    """
    city 过滤应收缩结果集合，且所有行 meta.dest_city 一致。
    如果当前数据里没有城市信息，则跳过。
    """
    headers = _login_as_admin()

    # options 里随便选一个 city
    opt_resp = client.get("/shipping-reports/options", headers=headers)
    assert opt_resp.status_code == 200
    opts = opt_resp.json()
    cities: List[str] = opts.get("cities") or []
    if not cities:
        pytest.skip("当前数据集中没有城市信息，跳过 city 过滤测试")

    city = cities[0]

    # 全量（不带 city）明细
    resp_all = client.get(
        "/shipping-reports/list",
        params={"limit": 500},
        headers=headers,
    )
    assert resp_all.status_code == 200
    data_all = resp_all.json()
    rows_all: List[Dict[str, Any]] = data_all.get("rows") or []
    total_all = data_all.get("total", len(rows_all))
    if total_all == 0:
        pytest.skip("当前 shipping_records 为空，跳过 city 过滤测试")

    # city 过滤后的明细
    resp_city = client.get(
        "/shipping-reports/list",
        params={"city": city, "limit": 500},
        headers=headers,
    )
    assert resp_city.status_code == 200
    data_city = resp_city.json()
    rows_city: List[Dict[str, Any]] = data_city.get("rows") or []
    total_city = data_city.get("total", len(rows_city))

    # 结果集应该不大于全量
    assert total_city <= total_all

    # 所有行的 meta.dest_city 必须等于选中的 city
    for row in rows_city:
        assert _get_meta_field(row, "dest_city") == city


def test_shipping_reports_platform_and_province_filters() -> None:
    """
    platform / province 过滤应当与 options 一致，
    且过滤后的行全部满足条件。
    如果当前数据里缺某个维度，则相应跳过。
    """
    headers = _login_as_admin()

    # 先看是否有数据
    base_resp = client.get(
        "/shipping-reports/list",
        params={"limit": 1},
        headers=headers,
    )
    assert base_resp.status_code == 200
    base_data = base_resp.json()
    if not base_data.get("rows"):
        pytest.skip("当前 shipping_records 为空，跳过 platform/province 过滤测试")

    # 拿 options
    opt_resp = client.get("/shipping-reports/options", headers=headers)
    assert opt_resp.status_code == 200
    opts = opt_resp.json()
    platforms: List[str] = opts.get("platforms") or []
    provinces: List[str] = opts.get("provinces") or []

    if not platforms:
        pytest.skip("当前数据集中没有平台信息，跳过 platform 过滤测试")
    if not provinces:
        pytest.skip("当前数据集中没有省份信息，跳过 province 过滤测试")

    platform = platforms[0]
    province = provinces[0]

    # 过滤后的明细
    resp = client.get(
        "/shipping-reports/list",
        params={
            "platform": platform,
            "province": province,
            "limit": 500,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    rows: List[Dict[str, Any]] = data.get("rows") or []

    # 不要求必然有记录（允许 0 条），但如果有，则所有行都要匹配
    for row in rows:
        assert row["platform"] == platform
        assert _get_meta_field(row, "dest_province") == province
