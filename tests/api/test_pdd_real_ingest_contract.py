from __future__ import annotations

import pytest

from app.platform_order_ingestion.pdd import router_ingest as pdd_router_ingest
from app.platform_order_ingestion.pdd.service_ingest import (
    PddOrderIngestPageResult,
    PddOrderIngestRowResult,
)

pytestmark = pytest.mark.asyncio


async def test_post_store_pdd_orders_ingest_returns_page_result(client, session, monkeypatch):
    captured = {}

    async def _fake_ingest_order_page(self, *, session, params):
        captured["store_id"] = params.store_id
        captured["start_confirm_at"] = params.start_confirm_at
        captured["end_confirm_at"] = params.end_confirm_at
        captured["order_status"] = params.order_status
        captured["page"] = params.page
        captured["page_size"] = params.page_size

        return PddOrderIngestPageResult(
            store_id=123,
            store_code="pdd-store-123",
            page=1,
            page_size=50,
            orders_count=2,
            success_count=1,
            failed_count=1,
            has_more=False,
            start_confirm_at="2026-03-29 00:00:00",
            end_confirm_at="2026-03-29 23:59:59",
            rows=[
                PddOrderIngestRowResult(
                    order_sn="PDD-ORDER-001",
                    pdd_order_id=101,
                    status="OK",
                    error=None,
                ),
                PddOrderIngestRowResult(
                    order_sn="PDD-ORDER-002",
                    pdd_order_id=None,
                    status="FAILED",
                    error="detail_failed: boom",
                ),
            ],
        )

    monkeypatch.setattr(
        pdd_router_ingest.PddOrderIngestService,
        "ingest_order_page",
        _fake_ingest_order_page,
    )

    resp = await client.post(
        "/oms/stores/123/pdd/orders/ingest",
        json={
            "start_confirm_at": "2026-03-29 00:00:00",
            "end_confirm_at": "2026-03-29 23:59:59",
            "order_status": 1,
            "page": 1,
            "page_size": 50,
        },
    )
    assert resp.status_code == 200, resp.text

    assert captured == {
        "store_id": 123,
        "start_confirm_at": "2026-03-29 00:00:00",
        "end_confirm_at": "2026-03-29 23:59:59",
        "order_status": 1,
        "page": 1,
        "page_size": 50,
    }

    body = resp.json()
    assert body["ok"] is True

    data = body["data"]
    assert data["platform"] == "pdd"
    assert data["store_id"] == 123
    assert data["store_code"] == "pdd-store-123"
    assert data["page"] == 1
    assert data["page_size"] == 50
    assert data["orders_count"] == 2
    assert data["success_count"] == 1
    assert data["failed_count"] == 1
    assert data["has_more"] is False
    assert data["start_confirm_at"] == "2026-03-29 00:00:00"
    assert data["end_confirm_at"] == "2026-03-29 23:59:59"

    assert len(data["rows"]) == 2
    assert data["rows"][0]["order_sn"] == "PDD-ORDER-001"
    assert data["rows"][0]["pdd_order_id"] == 101
    assert data["rows"][0]["status"] == "OK"
    assert data["rows"][0]["error"] is None

    assert data["rows"][1]["order_sn"] == "PDD-ORDER-002"
    assert data["rows"][1]["pdd_order_id"] is None
    assert data["rows"][1]["status"] == "FAILED"
    assert data["rows"][1]["error"] == "detail_failed: boom"


async def test_post_store_pdd_orders_ingest_returns_400_on_service_error(client, session, monkeypatch):
    async def _fake_ingest_order_page(self, *, session, params):
        raise pdd_router_ingest.PddOrderIngestServiceError("pdd pull failed: credential expired")

    monkeypatch.setattr(
        pdd_router_ingest.PddOrderIngestService,
        "ingest_order_page",
        _fake_ingest_order_page,
    )

    resp = await client.post(
        "/oms/stores/123/pdd/orders/ingest",
        json={
            "start_confirm_at": "2026-03-29 00:00:00",
            "end_confirm_at": "2026-03-29 23:59:59",
            "page": 1,
            "page_size": 50,
        },
    )
    assert resp.status_code == 400, resp.text
    assert "pdd pull failed: credential expired" in resp.text


async def test_post_store_pdd_orders_ingest_rejects_invalid_page_size(client):
    resp = await client.post(
        "/oms/stores/123/pdd/orders/ingest",
        json={
            "start_confirm_at": "2026-03-29 00:00:00",
            "end_confirm_at": "2026-03-29 23:59:59",
            "page": 1,
            "page_size": 101,
        },
    )
    assert resp.status_code == 422, resp.text
