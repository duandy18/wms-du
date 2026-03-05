# app/api/routers/shipping_provider_pricing_schemes/zones/delete.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_zone import ShippingProviderZone


def register_delete_routes(router: APIRouter) -> None:
    @router.delete(
        "/zones/{zone_id}",
        status_code=status.HTTP_200_OK,
    )
    def delete_zone(
        zone_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        z = db.get(ShippingProviderZone, zone_id)
        if not z:
            raise HTTPException(status_code=404, detail="Zone not found")

        db.delete(z)
        db.commit()
        return {"ok": True}
