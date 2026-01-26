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


async def _assert_warehouse_exists_or_404(session: AsyncSession, warehouse_id: int) -> None:
    chk = (await session.execute(text("SELECT 1 FROM warehouses WHERE id=:wid"), {"wid": int(warehouse_id)})).first()
    if not chk:
        raise HTTPException(status_code=404, detail="warehouse not found")


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
        新建仓库可用快递网点（主体事实）。

        权限：config.store.write

        刚性合同：
        - warehouse_id 必填且必须存在
        - code 必填（不允许 None / 空白）
        - code 全局唯一（strip + upper 后比较）
        """
        _check_perm(db, current_user, ["config.store.write"])

        await _assert_warehouse_exists_or_404(session, int(payload.warehouse_id))

        code = _norm_code(payload.code)
        if code is None:
            raise HTTPException(status_code=422, detail="code is required")

        await _assert_code_unique_or_409(session, code)

        addr = payload.address.strip() if payload.address is not None else None
        addr = addr if addr else None

        sql = text(
            """
            INSERT INTO shipping_providers
              (name, code, address, active, priority, warehouse_id, pricing_model, region_rules)
            VALUES
              (:name, :code, :address, :active, :priority, :warehouse_id, :pricing_model, :region_rules)
            RETURNING
              id, name, code, address, active, priority, warehouse_id, pricing_model, region_rules
            """
        )

        row = (
            (
                await session.execute(
                    sql,
                    {
                        "name": payload.name.strip(),
                        "code": code,
                        "address": addr,
                        "active": payload.active,
                        "priority": payload.priority if payload.priority is not None else 100,
                        "warehouse_id": int(payload.warehouse_id),
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
        更新仓库可用快递网点（主体事实）。

        权限：config.store.write

        刚性合同：
        - 如果更新 code：不允许置空；必须非空
        - code 全局唯一（strip + upper 后比较）
        - 如果更新 warehouse_id：必须存在
        """
        _check_perm(db, current_user, ["config.store.write"])

        fields: Dict[str, Any] = {}

        if payload.name is not None:
            fields["name"] = payload.name.strip()

        if payload.code is not None:
            code = _norm_code(payload.code)
            if code is None:
                raise HTTPException(status_code=422, detail="code cannot be empty")
            await _assert_code_unique_or_409(session, code, exclude_provider_id=provider_id)
            fields["code"] = code

        if payload.address is not None:
            # 允许显式置空：传 "" => 存 null；传非空 => strip 后入库
            addr = payload.address.strip()
            fields["address"] = addr if addr else None

        if payload.active is not None:
            fields["active"] = payload.active

        if payload.priority is not None:
            fields["priority"] = payload.priority
        if payload.pricing_model is not None:
            fields["pricing_model"] = payload.pricing_model
        if payload.region_rules is not None:
            fields["region_rules"] = payload.region_rules

        if payload.warehouse_id is not None:
            await _assert_warehouse_exists_or_404(session, int(payload.warehouse_id))
            fields["warehouse_id"] = int(payload.warehouse_id)

        if not fields:
            sql_select = text(
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
              id, name, code, address, active, priority, warehouse_id, pricing_model, region_rules
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
