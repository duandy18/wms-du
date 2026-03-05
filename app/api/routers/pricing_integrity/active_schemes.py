# app/api/routers/pricing_integrity/active_schemes.py
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme


class OpsActiveSchemeRow(BaseModel):
    scheme_id: int
    scheme_name: str
    shipping_provider_id: int
    shipping_provider_name: str


class OpsActiveSchemesOut(BaseModel):
    ok: bool = True
    data: List[OpsActiveSchemeRow] = Field(default_factory=list)


def register(router: APIRouter) -> None:
    @router.get(
        "/ops/pricing-integrity/active-schemes",
        response_model=OpsActiveSchemesOut,
        status_code=status.HTTP_200_OK,
    )
    def list_active_schemes(
        include_archived: bool = Query(False),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        # 运维中心：保持与你现有 ops pricing-integrity 一致的门槛
        check_perm(db, user, "config.store.write")

        q = (
            db.query(ShippingProviderPricingScheme)
            .options(selectinload(ShippingProviderPricingScheme.shipping_provider))
            .filter(ShippingProviderPricingScheme.active.is_(True))
            .order_by(ShippingProviderPricingScheme.id.asc())
        )

        if not include_archived:
            q = q.filter(ShippingProviderPricingScheme.archived_at.is_(None))

        rows = q.all()

        out: List[OpsActiveSchemeRow] = []
        for s in rows:
            sp = getattr(s, "shipping_provider", None)
            sp_id = int(getattr(s, "shipping_provider_id", 0) or 0)
            sp_name = str(getattr(sp, "name", "") or "").strip()
            out.append(
                OpsActiveSchemeRow(
                    scheme_id=int(s.id),
                    scheme_name=str(getattr(s, "name", "") or "").strip(),
                    shipping_provider_id=sp_id,
                    shipping_provider_name=sp_name or f"provider#{sp_id}",
                )
            )

        return OpsActiveSchemesOut(ok=True, data=out)
