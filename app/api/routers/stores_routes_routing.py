# app/api/routers/stores_routes_routing.py
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.api.routers.stores_routes_bindings_helpers import (
    check_store_perm,
    ensure_store_exists,
    ensure_warehouse_exists,
)
from app.api.routers.stores_schemas import (
    ProvinceRouteCreateIn,
    ProvinceRouteItem,
    ProvinceRouteListOut,
    ProvinceRouteUpdateIn,
    ProvinceRouteWriteOut,
    RoutingHealthOut,
)
from app.db.deps import get_db


# -----------------------------
# Province 规则：强校验/归一化
# -----------------------------
_ALLOWED_PROVINCE_SUFFIX = ("省", "市", "自治区", "特别行政区")


def _normalize_province(raw: str) -> str:
    p = (raw or "").strip()
    # 你定的合同：province 来自订单收件省（中文）
    # v0.2：强制要求以“省/市/自治区/特别行政区”结尾，避免 “广东 vs 广东省” 漂移
    if not p:
        raise HTTPException(status_code=422, detail="省不能为空（必须是订单收件省，例如：广东省）。")
    if len(p) > 32:
        raise HTTPException(status_code=422, detail="省名称过长（最多 32 个字符）。")
    if not any(p.endswith(s) for s in _ALLOWED_PROVINCE_SUFFIX):
        raise HTTPException(
            status_code=422,
            detail="省格式不合法：必须以“省/市/自治区/特别行政区”结尾（例如：广东省 / 北京市）。",
        )
    return p


async def _ensure_wh_is_bound_to_store(
    session: AsyncSession, *, store_id: int, warehouse_id: int
) -> None:
    """
    强约束：省级规则引用的仓库必须属于 store_warehouse 绑定集合。
    """
    chk = await session.execute(
        text(
            """
            SELECT 1
              FROM store_warehouse sw
             WHERE sw.store_id = :sid
               AND sw.warehouse_id = :wid
             LIMIT 1
            """
        ),
        {"sid": int(store_id), "wid": int(warehouse_id)},
    )
    if not chk.first():
        raise HTTPException(status_code=422, detail="该仓库未绑定到当前店铺，不能用于省级路由。")


