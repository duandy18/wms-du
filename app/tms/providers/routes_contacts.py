# app/tms/providers/routes_contacts.py
# 分拆说明：
# - 本文件承载 TMS / providers 子域下的联系人子资源写接口；
# - 当前已统一为 async + AsyncSession 风格，与 providers 子域其余路由对齐；
# - 权限校验统一消费 app.tms.permissions。
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session
from app.db.deps import get_db
from app.tms.permissions import check_config_perm

from .contracts import (
    ShippingProviderContactCreateIn,
    ShippingProviderContactOut,
    ShippingProviderContactUpdateIn,
)


def _to_out(row: dict[str, Any]) -> ShippingProviderContactOut:
    return ShippingProviderContactOut(
        id=int(row["id"]),
        shipping_provider_id=int(row["shipping_provider_id"]),
        name=str(row["name"]),
        phone=row.get("phone"),
        email=row.get("email"),
        wechat=row.get("wechat"),
        role=str(row.get("role") or "other"),
        is_primary=bool(row.get("is_primary")),
        active=bool(row.get("active")),
    )


def _trim_or_none(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    t = v.strip()
    return t if t else None


async def _load_provider_exists(session: AsyncSession, *, provider_id: int) -> bool:
    row = (
        await session.execute(
            text(
                """
                SELECT 1
                FROM shipping_providers
                WHERE id = :pid
                LIMIT 1
                """
            ),
            {"pid": provider_id},
        )
    ).first()
    return row is not None


async def _load_contact_row(session: AsyncSession, *, contact_id: int) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  shipping_provider_id,
                  name,
                  phone,
                  email,
                  wechat,
                  role,
                  is_primary,
                  active
                FROM shipping_provider_contacts
                WHERE id = :cid
                LIMIT 1
                """
            ),
            {"cid": contact_id},
        )
    ).mappings().first()
    return dict(row) if row else None


async def _clear_primary_contact(
    session: AsyncSession,
    *,
    provider_id: int,
) -> None:
    await session.execute(
        text(
            """
            UPDATE shipping_provider_contacts
               SET is_primary = false
             WHERE shipping_provider_id = :pid
               AND is_primary = true
            """
        ),
        {"pid": provider_id},
    )


def register(router: APIRouter) -> None:
    @router.post(
        "/shipping-assist/pricing/providers/{provider_id}/contacts",
        response_model=ShippingProviderContactOut,
        status_code=status.HTTP_201_CREATED,
        name="shipping_provider_create_contact",
    )
    async def create_contact(
        provider_id: int = Path(..., ge=1),
        payload: ShippingProviderContactCreateIn = ...,
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ) -> ShippingProviderContactOut:
        check_config_perm(db, user, ["config.store.write"])

        exists = await _load_provider_exists(session, provider_id=int(provider_id))
        if not exists:
            raise HTTPException(status_code=404, detail="ShippingProvider not found")

        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="name is required")

        phone = _trim_or_none(payload.phone)
        wechat = _trim_or_none(payload.wechat)
        role = (payload.role or "other").strip() or "other"

        if payload.is_primary:
            await _clear_primary_contact(session, provider_id=int(provider_id))

        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO shipping_provider_contacts (
                      shipping_provider_id,
                      name,
                      phone,
                      email,
                      wechat,
                      role,
                      is_primary,
                      active
                    )
                    VALUES (
                      :provider_id,
                      :name,
                      :phone,
                      :email,
                      :wechat,
                      :role,
                      :is_primary,
                      :active
                    )
                    RETURNING
                      id,
                      shipping_provider_id,
                      name,
                      phone,
                      email,
                      wechat,
                      role,
                      is_primary,
                      active
                    """
                ),
                {
                    "provider_id": int(provider_id),
                    "name": name,
                    "phone": phone,
                    "email": str(payload.email).strip() if payload.email else None,
                    "wechat": wechat,
                    "role": role,
                    "is_primary": bool(payload.is_primary),
                    "active": bool(payload.active),
                },
            )
        ).mappings().first()

        await session.commit()

        if not row:
            raise HTTPException(status_code=500, detail="failed to create contact")

        return _to_out(dict(row))

    @router.patch(
        "/shipping-assist/pricing/provider-contacts/{contact_id}",
        response_model=ShippingProviderContactOut,
        name="shipping_provider_update_contact",
    )
    async def update_contact(
        contact_id: int = Path(..., ge=1),
        payload: ShippingProviderContactUpdateIn = ...,
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ) -> ShippingProviderContactOut:
        check_config_perm(db, user, ["config.store.write"])

        contact = await _load_contact_row(session, contact_id=int(contact_id))
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        if payload.is_primary is True:
            await _clear_primary_contact(session, provider_id=int(contact["shipping_provider_id"]))

        data = payload.model_dump(exclude_unset=True)

        fields: dict[str, Any] = {}

        if "name" in data:
            n = (data["name"] or "").strip()
            if not n:
                raise HTTPException(status_code=422, detail="name is required")
            fields["name"] = n

        if "phone" in data:
            fields["phone"] = _trim_or_none(data["phone"])

        if "email" in data:
            fields["email"] = str(data["email"]).strip() if data["email"] else None

        if "wechat" in data:
            w = data["wechat"]
            fields["wechat"] = _trim_or_none(w) if isinstance(w, str) or w is None else None

        if "role" in data:
            fields["role"] = (data["role"] or "other").strip() or "other"

        if "is_primary" in data:
            fields["is_primary"] = bool(data["is_primary"])

        if "active" in data:
            fields["active"] = bool(data["active"])

        if not fields:
            return _to_out(contact)

        set_clauses: list[str] = []
        params: dict[str, Any] = {"cid": int(contact_id)}
        for idx, (key, value) in enumerate(fields.items()):
            pname = f"v{idx}"
            set_clauses.append(f"{key} = :{pname}")
            params[pname] = value

        row = (
            await session.execute(
                text(
                    f"""
                    UPDATE shipping_provider_contacts
                       SET {", ".join(set_clauses)}
                     WHERE id = :cid
                    RETURNING
                      id,
                      shipping_provider_id,
                      name,
                      phone,
                      email,
                      wechat,
                      role,
                      is_primary,
                      active
                    """
                ),
                params,
            )
        ).mappings().first()

        await session.commit()

        if not row:
            raise HTTPException(status_code=404, detail="Contact not found")

        return _to_out(dict(row))

    @router.delete(
        "/shipping-assist/pricing/provider-contacts/{contact_id}",
        status_code=status.HTTP_200_OK,
        name="shipping_provider_delete_contact",
    )
    async def delete_contact(
        contact_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_config_perm(db, user, ["config.store.write"])

        row = (
            await session.execute(
                text(
                    """
                    DELETE FROM shipping_provider_contacts
                     WHERE id = :cid
                    RETURNING id
                    """
                ),
                {"cid": int(contact_id)},
            )
        ).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Contact not found")

        await session.commit()
        return {"ok": True}
