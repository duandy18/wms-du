# tests/api/test_pms_sku_coding_api.py
from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from tests.api.pms_master_data_helpers import create_pms_brand, create_pms_category


def _suffix() -> str:
    return uuid4().hex[:4].upper()


async def _headers(client: httpx.AsyncClient) -> dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _create_brand(client: httpx.AsyncClient, headers: dict[str, str], *, name_cn: str, code: str) -> dict:
    return await create_pms_brand(client, headers, name_cn=name_cn, code=code)


async def _create_category(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    parent_id: int | None,
    level: int,
    product_kind: str,
    category_name: str,
    category_code: str,
    is_leaf: bool,
) -> dict:
    return await create_pms_category(
        client,
        headers,
        parent_id=parent_id,
        level=level,
        product_kind=product_kind,
        category_name=category_name,
        category_code=category_code,
        is_leaf=is_leaf,
    )




async def _attribute_def_id(client: httpx.AsyncClient, headers: dict[str, str], *, product_kind: str, code: str) -> int:
    r = await client.get(
        f"/pms/item-attribute-defs?product_kind={product_kind}&active_only=true",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    for row in rows:
        if row["code"] == code:
            return int(row["id"])
    raise AssertionError(f"attribute def not found: {product_kind}/{code}")


async def _create_attribute_option(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    attribute_def_id: int,
    option_name: str,
    option_code: str,
    sort_order: int,
) -> dict:
    r = await client.post(
        f"/pms/item-attribute-defs/{attribute_def_id}/options",
        json={"option_code": option_code, "option_name": option_name, "sort_order": sort_order},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_sku_coding_food_generate_contract(client: httpx.AsyncClient) -> None:
    headers = await _headers(client)
    sfx = _suffix()

    brand_code = f"KBK{sfx}"
    category_code = f"CF{sfx}"
    life_stage_code = f"ALS{sfx}"
    process_code = f"FM{sfx}"
    chicken_code = f"CHK{sfx}"
    salmon_code = f"SLM{sfx}"

    brand = await _create_brand(client, headers, name_cn=f"卡宾卡-UT-{sfx}", code=brand_code)

    root = await _create_category(
        client,
        headers,
        parent_id=None,
        level=1,
        product_kind="FOOD",
        category_name=f"宠物食品-UT-{sfx}",
        category_code=f"PF{sfx}",
        is_leaf=False,
    )
    mid = await _create_category(
        client,
        headers,
        parent_id=int(root["id"]),
        level=2,
        product_kind="FOOD",
        category_name=f"猫主食-UT-{sfx}",
        category_code=f"CATF{sfx}",
        is_leaf=False,
    )
    leaf = await _create_category(
        client,
        headers,
        parent_id=int(mid["id"]),
        level=3,
        product_kind="FOOD",
        category_name=f"干粮-UT-{sfx}",
        category_code=category_code,
        is_leaf=True,
    )

    life_stage_def_id = await _attribute_def_id(client, headers, product_kind="FOOD", code="LIFE_STAGE")
    process_def_id = await _attribute_def_id(client, headers, product_kind="FOOD", code="PROCESS")
    flavor_def_id = await _attribute_def_id(client, headers, product_kind="FOOD", code="FLAVOR")

    als = await _create_attribute_option(
        client,
        headers,
        attribute_def_id=life_stage_def_id,
        option_name=f"全期-UT-{sfx}",
        option_code=life_stage_code,
        sort_order=10,
    )
    fm = await _create_attribute_option(
        client,
        headers,
        attribute_def_id=process_def_id,
        option_name=f"鲜肉-UT-{sfx}",
        option_code=process_code,
        sort_order=10,
    )
    chkn = await _create_attribute_option(
        client,
        headers,
        attribute_def_id=flavor_def_id,
        option_name=f"鸡肉-UT-{sfx}",
        option_code=chicken_code,
        sort_order=10,
    )
    slmn = await _create_attribute_option(
        client,
        headers,
        attribute_def_id=flavor_def_id,
        option_name=f"三文鱼-UT-{sfx}",
        option_code=salmon_code,
        sort_order=20,
    )

    r = await client.post(
        "/pms/sku-coding/generate",
        json={
            "product_kind": "FOOD",
            "brand_id": int(brand["id"]),
            "category_id": int(leaf["id"]),
            "attribute_option_ids": {
                "LIFE_STAGE": [int(als["id"])],
                "PROCESS": [int(fm["id"])],
                "FLAVOR": [int(slmn["id"]), int(chkn["id"])],
            },
            "spec_text": "500g",
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["sku"] == f"SKU-{brand_code}-{category_code}-{life_stage_code}-{process_code}-{chicken_code}-{salmon_code}-500G"
    assert data["exists"] is False
    assert data["segments"][-1] == {"segment_key": "SPEC", "name_cn": "500g", "code": "500G"}


@pytest.mark.asyncio
async def test_sku_coding_supply_generate_contract(client: httpx.AsyncClient) -> None:
    headers = await _headers(client)
    sfx = _suffix()

    brand_code = f"XP{sfx}"
    category_code = f"SPW{sfx}"
    model_code = f"PRO{sfx}"
    color_code = f"WHT{sfx}"

    brand = await _create_brand(client, headers, name_cn=f"小佩-UT-{sfx}", code=brand_code)

    root = await _create_category(
        client,
        headers,
        parent_id=None,
        level=1,
        product_kind="SUPPLY",
        category_name=f"宠物用品-UT-{sfx}",
        category_code=f"PS{sfx}",
        is_leaf=False,
    )
    mid = await _create_category(
        client,
        headers,
        parent_id=int(root["id"]),
        level=2,
        product_kind="SUPPLY",
        category_name=f"喂食饮水-UT-{sfx}",
        category_code=f"FW{sfx}",
        is_leaf=False,
    )
    leaf = await _create_category(
        client,
        headers,
        parent_id=int(mid["id"]),
        level=3,
        product_kind="SUPPLY",
        category_name=f"智能饮水器-UT-{sfx}",
        category_code=category_code,
        is_leaf=True,
    )

    model_def_id = await _attribute_def_id(client, headers, product_kind="SUPPLY", code="MODEL")
    color_def_id = await _attribute_def_id(client, headers, product_kind="SUPPLY", code="COLOR")
    pro = await _create_attribute_option(
        client,
        headers,
        attribute_def_id=model_def_id,
        option_name=f"PRO-UT-{sfx}",
        option_code=model_code,
        sort_order=10,
    )
    wht = await _create_attribute_option(
        client,
        headers,
        attribute_def_id=color_def_id,
        option_name=f"白色-UT-{sfx}",
        option_code=color_code,
        sort_order=10,
    )

    r = await client.post(
        "/pms/sku-coding/generate",
        json={
            "product_kind": "SUPPLY",
            "brand_id": int(brand["id"]),
            "category_id": int(leaf["id"]),
            "attribute_option_ids": {
                "MODEL": [int(pro["id"])],
                "COLOR": [int(wht["id"])],
            },
            "spec_text": "2L",
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["sku"] == f"SKU-{brand_code}-{category_code}-{model_code}-2L-{color_code}"




@pytest.mark.asyncio
async def test_sku_coding_legacy_dictionary_routes_are_retired(client: httpx.AsyncClient) -> None:
    headers = await _headers(client)

    r_groups = await client.get("/pms/sku-coding/term-groups", headers=headers)
    assert r_groups.status_code == 404, r_groups.text

    r_terms = await client.get("/pms/sku-coding/terms", headers=headers)
    assert r_terms.status_code == 404, r_terms.text

    r_create = await client.post(
        "/pms/sku-coding/terms",
        json={"group_id": 1, "name_cn": "旧字典", "code": "OLD"},
        headers=headers,
    )
    assert r_create.status_code == 404, r_create.text
