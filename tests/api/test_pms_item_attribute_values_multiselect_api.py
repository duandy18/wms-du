# tests/api/test_pms_item_attribute_values_multiselect_api.py
from __future__ import annotations

from uuid import uuid4

import httpx
import pytest


async def _headers(client: httpx.AsyncClient) -> dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _first_item_id(client: httpx.AsyncClient, headers: dict[str, str]) -> int:
    r = await client.get("/items", headers=headers)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert rows, rows
    return int(rows[0]["id"])


async def _attribute_def(client: httpx.AsyncClient, headers: dict[str, str], *, product_kind: str, code: str) -> dict:
    r = await client.get(
        f"/pms/item-attribute-defs?product_kind={product_kind}&active_only=true",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    for row in r.json()["data"]:
        if row["code"] == code:
            return row
    raise AssertionError(f"attribute def not found: {product_kind}/{code}")


async def _create_option(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    attribute_def_id: int,
    option_code: str,
    option_name: str,
) -> dict:
    r = await client.post(
        f"/pms/item-attribute-defs/{attribute_def_id}/options",
        json={"option_code": option_code, "option_name": option_name, "sort_order": 999},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_item_attribute_option_multi_values_are_saved_and_returned(client: httpx.AsyncClient) -> None:
    headers = await _headers(client)
    item_id = await _first_item_id(client, headers)

    flavor = await _attribute_def(client, headers, product_kind="FOOD", code="FLAVOR")
    suffix = uuid4().hex[:6].upper()

    chicken = await _create_option(
        client,
        headers,
        attribute_def_id=int(flavor["id"]),
        option_code=f"CHK{suffix}",
        option_name=f"鸡肉-{suffix}",
    )
    salmon = await _create_option(
        client,
        headers,
        attribute_def_id=int(flavor["id"]),
        option_code=f"SLM{suffix}",
        option_name=f"三文鱼-{suffix}",
    )

    r = await client.put(
        f"/items/{item_id}/attributes",
        json={
            "values": [
                {
                    "attribute_def_id": int(flavor["id"]),
                    "value_option_ids": [int(chicken["id"]), int(salmon["id"])],
                }
            ]
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text

    rows = r.json()["data"]
    assert len(rows) == 1
    assert rows[0]["attribute_def_id"] == int(flavor["id"])
    assert set(rows[0]["value_option_ids"]) == {int(chicken["id"]), int(salmon["id"])}
    assert {f"CHK{suffix}", f"SLM{suffix}"} <= set(rows[0]["value_option_code_snapshots"])

    r_get = await client.get(f"/items/{item_id}/attributes", headers=headers)
    assert r_get.status_code == 200, r_get.text
    got = r_get.json()["data"][0]
    assert set(got["value_option_ids"]) == {int(chicken["id"]), int(salmon["id"])}


@pytest.mark.asyncio
async def test_item_attribute_single_rejects_multiple_options(client: httpx.AsyncClient) -> None:
    headers = await _headers(client)
    item_id = await _first_item_id(client, headers)

    life_stage = await _attribute_def(client, headers, product_kind="FOOD", code="LIFE_STAGE")
    suffix = uuid4().hex[:6].upper()

    a = await _create_option(
        client,
        headers,
        attribute_def_id=int(life_stage["id"]),
        option_code=f"A{suffix}",
        option_name=f"阶段A-{suffix}",
    )
    b = await _create_option(
        client,
        headers,
        attribute_def_id=int(life_stage["id"]),
        option_code=f"B{suffix}",
        option_name=f"阶段B-{suffix}",
    )

    r = await client.put(
        f"/items/{item_id}/attributes",
        json={
            "values": [
                {
                    "attribute_def_id": int(life_stage["id"]),
                    "value_option_ids": [int(a["id"]), int(b["id"])],
                }
            ]
        },
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert "最多只能选择一个" in r.text


@pytest.mark.asyncio
async def test_item_attribute_scalar_values_still_work(client: httpx.AsyncClient) -> None:
    headers = await _headers(client)
    item_id = await _first_item_id(client, headers)

    origin = await _attribute_def(client, headers, product_kind="COMMON", code="ORIGIN")

    r = await client.put(
        f"/items/{item_id}/attributes",
        json={
            "values": [
                {
                    "attribute_def_id": int(origin["id"]),
                    "value_text": "山东",
                }
            ]
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text

    rows = r.json()["data"]
    assert rows[0]["attribute_def_id"] == int(origin["id"])
    assert rows[0]["value_text"] == "山东"
    assert rows[0]["value_option_ids"] == []
