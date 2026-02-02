# tests/api/test_print_jobs_contract.py
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


pytestmark = pytest.mark.asyncio


async def _insert_print_job(session: AsyncSession, *, status: str = "queued") -> int:
    payload = {
        "kind": "pick_list",
        "platform": "UT",
        "shop_id": "1",
        "ext_order_no": "UT-PRINT-JOB",
        "order_id": 1,
        "pick_task_id": 1,
        "warehouse_id": 1,
        "lines": [{"item_id": 1, "req_qty": 1}],
        "trace_id": "TRACE-UT-PRINT-JOB",
        "version": 1,
    }
    res = await session.execute(
        text(
            """
            INSERT INTO print_jobs(kind, ref_type, ref_id, status, payload, requested_at, created_at, updated_at)
            VALUES ('pick_list', 'pick_task', 999999, :status, CAST(:payload AS jsonb), now(), now(), now())
            ON CONFLICT (kind, ref_type, ref_id)
            DO UPDATE SET
              status = EXCLUDED.status,
              payload = EXCLUDED.payload,
              updated_at = now()
            RETURNING id
            """
        ),
        {"status": str(status), "payload": json.dumps(payload, ensure_ascii=False)},
    )
    job_id = int(res.scalar_one())
    await session.commit()
    return job_id


async def _get_job_row(session: AsyncSession, *, job_id: int) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT id, status, printed_at, error
                  FROM print_jobs
                 WHERE id = :id
                 LIMIT 1
                """
            ),
            {"id": int(job_id)},
        )
    ).mappings().first()
    assert row, f"missing print_job row id={job_id}"
    return dict(row)


async def test_print_jobs_mark_printed_and_failed_contract(
    client: AsyncClient,
    db_session_like_pg: AsyncSession,
):
    # 1) seed job
    job_id = await _insert_print_job(db_session_like_pg, status="queued")

    # 2) GET
    r0 = await client.get(f"/print-jobs/{job_id}")
    assert r0.status_code == 200, r0.text
    body0 = r0.json()
    assert body0.get("status") == "OK"
    assert body0.get("job", {}).get("id") == job_id

    # 3) mark printed
    r1 = await client.post(f"/print-jobs/{job_id}/printed", json={})
    assert r1.status_code == 200, r1.text
    row1 = await _get_job_row(db_session_like_pg, job_id=job_id)
    assert row1["status"] == "printed"
    assert row1["printed_at"] is not None
    assert row1["error"] is None

    # 4) mark failed
    r2 = await client.post(f"/print-jobs/{job_id}/failed", json={"error": "printer offline"})
    assert r2.status_code == 200, r2.text
    row2 = await _get_job_row(db_session_like_pg, job_id=job_id)
    assert row2["status"] == "failed"
    assert isinstance(row2["error"], str) and len(row2["error"]) > 0
