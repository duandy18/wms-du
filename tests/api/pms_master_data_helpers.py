# tests/api/pms_master_data_helpers.py
from __future__ import annotations

from uuid import uuid4

import httpx


def _suffix() -> str:
    return uuid4().hex[:8].upper()


async def create_pms_brand(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    name_cn: str | None = None,
    code: str | None = None,
) -> dict:
    sfx = _suffix()
    payload = {
        "name_cn": name_cn or f"品牌-UT-{sfx}",
        "code": code or f"BR{sfx[:10]}",
    }
    r = await client.post("/pms/brands", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def create_pms_category(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    parent_id: int | None = None,
    level: int = 1,
    product_kind: str = "OTHER",
    category_name: str | None = None,
    category_code: str | None = None,
    is_leaf: bool = True,
) -> dict:
    sfx = _suffix()
    payload = {
        "parent_id": parent_id,
        "level": level,
        "product_kind": product_kind,
        "category_name": category_name or f"分类-UT-{sfx}",
        "category_code": category_code or f"CAT{sfx[:10]}",
        "is_leaf": is_leaf,
    }
    r = await client.post("/pms/categories", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def create_pms_brand_and_category(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    brand_name: str | None = None,
    category_name: str | None = None,
    product_kind: str = "OTHER",
) -> dict[str, int]:
    brand = await create_pms_brand(client, headers, name_cn=brand_name)
    category = await create_pms_category(
        client,
        headers,
        product_kind=product_kind,
        category_name=category_name,
        is_leaf=True,
    )
    return {
        "brand_id": int(brand["id"]),
        "category_id": int(category["id"]),
    }
