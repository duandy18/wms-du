# app/api/routers/shipping_providers/providers_routes_write.py
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.db.deps import get_db

from .common import (
    ShippingProviderCreateIn,
    ShippingProviderCreateOut,
    ShippingProviderUpdateIn,
    ShippingProviderUpdateOut,
    _check_perm,
    _row_to_contact,
    _row_to_provider,
)


def register(router: APIRouter) -> None:
    @router.post(
        "/shipping-providers",
        status_code=status.HTTP_201_CREATED,
        response_model=ShippingProviderCreateOut,
    )
    async def create_shipping_provider(
        payload: ShippingProviderCreateIn,
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> ShippingProviderCreateOut:
        """
        新建物流/快递公司（主体事实 only）。

        权限：config.store.write
        """
        _check_perm(db, current_user, ["config.store.write"])

        sql = text(
            """
            INSERT INTO shipping_providers
              (name, code, active, priority, pricing_model, region_rules)
            VALUES
              (:name, :code, :active, :priority, :pricing_model, :region_rules)
            RETURNING
              id, name, code, active, priority, pricing_model, region_rules
            """
        )

        row = (
            (
                await session.execute(
                    sql,
                    {
                        "name": payload.name.strip(),
                        "code": payload.code.strip() if payload.code else None,
                        "active": payload.active,
                        "priority": payload.priority if payload.priority is not None else 100,
                        "pricing_model": payload.pricing_model,
                        "region_rules": payload.region_rules,
                    },
                )
            )
            .mappings()
            .first()
        )
        await session.commit()

        if not row:
            raise HTTPException(status_code=500, detail="failed to create shipping provider")

        return ShippingProviderCreateOut(ok=True, data=_row_to_provider(row, []))

    @router.patch("/shipping-providers/{provider_id}", response_model=ShippingProviderUpdateOut)
    async def update_shipping_provider(
        provider_id: int = Path(..., ge=1),
        payload: ShippingProviderUpdateIn = ...,
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> ShippingProviderUpdateOut:
        """
        更新物流/快递公司（主体事实 only）。

        权限：config.store.write
        """
        _check_perm(db, current_user, ["config.store.write"])

        fields: Dict[str, Any] = {}

        if payload.name is not None:
            fields["name"] = payload.name.strip()
        if payload.code is not None:
            fields["code"] = payload.code.strip()
        if payload.active is not None:
            fields["active"] = payload.active

        if payload.priority is not None:
            fields["priority"] = payload.priority
        if payload.pricing_model is not None:
            fields["pricing_model"] = payload.pricing_model
        if payload.region_rules is not None:
            fields["region_rules"] = payload.region_rules

        if not fields:
            # 返回当前记录 + contacts（不更新）
            sql_select = text(
                """
                SELECT
                  s.id,
                  s.name,
                  s.code,
                  s.active,
                  s.priority,
                  s.pricing_model,
                  s.region_rules
                FROM shipping_providers AS s
                WHERE s.id = :sid
                LIMIT 1
                """
            )
            row = (await session.execute(sql_select, {"sid": provider_id})).mappings().first()
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
            return ShippingProviderUpdateOut(ok=True, data=_row_to_provider(row, contacts))

        set_clauses: List[str] = []
        params: Dict[str, Any] = {"sid": provider_id}
        for idx, (key, value) in enumerate(fields.items()):
            pname = f"v{idx}"
            set_clauses.append(f"{key} = :{pname}")
            params[pname] = value

        sql_update = text(
            f"""
            UPDATE shipping_providers
               SET {", ".join(set_clauses)},
                   updated_at = now()
             WHERE id = :sid
            RETURNING
              id, name, code, active, priority, pricing_model, region_rules
            """
        )

        result = await session.execute(sql_update, params)
        row = result.mappings().first()
        await session.commit()

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

        return ShippingProviderUpdateOut(ok=True, data=_row_to_provider(row, contacts))
