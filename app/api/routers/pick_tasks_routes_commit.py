# app/api/routers/pick_tasks_routes_commit.py
from __future__ import annotations

from typing import Set

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.batch_code_contract import fetch_item_has_shelf_life_map, validate_batch_code_contract
from app.api.problem import raise_409, raise_422
from app.api.routers.pick_tasks_helpers import load_task_with_lines
from app.api.routers.pick_tasks_schemas import PickTaskCommitIn, PickTaskCommitResult
from app.db.session import get_session
from app.services.pick_task_service import PickTaskService

# 事务内护栏：避免 commit 在 DB 锁等待/慢查询上“无限卡死”
# - lock_timeout：等待行锁/表锁的上限（超时后 PG 抛 query_canceled 或 lock_not_available）
# - statement_timeout：单条 SQL 的上限（超时后 PG 抛 query_canceled）
_COMMIT_LOCK_TIMEOUT_MS = 1500
_COMMIT_STATEMENT_TIMEOUT_MS = 8000

# Postgres SQLSTATE:
# - 57014: query_canceled（包含 statement_timeout / lock_timeout）
# - 55P03: lock_not_available（某些锁等待/nowait/lock_timeout 场景会落到这里）
_PG_QUERY_CANCELED = "57014"
_PG_LOCK_NOT_AVAILABLE = "55P03"


def register_commit(router: APIRouter) -> None:
    @router.post("/{task_id}/commit", response_model=PickTaskCommitResult)
    async def commit_pick_task(
        task_id: int,
        payload: PickTaskCommitIn,
        session: AsyncSession = Depends(get_session),
    ) -> PickTaskCommitResult:
        task = await load_task_with_lines(session, task_id)
        item_ids: Set[int] = {int(ln.item_id) for ln in (task.lines or [])}
        has_shelf_life_map = await fetch_item_has_shelf_life_map(session, item_ids)

        missing_items = [int(i) for i in sorted(item_ids) if i not in has_shelf_life_map]
        if missing_items:
            raise_422(
                "unknown_item",
                "存在未知商品，禁止提交。",
                details=[
                    {"type": "validation", "path": f"lines[{idx}].item_id", "item_id": int(ln.item_id), "reason": "unknown"}
                    for idx, ln in enumerate(task.lines or [])
                    if int(ln.item_id) in set(missing_items)
                ],
            )

        for idx, ln in enumerate(task.lines or []):
            requires_batch = has_shelf_life_map.get(int(ln.item_id), False) is True
            try:
                validate_batch_code_contract(requires_batch=requires_batch, batch_code=ln.batch_code)
            except HTTPException as e:
                raise_422(
                    "batch_required" if requires_batch else "invalid_batch",
                    "批次信息不合法，禁止提交。",
                    details=[
                        {
                            "type": "batch",
                            "path": f"lines[{idx}]",
                            "item_id": int(ln.item_id),
                            "batch_code": ln.batch_code,
                            "reason": str(e.detail),
                        }
                    ],
                )

        svc = PickTaskService(session)

        try:
            # ✅ 事务内护栏：防止 commit 路径在 DB 等锁/慢 SQL 上无限卡住
            await session.execute(text(f"SET LOCAL lock_timeout = {_COMMIT_LOCK_TIMEOUT_MS}"))
            await session.execute(text(f"SET LOCAL statement_timeout = {_COMMIT_STATEMENT_TIMEOUT_MS}"))

            result = await svc.commit_ship(
                task_id=task_id,
                platform=payload.platform,
                shop_id=payload.shop_id,
                handoff_code=payload.handoff_code,
                trace_id=payload.trace_id,
                allow_diff=payload.allow_diff,
            )
            await session.commit()

        except HTTPException:
            await session.rollback()
            raise

        except ValueError as e:
            await session.rollback()
            # 业务冲突（状态/幂等/交接码等）→ 409 Problem
            raise_409(
                "pick_commit_reject",
                str(e),
                details=[{"type": "state", "path": "commit", "reason": str(e)}],
            )

        except DBAPIError as e:
            await session.rollback()
            pgcode = getattr(getattr(e, "orig", None), "pgcode", None)
            if pgcode in {_PG_QUERY_CANCELED, _PG_LOCK_NOT_AVAILABLE}:
                raise_409(
                    "pick_commit_timeout",
                    "提交拣货单超时（可能存在锁等待或慢查询）。",
                    details=[
                        {
                            "type": "timeout",
                            "path": "commit",
                            "pgcode": pgcode,
                            "lock_timeout_ms": _COMMIT_LOCK_TIMEOUT_MS,
                            "statement_timeout_ms": _COMMIT_STATEMENT_TIMEOUT_MS,
                        }
                    ],
                )
            raise

        except Exception:
            await session.rollback()
            raise

        return PickTaskCommitResult(**result)
