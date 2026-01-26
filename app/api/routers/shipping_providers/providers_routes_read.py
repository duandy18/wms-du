# app/api/routers/shipping_providers/providers_routes_read.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.db.deps import get_db

from .common import (
    ShippingProviderContactOut,
    ShippingProviderDetailOut,
    ShippingProviderListOut,
    ShippingProviderOut,
    _check_perm,
    _row_to_contact,
    _row_to_provider,
)


def register(router: APIRouter) -> None:
    @router.get("/shipping-providers", response_model=ShippingProviderListOut)
    async def list_shipping_providers(
        active: Optional[bool] = Query(None, description="按启用状态筛选；active=true 用于下拉。"),
        q: Optional[str] = Query(None, description="按名称 / 联系人模糊搜索（基于 contacts 子表）。"),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> ShippingProviderListOut:
        """
        物流/快递网点列表（读聚合 contacts）。

        权限：config.store.read
        """
        _check_perm(db, current_user, ["config.store.read"])

        where_clauses: List[str] = []
        params: Dict[str, Any] = {}

        if active is not None:
            where_clauses.append("s.active = :active")
            params["active"] = active

        if q:
            where_clauses.append(
                """(
                  s.name ILIKE :q
                  OR EXISTS (
                    SELECT 1
                      FROM shipping_provider_contacts c
                     WHERE c.shipping_provider_id = s.id
                       AND (c.name ILIKE :q OR c.phone ILIKE :q OR c.email::text ILIKE :q OR c.wechat ILIKE :q)
                  )
                )"""
            )
            params["q"] = f"%{q.strip()}%"

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        sql = text(
            f"""
            SELECT
              s.id,
              s.name,
              s.code,
              s.address,
              s.active,
              s.priority,
              s.warehouse_id,
              s.pricing_model,
              s.region_rules
            FROM shipping_providers AS s
            {where_sql}
            ORDER BY s.priority ASC, s.id ASC
            """
        )

        result = await session.execute(sql, params)
        prov_rows = result.mappings().all()
        if not prov_rows:
            return ShippingProviderListOut(ok=True, data=[])

        ids = [int(r["id"]) for r in prov_rows]

        sql_contacts = text(
            """
            SELECT
              c.id,
              c.shipping_provider_id,
              c.name,
              c.phone,
              c.email,
              c.wechat,
              c.role,
              c.is_primary,
              c.active
            FROM shipping_provider_contacts c
            WHERE c.shipping_provider_id = ANY(:ids)
            ORDER BY c.shipping_provider_id ASC, c.is_primary DESC, c.id ASC
            """
        )
        c_rows = (await session.execute(sql_contacts, {"ids": ids})).mappings().all()

        by_pid: Dict[int, List[ShippingProviderContactOut]] = {}
        for r in c_rows:
            pid = int(r["shipping_provider_id"])
            by_pid.setdefault(pid, []).append(_row_to_contact(r))

        data: List[ShippingProviderOut] = []
        for r in prov_rows:
            pid = int(r["id"])
            contacts = by_pid.get(pid, [])
            data.append(_row_to_provider(r, contacts))

        return ShippingProviderListOut(ok=True, data=data)

    @router.get("/shipping-providers/{provider_id}", response_model=ShippingProviderDetailOut)
    async def get_shipping_provider(
        provider_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> ShippingProviderDetailOut:
        """
        物流/快递网点详情（读聚合 contacts）。

        权限：config.store.read
        """
        _check_perm(db, current_user, ["config.store.read"])

        sql = text(
            """
            SELECT
              s.id,
              s.name,
              s.code,
              s.address,
              s.active,
              s.priority,
              s.warehouse_id,
              s.pricing_model,
              s.region_rules
            FROM shipping_providers AS s
            WHERE s.id = :sid
            LIMIT 1
            """
        )

        row = (await session.execute(sql, {"sid": provider_id})).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="shipping_provider not found")

        sql_contacts = text(
            """
            SELECT
              c.id,
              c.shipping_provider_id,
              c.name,
              c.phone,
              c.email,
              c.wechat,
              c.role,
              c.is_primary,
              c.active
            FROM shipping_provider_contacts c
            WHERE c.shipping_provider_id = :sid
            ORDER BY c.is_primary DESC, c.id ASC
            """
        )
        c_rows = (await session.execute(sql_contacts, {"sid": provider_id})).mappings().all()
        contacts = [_row_to_contact(r) for r in c_rows]

        return ShippingProviderDetailOut(ok=True, data=_row_to_provider(row, contacts))
