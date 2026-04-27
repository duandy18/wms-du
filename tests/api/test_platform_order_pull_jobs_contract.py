from __future__ import annotations

import pytest
from sqlalchemy import text

from app.platform_order_ingestion.taobao import service_ingest as taobao_service_ingest
from app.platform_order_ingestion.taobao.service_ingest import (
    TaobaoOrderIngestPageResult,
    TaobaoOrderIngestRowResult,
)
from app.platform_order_ingestion.jd import service_ingest as jd_service_ingest
from app.platform_order_ingestion.jd.service_ingest import (
    JdOrderIngestPageResult,
    JdOrderIngestRowResult,
)
from app.platform_order_ingestion.pdd import service_ingest as pdd_service_ingest
from app.platform_order_ingestion.pdd.service_ingest import (
    PddOrderIngestPageResult,
    PddOrderIngestRowResult,
)

pytestmark = pytest.mark.asyncio

from app.main import app
from app.user.deps.auth import get_current_user


class _PlatformOrderIngestionPermissionUser:
    id: int = 999
    username: str = "test-user"
    is_active: bool = True
    permissions = [
        "page.platform_order_ingestion.read",
        "page.platform_order_ingestion.write",
    ]


@pytest.fixture(autouse=True)
def _override_platform_order_ingestion_user():
    app.dependency_overrides[get_current_user] = lambda: _PlatformOrderIngestionPermissionUser()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)



async def _seed_store(session, *, store_id: int = 7101, platform: str = "PDD") -> None:
    await session.execute(
        text(
            """
            INSERT INTO stores (id, platform, store_code, store_name, active)
            VALUES (:id, :platform, :store_code, :store_name, TRUE)
            ON CONFLICT (id) DO UPDATE
              SET platform = EXCLUDED.platform,
                  store_code = EXCLUDED.store_code,
                  store_name = EXCLUDED.store_name,
                  active = TRUE
            """
        ),
        {
            "id": store_id,
            "platform": platform,
            "store_code": f"store-{store_id}",
            "store_name": f"store-{store_id}",
        },
    )
    await session.commit()


