# app/api/routers/pick_tasks_routes_commit.py
from __future__ import annotations

from typing import Any, Set

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.lot_code_contract import (
    fetch_item_expiry_policy_map,
    validate_lot_code_contract,
)
from app.api.problem import raise_409, raise_422
from app.api.routers.pick_tasks_helpers import load_task_with_lines
from app.api.routers.pick_tasks_schemas import PickTaskCommitIn, PickTaskCommitResult
from app.db.session import get_session
from app.services.pick_task_service import PickTaskService

_COMMIT_LOCK_TIMEOUT_MS = 1500
_COMMIT_STATEMENT_TIMEOUT_MS = 8000

_PG_QUERY_CANCELED = "57014"
_PG_LOCK_NOT_AVAILABLE = "55P03"


def _requires_batch_from_expiry_policy(v: object) -> bool:
    return str(v or "").upper() == "REQUIRED"


def _extract_contract_error_code(exc: HTTPException, *, requires_batch: bool) -> tuple[str, str]:
    """
    从 validate_lot_code_contract 抛出的 HTTPException.detail 中提取 (error_code, message)。

    终态合同（Phase M）下 detail 应为 dict：
      {"error_code": "...", "message": "...", ...}

    兜底策略：
    - 若 detail 不是 dict（极端情况），用 requires_batch 推导到 batch_required/batch_forbidden，并用 str(detail) 做 message。
    """
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        code = detail.get("error_code")
        msg = detail.get("message")
        if isinstance(code, str) and code.strip():
            return code.strip(), str(msg or "")
        # dict 但缺字段，做保守兜底
        fallback = "batch_required" if requires_batch else "batch_forbidden"
        return fallback, str(msg or "")
    fallback = "batch_required" if requires_batch else "batch_forbidden"
    return fallback, str(detail)


def register_commit(router: APIRouter) -> None:
    @router.post("/{task_id}/commit", response_model=PickTaskCommitResult)
    async def commit_pick_task(
        task_id: int,
        payload: PickTaskCommitIn,
        session: AsyncSession = Depends(get_session),
    ) -> PickTaskCommitResult:

        task = await load_task_with_lines(session, task_id)
        item_ids: Set[int] = {int(ln.item_id) for ln in (task.lines or [])}

        expiry_policy_map = await fetch_item_expiry_policy_map(session, item_ids)

        missing_items = [int(i) for i in sorted(item_ids) if i not in expiry_policy_map]
        if missing_items:
            raise_422(
                "unknown_item",
                "存在未知商品，禁止提交。",
                details=[
                    {
                        "type": "validation",
                        "path": f"lines[{idx}].item_id",
                        "item_id": int(ln.item_id),
                        "reason": "unknown",
                    }
                    for idx, ln in enumerate(task.lines or [])
                    if int(ln.item_id) in set(missing_items)
                ],
            )

        for idx, ln in enumerate(task.lines or []):
            requires_batch = _requires_batch_from_expiry_policy(expiry_policy_map.get(int(ln.item_id)))

            try:
                validate_lot_code_contract(
                    requires_batch=requires_batch,
                    lot_code=ln.batch_code,
                )
            except HTTPException as e:
                code, msg = _extract_contract_error_code(e, requires_batch=requires_batch)
                raise_422(
                    code,
                    "批次信息不合法，禁止提交。",
                    details=[
                        {
                            "type": "batch",
                            "path": f"lines[{idx}]",
                            "item_id": int(ln.item_id),
                            "batch_code": ln.batch_code,
                            "reason": msg or "contract_reject",
                        }
                    ],
                )

        svc = PickTaskService(session)

        try:
            await session.execute(text(f"SET LOCAL lock_timeout = {_COMMIT_LOCK_TIMEOUT_MS}"))
            await session.execute(text(f"SET LOCAL statement_timeout = {_COMMIT_STATEMENT_TIMEOUT_MS}"))

            result: Any = await svc.commit_ship(
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
