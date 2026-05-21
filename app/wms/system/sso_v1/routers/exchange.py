# app/wms/system/sso_v1/routers/exchange.py
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.wms.system.sso_v1.contracts import WmsSsoExchangeIn, WmsSsoExchangeOut
from app.wms.system.sso_v1.services import ERP_SSO_BINDING_COOKIE_NAME
from app.wms.system.sso_v1.services.sso_exchange_service import (
    WmsSsoAppMismatchError,
    WmsSsoBindingRequiredError,
    WmsSsoErpExchangeFailedError,
    WmsSsoExchangeService,
    WmsSsoUserInactiveError,
    WmsSsoUserNotFoundError,
)

router = APIRouter(prefix="/system/sso/v1", tags=["system-sso-v1"])

DBSessionDep = Annotated[Session, Depends(get_db)]
BindingCookieDep = Annotated[
    str | None,
    Cookie(alias=ERP_SSO_BINDING_COOKIE_NAME),
]


def get_wms_sso_exchange_service(
    db: DBSessionDep,
) -> WmsSsoExchangeService:
    return WmsSsoExchangeService(db)


WmsSsoExchangeServiceDep = Annotated[
    WmsSsoExchangeService,
    Depends(get_wms_sso_exchange_service),
]


@router.post("/exchange", response_model=WmsSsoExchangeOut)
async def exchange_wms_sso_authorization_code(
    body: WmsSsoExchangeIn,
    service: WmsSsoExchangeServiceDep,
    binding: BindingCookieDep = None,
) -> WmsSsoExchangeOut:
    try:
        return await service.exchange(body, binding=binding)
    except WmsSsoBindingRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="wms_sso_binding_required",
        ) from exc
    except WmsSsoErpExchangeFailedError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="wms_sso_erp_exchange_failed",
        ) from exc
    except WmsSsoAppMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="wms_sso_app_mismatch",
        ) from exc
    except WmsSsoUserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="wms_sso_user_not_found",
        ) from exc
    except WmsSsoUserInactiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="wms_sso_user_inactive",
        ) from exc


__all__ = [
    "get_wms_sso_exchange_service",
    "router",
]
