# tests/api/test_platform_orders_replay_contract.py
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.main import app


@pytest.fixture
async def db_session() -> AsyncSession:
    async for session in get_session():
        try:
            yield session
        finally:
            await session.close()


@pytest.fixture
async def async_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def _ensure_store(session: AsyncSession, *, platform: str, shop_id: str, name: str) -> int:
    plat = platform.strip().upper()
    sid = shop_id.strip()
    await session.execute(
        text(
            """
            INSERT INTO stores(platform, shop_id, name, active, created_at, updated_at)
            VALUES (:p, :s, :n, true, now(), now())
            ON CONFLICT (platform, shop_id) DO UPDATE
              SET name = EXCLUDED.name,
                  updated_at = now();
            """
        ),
        {"p": plat, "s": sid, "n": name},
    )
    row = (
        (
            await session.execute(
                text("SELECT id FROM stores WHERE platform=:p AND shop_id=:s LIMIT 1"),
                {"p": plat, "s": sid},
            )
        )
        .mappings()
        .first()
    )
    assert row and row.get("id") is not None
    return int(row["id"])


async def _insert_fact_line(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    store_id: int,
    ext_order_no: str,
    line_no: int,
    line_key: str,
    platform_sku_id: Optional[str],
    qty: int,
    title: str,
    spec: str,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO platform_order_lines(
              platform, shop_id, store_id, ext_order_no,
              line_no, line_key,
              platform_sku_id, qty, title, spec,
              extras, raw_payload,
              created_at, updated_at
            ) VALUES (
              :platform, :shop_id, :store_id, :ext_order_no,
              :line_no, :line_key,
              :platform_sku_id, :qty, :title, :spec,
              (:extras)::jsonb, (:raw_payload)::jsonb,
              now(), now()
            )
            ON CONFLICT (platform, shop_id, ext_order_no, line_key)
            DO UPDATE SET
              store_id=EXCLUDED.store_id,
              platform_sku_id=EXCLUDED.platform_sku_id,
              qty=EXCLUDED.qty,
              title=EXCLUDED.title,
              spec=EXCLUDED.spec,
              extras=EXCLUDED.extras,
              raw_payload=EXCLUDED.raw_payload,
              updated_at=now();
            """
        ),
        {
            "platform": platform,
            "shop_id": shop_id,
            "store_id": int(store_id),
            "ext_order_no": ext_order_no,
            "line_no": int(line_no),
            "line_key": line_key,
            "platform_sku_id": platform_sku_id,
            "qty": int(qty),
            "title": title,
            "spec": spec,
            "extras": json.dumps({}, ensure_ascii=False),
            "raw_payload": json.dumps({}, ensure_ascii=False),
        },
    )


async def _create_published_fsku_with_component(session: AsyncSession, *, item_id: int) -> int:
    uniq = uuid.uuid4().hex[:10]
    code = f"UT-REPLAY-{uniq}"
    name = f"UT-REPLAY-FSKU-{uniq}"

    row = (
        (
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
        )
        .mappings()
        .first()
    )
    assert row and row.get("id") is not None
    fsku_id = int(row["id"])

    await session.execute(
        text(
            """
            INSERT INTO fsku_components(fsku_id, item_id, qty, role, created_at, updated_at)
            VALUES (:fid, :item_id, 1, 'main', now(), now())
            """
        ),
        {"fid": fsku_id, "item_id": int(item_id)},
    )
    return fsku_id


async def _upsert_current_binding(
    session: AsyncSession,
    *,
    platform: str,
    store_id: int,
    platform_sku_id: str,
    fsku_id: int,
) -> None:
    await session.execute(
        text(
            """
            UPDATE platform_sku_bindings
               SET effective_to = now()
             WHERE platform = :p
               AND store_id = :sid
               AND platform_sku_id = :psku
               AND effective_to IS NULL;
            """
        ),
        {"p": platform, "sid": int(store_id), "psku": platform_sku_id},
    )

    await session.execute(
        text(
            """
            INSERT INTO platform_sku_bindings(
              platform, store_id, platform_sku_id,
              fsku_id, item_id,
              effective_from, effective_to,
              reason, created_at
            )
            VALUES (
              :p, :sid, :psku,
              :fid, NULL,
              now(), NULL,
              'UT replay', now()
            );
            """
        ),
        {"p": platform, "sid": int(store_id), "psku": platform_sku_id, "fid": int(fsku_id)},
    )


async def _orders_count(session: AsyncSession, *, platform: str, shop_id: str, ext_order_no: str) -> int:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT count(*) AS n
                      FROM orders
                     WHERE platform = :p
                       AND shop_id = :s
                       AND ext_order_no = :e
                    """
                ),
                {"p": platform, "s": shop_id, "e": ext_order_no},
            )
        )
        .mappings()
        .first()
    )
    return int(row["n"] if row and row.get("n") is not None else 0)