def register(router: APIRouter) -> None:
    # ---------------- 省级路由：列表 ----------------
    @router.get(
        "/stores/{store_id}/routes/provinces",
        response_model=ProvinceRouteListOut,
    )
    async def list_province_routes(
        store_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        check_store_perm(db, current_user, ["config.store.read"])
        await ensure_store_exists(session, store_id)

        sql = text(
            """
            SELECT
              r.id,
              r.store_id,
              r.province,
              r.warehouse_id,
              w.name AS warehouse_name,
              w.code AS warehouse_code,
              COALESCE(w.active, TRUE) AS warehouse_active,
              r.priority,
              r.active
            FROM store_province_routes r
            LEFT JOIN warehouses w ON w.id = r.warehouse_id
            WHERE r.store_id = :sid
            ORDER BY r.province ASC, r.priority ASC, r.id ASC
            """
        )
        rows = (await session.execute(sql, {"sid": store_id})).mappings().all()
        items = [
            ProvinceRouteItem(
                id=int(r["id"]),
                store_id=int(r["store_id"]),
                province=str(r["province"]),
                warehouse_id=int(r["warehouse_id"]),
                warehouse_name=r.get("warehouse_name"),
                warehouse_code=r.get("warehouse_code"),
                warehouse_active=bool(r.get("warehouse_active", True)),
                priority=int(r["priority"]),
                active=bool(r["active"]),
            )
            for r in rows
        ]
        return ProvinceRouteListOut(ok=True, data=items)

    # ---------------- 省级路由：新增 ----------------
    @router.post(
        "/stores/{store_id}/routes/provinces",
        response_model=ProvinceRouteWriteOut,
    )
    async def create_province_route(
        store_id: int = Path(..., ge=1),
        payload: ProvinceRouteCreateIn = ...,
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        check_store_perm(db, current_user, ["config.store.write"])
        await ensure_store_exists(session, store_id)

        prov = _normalize_province(payload.province)
        wid = int(payload.warehouse_id)

        await ensure_warehouse_exists(session, wid, require_active=True)
        await _ensure_wh_is_bound_to_store(session, store_id=store_id, warehouse_id=wid)

        try:
            row = (
                await session.execute(
                    text(
                        """
                        INSERT INTO store_province_routes (
                          store_id, province, warehouse_id, priority, active
                        )
                        VALUES (
                          :sid, :prov, :wid, :prio, :active
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "sid": int(store_id),
                        "prov": prov,
                        "wid": wid,
                        "prio": int(payload.priority),
                        "active": bool(payload.active),
                    },
                )
            ).first()
            await session.commit()
        except IntegrityError:
            await session.rollback()
            # 你已有唯一键：(store_id, province, priority)
            raise HTTPException(status_code=400, detail="新增失败：同一省份下该优先级已存在。")
        except Exception as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=f"新增省级路由失败：{str(e)}")

        return ProvinceRouteWriteOut(ok=True, data={"id": int(row[0]) if row else None})

    # ---------------- 省级路由：更新 ----------------
    @router.patch(
        "/stores/{store_id}/routes/provinces/{route_id}",
        response_model=ProvinceRouteWriteOut,
    )
    async def update_province_route(
        store_id: int = Path(..., ge=1),
        route_id: int = Path(..., ge=1),
        payload: ProvinceRouteUpdateIn = ...,
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        check_store_perm(db, current_user, ["config.store.write"])
        await ensure_store_exists(session, store_id)

        fields: Dict[str, Any] = {}
        if payload.province is not None:
            fields["province"] = _normalize_province(payload.province)
        if payload.warehouse_id is not None:
            wid = int(payload.warehouse_id)
            await ensure_warehouse_exists(session, wid, require_active=True)
            await _ensure_wh_is_bound_to_store(session, store_id=store_id, warehouse_id=wid)
            fields["warehouse_id"] = wid

        if payload.priority is not None:
            fields["priority"] = int(payload.priority)
        if payload.active is not None:
            fields["active"] = bool(payload.active)

        if not fields:
            raise HTTPException(status_code=400, detail="no fields to update")

        set_parts = []
        params: Dict[str, Any] = {"sid": int(store_id), "rid": int(route_id)}
        for idx, (k, v) in enumerate(fields.items()):
            p = f"p{idx}"
            set_parts.append(f"{k} = :{p}")
            params[p] = v

        sql = text(
            f"""
            UPDATE store_province_routes
               SET {", ".join(set_parts)},
                   updated_at = now()
             WHERE id = :rid
               AND store_id = :sid
            RETURNING id
            """
        )

        try:
            row = (await session.execute(sql, params)).first()
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(status_code=400, detail="更新失败：同一省份下该优先级已存在。")
        except Exception as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=f"更新省级路由失败：{str(e)}")

        if not row:
            raise HTTPException(status_code=404, detail="route not found")

        return ProvinceRouteWriteOut(ok=True, data={"id": int(row[0])})

    # ---------------- 省级路由：删除 ----------------
    @router.delete(
        "/stores/{store_id}/routes/provinces/{route_id}",
        response_model=ProvinceRouteWriteOut,
    )
    async def delete_province_route(
        store_id: int = Path(..., ge=1),
        route_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        check_store_perm(db, current_user, ["config.store.write"])
        await ensure_store_exists(session, store_id)

        sql = text(
            """
            DELETE FROM store_province_routes
             WHERE id = :rid
               AND store_id = :sid
            RETURNING id
            """
        )
        row = (await session.execute(sql, {"rid": int(route_id), "sid": int(store_id)})).first()
        await session.commit()
        if not row:
            raise HTTPException(status_code=404, detail="route not found")
        return ProvinceRouteWriteOut(ok=True, data={"id": int(row[0])})

    # ---------------- 健康检查（v0） ----------------
    @router.get(
        "/stores/{store_id}/routing/health",
        response_model=RoutingHealthOut,
    )
    async def routing_health(
        store_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        check_store_perm(db, current_user, ["config.store.read"])
        await ensure_store_exists(session, store_id)

        row = (
            await session.execute(
                text(
                    """
                    SELECT
                      (SELECT COUNT(*) FROM store_warehouse sw WHERE sw.store_id=:sid) AS bind_n,
                      (SELECT COUNT(*) FROM store_warehouse sw WHERE sw.store_id=:sid AND COALESCE(sw.is_default,FALSE)=TRUE) AS default_n,
                      (SELECT COUNT(*) FROM store_province_routes r WHERE r.store_id=:sid AND COALESCE(r.active,TRUE)=TRUE) AS route_n
                    """
                ),
                {"sid": int(store_id)},
            )
        ).mappings().first()

        bind_n = int(row["bind_n"] or 0)
        default_n = int(row["default_n"] or 0)
        route_n = int(row["route_n"] or 0)

        errors: List[str] = []
        warnings: List[str] = []

        if bind_n <= 0:
            errors.append("店铺尚未绑定任何仓库。")
        if default_n <= 0:
            warnings.append("未设置默认仓：未命中省级规则时将进入人工强制。")
        elif default_n > 1:
            errors.append("默认仓配置异常：存在多个默认仓（is_default=true）。")

        if route_n <= 0:
            warnings.append("未配置任何省级路由规则：将全部走默认仓或人工强制。")

        ok = len(errors) == 0
        status = "OK" if ok and len(warnings) == 0 else ("WARN" if ok else "ERROR")

        return RoutingHealthOut(
            ok=True,
            data={
                "store_id": int(store_id),
                "bindings_count": bind_n,
                "default_count": default_n,
                "routes_count": route_n,
                "status": status,
                "warnings": warnings,
                "errors": errors,
            },
        )
