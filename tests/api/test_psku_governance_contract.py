# tests/api/test_psku_governance_contract.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_psku_governance_contract_shape():
    client = TestClient(app)

    r = client.get("/psku-governance?limit=10&offset=0")
    assert r.status_code in (200, 401, 403)

    if r.status_code != 200:
        return

    j = r.json()
    assert isinstance(j, dict)
    assert isinstance(j.get("items"), list)
    assert isinstance(j.get("total"), int)
    assert isinstance(j.get("limit"), int)
    assert isinstance(j.get("offset"), int)

    for it in j["items"]:
        assert isinstance(it, dict)
        assert isinstance(it.get("platform"), str) and it["platform"]
        assert isinstance(it.get("store_id"), int) and it["store_id"] >= 1
        assert isinstance(it.get("platform_sku_id"), str) and it["platform_sku_id"]

        gov = it.get("governance")
        assert isinstance(gov, dict)
        assert gov.get("status") in ("BOUND", "UNBOUND", "LEGACY_ITEM_BOUND")

        ah = it.get("action_hint")
        assert isinstance(ah, dict)
        assert ah.get("action") in ("OK", "BIND_FIRST", "MIGRATE_LEGACY")
        req = ah.get("required")
        assert isinstance(req, list)
        for x in req:
            assert x in ("fsku_id", "binding_id", "to_fsku_id")

        # bind_ctx：只在 BIND_FIRST 可能出现（允许为空）
        if ah.get("action") == "BIND_FIRST":
            ctx = it.get("bind_ctx")
            assert ctx is None or (isinstance(ctx, dict) and isinstance(ctx.get("suggest_q"), str) and isinstance(ctx.get("suggest_fsku_query"), str))

        cids = it.get("component_item_ids")
        assert isinstance(cids, list)
        for x in cids:
            assert isinstance(x, int)


def test_psku_governance_accepts_status_filter():
    client = TestClient(app)

    for st in ("BOUND", "UNBOUND", "LEGACY_ITEM_BOUND"):
        r = client.get(f"/psku-governance?status={st}&limit=5&offset=0")
        assert r.status_code in (200, 401, 403)
        if r.status_code != 200:
            return

        j = r.json()
        assert isinstance(j, dict)
        assert isinstance(j.get("items"), list)

        for it in j["items"]:
            gov = it.get("governance")
            assert isinstance(gov, dict)
            assert gov.get("status") == st


def test_psku_governance_accepts_action_filter():
    client = TestClient(app)

    for act in ("OK", "BIND_FIRST", "MIGRATE_LEGACY"):
        r = client.get(f"/psku-governance?action={act}&limit=5&offset=0")
        assert r.status_code in (200, 401, 403)
        if r.status_code != 200:
            return

        j = r.json()
        assert isinstance(j, dict)
        assert isinstance(j.get("items"), list)

        for it in j["items"]:
            ah = it.get("action_hint")
            assert isinstance(ah, dict)
            assert ah.get("action") == act
