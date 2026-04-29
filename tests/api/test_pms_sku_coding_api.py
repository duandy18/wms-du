# tests/api/test_pms_sku_coding_api.py
from __future__ import annotations

from uuid import uuid4

import httpx
import pytest


def _suffix() -> str:
    return uuid4().hex[:4].upper()


async def _headers(client: httpx.AsyncClient) -> dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _create_brand(client: httpx.AsyncClient, headers: dict[str, str], *, name_cn: str, code: str) -> dict:
    r = await client.post("/pms/sku-coding/brands", json={"name_cn": name_cn, "code": code}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


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
    r = await client.post(
        "/pms/sku-coding/business-categories",
        json={
            "parent_id": parent_id,
            "level": level,
            "product_kind": product_kind,
            "category_name": category_name,
            "category_code": category_code,
            "is_leaf": is_leaf,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _group_id(client: httpx.AsyncClient, headers: dict[str, str], *, product_kind: str, group_code: str) -> int:
    r = await client.get(f"/pms/sku-coding/term-groups?product_kind={product_kind}", headers=headers)
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    for row in rows:
        if row["group_code"] == group_code:
            return int(row["id"])
    raise AssertionError(f"group not found: {product_kind}/{group_code}")


async def _create_term(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    group_id: int,
    name_cn: str,
    code: str,
    sort_order: int,
) -> dict:
    r = await client.post(
        "/pms/sku-coding/terms",
        json={"group_id": group_id, "name_cn": name_cn, "code": code, "sort_order": sort_order},
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

    life_stage_gid = await _group_id(client, headers, product_kind="FOOD", group_code="LIFE_STAGE")
    process_gid = await _group_id(client, headers, product_kind="FOOD", group_code="PROCESS")
    flavor_gid = await _group_id(client, headers, product_kind="FOOD", group_code="FLAVOR")

    als = await _create_term(
        client,
        headers,
        group_id=life_stage_gid,
        name_cn=f"全期-UT-{sfx}",
        code=life_stage_code,
        sort_order=10,
    )
    fm = await _create_term(
        client,
        headers,
        group_id=process_gid,
        name_cn=f"鲜肉-UT-{sfx}",
        code=process_code,
        sort_order=10,
    )
    chkn = await _create_term(
        client,
        headers,
        group_id=flavor_gid,
        name_cn=f"鸡肉-UT-{sfx}",
        code=chicken_code,
        sort_order=10,
    )
    slmn = await _create_term(
        client,
        headers,
        group_id=flavor_gid,
        name_cn=f"三文鱼-UT-{sfx}",
        code=salmon_code,
        sort_order=20,
    )

    r = await client.post(
        "/pms/sku-coding/generate",
        json={
            "product_kind": "FOOD",
            "brand_id": int(brand["id"]),
            "category_id": int(leaf["id"]),
            "term_ids": {
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

    model_gid = await _group_id(client, headers, product_kind="SUPPLY", group_code="MODEL")
    color_gid = await _group_id(client, headers, product_kind="SUPPLY", group_code="COLOR")
    pro = await _create_term(
        client,
        headers,
        group_id=model_gid,
        name_cn=f"PRO-UT-{sfx}",
        code=model_code,
        sort_order=10,
    )
    wht = await _create_term(
        client,
        headers,
        group_id=color_gid,
        name_cn=f"白色-UT-{sfx}",
        code=color_code,
        sort_order=10,
    )

    r = await client.post(
        "/pms/sku-coding/generate",
        json={
            "product_kind": "SUPPLY",
            "brand_id": int(brand["id"]),
            "category_id": int(leaf["id"]),
            "term_ids": {
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
async def test_sku_coding_dictionary_update_and_toggle_contract(client: httpx.AsyncClient) -> None:
    headers = await _headers(client)
    sfx = _suffix()

    brand = await _create_brand(client, headers, name_cn=f"品牌编辑-UT-{sfx}", code=f"BR{sfx}")

    r_brand_patch = await client.patch(
        f"/pms/sku-coding/brands/{brand['id']}",
        json={
            "name_cn": f"品牌编辑后-UT-{sfx}",
            "code": f"BRX{sfx}",
            "sort_order": 77,
            "remark": "updated brand",
        },
        headers=headers,
    )
    assert r_brand_patch.status_code == 200, r_brand_patch.text
    brand_updated = r_brand_patch.json()
    assert brand_updated["name_cn"] == f"品牌编辑后-UT-{sfx}"
    assert brand_updated["code"] == f"BRX{sfx}"
    assert brand_updated["sort_order"] == 77
    assert brand_updated["remark"] == "updated brand"

    r_brand_disable = await client.post(f"/pms/sku-coding/brands/{brand['id']}/disable", headers=headers)
    assert r_brand_disable.status_code == 200, r_brand_disable.text
    assert r_brand_disable.json()["is_active"] is False

    r_brand_enable = await client.post(f"/pms/sku-coding/brands/{brand['id']}/enable", headers=headers)
    assert r_brand_enable.status_code == 200, r_brand_enable.text
    assert r_brand_enable.json()["is_active"] is True

    category = await _create_category(
        client,
        headers,
        parent_id=None,
        level=1,
        product_kind="FOOD",
        category_name=f"分类编辑-UT-{sfx}",
        category_code=f"CAT{sfx}",
        is_leaf=False,
    )

    r_category_patch = await client.patch(
        f"/pms/sku-coding/business-categories/{category['id']}",
        json={
            "category_name": f"分类编辑后-UT-{sfx}",
            "category_code": f"CATX{sfx}",
            "is_leaf": True,
            "sort_order": 88,
            "remark": "updated category",
        },
        headers=headers,
    )
    assert r_category_patch.status_code == 200, r_category_patch.text
    category_updated = r_category_patch.json()
    assert category_updated["category_name"] == f"分类编辑后-UT-{sfx}"
    assert category_updated["category_code"] == f"CATX{sfx}"
    assert category_updated["path_code"] == f"CATX{sfx}"
    assert category_updated["is_leaf"] is True
    assert category_updated["sort_order"] == 88
    assert category_updated["remark"] == "updated category"

    r_category_disable = await client.post(
        f"/pms/sku-coding/business-categories/{category['id']}/disable",
        headers=headers,
    )
    assert r_category_disable.status_code == 200, r_category_disable.text
    assert r_category_disable.json()["is_active"] is False

    r_category_enable = await client.post(
        f"/pms/sku-coding/business-categories/{category['id']}/enable",
        headers=headers,
    )
    assert r_category_enable.status_code == 200, r_category_enable.text
    assert r_category_enable.json()["is_active"] is True

    flavor_gid = await _group_id(client, headers, product_kind="FOOD", group_code="FLAVOR")
    term = await _create_term(
        client,
        headers,
        group_id=flavor_gid,
        name_cn=f"口味编辑-UT-{sfx}",
        code=f"FLV{sfx}",
        sort_order=10,
    )

    r_term_patch = await client.patch(
        f"/pms/sku-coding/terms/{term['id']}",
        json={
            "name_cn": f"口味编辑后-UT-{sfx}",
            "code": f"FLVX{sfx}",
            "sort_order": 99,
            "remark": "updated term",
        },
        headers=headers,
    )
    assert r_term_patch.status_code == 200, r_term_patch.text
    term_updated = r_term_patch.json()
    assert term_updated["name_cn"] == f"口味编辑后-UT-{sfx}"
    assert term_updated["code"] == f"FLVX{sfx}"
    assert term_updated["sort_order"] == 99
    assert term_updated["remark"] == "updated term"

    r_term_disable = await client.post(f"/pms/sku-coding/terms/{term['id']}/disable", headers=headers)
    assert r_term_disable.status_code == 200, r_term_disable.text
    assert r_term_disable.json()["is_active"] is False

    r_term_enable = await client.post(f"/pms/sku-coding/terms/{term['id']}/enable", headers=headers)
    assert r_term_enable.status_code == 200, r_term_enable.text
    assert r_term_enable.json()["is_active"] is True
