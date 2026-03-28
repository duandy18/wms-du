# app/oms/routers/shop_product_bundles_fskus_routes_base.py
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.oms.services.stores_helpers import check_perm
from app.services.fsku_service import FskuService


def _svc(db: Session = Depends(get_db)) -> FskuService:
    return FskuService(db)


def _check_write_perm(db: Session, current_user) -> None:
    check_perm(db, current_user, ["config.store.write"])
