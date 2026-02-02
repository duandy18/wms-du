# app/services/print_jobs_service.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


UTC = timezone.utc


async def enqueue_pick_list_job(
    session: AsyncSession,
    *,
    ref_type: str,
    ref_id: int,
    payload: Dict[str, Any],
) -> int:
    """
    幂等入队打印任务（pick_list）：
    - 对齐你现有 SQL（行为不变）
    """
    rt = str(ref_type or "").strip() or "pick_task"
    rid = int(ref_id)
    payload_json = json.dumps(payload, ensure_ascii=False)

    ins = await session.execute(
        text(
            """
            INSERT INTO print_jobs(kind, ref_type, ref_id, status, payload, requested_at, created_at, updated_at)
            VALUES ('pick_list', :rt, :rid, 'queued', CAST(:payload AS jsonb), now(), now(), now())
            ON CONFLICT (kind, ref_type, ref_id)
            DO UPDATE SET
              updated_at = EXCLUDED.updated_at
            RETURNING id
            """
        ),
        {"rt": rt, "rid": rid, "payload": payload_json},
    )
    return int(ins.first()[0])


async def mark_print_job_printed(
    session: AsyncSession,
    *,
    job_id: int,
    printed_at: Optional[datetime] = None,
) -> None:
    """
    打印成功回写：
    - status -> printed
    - printed_at -> now()
    - error -> NULL
    """
    ts = printed_at or datetime.now(UTC)
    await session.execute(
        text(
            """
            UPDATE print_jobs
               SET status = 'printed',
                   printed_at = :ts,
                   error = NULL,
                   updated_at = now()
             WHERE id = :id
            """
        ),
        {"id": int(job_id), "ts": ts},
    )


async def mark_print_job_failed(
    session: AsyncSession,
    *,
    job_id: int,
    error: str,
) -> None:
    """
    打印失败回写：
    - status -> failed
    - error -> 文本原因
    - printed_at 不动（保留空或历史值）
    """
    await session.execute(
        text(
            """
            UPDATE print_jobs
               SET status = 'failed',
                   error = :err,
                   updated_at = now()
             WHERE id = :id
            """
        ),
        {"id": int(job_id), "err": str(error or "").strip() or "print_failed"},
    )


async def load_print_job(
    session: AsyncSession,
    *,
    job_id: int,
) -> Optional[dict[str, Any]]:
    row = (
        await session.execute(
            text(
                """
                SELECT id, kind, ref_type, ref_id, status, payload, requested_at, printed_at, error, created_at, updated_at
                  FROM print_jobs
                 WHERE id = :id
                 LIMIT 1
                """
            ),
            {"id": int(job_id)},
        )
    ).mappings().first()
    return dict(row) if row else None