async def test_create_and_list_platform_order_pull_job(client, session):
    await _seed_store(session, store_id=7101, platform="PDD")

    resp = await client.post(
        "/oms/platform-order-ingestion/pull-jobs",
        json={
            "platform": "pdd",
            "store_id": 7101,
            "job_type": "manual",
            "time_from": "2026-03-29 00:00:00",
            "time_to": "2026-03-29 23:59:59",
            "order_status": 1,
            "page_size": 50,
            "request_payload": {"source": "contract-test"},
        },
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["ok"] is True
    job = body["data"]
    assert job["id"] > 0
    assert job["platform"] == "pdd"
    assert job["store_id"] == 7101
    assert job["job_type"] == "manual"
    assert job["status"] == "pending"
    assert job["page_size"] == 50
    assert job["cursor_page"] == 1
    assert job["order_status"] == 1
    assert job["request_payload"] == {"source": "contract-test"}

    list_resp = await client.get("/oms/platform-order-ingestion/pull-jobs?platform=pdd&store_id=7101")
    assert list_resp.status_code == 200, list_resp.text
    data = list_resp.json()["data"]
    assert data["total"] >= 1
    assert any(row["id"] == job["id"] for row in data["rows"])

    detail_resp = await client.get(f"/oms/platform-order-ingestion/pull-jobs/{job['id']}")
    assert detail_resp.status_code == 200, detail_resp.text
    detail = detail_resp.json()["data"]
    assert detail["job"]["id"] == job["id"]
    assert detail["runs"] == []
    assert detail["logs"] == []


async def test_run_pdd_platform_order_pull_job_records_run_and_logs(client, session, monkeypatch):
    await _seed_store(session, store_id=7102, platform="PDD")

    captured = {}

    async def _fake_ingest_order_page(self, *, session, params):
        captured["store_id"] = params.store_id
        captured["start_confirm_at"] = params.start_confirm_at
        captured["end_confirm_at"] = params.end_confirm_at
        captured["order_status"] = params.order_status
        captured["page"] = params.page
        captured["page_size"] = params.page_size

        return PddOrderIngestPageResult(
            store_id=7102,
            store_code="store-7102",
            page=params.page,
            page_size=params.page_size,
            orders_count=2,
            success_count=1,
            failed_count=1,
            has_more=True,
            start_confirm_at=params.start_confirm_at,
            end_confirm_at=params.end_confirm_at,
            rows=[
                PddOrderIngestRowResult(
                    order_sn="PDD-JOB-ORDER-001",
                    pdd_order_id=9001,
                    status="OK",
                    error=None,
                ),
                PddOrderIngestRowResult(
                    order_sn="PDD-JOB-ORDER-002",
                    pdd_order_id=None,
                    status="FAILED",
                    error="detail_failed: boom",
                ),
            ],
        )

    monkeypatch.setattr(
        pdd_service_ingest.PddOrderIngestService,
        "ingest_order_page",
        _fake_ingest_order_page,
    )

    create_resp = await client.post(
        "/oms/platform-order-ingestion/pull-jobs",
        json={
            "platform": "pdd",
            "store_id": 7102,
            "job_type": "manual",
            "time_from": "2026-03-29 00:00:00",
            "time_to": "2026-03-29 23:59:59",
            "order_status": 1,
            "page_size": 50,
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    job_id = create_resp.json()["data"]["id"]

    run_resp = await client.post(
        f"/oms/platform-order-ingestion/pull-jobs/{job_id}/runs",
        json={"page": 1},
    )
    assert run_resp.status_code == 200, run_resp.text

    assert captured == {
        "store_id": 7102,
        "start_confirm_at": "2026-03-29 00:00:00",
        "end_confirm_at": "2026-03-29 23:59:59",
        "order_status": 1,
        "page": 1,
        "page_size": 50,
    }

    data = run_resp.json()["data"]
    assert data["job"]["id"] == job_id
    assert data["job"]["status"] == "partial_success"
    assert data["job"]["cursor_page"] == 2

    run = data["run"]
    assert run["job_id"] == job_id
    assert run["status"] == "partial_success"
    assert run["page"] == 1
    assert run["page_size"] == 50
    assert run["has_more"] is True
    assert run["orders_count"] == 2
    assert run["success_count"] == 1
    assert run["failed_count"] == 1
    assert run["result_payload"]["rows"][0]["order_sn"] == "PDD-JOB-ORDER-001"

    logs = data["logs"]
    assert [log["event_type"] for log in logs] == [
        "page_started",
        "order_ingested",
        "order_failed",
        "page_finished",
    ]
    assert logs[1]["platform_order_no"] == "PDD-JOB-ORDER-001"
    assert logs[1]["native_order_id"] == 9001
    assert logs[2]["level"] == "error"

    detail_resp = await client.get(f"/oms/platform-order-ingestion/pull-jobs/{job_id}")
    assert detail_resp.status_code == 200, detail_resp.text
    detail = detail_resp.json()["data"]
    assert len(detail["runs"]) == 1
    assert len(detail["logs"]) == 4


async def test_run_taobao_platform_order_pull_job_records_run_and_logs_after_executor_registration(client, session, monkeypatch):
    await _seed_store(session, store_id=7103, platform="TAOBAO")

    captured = {}

    async def _fake_ingest_order_page(self, *, session, params):
        captured["store_id"] = params.store_id
        captured["start_time"] = params.start_time
        captured["end_time"] = params.end_time
        captured["status"] = params.status
        captured["page"] = params.page
        captured["page_size"] = params.page_size

        return TaobaoOrderIngestPageResult(
            store_id=7103,
            store_code="store-7103",
            page=params.page,
            page_size=params.page_size,
            orders_count=2,
            success_count=1,
            failed_count=1,
            has_more=True,
            start_time=params.start_time,
            end_time=params.end_time,
            rows=[
                TaobaoOrderIngestRowResult(
                    tid="TB-JOB-ORDER-001",
                    taobao_order_id=9701,
                    status="OK",
                    error=None,
                ),
                TaobaoOrderIngestRowResult(
                    tid="TB-JOB-ORDER-002",
                    taobao_order_id=None,
                    status="FAILED",
                    error="detail_failed: boom",
                ),
            ],
        )

    monkeypatch.setattr(
        taobao_service_ingest.TaobaoOrderIngestService,
        "ingest_order_page",
        _fake_ingest_order_page,
    )

    create_resp = await client.post(
        "/oms/platform-order-ingestion/pull-jobs",
        json={
            "platform": "taobao",
            "store_id": 7103,
            "job_type": "manual",
            "time_from": "2026-03-29 00:00:00",
            "time_to": "2026-03-29 23:59:59",
            "page_size": 50,
            "request_payload": {"status": "WAIT_SELLER_SEND_GOODS"},
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    job_id = create_resp.json()["data"]["id"]

    run_resp = await client.post(
        f"/oms/platform-order-ingestion/pull-jobs/{job_id}/runs",
        json={"page": 1},
    )
    assert run_resp.status_code == 200, run_resp.text

    assert captured == {
        "store_id": 7103,
        "start_time": "2026-03-29 00:00:00",
        "end_time": "2026-03-29 23:59:59",
        "status": "WAIT_SELLER_SEND_GOODS",
        "page": 1,
        "page_size": 50,
    }

    data = run_resp.json()["data"]
    assert data["job"]["platform"] == "taobao"
    assert data["job"]["status"] == "partial_success"
    assert data["job"]["cursor_page"] == 2

    run = data["run"]
    assert run["status"] == "partial_success"
    assert run["page"] == 1
    assert run["page_size"] == 50
    assert run["has_more"] is True
    assert run["orders_count"] == 2
    assert run["success_count"] == 1
    assert run["failed_count"] == 1
    assert run["result_payload"]["rows"][0]["tid"] == "TB-JOB-ORDER-001"
    assert run["result_payload"]["rows"][0]["taobao_order_id"] == 9701

    logs = data["logs"]
    assert [log["event_type"] for log in logs] == [
        "page_started",
        "order_ingested",
        "order_failed",
        "page_finished",
    ]
    assert logs[1]["platform_order_no"] == "TB-JOB-ORDER-001"
    assert logs[1]["native_order_id"] == 9701
    assert logs[1]["message"] == "taobao order ingested"
    assert logs[2]["level"] == "error"


async def test_run_pdd_platform_order_pull_job_pages_stops_when_no_more(client, session, monkeypatch):
    await _seed_store(session, store_id=7104, platform="PDD")

    captured_pages = []

    async def _fake_ingest_order_page(self, *, session, params):
        captured_pages.append(params.page)
        has_more = params.page == 1
        return PddOrderIngestPageResult(
            store_id=7104,
            store_code="store-7104",
            page=params.page,
            page_size=params.page_size,
            orders_count=1,
            success_count=1,
            failed_count=0,
            has_more=has_more,
            start_confirm_at=params.start_confirm_at,
            end_confirm_at=params.end_confirm_at,
            rows=[
                PddOrderIngestRowResult(
                    order_sn=f"PDD-JOB-ORDER-PAGE-{params.page}",
                    pdd_order_id=9100 + params.page,
                    status="OK",
                    error=None,
                )
            ],
        )

    monkeypatch.setattr(
        pdd_service_ingest.PddOrderIngestService,
        "ingest_order_page",
        _fake_ingest_order_page,
    )

    create_resp = await client.post(
        "/oms/platform-order-ingestion/pull-jobs",
        json={
            "platform": "pdd",
            "store_id": 7104,
            "job_type": "manual",
            "time_from": "2026-03-29 00:00:00",
            "time_to": "2026-03-29 23:59:59",
            "order_status": 1,
            "page_size": 50,
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    job_id = create_resp.json()["data"]["id"]

    run_resp = await client.post(
        f"/oms/platform-order-ingestion/pull-jobs/{job_id}/run-pages",
        json={"max_pages": 5},
    )
    assert run_resp.status_code == 200, run_resp.text

    data = run_resp.json()["data"]
    assert captured_pages == [1, 2]
    assert data["pages_executed"] == 2
    assert data["stopped_reason"] == "no_more"
    assert [run["page"] for run in data["runs"]] == [1, 2]
    assert data["runs"][0]["has_more"] is True
    assert data["runs"][1]["has_more"] is False
    assert data["job"]["status"] == "success"
    assert data["job"]["cursor_page"] == 2


async def test_run_pdd_platform_order_pull_job_pages_respects_max_pages(client, session, monkeypatch):
    await _seed_store(session, store_id=7105, platform="PDD")

    captured_pages = []

    async def _fake_ingest_order_page(self, *, session, params):
        captured_pages.append(params.page)
        return PddOrderIngestPageResult(
            store_id=7105,
            store_code="store-7105",
            page=params.page,
            page_size=params.page_size,
            orders_count=1,
            success_count=1,
            failed_count=0,
            has_more=True,
            start_confirm_at=params.start_confirm_at,
            end_confirm_at=params.end_confirm_at,
            rows=[
                PddOrderIngestRowResult(
                    order_sn=f"PDD-JOB-MAX-PAGE-{params.page}",
                    pdd_order_id=9200 + params.page,
                    status="OK",
                    error=None,
                )
            ],
        )

    monkeypatch.setattr(
        pdd_service_ingest.PddOrderIngestService,
        "ingest_order_page",
        _fake_ingest_order_page,
    )

    create_resp = await client.post(
        "/oms/platform-order-ingestion/pull-jobs",
        json={
            "platform": "pdd",
            "store_id": 7105,
            "job_type": "manual",
            "time_from": "2026-03-29 00:00:00",
            "time_to": "2026-03-29 23:59:59",
            "order_status": 1,
            "page_size": 50,
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    job_id = create_resp.json()["data"]["id"]

    run_resp = await client.post(
        f"/oms/platform-order-ingestion/pull-jobs/{job_id}/run-pages",
        json={"max_pages": 2},
    )
    assert run_resp.status_code == 200, run_resp.text

    data = run_resp.json()["data"]
    assert captured_pages == [1, 2]
    assert data["pages_executed"] == 2
    assert data["stopped_reason"] == "max_pages_reached"
    assert [run["page"] for run in data["runs"]] == [1, 2]
    assert all(run["has_more"] is True for run in data["runs"])
    assert data["job"]["cursor_page"] == 3


async def test_run_jd_platform_order_pull_job_records_run_and_logs_after_executor_registration(client, session, monkeypatch):
    await _seed_store(session, store_id=7106, platform="JD")

    captured = {}

    async def _fake_ingest_order_page(self, *, session, params):
        captured["store_id"] = params.store_id
        captured["start_time"] = params.start_time
        captured["end_time"] = params.end_time
        captured["order_state"] = params.order_state
        captured["page"] = params.page
        captured["page_size"] = params.page_size

        return JdOrderIngestPageResult(
            store_id=7106,
            store_code="store-7106",
            page=params.page,
            page_size=params.page_size,
            orders_count=2,
            success_count=1,
            failed_count=1,
            has_more=True,
            start_time=params.start_time,
            end_time=params.end_time,
            rows=[
                JdOrderIngestRowResult(
                    order_id="JD-JOB-ORDER-001",
                    jd_order_id=9601,
                    status="OK",
                    error=None,
                ),
                JdOrderIngestRowResult(
                    order_id="JD-JOB-ORDER-002",
                    jd_order_id=None,
                    status="FAILED",
                    error="detail_failed: boom",
                ),
            ],
        )

    monkeypatch.setattr(
        jd_service_ingest.JdOrderIngestService,
        "ingest_order_page",
        _fake_ingest_order_page,
    )

    create_resp = await client.post(
        "/oms/platform-order-ingestion/pull-jobs",
        json={
            "platform": "jd",
            "store_id": 7106,
            "job_type": "manual",
            "time_from": "2026-03-29 00:00:00",
            "time_to": "2026-03-29 23:59:59",
            "page_size": 20,
            "request_payload": {"order_state": "WAIT_SELLER_STOCK_OUT"},
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    job_id = create_resp.json()["data"]["id"]

    run_resp = await client.post(
        f"/oms/platform-order-ingestion/pull-jobs/{job_id}/runs",
        json={"page": 1},
    )
    assert run_resp.status_code == 200, run_resp.text

    assert captured == {
        "store_id": 7106,
        "start_time": "2026-03-29 00:00:00",
        "end_time": "2026-03-29 23:59:59",
        "order_state": "WAIT_SELLER_STOCK_OUT",
        "page": 1,
        "page_size": 20,
    }

    data = run_resp.json()["data"]
    assert data["job"]["platform"] == "jd"
    assert data["job"]["status"] == "partial_success"
    assert data["job"]["cursor_page"] == 2

    run = data["run"]
    assert run["status"] == "partial_success"
    assert run["page"] == 1
    assert run["page_size"] == 20
    assert run["has_more"] is True
    assert run["orders_count"] == 2
    assert run["success_count"] == 1
    assert run["failed_count"] == 1
    assert run["result_payload"]["rows"][0]["order_id"] == "JD-JOB-ORDER-001"
    assert run["result_payload"]["rows"][0]["jd_order_id"] == 9601

    logs = data["logs"]
    assert [log["event_type"] for log in logs] == [
        "page_started",
        "order_ingested",
        "order_failed",
        "page_finished",
    ]
    assert logs[1]["platform_order_no"] == "JD-JOB-ORDER-001"
    assert logs[1]["native_order_id"] == 9601
    assert logs[1]["message"] == "jd order ingested"
    assert logs[2]["level"] == "error"
