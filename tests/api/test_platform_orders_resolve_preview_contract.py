# tests/api/test_platform_orders_resolve_preview_contract.py
from __future__ import annotations

import json
import uuid
from typing import Optional, Tuple

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _ensure_store(session: AsyncSession, *, platform: str, store_code: str, name: str) -> int:
    plat = platform.strip().upper()
    sid = store_code.strip()
    await session.execute(
        text(
            """
            INSERT INTO stores(platform, store_code, store_name, active, created_at, updated_at)
            VALUES (:p, :s, :n, true, now(), now())
            ON CONFLICT (platform, store_code) DO UPDATE
              SET store_name = EXCLUDED.store_name,
                  active = true,
                  updated_at = now()
            """
        ),
        {"p": plat, "s": sid, "n": name},
    )
    row = (
        await session.execute(
            text("SELECT id FROM stores WHERE platform=:p AND store_code=:s LIMIT 1"),
            {"p": plat, "s": sid},
        )
    ).mappings().first()
    assert row and row.get("id") is not None
    return int(row["id"])


def _locator_from_fact(*, filled_code: Optional[str], line_no: int) -> Tuple[str, str]:
    fc = (filled_code or "").strip()
    if fc:
        return "FILLED_CODE", fc
    return "LINE_NO", str(int(line_no))


async def _insert_fact_line(
    session: AsyncSession,
    *,
    platform: str,
    store_code: str,
    store_id: int,
    ext_order_no: str,
    line_no: int,
    line_key: str,
    filled_code: Optional[str],
    qty: int,
    title: str,
    spec: str,
) -> None:
    locator_kind, locator_value = _locator_from_fact(
        filled_code=filled_code,
        line_no=int(line_no),
    )
    await session.execute(
        text(
            """
            INSERT INTO platform_order_lines(
              platform, store_code, store_id, ext_order_no,
              line_no, line_key,
              locator_kind, locator_value,
              filled_code, qty, title, spec,
              extras, raw_payload,
              created_at, updated_at
            ) VALUES (
              :platform, :store_code, :store_id, :ext_order_no,
              :line_no, :line_key,
              :locator_kind, :locator_value,
              :filled_code, :qty, :title, :spec,
              (:extras)::jsonb, (:raw_payload)::jsonb,
              now(), now()
            )
            ON CONFLICT (platform, store_code, ext_order_no, line_key)
            DO UPDATE SET
              store_id=EXCLUDED.store_id,
              locator_kind=EXCLUDED.locator_kind,
              locator_value=EXCLUDED.locator_value,
              filled_code=EXCLUDED.filled_code,
              qty=EXCLUDED.qty,
              title=EXCLUDED.title,
              spec=EXCLUDED.spec,
              extras=EXCLUDED.extras,
              raw_payload=EXCLUDED.raw_payload,
              updated_at=now()
            """
        ),
        {
            "platform": platform,
            "store_code": store_code,
            "store_id": int(store_id),
            "ext_order_no": ext_order_no,
            "line_no": int(line_no),
            "line_key": line_key,
            "locator_kind": locator_kind,
            "locator_value": locator_value,
            "filled_code": filled_code,
            "qty": int(qty),
            "title": title,
            "spec": spec,
            "extras": json.dumps({"source": "resolve-preview-test"}, ensure_ascii=False),
            "raw_payload": json.dumps({"source": "resolve-preview-test"}, ensure_ascii=False),
        },
    )


async def _create_published_fsku_with_component(
    session: AsyncSession,
    *,
    item_id: int,
    component_qty: int = 1,
) -> tuple[int, str]:
    uniq = uuid.uuid4().hex[:10]
    code = f"UT-PREVIEW-{uniq}"
    name = f"UT-PREVIEW-FSKU-{uniq}"

    row = (
        await session.execute(
            text(
                """
                INSERT INTO fskus(name, code, shape, status, published_at, created_at, updated_at)
                VALUES (:name, :code, 'bundle', 'published', now(), now(), now())
                RETURNING id
                """
            ),
            {"name": name, "code": code},
        )
    ).mappings().first()
    assert row and row.get("id") is not None
    fsku_id = int(row["id"])

    await session.execute(
        text(
            """
            INSERT INTO fsku_components(fsku_id, item_id, qty, role, created_at, updated_at)
            VALUES (:fid, :item_id, :qty, 'main', now(), now())
            """
        ),
        {"fid": fsku_id, "item_id": int(item_id), "qty": int(component_qty)},
    )
    return fsku_id, code


