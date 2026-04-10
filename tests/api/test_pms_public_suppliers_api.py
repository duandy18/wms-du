# tests/api/test_pms_public_suppliers_api.py
from __future__ import annotations

from urllib.parse import quote

import httpx
import pytest

pytestmark = pytest.mark.asyncio


async def test_public_suppliers_returns_basic_rows_without_contacts(
    client: httpx.AsyncClient,
) -> None:
    r = await client.get("/public/suppliers")
    assert r.status_code == 200, r.text

    data = r.json()
    assert isinstance(data, list)
    assert data, "base_seed 应至少存在一个供应商"

    row = data[0]
    assert {"id", "name", "code", "active"} <= set(row.keys())
    assert "contacts" not in row


async def test_public_suppliers_supports_active_and_q(
    client: httpx.AsyncClient,
) -> None:
    r = await client.get("/public/suppliers?active=true")
    assert r.status_code == 200, r.text

    rows = r.json()
    assert isinstance(rows, list)
    assert rows, "active=true 应至少返回一个合作中供应商"

    for row in rows:
        assert row["active"] is True

    sample = rows[0]
    source = str(sample.get("code") or sample.get("name") or "").strip()
    assert source

    q = source[:2] if len(source) >= 2 else source[:1]
    assert q

    rq = await client.get(f"/public/suppliers?active=true&q={quote(q)}")
    assert rq.status_code == 200, rq.text

    filtered = rq.json()
    assert isinstance(filtered, list)
    assert filtered

    q_lower = q.lower()
    for row in filtered:
        name = str(row.get("name") or "").lower()
        code = str(row.get("code") or "").lower()
        assert q_lower in name or q_lower in code