@pytest.mark.asyncio
async def test_replay_no_psku_returns_unresolved_and_does_not_create_order(
    async_client: AsyncClient,
    db_session: AsyncSession,
    _db_clean_and_seed,
) -> None:
    platform = "DEMO"
    shop_id = "1"
    store_id = await _ensure_store(db_session, platform=platform, shop_id=shop_id, name="DEMO-1")

    ext = f"UT-NO-PSKU-{uuid.uuid4().hex[:8]}"

    await _insert_fact_line(
        db_session,
        platform=platform,
        shop_id=shop_id,
        store_id=store_id,
        ext_order_no=ext,
        line_no=1,
        line_key="NO_PSKU:1",
        platform_sku_id=None,
        qty=1,
        title="只有标题没有PSKU",
        spec="颜色:黑",
    )
    await db_session.commit()

    n0 = await _orders_count(db_session, platform=platform, shop_id=shop_id, ext_order_no=ext)

    resp = await async_client.post(
        "/platform-orders/replay",
        json={"platform": platform, "store_id": store_id, "ext_order_no": ext},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["status"] == "UNRESOLVED"
    assert data["platform"] == platform
    assert data["store_id"] == store_id
    assert data["ext_order_no"] == ext
    assert data["facts_n"] == 1
    assert isinstance(data.get("unresolved") or [], list)
    assert len(data["unresolved"]) >= 1
    assert data["unresolved"][0].get("reason") == "MISSING_PSKU"

    n1 = await _orders_count(db_session, platform=platform, shop_id=shop_id, ext_order_no=ext)
    assert n1 == n0, f"orders should not be created on UNRESOLVED, before={n0}, after={n1}"


@pytest.mark.asyncio
async def test_replay_with_binding_is_idempotent(
    async_client: AsyncClient,
    db_session: AsyncSession,
    _db_clean_and_seed,
) -> None:
    platform = "DEMO"
    shop_id = "1"
    store_id = await _ensure_store(db_session, platform=platform, shop_id=shop_id, name="DEMO-1")

    psku = f"PSKU-UT-REPLAY-{uuid.uuid4().hex[:8]}"
    ext = f"UT-REPLAY-OK-{uuid.uuid4().hex[:8]}"

    # published fsku + component(item_id=1)
    fsku_id = await _create_published_fsku_with_component(db_session, item_id=1)
    await _upsert_current_binding(db_session, platform=platform, store_id=store_id, platform_sku_id=psku, fsku_id=fsku_id)

    await _insert_fact_line(
        db_session,
        platform=platform,
        shop_id=shop_id,
        store_id=store_id,
        ext_order_no=ext,
        line_no=1,
        line_key=f"PSKU:{psku}",
        platform_sku_id=psku,
        qty=2,
        title="UT-REPLAY-TITLE",
        spec="UT-SPEC",
    )
    await db_session.commit()

    # replay #1
    resp1 = await async_client.post(
        "/platform-orders/replay",
        json={"platform": platform, "store_id": store_id, "ext_order_no": ext},
    )
    assert resp1.status_code == 200, resp1.text
    d1 = resp1.json()
    assert d1["platform"] == platform
    assert d1["store_id"] == store_id
    assert d1["ext_order_no"] == ext
    assert d1["facts_n"] == 1
    assert d1.get("id") is not None
    assert d1["status"] in ("OK", "FULFILLMENT_BLOCKED", "IDEMPOTENT")

    order_id_1 = int(d1["id"])

    # replay #2 (must be idempotent)
    resp2 = await async_client.post(
        "/platform-orders/replay",
        json={"platform": platform, "store_id": store_id, "ext_order_no": ext},
    )
    assert resp2.status_code == 200, resp2.text
    d2 = resp2.json()
    assert d2.get("id") is not None
    assert int(d2["id"]) == order_id_1
    assert d2["status"] == "IDEMPOTENT"
