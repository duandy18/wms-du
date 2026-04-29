# tests/api/test_pms_master_data_api.py
from __future__ import annotations

from uuid import uuid4

import httpx
import pytest


def _suffix() -> str:
    return uuid4().hex[:6].upper()


async def _headers(client: httpx.AsyncClient) -> dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_pms_brand_and_category_owner_contract(client: httpx.AsyncClient) -> None:
    headers = await _headers(client)
    sfx = _suffix()

    r_brand = await client.post(
        "/pms/brands",
        json={"name_cn": f"品牌治理-UT-{sfx}", "code": f"BR{sfx}", "sort_order": 10},
        headers=headers,
    )
    assert r_brand.status_code == 201, r_brand.text
    brand = r_brand.json()
    assert brand["name_cn"] == f"品牌治理-UT-{sfx}"
    assert brand["code"] == f"BR{sfx}"
    assert brand["is_active"] is True

    r_brand_patch = await client.patch(
        f"/pms/brands/{brand['id']}",
        json={"name_cn": f"品牌治理更新-UT-{sfx}", "code": f"BRX{sfx}", "remark": "updated"},
        headers=headers,
    )
    assert r_brand_patch.status_code == 200, r_brand_patch.text
    assert r_brand_patch.json()["name_cn"] == f"品牌治理更新-UT-{sfx}"
    assert r_brand_patch.json()["code"] == f"BRX{sfx}"

    r_disable = await client.post(f"/pms/brands/{brand['id']}/disable", headers=headers)
    assert r_disable.status_code == 200, r_disable.text
    assert r_disable.json()["is_active"] is False

    r_enable = await client.post(f"/pms/brands/{brand['id']}/enable", headers=headers)
    assert r_enable.status_code == 200, r_enable.text
    assert r_enable.json()["is_active"] is True

    r_category = await client.post(
        "/pms/categories",
        json={
            "parent_id": None,
            "level": 1,
            "product_kind": "OTHER",
            "category_name": f"分类治理-UT-{sfx}",
            "category_code": f"CAT{sfx}",
            "is_leaf": True,
        },
        headers=headers,
    )
    assert r_category.status_code == 201, r_category.text
    category = r_category.json()
    assert category["product_kind"] == "OTHER"
    assert category["category_code"] == f"CAT{sfx}"
    assert category["is_leaf"] is True

    r_category_patch = await client.patch(
        f"/pms/categories/{category['id']}",
        json={
            "category_name": f"分类治理更新-UT-{sfx}",
            "category_code": f"CATX{sfx}",
            "sort_order": 88,
        },
        headers=headers,
    )
    assert r_category_patch.status_code == 200, r_category_patch.text
    assert r_category_patch.json()["category_name"] == f"分类治理更新-UT-{sfx}"
    assert r_category_patch.json()["category_code"] == f"CATX{sfx}"
    assert r_category_patch.json()["path_code"] == f"CATX{sfx}"


@pytest.mark.asyncio
async def test_pms_attribute_template_options_and_item_values_contract(client: httpx.AsyncClient) -> None:
    headers = await _headers(client)
    sfx = _suffix()

    r_brand = await client.post(
        "/pms/brands",
        json={"name_cn": f"属性品牌-UT-{sfx}", "code": f"AB{sfx}"},
        headers=headers,
    )
    assert r_brand.status_code == 201, r_brand.text
    brand_id = int(r_brand.json()["id"])

    r_category = await client.post(
        "/pms/categories",
        json={
            "parent_id": None,
            "level": 1,
            "product_kind": "OTHER",
            "category_name": f"属性分类-UT-{sfx}",
            "category_code": f"AC{sfx}",
            "is_leaf": True,
        },
        headers=headers,
    )
    assert r_category.status_code == 201, r_category.text
    category_id = int(r_category.json()["id"])

    r_attr = await client.post(
        "/pms/item-attribute-defs",
        json={
            "code": f"COLOR_{sfx}",
            "name_cn": "颜色",
            "product_kind": "OTHER",
            "category_id": category_id,
            "value_type": "OPTION",
            "is_required": True,
            "is_filterable": True,
            "sort_order": 10,
        },
        headers=headers,
    )
    assert r_attr.status_code == 201, r_attr.text
    attr = r_attr.json()
    assert attr["code"] == f"COLOR_{sfx}"
    assert attr["value_type"] == "OPTION"

    r_option = await client.post(
        f"/pms/item-attribute-defs/{attr['id']}/options",
        json={"option_code": f"WHT{sfx}", "option_name": "白色", "sort_order": 10},
        headers=headers,
    )
    assert r_option.status_code == 201, r_option.text
    option = r_option.json()
    assert option["option_code"] == f"WHT{sfx}"

    r_item = await client.post(
        "/items",
        json={
            "sku": f"ATTR-ITEM-{sfx}",
            "name": f"属性商品-UT-{sfx}",
            "brand_id": brand_id,
            "category_id": category_id,
            "supplier_id": 1,
            "lot_source_policy": "SUPPLIER_ONLY",
            "expiry_policy": "NONE",
            "derivation_allowed": True,
            "uom_governance_enabled": False,
        },
        headers=headers,
    )
    assert r_item.status_code == 201, r_item.text
    item_id = int(r_item.json()["id"])
    assert r_item.json()["brand_id"] == brand_id
    assert r_item.json()["category_id"] == category_id
    assert r_item.json()["brand"] == f"属性品牌-UT-{sfx}"
    assert r_item.json()["category"] == f"属性分类-UT-{sfx}"

    r_values = await client.put(
        f"/items/{item_id}/attributes",
        json={"values": [{"attribute_def_id": int(attr["id"]), "value_option_id": int(option["id"])}]},
        headers=headers,
    )
    assert r_values.status_code == 200, r_values.text
    values = r_values.json()["data"]
    assert len(values) == 1
    assert values[0]["item_id"] == item_id
    assert values[0]["attribute_def_id"] == int(attr["id"])
    assert values[0]["value_option_id"] == int(option["id"])
    assert values[0]["value_option_code_snapshot"] == f"WHT{sfx}"

    r_get = await client.get(f"/items/{item_id}/attributes", headers=headers)
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["data"][0]["value_option_code_snapshot"] == f"WHT{sfx}"
