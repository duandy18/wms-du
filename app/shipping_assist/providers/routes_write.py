# app/shipping_assist/providers/routes_write.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session
from app.db.deps import get_db
from app.shipping_assist.permissions import check_config_perm

from .contracts import (
    ShippingProviderCreateIn,
    ShippingProviderCreateOut,
    ShippingProviderUpdateIn,
    ShippingProviderUpdateOut,
)
from .mappers import row_to_contact, row_to_provider


def _norm_code(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    return s.upper()


def _norm_nullable_text(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    s = raw.strip()
    return s if s else None


async def _assert_code_unique_or_409(
    session: AsyncSession,
    code: str,
    *,
    exclude_provider_id: Optional[int] = None,
) -> None:
    if exclude_provider_id is None:
        sql = text("SELECT 1 FROM shipping_providers WHERE code = :code LIMIT 1")
        exists = (await session.execute(sql, {"code": code})).first()
    else:
        sql = text("SELECT 1 FROM shipping_providers WHERE code = :code AND id <> :sid LIMIT 1")
        exists = (await session.execute(sql, {"code": code, "sid": int(exclude_provider_id)})).first()

    if exists:
        raise HTTPException(status_code=409, detail=f"shipping_provider code already exists: {code}")


def register(router: APIRouter) -> None:
    @router.post(
        "/shipping-assist/pricing/providers",
        status_code=status.HTTP_201_CREATED,
        response_model=ShippingProviderCreateOut,
    )
    async def create_shipping_provider(
        payload: ShippingProviderCreateIn,
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> ShippingProviderCreateOut:
        check_config_perm(db, current_user, ["config.store.write"])

        code = _norm_code(payload.code)
        if code is None:
            raise HTTPException(status_code=422, detail="code is required")

        await _assert_code_unique_or_409(session, code)

        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="name is required")

        company_code = _norm_nullable_text(payload.company_code)
        resource_code = _norm_nullable_text(payload.resource_code)
        addr = _norm_nullable_text(payload.address)

        sql = text(
            """
            INSERT INTO shipping_providers
              (name, code, company_code, resource_code, address, active, priority)
            VALUES
              (:name, :code, :company_code, :resource_code, :address, :active, :priority)
            RETURNING
              id, name, code, company_code, resource_code, address, active, priority
            """
        )

        row = (
            (
                await session.execute(
                    sql,
                    {
                        "name": name,
                        "code": code,
                        "company_code": company_code,
                        "resource_code": resource_code,
                        "address": addr,
                        "active": payload.active,
                        "priority": payload.priority if payload.priority is not None else 100,
                    },
                )
            )
            .mappings()
            .first()
        )
        await session.commit()

        if not row:
            raise HTTPException(status_code=500, detail="failed to create shipping provider")

        return ShippingProviderCreateOut(ok=True, data=row_to_provider(row, []))

    @router.patch("/shipping-assist/pricing/providers/{provider_id}", response_model=ShippingProviderUpdateOut)
    async def update_shipping_provider(
        provider_id: int = Path(..., ge=1),
        payload: ShippingProviderUpdateIn = ...,
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> ShippingProviderUpdateOut:
        check_config_perm(db, current_user, ["config.store.write"])

        fields: Dict[str, Any] = {}

        if payload.name is not None:
            name = payload.name.strip()
            fields["name"] = name if name else None

        if payload.code is not None:
            code = _norm_code(payload.code)
            if code is None:
                raise HTTPException(status_code=422, detail="code is required")
            await _assert_code_unique_or_409(session, code, exclude_provider_id=provider_id)
            fields["code"] = code

        if payload.company_code is not None:
            fields["company_code"] = _norm_nullable_text(payload.company_code)

        if payload.resource_code is not None:
            fields["resource_code"] = _norm_nullable_text(payload.resource_code)

        if payload.address is not None:
            fields["address"] = _norm_nullable_text(payload.address)

        if payload.active is not None:
            fields["active"] = payload.active

        if payload.priority is not None:
            fields["priority"] = payload.priority

        if not fields:
            sql_select = text(
                """
                SELECT
                  s.id,
                  s.name,
                  s.code,
                  s.company_code,
                  s.resource_code,
                  s.address,
                  s.active,
                  s.priority
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
            contacts = [row_to_contact(r) for r in c_rows]
            return ShippingProviderUpdateOut(ok=True, data=row_to_provider(row, contacts))

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
              id, name, code, company_code, resource_code, address, active, priority
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
        contacts = [row_to_contact(r) for r in c_rows]

        return ShippingProviderUpdateOut(ok=True, data=row_to_provider(row, contacts))
