from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_db
from app.tms.permissions import check_config_perm
from app.tms.pricing.templates.repository import list_templates as repo_list_templates
from app.tms.pricing.templates.contracts.template import TemplateListOut

_ALLOWED_TEMPLATE_STATUS_FILTERS = {"draft", "archived"}


def _normalize_template_status_filter(status: str | None) -> str | None:
    if status is None:
        return None

    normalized = str(status).strip()
    if not normalized:
        return None

    if normalized not in _ALLOWED_TEMPLATE_STATUS_FILTERS:
        raise HTTPException(status_code=422, detail="status must be one of: draft / archived")

    return normalized


def register_list_routes(router: APIRouter) -> None:
    @router.get(
        "/templates",
        response_model=TemplateListOut,
        name="pricing_templates_list",
    )
    def list_templates(
        shipping_provider_id: int | None = Query(default=None, ge=1),
        status: str | None = Query(default=None),
        include_archived: bool = Query(False),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_config_perm(db, user, ["config.store.read"])

        normalized_status = _normalize_template_status_filter(status)
        result = repo_list_templates(
            db,
            shipping_provider_id=shipping_provider_id,
            status=normalized_status,
            include_archived=include_archived,
        )

        return TemplateListOut(
            ok=True,
            data=result,
        )

    @router.get(
        "/shipping-providers/{provider_id}/templates",
        response_model=TemplateListOut,
        name="pricing_templates_provider_list",
    )
    def list_provider_templates(
        provider_id: int = Path(..., ge=1),
        status: str | None = Query(default=None),
        include_archived: bool = Query(False),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_config_perm(db, user, ["config.store.read"])

        normalized_status = _normalize_template_status_filter(status)
        result = repo_list_templates(
            db,
            shipping_provider_id=int(provider_id),
            status=normalized_status,
            include_archived=include_archived,
        )

        return TemplateListOut(
            ok=True,
            data=result,
        )
