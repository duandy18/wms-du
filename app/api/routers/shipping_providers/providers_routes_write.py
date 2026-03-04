# app/api/routers/shipping_providers/providers_routes_write.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

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


def _norm_code(raw: Optional[str]) -> Optional[str]:
    """
    code 口径护栏
    - None -> None
    - 空白/全空格 -> None
    - 其它 -> strip + upper
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    return s.upper()


async def _assert_code_unique_or_409(
    session: AsyncSession,
    code: str,
    *,
    exclude_provider_id: Optional[int] = None,
) -> None:
    """
    刚性合同：shipping_providers.code 全局唯一（strip + upper 后比较）。
    - exclude_provider_id：更新时排除自身
    """
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
        新建运输网点（主体事实）。

        权限：config.store.write

        刚性合同：
        - code 必填（不允许 None / 空白）
        - code 全局唯一（strip + upper 后比较）
        - 与仓库的绑定通过 warehouse_shipping_providers 另行配置（M:N）
        """
        _check_perm(db, current_user, ["config.store.write"])

        code = _norm_code(payload.code)
        if code is None:
            raise HTTPException(status_code=422, detail="code is required")

        await _assert_code_unique_or_409(session, code)

        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="name is required")

        addr = payload.address.strip() if payload.address is not None else None
        addr = addr if addr else None

        ext = payload.external_outlet_code.strip() if payload.external_outlet_code is not None else None
        ext = ext if ext else None

        sql = text(
            """
            INSERT INTO shipping_providers
              (name, code, external_outlet_code, address, active, priority)
            VALUES
              (:name, :code, :external_outlet_code, :address, :active, :priority)
            RETURNING
              id, name, code, external_outlet_code, address, active, priority
            """
        )

        row = (
            (
                await session.execute(
                    sql,
                    {
                        "name": name,
                        "code": code,
                        "external_outlet_code": ext,
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
        更新运输网点（主体事实）。

        权限：config.store.write

        刚性合同：
        - code 不允许更新（DB 级不可变）
        - 与仓库的绑定不在此接口更新（走 warehouse_shipping_providers）
        """
        _check_perm(db, current_user, ["config.store.write"])

        fields: Dict[str, Any] = {}

        if payload.name is not None:
            name = payload.name.strip()
            fields["name"] = name if name else None

        if payload.external_outlet_code is not None:
            ext = payload.external_outlet_code.strip()
            fields["external_outlet_code"] = ext if ext else None

        if payload.address is not None:
            # 允许显式置空：传 "" => 存 null；传非空 => strip 后入库
            addr = payload.address.strip()
            fields["address"] = addr if addr else None

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
                  s.external_outlet_code,
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
              id, name, code, external_outlet_code, address, active, priority
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