async def _orders_count(session: AsyncSession, *, platform: str, store_code: str, ext_order_no: str) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT count(*) AS n
                  FROM orders
                 WHERE platform = :p
                   AND store_code = :s
                   AND ext_order_no = :e
                """
            ),
            {"p": platform, "s": store_code, "e": ext_order_no},
        )
    ).mappings().first()
    return int(row["n"] if row and row.get("n") is not None else 0)


async def test_platform_orders_resolve_preview_expands_fsku_without_creating_order(client, session):
    platform = "PDD"
    store_code = "UT-PREVIEW-PDD"
    store_id = await _ensure_store(
        session,
        platform=platform,
        store_code=store_code,
        name="UT Preview PDD",
    )
    ext = f"UT-PREVIEW-OK-{uuid.uuid4().hex[:8]}"

    fsku_id, fsku_code = await _create_published_fsku_with_component(
        session,
        item_id=1,
        component_qty=2,
    )
    assert fsku_id > 0

    await _insert_fact_line(
        session,
        platform=platform,
        store_code=store_code,
        store_id=store_id,
        ext_order_no=ext,
        line_no=1,
        line_key=f"PSKU:{fsku_code}",
        filled_code=fsku_code,
        qty=3,
        title="只读解析预览商品",
        spec="默认规格",
    )
    await session.commit()

    before = await _orders_count(
        session,
        platform=platform,
        store_code=store_code,
        ext_order_no=ext,
    )

    resp = await client.post(
        "/oms/platform-orders/resolve-preview",
        json={"platform": platform, "store_id": store_id, "ext_order_no": ext},
    )
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["status"] == "OK"
    assert data["platform"] == platform
    assert data["store_id"] == store_id
    assert data["ext_order_no"] == ext
    assert data["facts_n"] == 1
    assert len(data["fact_lines"]) == 1
    assert data["fact_lines"][0]["filled_code"] == fsku_code
    assert data["fact_lines"][0]["qty"] == 3

    assert len(data["resolved"]) == 1
    resolved = data["resolved"][0]
    assert resolved["filled_code"] == fsku_code
    assert resolved["qty"] == 3
    assert int(resolved["fsku_id"]) == int(fsku_id)
    assert resolved["expanded_items"] == [
        {
            "item_id": 1,
            "component_qty": 2,
            "need_qty": 6,
            "role": "main",
        }
    ]

    assert data["unresolved"] == []
    assert data["item_qty_map"] == {"1": 6}
    assert data["item_qty_items"][0]["item_id"] == 1
    assert data["item_qty_items"][0]["qty"] == 6
    assert isinstance(data["item_qty_items"][0]["sku"], str)
    assert isinstance(data["item_qty_items"][0]["name"], str)

    after = await _orders_count(
        session,
        platform=platform,
        store_code=store_code,
        ext_order_no=ext,
    )
    assert after == before


async def test_platform_orders_resolve_preview_returns_unresolved_for_missing_filled_code(client, session):
    platform = "PDD"
    store_code = "UT-PREVIEW-PDD-MISSING"
    store_id = await _ensure_store(
        session,
        platform=platform,
        store_code=store_code,
        name="UT Preview Missing",
    )
    ext = f"UT-PREVIEW-MISSING-{uuid.uuid4().hex[:8]}"

    await _insert_fact_line(
        session,
        platform=platform,
        store_code=store_code,
        store_id=store_id,
        ext_order_no=ext,
        line_no=1,
        line_key="NO_PSKU:1",
        filled_code=None,
        qty=1,
        title="缺填写码商品",
        spec="默认规格",
    )
    await session.commit()

    resp = await client.post(
        "/oms/platform-orders/resolve-preview",
        json={"platform": platform, "store_id": store_id, "ext_order_no": ext},
    )
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["status"] == "UNRESOLVED"
    assert data["facts_n"] == 1
    assert data["resolved"] == []
    assert data["item_qty_map"] == {}
    assert data["item_qty_items"] == []
    assert len(data["unresolved"]) == 1
    assert data["unresolved"][0]["reason"] == "MISSING_FILLED_CODE"


async def test_platform_orders_resolve_preview_returns_not_found(client, session):
    platform = "PDD"
    store_code = "UT-PREVIEW-PDD-NOTFOUND"
    store_id = await _ensure_store(
        session,
        platform=platform,
        store_code=store_code,
        name="UT Preview NotFound",
    )
    await session.commit()

    resp = await client.post(
        "/oms/platform-orders/resolve-preview",
        json={
            "platform": platform,
            "store_id": store_id,
            "ext_order_no": f"UT-PREVIEW-NOTFOUND-{uuid.uuid4().hex[:8]}",
        },
    )
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["status"] == "NOT_FOUND"
    assert data["facts_n"] == 0
    assert data["fact_lines"] == []
    assert data["resolved"] == []
    assert data["item_qty_map"] == {}
    assert data["item_qty_items"] == []
    assert data["unresolved"][0]["reason"] == "FACTS_NOT_FOUND"
