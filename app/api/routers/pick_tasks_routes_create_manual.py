# app/api/routers/pick_tasks_routes_create_manual.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_422
from app.db.session import get_session
from app.services.pick_task_service import PickTaskService
from app.api.routers.pick_tasks_schemas import PickTaskCreateFromOrder, PickTaskOut
from app.api.routers.pick_tasks_routes_common import load_latest_pick_list_print_job
from app.api.routers.pick_tasks_helpers import load_task_with_lines


async def _load_order_scope_ref(
    session: AsyncSession,
    *,
    order_id: int,
) -> tuple[str, str]:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT scope, platform, shop_id, ext_order_no
                    FROM orders
                    WHERE id = :id
                    LIMIT 1
                    """
                ),
                {"id": int(order_id)},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise_422(
            "order_not_found",
            "订单不存在，无法创建拣货任务。",
            details=[{"type": "validation", "path": "order_id", "reason": "not_found", "order_id": int(order_id)}],
        )

    scope = str(row.get("scope") or "").strip().upper()
    platform = str(row.get("platform") or "").strip().upper()
    shop_id = str(row.get("shop_id") or "").strip()
    ext = str(row.get("ext_order_no") or "").strip()

    if not scope or not platform or not shop_id or not ext:
        raise_422(
            "order_meta_invalid",
            "订单关键字段缺失，无法创建拣货任务。",
            details=[
                {
                    "type": "state",
                    "path": "orders",
                    "reason": "missing_scope_platform_shop_ext",
                    "order_id": int(order_id),
                    "scope": scope,
                    "platform": platform,
                    "shop_id": shop_id,
                    "ext_order_no": ext,
                }
            ],
        )

    ref = f"ORD:{platform}:{shop_id}:{ext}"
    return scope, ref


async def _find_existing_task_id(
    session: AsyncSession,
    *,
    scope: str,
    ref: str,
    warehouse_id: int,
) -> int | None:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT id
                    FROM pick_tasks
                    WHERE scope = :scope
                      AND ref = :ref
                      AND warehouse_id = :wid
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ),
                {"scope": str(scope).upper(), "ref": str(ref), "wid": int(warehouse_id)},
            )
        )
        .mappings()
        .first()
    )
    return int(row["id"]) if row and row.get("id") is not None else None


def register_manual_create(router: APIRouter) -> None:
    async def _create_impl(
        *,
        order_id: int,
        payload: PickTaskCreateFromOrder,
        session: AsyncSession,
        require_warehouse: bool,
    ) -> PickTaskOut:
        # ✅ 手工主线：必须显式 warehouse_id
        # ✅ 自动主线：允许 warehouse_id=None，由服务层解析执行仓
        if require_warehouse and payload.warehouse_id is None:
            raise_422(
                "warehouse_required",
                "创建拣货任务必须选择仓库（手工模式）。",
                details=[{"type": "validation", "path": "warehouse_id", "reason": "required"}],
            )

        # ✅ scope 必须继承订单（DRILL/PROD），ref 必须与订单一致
        scope, ref = await _load_order_scope_ref(session, order_id=int(order_id))

        wid = int(payload.warehouse_id) if payload.warehouse_id is not None else None
        if wid is None:
            # 兼容入口允许 None，但我们这里仍然要求：后续能解析出仓库，否则无意义
            raise_422(
                "warehouse_required",
                "创建拣货任务必须选择仓库（当前实现不支持自动解析执行仓）。",
                details=[{"type": "validation", "path": "warehouse_id", "reason": "required"}],
            )

        # ✅ 幂等隔离：同 scope + ref + warehouse_id 已存在则直接返回（避免误复用 PROD 任务）
        existing_id = await _find_existing_task_id(session, scope=scope, ref=ref, warehouse_id=wid)
        if existing_id is not None:
            task = await load_task_with_lines(session, existing_id)
            out = PickTaskOut.model_validate(task)
            out.print_job = await load_latest_pick_list_print_job(session, task_id=int(out.id))
            return out

        svc = PickTaskService(session)
        try:
            task = await svc.create_for_order(
                order_id=int(order_id),
                warehouse_id=wid,
                source=payload.source,
                priority=payload.priority,
            )

            # ✅ 关键修复：强制把 pick_tasks.scope 写成订单 scope（默认值 PROD 会串线）
            await session.execute(
                text("UPDATE pick_tasks SET scope = :scope, ref = :ref WHERE id = :id"),
                {"scope": scope, "ref": ref, "id": int(task.id)},
            )

            await session.commit()

        except HTTPException:
            await session.rollback()
            raise
        except ValueError as e:
            await session.rollback()
            raise_422("pick_task_create_reject", str(e))
        except Exception:
            await session.rollback()
            raise

        # 重新 load（拿到更新后的 scope/ref + lines）
        task2 = await load_task_with_lines(session, int(task.id))
        out = PickTaskOut.model_validate(task2)
        out.print_job = await load_latest_pick_list_print_job(session, task_id=int(out.id))
        return out

    @router.post("/manual-from-order/{order_id}", response_model=PickTaskOut)
    async def manual_create_pick_task_from_order(
        order_id: int,
        payload: PickTaskCreateFromOrder,
        session: AsyncSession = Depends(get_session),
    ) -> PickTaskOut:
        """
        手工入口（推荐）：
        - 必须显式 warehouse_id
        - 只创建 pick_task + lines
        - ❌ 不自动 enqueue 打印
        """
        return await _create_impl(
            order_id=int(order_id),
            payload=payload,
            session=session,
            require_warehouse=True,
        )

    @router.post("/from-order/{order_id}", response_model=PickTaskOut, deprecated=True)
    async def create_pick_task_from_order_compat(
        order_id: int,
        payload: PickTaskCreateFromOrder,
        session: AsyncSession = Depends(get_session),
    ) -> PickTaskOut:
        """
        兼容入口（deprecated）：
        - 允许不传 warehouse_id（Phase 2：后端解析执行仓）
        - ❌ 不自动化、不自动打印
        """
        return await _create_impl(
            order_id=int(order_id),
            payload=payload,
            session=session,
            require_warehouse=False,
        )
